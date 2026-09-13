"""
TypeBuffer — masked typing mode.
Intercepts "normal" typing and, after a pause, dumps it into the active app.
Shortcuts, arrows, Caps Lock, etc. pass instantly (no delay).

On Windows: WH_KEYBOARD_LL hook with selective blocking.
On macOS/Linux: pynput (global suppress; more limited).
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
import threading
import time
import unicodedata
from ctypes import wintypes
from pathlib import Path

from corrector import correct_text, translate_text, is_translation_prefix, detect_translation
from config import config as app_config
from updater import check_for_update, is_packaged_build
from version import __version__

DEFAULT_TIMEOUT = 0.3
DEFAULT_HOTKEY = "ctrl+shift+space"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "TypeBuffer"
LOG_FILE = LOG_DIR / "typebuffer.log"

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10

VK_BACK, VK_TAB, VK_RETURN = 0x08, 0x09, 0x0D
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_PAUSE, VK_CAPITAL, VK_ESCAPE, VK_SPACE = 0x13, 0x14, 0x1B, 0x20
VK_PRIOR, VK_NEXT, VK_END, VK_HOME = 0x21, 0x22, 0x23, 0x24
VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x25, 0x26, 0x27, 0x28
VK_SNAPSHOT, VK_INSERT, VK_DELETE = 0x2C, 0x2D, 0x2E
VK_LWIN, VK_RWIN, VK_APPS = 0x5B, 0x5C, 0x5D
VK_F1, VK_F24 = 0x70, 0x87
VK_NUMLOCK, VK_SCROLL = 0x90, 0x91
VK_LSHIFT, VK_RSHIFT = 0xA0, 0xA1
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
VK_LMENU, VK_RMENU = 0xA4, 0xA5

_PASSTHROUGH_VK = frozenset(
    {
        VK_SHIFT,
        VK_CONTROL,
        VK_MENU,
        VK_CAPITAL,
        VK_LSHIFT,
        VK_RSHIFT,
        VK_LCONTROL,
        VK_RCONTROL,
        VK_LMENU,
        VK_RMENU,
        VK_LWIN,
        VK_RWIN,
        VK_APPS,
        VK_NUMLOCK,
        VK_SCROLL,
        VK_PAUSE,
        VK_ESCAPE,
        VK_SNAPSHOT,
        VK_INSERT,
        VK_DELETE,
        VK_PRIOR,
        VK_NEXT,
        VK_END,
        VK_HOME,
        VK_LEFT,
        VK_UP,
        VK_RIGHT,
        VK_DOWN,
        *range(VK_F1, VK_F24 + 1),
        *range(0xA6, 0xB8),
    }
)


if sys.platform == "win32":
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    # In Win64, LPARAM/LRESULT are pointer-sized; c_long is 32-bit and causes OverflowError
    _LRESULT = ctypes.c_ssize_t
    _HHOOK = ctypes.c_void_p
    _HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, ctypes.c_void_p)

    def _setup_user32_hook_apis() -> None:
        user32 = ctypes.windll.user32
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            _HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = _HHOOK
        user32.CallNextHookEx.argtypes = [_HHOOK, ctypes.c_int, wintypes.WPARAM, ctypes.c_void_p]
        user32.CallNextHookEx.restype = _LRESULT
        user32.UnhookWindowsHookEx.argtypes = [_HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    _setup_user32_hook_apis()

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    MAPVK_VK_TO_VSC = 0
    _ULONG_PTR = ctypes.c_size_t

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", _ULONG_PTR),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", _ULONG_PTR),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = [("type", wintypes.DWORD), ("value", _INPUTUNION)]

    ctypes.windll.user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    ctypes.windll.user32.SendInput.restype = wintypes.UINT
else:
    _HOOKPROC = None


_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "win": "win",
    "super": "win",
    "cmd": "win",
    "meta": "win",
}

_HOTKEY_VK_NAMES = {
    "space": VK_SPACE,
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "tab": VK_TAB,
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "backspace": VK_BACK,
    "pause": VK_PAUSE,
    "break": VK_PAUSE,
    "scrolllock": VK_SCROLL,
    "capslock": VK_CAPITAL,
    "insert": VK_INSERT,
    "delete": VK_DELETE,
    "home": VK_HOME,
    "end": VK_END,
    "pageup": VK_PRIOR,
    "pagedown": VK_NEXT,
    "left": VK_LEFT,
    "right": VK_RIGHT,
    "up": VK_UP,
    "down": VK_DOWN,
}
_HOTKEY_VK_NAMES.update({f"f{i}": VK_F1 + i - 1 for i in range(1, 25)})

# Keys that are safe to use on their own, without any modifier.
_STANDALONE_SAFE_VK = frozenset({VK_PAUSE, VK_SCROLL, *range(VK_F1, VK_F24 + 1)})


def parse_hotkey(spec: str) -> tuple[frozenset[str], int] | None:
    """
    Parses a shortcut such as 'ctrl+shift+space' into ({'ctrl', 'shift'}, VK_SPACE).
    Returns None when the shortcut is malformed or too dangerous to bind globally
    (a bare printable key would swallow normal typing).
    """
    if not isinstance(spec, str):
        return None

    mods: set[str] = set()
    key_vk: int | None = None
    for part in spec.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _MODIFIER_ALIASES:
            mods.add(_MODIFIER_ALIASES[part])
        elif part in _HOTKEY_VK_NAMES:
            key_vk = _HOTKEY_VK_NAMES[part]
        elif len(part) == 1 and part.isalnum():
            key_vk = ord(part.upper())
        else:
            return None

    if key_vk is None:
        return None
    if not mods and key_vk not in _STANDALONE_SAFE_VK:
        return None
    return frozenset(mods), key_vk


def _win_send_text(text: str) -> None:
    """
    Injects text on Windows as literal UTF-16 units (KEYEVENTF_UNICODE).

    Sending real virtual keys instead would let whatever modifier the user
    happens to be holding rewrite the batch: with Shift down a Spanish layout
    turns 'www.allwr.io' into 'WWW:ALLWR:IO'. Unicode injection carries the
    character itself, so the keyboard state cannot alter it. Enter and Tab
    still need real keys, since apps act on the keystroke rather than the
    control character.
    """
    user32 = ctypes.windll.user32
    events: list[INPUT] = []

    def add(vk: int, scan: int, flags: int) -> None:
        item = INPUT(type=INPUT_KEYBOARD)
        item.ki = _KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        events.append(item)

    def add_key(vk: int) -> None:
        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        add(vk, scan, 0)
        add(vk, scan, KEYEVENTF_KEYUP)

    for ch in text:
        if ch == "\n":
            add_key(VK_RETURN)
        elif ch == "\t":
            add_key(VK_TAB)
        else:
            # Characters outside the BMP need both surrogate halves.
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):
                unit = data[i] | (data[i + 1] << 8)
                add(0, unit, KEYEVENTF_UNICODE)
                add(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

    # Sent in chunks so very long AI-corrected paragraphs are not dropped.
    for start in range(0, len(events), 256):
        chunk = events[start : start + 256]
        array = (INPUT * len(chunk))(*chunk)
        user32.SendInput(len(chunk), ctypes.byref(array), ctypes.sizeof(INPUT))


def setup_logging(quiet: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
    if not quiet:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _down(vk: int) -> bool:
    if sys.platform == "win32":
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    return False


def _sanitize_chars(text: str) -> str:
    """Removes orphaned accents (´ ` ¨…) from dead keys; keeps accented letters."""
    out: list[str] = []
    for ch in text:
        if ch in "\t\n\r ":
            out.append(ch)
            continue
        # Sk = symbol, modifier (´ ` ¨ ^ ~ as standalone chars)
        if unicodedata.category(ch) == "Sk":
            continue
        if ord(ch) >= 32:
            out.append(ch)
    return "".join(out)


def _to_unicode(vk: int, scan: int, shift: bool, ctrl: bool, alt: bool) -> str | None:
    """
    Resolves character with current layout.
    n < 0 -> dead key (´ ` ¨…): block it but don't add to buffer.
    """
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    state = (ctypes.c_ubyte * 256)()
    if shift:
        state[VK_SHIFT] = 0x80
        state[VK_LSHIFT] = 0x80
    if ctrl:
        state[VK_CONTROL] = 0x80
        state[VK_LCONTROL] = 0x80
    if alt:
        state[VK_MENU] = 0x80
        state[VK_LMENU] = 0x80
    if user32.GetKeyState(VK_CAPITAL) & 1:
        state[VK_CAPITAL] = 0x01

    buf = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicode(vk, scan, state, buf, len(buf), 0)
    if n < 0:
        # Dead key: return empty string so it gets blocked but NOT pushed to buffer
        return ""
    if n > 0:
        return _sanitize_chars(buf.value[:n]) or None
    return None


class TypeBufferApp:
    def __init__(
        self,
        timeout: float | None = None,
        *,
        corrector: str | None = None,
        language: str | None = None,
        corrector_timeout: float = 8.0,
        cli_timeout: float | None = None,
        cli_corrector: str | None = None,
        cli_lang: str | None = None,
    ) -> None:
        self._cli_timeout = cli_timeout
        self._cli_corrector = cli_corrector
        self._cli_lang = cli_lang
        self.corrector_timeout = corrector_timeout
        self.buffer: list[str] = []
        self.last_type_time = time.time()
        self.lock = threading.Lock()
        self.running = True
        self._hook = None
        self._hook_tid: int | None = None
        self._thread: threading.Thread | None = None
        self._proc = None
        self._controller = None
        self._pynput_listener = None
        # Keys whose KEYDOWN we block -> we also block their KEYUP
        self._blocked_downs: set[int] = set()
        self._on_stop_callback = None
        self._on_toggle_request = None
        self._last_config_check = time.time()
        # Toggle requests are raised by the hook thread and applied by the run loop,
        # so the hook procedure stays well under Windows' LowLevelHooksTimeout.
        self._toggle_requested = False
        self._hotkey_spec: str | None = None
        self._hotkey_parsed: tuple[frozenset[str], int] | None = None
        # Set by Enter to release the buffer without waiting for the idle timeout.
        self._flush_now = False
        self._wake = threading.Event()

    @property
    def timeout(self) -> float:
        if self._cli_timeout is not None:
            return min(3.0, max(0.1, float(self._cli_timeout)))
        val = app_config.get("timeout", DEFAULT_TIMEOUT)
        try:
            return min(3.0, max(0.1, float(val)))
        except (ValueError, TypeError):
            return DEFAULT_TIMEOUT

    @property
    def corrector(self) -> str:
        if self._cli_corrector is not None:
            return self._cli_corrector
        return app_config.get("ai_provider", "languagetool")

    @property
    def language(self) -> str:
        if self._cli_lang is not None:
            return self._cli_lang
        return app_config.get("lang", "en")

    @property
    def active(self) -> bool:
        return app_config.get("active", True)

    @active.setter
    def active(self, value: bool) -> None:
        app_config.set("active", value)

    @property
    def hotkey(self) -> tuple[frozenset[str], int] | None:
        """Parsed pause/resume shortcut, re-parsed only when the setting changes."""
        spec = app_config.get("hotkey_toggle", DEFAULT_HOTKEY)
        if spec != self._hotkey_spec:
            self._hotkey_spec = spec
            parsed = parse_hotkey(spec)
            if parsed is None:
                logging.warning("Invalid shortcut %r, falling back to %s", spec, DEFAULT_HOTKEY)
                parsed = parse_hotkey(DEFAULT_HOTKEY)
            self._hotkey_parsed = parsed
        return self._hotkey_parsed

    def reload_config(self) -> None:
        """Reloads settings from disk and applies them immediately."""
        app_config.load()
        logging.info(
            "Config reloaded: timeout=%.2fs, provider=%s, lang=%s, active=%s",
            self.timeout,
            self.corrector,
            self.language,
            self.active,
        )

    def set_active(self, active: bool) -> None:
        """Enable/disable masking (used by the tray icon)."""
        self.active = active
        if not active:
            with self.lock:
                self.buffer.clear()
        logging.info("TypeBuffer %s", "ACTIVE" if active else "PAUSED")

    def set_on_stop(self, callback) -> None:
        self._on_stop_callback = callback

    def set_on_toggle_request(self, callback) -> None:
        """Routes hotkey toggles through the tray icon so its state stays in sync."""
        self._on_toggle_request = callback

    def _hotkey_matches(self, vk: int) -> bool:
        parsed = self.hotkey
        if parsed is None:
            return False
        mods, target_vk = parsed
        if vk != target_vk:
            return False
        # Modifiers must match exactly: on Spanish layouts AltGr reports as Ctrl+Alt,
        # so a Ctrl-only shortcut must not fire while typing '@' or '€'.
        return (
            ("ctrl" in mods) == _down(VK_CONTROL)
            and ("shift" in mods) == _down(VK_SHIFT)
            and ("alt" in mods) == _down(VK_MENU)
            and ("win" in mods) == (_down(VK_LWIN) or _down(VK_RWIN))
        )

    def _apply_toggle_request(self) -> None:
        if self._on_toggle_request:
            self._on_toggle_request()
        else:
            self.set_active(not self.active)

    def stop(self) -> None:
        self.running = False
        self._wake.set()

    def _push(self, text: str) -> None:
        text = _sanitize_chars(text)
        if not text:
            return
        with self.lock:
            self.buffer.extend(text)
            self.last_type_time = time.time()

    def _request_flush(self) -> None:
        """Releases the buffer on the next loop pass, skipping the idle timeout."""
        with self.lock:
            self._flush_now = True
        self._wake.set()

    def _backspace(self) -> bool:
        with self.lock:
            if self.buffer:
                self.buffer.pop()
                self.last_type_time = time.time()
                return True
            return False

    def _take_flush(self) -> str | None:
        with self.lock:
            if not self.buffer:
                self._flush_now = False
                return None

            current_text = "".join(self.buffer)
            now = time.time()
            elapsed = now - self.last_type_time
            forced = self._flush_now

            # Translation mode handling:
            # If the user is typing a translation prefix (e.g. 'en:' or '{es]:'),
            # DO NOT flush prematurely while only the prefix is typed!
            # Keep buffering until the user types the message to translate.
            if (
                not forced
                and app_config.get("translate", True)
                and is_translation_prefix(current_text)
            ):
                has_content = detect_translation(current_text) is not None
                if not has_content:
                    # Incomplete prefix; do not flush unless idle for 5 seconds fallback.
                    if elapsed < 5.0:
                        return None

            if forced or elapsed > self.timeout:
                self._flush_now = False
                texto = _sanitize_chars(current_text)
                self.buffer.clear()
                return texto or None

            return None

    def _modifier_passthrough(self) -> bool:
        """True if Ctrl/Alt/Win indicate a system shortcut (not masked typing)."""
        ctrl = _down(VK_CONTROL)
        alt = _down(VK_MENU)
        win = _down(VK_LWIN) or _down(VK_RWIN)
        if win:
            return True
        # Pure Ctrl -> Ctrl+C/V/... (AltGr = Ctrl+Alt -> False)
        if ctrl and not alt:
            return True
        # Pure Alt -> menus / Alt+F4
        if alt and not ctrl:
            return True
        return False

    def _should_block_down(self, vk: int, scan: int) -> bool:
        if not self.active:
            return False

        if vk in _PASSTHROUGH_VK:
            return False

        if self._modifier_passthrough():
            return False

        if vk == VK_BACK:
            return self._backspace()

        # If Space is the very first character typed, pass it through instantly without delay.
        if vk == VK_SPACE:
            with self.lock:
                if not self.buffer:
                    return False
            self._push(" ")
            return True

        if vk == VK_RETURN:
            # Enter releases the buffer straight away, no idle wait.
            self._push("\n")
            self._request_flush()
            return True
        if vk == VK_TAB:
            self._push("\t")
            return True

        ch = _to_unicode(
            vk,
            scan,
            shift=_down(VK_SHIFT),
            ctrl=_down(VK_CONTROL),
            alt=_down(VK_MENU),
        )
        if ch is not None:
            if ch == "":
                # It's a dead key. Block it from the active app, but don't buffer it.
                return True
            if all(ord(c) >= 32 for c in ch):
                self._push(ch)
                return True

        return False

    def _low_level_proc(self, nCode, wParam, lParam):
        user32 = ctypes.windll.user32
        try:
            if nCode == 0 and self.running:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (kb.flags & LLKHF_INJECTED):
                    vk = int(kb.vkCode)

                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        # Checked before anything else so it also works while paused.
                        if self._hotkey_matches(vk):
                            self._toggle_requested = True
                            self._blocked_downs.add(vk)
                            return 1

                        if self._should_block_down(vk, int(kb.scanCode)):
                            self._blocked_downs.add(vk)
                            return 1
                        self._blocked_downs.discard(vk)

                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        if vk in self._blocked_downs:
                            self._blocked_downs.discard(vk)
                            return 1
        except Exception:
            logging.exception("Error in keyboard hook")

        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _hook_thread_main(self) -> None:
        user32 = ctypes.windll.user32
        self._proc = _HOOKPROC(self._low_level_proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            logging.error("Could not install keyboard hook")
            self.running = False
            return

        logging.info("Windows hook active (selective blocking, no delay on shortcuts)")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _start_windows(self) -> None:
        ready = threading.Event()

        def run() -> None:
            self._hook_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            ready.set()
            self._hook_thread_main()

        self._thread = threading.Thread(target=run, name="kb-hook", daemon=True)
        self._thread.start()
        ready.wait(timeout=2)

    def _stop_windows(self) -> None:
        if self._hook_tid:
            ctypes.windll.user32.PostThreadMessageW(self._hook_tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def _type_text(self, texto: str) -> None:
        # LLKHF_INJECTED -> the hook won't mask these again
        if sys.platform == "win32":
            _win_send_text(texto)
            return
        if self._controller is None:
            from pynput.keyboard import Controller

            self._controller = Controller()
        self._controller.type(texto)

    def _start_pynput(self) -> None:
        from pynput import keyboard

        self._controller = keyboard.Controller()

        modifier_keys = {
            keyboard.Key.ctrl: "ctrl",
            keyboard.Key.ctrl_l: "ctrl",
            keyboard.Key.ctrl_r: "ctrl",
            keyboard.Key.shift: "shift",
            keyboard.Key.shift_l: "shift",
            keyboard.Key.shift_r: "shift",
            keyboard.Key.alt: "alt",
            keyboard.Key.alt_l: "alt",
            keyboard.Key.alt_r: "alt",
            keyboard.Key.cmd: "win",
        }
        held: set[str] = set()

        def is_hotkey(key) -> bool:
            parsed = self.hotkey
            if parsed is None:
                return False
            mods, target_vk = parsed
            vk = getattr(key, "vk", None)
            if vk is None:
                char = getattr(key, "char", None)
                vk = ord(char.upper()) if char and char.isalnum() else None
            if vk is None or vk != target_vk:
                return False
            return held == set(mods)

        def on_release(key):
            name = modifier_keys.get(key)
            if name:
                held.discard(name)

        def on_press(key):
            name = modifier_keys.get(key)
            if name:
                held.add(name)
                return
            if is_hotkey(key):
                self._toggle_requested = True
                return
            if not self.active:
                return
            try:
                if key.char and ord(key.char) >= 32:
                    self._push(key.char)
                    return
            except AttributeError:
                pass
            if key == keyboard.Key.space:
                self._push(" ")
            elif key == keyboard.Key.enter:
                self._push("\n")
                self._request_flush()
            elif key == keyboard.Key.tab:
                self._push("\t")
            elif key == keyboard.Key.backspace:
                self._backspace()

        self._pynput_listener = keyboard.Listener(
            on_press=on_press, on_release=on_release, suppress=True
        )
        self._pynput_listener.start()

    def _prepare_and_type(self, texto: str) -> None:
        if not texto:
            return
        # Skip fragments that are only spaces (avoid dumping lone whitespace),
        # but keep meaningful control characters like newline (Enter) or tab.
        if texto.strip() == "" and "\n" not in texto and "\t" not in texto:
            return

        # Both AI paths strip surrounding whitespace, which would eat the Enter
        # that triggered the flush. Keep it aside and re-attach it afterwards.
        body = texto.rstrip("\n")
        trailing = texto[len(body):]

        # 1) Translation mode: "en: some text" -> translate via AI.
        if app_config.get("translate", True):
            translated = translate_text(body, timeout=self.corrector_timeout)
            if translated is not None:
                logging.info("Sending (translated): %r", translated + trailing)
                self._type_text(translated + trailing)
                return

        # 2) Spellchecker.
        if app_config.get("spellcheck", False) and self.corrector not in ("none", "off", "no"):
            logging.info("Checking (%s, %s)...", self.corrector, self.language)
            texto = correct_text(
                body,
                provider=self.corrector,
                language=self.language,
                timeout=self.corrector_timeout,
            ) + trailing

        logging.info("Sending: %r", texto)
        self._type_text(texto)

    def run(self) -> None:
        logging.info("TypeBuffer %s — MASKED MODE (timeout=%.1fs).", __version__, self.timeout)
        logging.info(
            "Pause/resume shortcut: %s (exit from the tray icon)",
            app_config.get("hotkey_toggle", DEFAULT_HOTKEY),
        )
        logging.info(
            "Instant pass-through: arrows, Esc, Caps Lock, Ctrl+C/V, Alt, Win, Del, F-keys..."
        )
        logging.info("Spellchecker: %s (lang=%s)", self.corrector, self.language)
        logging.info("Translation mode: %s", app_config.get("translate", True))
        logging.info("Log: %s", LOG_FILE)

        if sys.platform == "win32":
            self._start_windows()
        else:
            self._start_pynput()
            logging.info("Non-Windows platform: global suppress (limited)")

        try:
            while self.running:
                # Woken immediately by Enter; otherwise polls for the idle timeout.
                self._wake.wait(0.05)
                self._wake.clear()

                if self._toggle_requested:
                    self._toggle_requested = False
                    self._apply_toggle_request()

                now = time.time()
                if now - self._last_config_check > 1.0:
                    self._last_config_check = now
                    if app_config.check_reload():
                        logging.info("Config file changed on disk, reloaded.")

                texto = self._take_flush()
                if texto is not None:
                    self._prepare_and_type(texto)
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.running = False
            if sys.platform == "win32":
                self._stop_windows()
            elif self._pynput_listener is not None:
                self._pynput_listener.stop()
            logging.info("Session ended")
            if self._on_stop_callback:
                self._on_stop_callback()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TypeBuffer — masked keyboard with delayed output")
    p.add_argument("--timeout", type=float, default=None)
    p.add_argument("--quiet", action="store_true")
    p.add_argument(
        "--corrector",
        choices=("languagetool", "openai", "claude", "deepseek", "none"),
        default=None,
        help="Spellchecker/AI provider to use (default: from config, else languagetool)",
    )
    p.add_argument(
        "--lang",
        default=None,
        help="Language for the spellchecker (default: from config, else en)",
    )
    p.add_argument(
        "--corrector-timeout",
        type=float,
        default=8.0,
        help="Spellchecker network timeout in seconds",
    )
    return p.parse_args(argv)


def _announce_update_if_any(tray) -> None:
    """Looks for a newer release and surfaces it on the tray icon."""
    if not is_packaged_build():
        logging.info("Running from source; skipping the update check.")
        return

    # Give the tray icon a moment to appear, otherwise the notification is lost.
    time.sleep(3)
    found = check_for_update()
    if found:
        tray.announce_update(*found)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(quiet=args.quiet)

    from single_instance import SingleInstance
    single_inst = SingleInstance()
    if single_inst.is_running():
        msg = "TypeBuffer is already running! (Check the system tray icon near your clock)."
        if not args.quiet:
            print(msg)
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, msg, "TypeBuffer", 0x40 | 0x10000)
                except Exception:
                    pass
        logging.warning("Another instance of TypeBuffer is already running. Exiting.")
        return 0

    # Resolve settings: CLI override > config > default.
    provider = args.corrector or app_config.get("ai_provider", "languagetool")
    language = args.lang or app_config.get("lang", "en")
    timeout = args.timeout if args.timeout is not None else app_config.get("timeout", DEFAULT_TIMEOUT)
    if timeout > 3.0:
        timeout = 3.0

    # First-run welcome screen (skip in quiet/autostart mode).
    if app_config.get("first_run", True) and not args.quiet:
        try:
            from gui import show_settings
            show_settings(is_welcome=True)
            app_config.load()
        except Exception as exc:
            logging.warning("Could not show the welcome screen: %s", exc)

    app = TypeBufferApp(
        timeout=timeout,
        corrector=provider,
        language=language,
        corrector_timeout=args.corrector_timeout,
        cli_timeout=args.timeout,
        cli_corrector=args.corrector,
        cli_lang=args.lang,
    )

    # System tray icon (double-click toggles active/inactive).
    tray = None
    try:
        from tray import TrayIcon
        tray = TrayIcon(
            on_exit_callback=app.stop,
            on_toggle_callback=app.set_active,
            on_settings_saved_callback=app.reload_config,
        )
        app.set_on_stop(lambda: tray.stop() if tray else None)
        app.set_on_toggle_request(tray.toggle_active)
    except Exception as exc:
        logging.warning("Could not start the tray icon: %s", exc)

    if tray is not None and app_config.get("check_updates", True):
        threading.Thread(
            target=_announce_update_if_any,
            args=(tray,),
            daemon=True,
            name="update-check",
        ).start()

    # Run the keyboard hook in a background thread.
    app_thread = threading.Thread(target=app.run, daemon=True, name="typebuffer-app")
    app_thread.start()

    # Keep the main thread alive with the tray (or a simple loop as fallback).
    if tray is not None:
        tray.run()
    else:
        try:
            while app.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

    app.stop()
    app_thread.join(timeout=2)
    single_inst.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

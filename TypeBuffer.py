"""
TypeBuffer — modo máscara de teclado.
Intercepta la escritura "normal" y, tras una pausa, la vuelca en la app activa.
Atajos, flechas, Bloq Mayús, etc. pasan al instante (sin delay).

En Windows: hook WH_KEYBOARD_LL con bloqueo selectivo.
En macOS/Linux: pynput (suppress global; más limitado).
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

from corrector import correct_text

DEFAULT_TIMEOUT = 2.0
LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "TypeBuffer"
LOG_FILE = LOG_DIR / "typebuffer.log"

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10

VK_BACK, VK_TAB, VK_RETURN = 0x08, 0x09, 0x0D
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_CAPITAL, VK_ESCAPE, VK_SPACE = 0x14, 0x1B, 0x20
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


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


# En Win64, LPARAM/LRESULT son pointer-sized; c_long es 32-bit y provoca OverflowError
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
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def _sanitize_chars(text: str) -> str:
    """Quita acentos huérfanos (´ ` ¨…) de teclas muertas; conserva letras acentuadas."""
    out: list[str] = []
    for ch in text:
        if ch in "\t\n\r ":
            out.append(ch)
            continue
        # Sk = symbol, modifier (´ ` ¨ ^ ~ como caracteres sueltos)
        if unicodedata.category(ch) == "Sk":
            continue
        if ord(ch) >= 32:
            out.append(ch)
    return "".join(out)


def _to_unicode(vk: int, scan: int, shift: bool, ctrl: bool, alt: bool) -> str | None:
    """
    Resuelve el caracter con el layout actual.
    n < 0 → tecla muerta (´ ` ¨…): no insertar nada; la siguiente tecla compondrá (á, é…).
    """
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
        # Tecla muerta consumida; esperar vocal/consonante
        return None
    if n > 0:
        return _sanitize_chars(buf.value[:n]) or None
    return None


class TypeBufferApp:
    def __init__(
        self,
        timeout: float,
        *,
        corrector: str = "languagetool",
        language: str = "es",
        corrector_timeout: float = 8.0,
    ) -> None:
        self.timeout = timeout
        self.corrector = corrector
        self.language = language
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
        # Teclas cuyo KEYDOWN bloqueamos → también bloqueamos su KEYUP
        self._blocked_downs: set[int] = set()

    def _push(self, text: str) -> None:
        text = _sanitize_chars(text)
        if not text:
            return
        with self.lock:
            self.buffer.extend(text)
            self.last_type_time = time.time()

    def _backspace(self) -> bool:
        with self.lock:
            if self.buffer:
                self.buffer.pop()
                self.last_type_time = time.time()
                return True
            return False

    def _take_flush(self) -> str | None:
        with self.lock:
            if self.buffer and (time.time() - self.last_type_time > self.timeout):
                texto = _sanitize_chars("".join(self.buffer))
                self.buffer.clear()
                return texto or None
            return None

    def _modifier_passthrough(self) -> bool:
        """True si Ctrl/Alt/Win indican un atajo del sistema (no escritura enmascarada)."""
        ctrl = _down(VK_CONTROL)
        alt = _down(VK_MENU)
        win = _down(VK_LWIN) or _down(VK_RWIN)
        if win:
            return True
        # Ctrl puro → Ctrl+C/V/...  (AltGr = Ctrl+Alt → False)
        if ctrl and not alt:
            return True
        # Alt puro → menús / Alt+F4
        if alt and not ctrl:
            return True
        return False

    def _should_block_down(self, vk: int, scan: int) -> bool:
        if vk == VK_ESCAPE:
            self.running = False
            return True

        if vk in _PASSTHROUGH_VK:
            return False

        if self._modifier_passthrough():
            return False

        if vk == VK_BACK:
            return self._backspace()

        if vk == VK_SPACE:
            self._push(" ")
            return True
        if vk == VK_RETURN:
            self._push("\n")
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
        if ch and all(ord(c) >= 32 for c in ch):
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
                        if self._should_block_down(vk, int(kb.scanCode)):
                            self._blocked_downs.add(vk)
                            return 1
                        self._blocked_downs.discard(vk)

                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        if vk in self._blocked_downs:
                            self._blocked_downs.discard(vk)
                            return 1
                        if vk == VK_ESCAPE:
                            return 1
        except Exception:
            logging.exception("Error en hook de teclado")

        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _hook_thread_main(self) -> None:
        user32 = ctypes.windll.user32
        self._proc = _HOOKPROC(self._low_level_proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            logging.error("No se pudo instalar el hook de teclado")
            self.running = False
            return

        logging.info("Hook Windows activo (bloqueo selectivo, sin delay en atajos)")
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
        if self._controller is None:
            from pynput.keyboard import Controller

            self._controller = Controller()
        # LLKHF_INJECTED → el hook no las vuelve a enmascarar
        self._controller.type(texto)

    def _start_pynput(self) -> None:
        from pynput import keyboard

        self._controller = keyboard.Controller()

        def on_press(key):
            if key == keyboard.Key.esc:
                self.running = False
                return False
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
            elif key == keyboard.Key.tab:
                self._push("\t")
            elif key == keyboard.Key.backspace:
                self._backspace()

        self._pynput_listener = keyboard.Listener(on_press=on_press, suppress=True)
        self._pynput_listener.start()

    def _prepare_and_type(self, texto: str) -> None:
        if not texto or not texto.strip():
            return
        if self.corrector not in ("none", "off", "no"):
            logging.info("Corrigiendo (%s, %s)...", self.corrector, self.language)
            texto = correct_text(
                texto,
                provider=self.corrector,
                language=self.language,
                timeout=self.corrector_timeout,
            )
        logging.info("Enviando: %r", texto)
        self._type_text(texto)

    def run(self) -> None:
        logging.info("MODO MASCARA (timeout=%.1fs). ESC para salir.", self.timeout)
        logging.info(
            "Pasan al instante: flechas, Bloq Mayus, Ctrl+C/V, Alt, Win, Supr, F-keys..."
        )
        logging.info("Corrector: %s (idioma=%s)", self.corrector, self.language)
        logging.info("Log: %s", LOG_FILE)

        if sys.platform == "win32":
            self._start_windows()
        else:
            self._start_pynput()
            logging.info("Plataforma no Windows: suppress global (limitado)")

        try:
            while self.running:
                time.sleep(0.05)
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
            logging.info("Sesion finalizada")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TypeBuffer — teclado enmascarado con volcado diferido")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--quiet", action="store_true")
    p.add_argument(
        "--corrector",
        choices=("languagetool", "openai", "none"),
        default=os.environ.get("TYPEBUFFER_CORRECTOR", "languagetool"),
        help="Corrector antes de soltar el texto (default: languagetool)",
    )
    p.add_argument(
        "--lang",
        default=os.environ.get("TYPEBUFFER_LANG", "es"),
        help="Idioma del corrector (default: es)",
    )
    p.add_argument(
        "--corrector-timeout",
        type=float,
        default=8.0,
        help="Timeout de red del corrector en segundos",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(quiet=args.quiet)
    TypeBufferApp(
        timeout=args.timeout,
        corrector=args.corrector,
        language=args.lang,
        corrector_timeout=args.corrector_timeout,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Zen Focus Overlay for TypeBuffer.

Provides a floating, fullscreen, frameless overlay that appears while typing and
fades out after an inactivity pause (when the buffer flushes).

Key properties:
- Uses Win32 WS_EX_NOACTIVATE so it never steals focus from the active window.
- Mouse clicks pass through (WS_EX_TRANSPARENT).
- Automatically targets the monitor of the active window.
- Dynamically samples the ambient background color and perceived luminance to
  adjust contrast and avoid eye strain.
- Monospaced retro typewriter typography with smooth fade transitions.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import queue
import sys
import threading
import tkinter as tk
from typing import Tuple
import warnings

# Suppress harmless Python 3.12+ cross-thread Tcl deallocation warning on shutdown.
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*Tcl interpreter is leaked.*")

# Win32 Constants
MONITOR_DEFAULTTONEAREST = 2
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
HALFTONE = 4
SRCCOPY = 0x00CC0020


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_active_monitor_bounds() -> Tuple[int, int, int, int]:
    """Returns (x, y, width, height) of the monitor containing the active window."""
    if sys.platform != "win32":
        return 0, 0, 1920, 1080

    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if hwnd:
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if hmon:
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                rc = mi.rcMonitor
                return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top

    # Fallback: primary monitor metrics
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def sample_screen_color(x: int, y: int, w: int, h: int) -> Tuple[int, int, int]:
    """
    Samples the average RGB color of the specified screen region in under 30ms.
    Uses Win32 GDI StretchBlt with HALFTONE mode to downsample directly in hardware/kernel.
    """
    if sys.platform != "win32":
        return 30, 30, 32

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    try:
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, 1, 1)
        hbmp_old = gdi32.SelectObject(hdc_mem, hbmp)

        gdi32.SetStretchBltMode(hdc_mem, HALFTONE)
        pt = wintypes.POINT(0, 0)
        gdi32.SetBrushOrgEx(hdc_mem, 0, 0, ctypes.byref(pt))

        gdi32.StretchBlt(hdc_mem, 0, 0, 1, 1, hdc_screen, x, y, w, h, SRCCOPY)
        px = gdi32.GetPixel(hdc_mem, 0, 0)

        gdi32.SelectObject(hdc_mem, hbmp_old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        r = px & 0xFF
        g = (px >> 8) & 0xFF
        b = (px >> 16) & 0xFF
        return r, g, b
    except Exception as exc:
        logging.debug("GDI screen sampling fallback: %s", exc)
        return 30, 30, 32


def compute_theme(r: int, g: int, b: int) -> Tuple[str, str]:
    """
    Calculates perceived luminance and returns (text_color_hex, background_color_hex).
    Luminance formula: 0.299R + 0.587G + 0.114B.
    Blends with calming neutrals so the background is soothing and eye-friendly.
    """
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    if lum > 128:
        # High luminance (light screen): dark text, calmed light background
        text_color = "#141414"
        bg_r = int(0.65 * r + 0.35 * 246)
        bg_g = int(0.65 * g + 0.35 * 246)
        bg_b = int(0.65 * b + 0.35 * 242)
    else:
        # Low luminance (dark screen): light text, calmed dark background
        text_color = "#F0F0F0"
        bg_r = int(0.65 * r + 0.35 * 22)
        bg_g = int(0.65 * g + 0.35 * 22)
        bg_b = int(0.65 * b + 0.35 * 26)

    bg_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
    return text_color, bg_hex


class ZenOverlay:
    """Manages the lifecycle, non-activating window styles, and animation of the overlay."""

    def __init__(self, target_alpha: float = 0.94) -> None:
        self.target_alpha = target_alpha
        self._queue: queue.Queue = queue.Queue()
        self._ready_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="zen-overlay", daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=3.0)

    # ----------------- Thread-Safe Public API -----------------

    def on_typing_start(self, initial_text: str) -> None:
        """Called on the first keystroke of a buffer to capture screen and fade in."""
        self._queue.put(("start", initial_text))

    def on_typing_update(self, current_text: str) -> None:
        """Called as the buffer grows or shrinks to update the on-screen text."""
        self._queue.put(("update", current_text))

    def on_typing_end(self) -> None:
        """Called when the buffer is flushed or paused to trigger fade-out."""
        self._queue.put(("end",))

    def stop(self) -> None:
        """Cleanly closes the overlay and terminates its GUI thread."""
        self._queue.put(("stop",))
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    # ----------------- Tkinter Thread Implementation -----------------

    def _run(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.0)
        self.root.attributes("-topmost", True)

        self._font_family = "Consolas"
        self._base_font_size = 32

        self.label = tk.Label(
            self.root,
            text="",
            font=(self._font_family, self._base_font_size),
            wraplength=800,
            justify="center",
        )
        self.label.place(relx=0.5, rely=0.5, anchor="center")

        self._anim_id = None
        self._current_alpha = 0.0
        self._is_visible = False
        self._current_text = ""

        self._ready_event.set()
        self.root.after(16, self._check_queue)
        try:
            self.root.mainloop()
        except Exception as exc:
            logging.debug("Overlay mainloop ended: %s", exc)

    def _apply_styles(self) -> None:
        """Applies Win32 non-activating and click-through styles so the active app keeps focus."""
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_style = style | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _check_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                action = msg[0]
                if action == "start":
                    self._do_start(msg[1])
                elif action == "update":
                    self._do_update(msg[1])
                elif action == "end":
                    self._do_end()
                elif action == "stop":
                    self._do_stop()
                    return
        except queue.Empty:
            pass
        self.root.after(16, self._check_queue)

    def _do_start(self, text: str) -> None:
        self._current_text = text
        x, y, w, h = get_active_monitor_bounds()
        r, g, b = sample_screen_color(x, y, w, h)
        text_color, bg_color = compute_theme(r, g, b)

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.configure(bg=bg_color)

        wraplen = max(400, int(w * 0.72))
        font_size = self._calc_font_size(text)

        self.label.configure(
            text=text,
            fg=text_color,
            bg=bg_color,
            wraplength=wraplen,
            font=(self._font_family, font_size),
        )

        self.root.deiconify()
        self._apply_styles()
        self._is_visible = True
        self._fade_to(self.target_alpha)

    def _do_update(self, text: str) -> None:
        self._current_text = text
        if not self._is_visible:
            self._do_start(text)
            return

        font_size = self._calc_font_size(text)
        self.label.configure(
            text=text,
            font=(self._font_family, font_size),
        )

        # If fade-out was in progress and user resumes typing, reverse to fade-in
        if self._current_alpha < self.target_alpha:
            self._fade_to(self.target_alpha)

    def _do_end(self) -> None:
        if self._is_visible or self._current_alpha > 0.0:
            self._fade_to(0.0, on_done=self._on_fade_out_done)

    def _on_fade_out_done(self) -> None:
        self._is_visible = False
        self.root.withdraw()
        self.label.configure(text="")
        self._current_text = ""

    def _do_stop(self) -> None:
        if self._anim_id is not None:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None
        self.root.destroy()
        self.root.quit()

    def _calc_font_size(self, text: str) -> int:
        """Adjusts font size dynamically if the text becomes very long."""
        length = len(text)
        if length > 240:
            return 22
        if length > 120:
            return 26
        return self._base_font_size

    def _fade_to(self, target: float, on_done=None) -> None:
        """Smooth fade transition using Tkinter's event timer."""
        if self._anim_id is not None:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None

        def step():
            diff = target - self._current_alpha
            if abs(diff) < 0.09:
                self._current_alpha = target
                self.root.attributes("-alpha", self._current_alpha)
                self._anim_id = None
                if on_done:
                    on_done()
                return

            step_size = 0.12 if diff > 0 else -0.12
            self._current_alpha = max(0.0, min(1.0, self._current_alpha + step_size))
            self.root.attributes("-alpha", self._current_alpha)
            self._anim_id = self.root.after(16, step)

        step()

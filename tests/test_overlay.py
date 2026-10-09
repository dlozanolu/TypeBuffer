import sys

from overlay import compute_theme, get_active_monitor_bounds, sample_screen_color


def test_compute_theme_light_screen():
    text, bg = compute_theme(250, 250, 250)
    assert text == "#141414"
    assert bg.startswith("#") and len(bg) == 7


def test_compute_theme_dark_screen():
    text, bg = compute_theme(10, 10, 10)
    assert text == "#F0F0F0"
    assert bg.startswith("#") and len(bg) == 7


def test_compute_theme_switches_at_half_luminance():
    assert compute_theme(200, 200, 200)[0] == "#141414"
    assert compute_theme(100, 100, 100)[0] == "#F0F0F0"


def test_non_windows_fallbacks():
    if sys.platform == "win32":
        return
    assert get_active_monitor_bounds() == (0, 0, 1920, 1080)
    assert sample_screen_color(0, 0, 100, 100) == (30, 30, 32)

import threading
from pathlib import Path
from PIL import Image
import pystray
from pystray import MenuItem as item

from config import config
from gui import show_settings

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


class TrayIcon:
    def __init__(self, on_exit_callback=None, on_toggle_callback=None):
        self.on_exit_callback = on_exit_callback
        self.on_toggle_callback = on_toggle_callback

        try:
            self.icon_active = Image.open(ASSETS_DIR / "icon_active.png")
            self.icon_inactive = Image.open(ASSETS_DIR / "icon_inactive.png")
        except Exception as e:
            print(f"Failed to load icons: {e}")
            self.icon_active = Image.new('RGB', (64, 64), color=(0, 255, 0))
            self.icon_inactive = Image.new('RGB', (64, 64), color=(255, 0, 0))

        self.is_active = config.get("active", True)

        self.icon = pystray.Icon(
            "TypeBuffer",
            self.icon_active if self.is_active else self.icon_inactive,
            "TypeBuffer"
        )
        self.update_menu()

    def update_menu(self):
        # The item with `default=True` is triggered by double-click on the tray icon.
        self.icon.menu = pystray.Menu(
            item(
                'Pause TypeBuffer' if self.is_active else 'Resume TypeBuffer',
                self.toggle_active,
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            item('Settings...', self.open_settings),
            item('Exit', self.exit_app),
        )

    def toggle_active(self, icon=None, item=None):
        self.set_active(not self.is_active)

    def set_active(self, active: bool):
        self.is_active = active
        config.set("active", active)
        self.icon.icon = self.icon_active if active else self.icon_inactive
        self.update_menu()
        if self.on_toggle_callback:
            self.on_toggle_callback(active)

    def open_settings(self, icon=None, item=None):
        # Run tkinter in a separate thread so it does not block the pystray loop.
        threading.Thread(target=show_settings, args=(False,), daemon=True).start()

    def exit_app(self, icon=None, item=None):
        self.icon.stop()
        if self.on_exit_callback:
            self.on_exit_callback()

    def run(self):
        self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()


if __name__ == "__main__":
    import sys
    from single_instance import SingleInstance

    single_inst = SingleInstance()
    if single_inst.is_running():
        msg = "TypeBuffer is already running! (Check the system tray icon near your clock)."
        print(msg)
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "TypeBuffer", 0x40 | 0x10000)
            except Exception:
                pass
        sys.exit(0)

    print("Testing Tray Icon... Look at your system tray (near the clock).")
    print("Double-click the icon or use the menu to toggle pause/resume.")
    tray = TrayIcon(on_exit_callback=lambda: print("Exiting tray..."))
    try:
        tray.run()
    except KeyboardInterrupt:
        tray.stop()
    finally:
        single_inst.release()

import copy
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from config import config

_settings_window = None
_settings_lock = threading.Lock()


class SettingsWindow:
    def __init__(self, is_welcome=False, on_close_callback=None):
        self.is_welcome = is_welcome
        self.on_close_callback = on_close_callback

        # Ensure config is freshly loaded
        config.load()

        self.root = tk.Tk()
        self.root.title("TypeBuffer Settings" if not is_welcome else "Welcome to TypeBuffer")
        self.root.geometry("500x650")
        self.root.resizable(False, False)

        # Center window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_ui()

    def build_ui(self):
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        if self.is_welcome:
            welcome_lbl = ttk.Label(
                container,
                text="Welcome to TypeBuffer!",
                font=("Helvetica", 16, "bold"),
            )
            welcome_lbl.pack(pady=(0, 10))

            desc_text = (
                "TypeBuffer lets you type silently and flushes the text after a short pause.\n\n"
                "New Feature: Translation Mode! Start your sentence with a language code (e.g., 'en: Hola') "
                "to translate it on the fly using AI.\n\n"
                "Please configure your preferences below."
            )
            desc_lbl = ttk.Label(container, text=desc_text, wraplength=450, justify=tk.LEFT)
            desc_lbl.pack(pady=(0, 20))

        # General Settings
        lf_general = ttk.LabelFrame(container, text=" General Settings ", padding=10)
        lf_general.pack(fill=tk.X, pady=(0, 10))

        # Timeout
        timeout_frame = ttk.Frame(lf_general)
        timeout_frame.pack(fill=tk.X, pady=5)
        ttk.Label(timeout_frame, text="Pause before typing (seconds):").pack(side=tk.LEFT)
        self.timeout_var = tk.StringVar(value=str(config.get("timeout", 0.3)))
        ttk.Entry(timeout_frame, textvariable=self.timeout_var, width=8).pack(side=tk.RIGHT)

        # Autostart
        self.autostart_var = tk.BooleanVar(value=config.get("autostart", True))
        ttk.Checkbutton(
            lf_general,
            text="Start TypeBuffer on system login (Recommended)",
            variable=self.autostart_var,
        ).pack(anchor=tk.W, pady=2)

        # Spellcheck
        self.spellcheck_var = tk.BooleanVar(value=config.get("spellcheck", True))
        ttk.Checkbutton(
            lf_general,
            text="Enable spell checking and grammar correction",
            variable=self.spellcheck_var,
        ).pack(anchor=tk.W, pady=2)

        # Translate
        self.translate_var = tk.BooleanVar(value=config.get("translate", True))
        ttk.Checkbutton(
            lf_general,
            text="Enable 'lang: text' translation mode",
            variable=self.translate_var,
        ).pack(anchor=tk.W, pady=2)

        # AI Providers
        lf_ai = ttk.LabelFrame(container, text=" AI & Services ", padding=10)
        lf_ai.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        provider_frame = ttk.Frame(lf_ai)
        provider_frame.pack(fill=tk.X, pady=5)
        ttk.Label(provider_frame, text="Active AI Provider:").pack(side=tk.LEFT)

        self.providers = copy.deepcopy(config.get("providers", {}))
        self.provider_keys = list(self.providers.keys())

        # Determine active provider canonical key and display name
        active_key = config.get("ai_provider", "openai")
        matched_key = None
        for k, v in self.providers.items():
            if k.lower() == str(active_key).lower() or v.get("name", "").lower() == str(active_key).lower():
                matched_key = k
                break
        if not matched_key:
            matched_key = self.provider_keys[0] if self.provider_keys else "openai"

        self._current_provider_key = matched_key
        canonical_name = self.providers.get(matched_key, {}).get("name", matched_key)
        self.active_provider_var = tk.StringVar(value=canonical_name)

        provider_display_names = [self.providers[k].get("name", k) for k in self.provider_keys]
        self.provider_cb = ttk.Combobox(
            provider_frame,
            textvariable=self.active_provider_var,
            values=provider_display_names,
            state="readonly",
        )
        self.provider_cb.pack(side=tk.RIGHT)
        self.provider_cb.bind("<<ComboboxSelected>>", self.on_provider_change)

        # Provider Config Fields
        self.prov_config_frame = ttk.Frame(lf_ai)
        self.prov_config_frame.pack(fill=tk.X, pady=10)

        ttk.Label(self.prov_config_frame, text="Endpoint URL:").grid(row=0, column=0, sticky=tk.W, pady=2)
        initial_data = self.providers.get(matched_key, {})
        self.endpoint_var = tk.StringVar(value=initial_data.get("endpoint", ""))
        ttk.Entry(self.prov_config_frame, textvariable=self.endpoint_var, width=45).grid(
            row=0, column=1, sticky=tk.E, pady=2
        )

        ttk.Label(self.prov_config_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.apikey_var = tk.StringVar(value=initial_data.get("api_key", ""))
        ttk.Entry(self.prov_config_frame, textvariable=self.apikey_var, width=45, show="*").grid(
            row=1, column=1, sticky=tk.E, pady=2
        )

        # Save Button
        btn_text = "Continue" if self.is_welcome else "Save Settings"
        ttk.Button(container, text=btn_text, command=self.save_and_close).pack(pady=10)

    def on_provider_change(self, event=None):
        selected_display = self.active_provider_var.get()
        matched_key = None
        for k, v in self.providers.items():
            if (
                v.get("name") == selected_display
                or k == selected_display
                or v.get("name", "").lower() == selected_display.lower()
            ):
                matched_key = k
                break

        if not matched_key:
            return

        # If switching away from a different provider, persist its current input fields
        if hasattr(self, "_current_provider_key") and self._current_provider_key != matched_key:
            if self._current_provider_key in self.providers:
                self.providers[self._current_provider_key]["endpoint"] = self.endpoint_var.get().strip()
                self.providers[self._current_provider_key]["api_key"] = self.apikey_var.get().strip()

        self._current_provider_key = matched_key
        prov_data = self.providers.get(matched_key, {})
        canonical_name = prov_data.get("name", matched_key)
        if self.active_provider_var.get() != canonical_name:
            self.active_provider_var.set(canonical_name)
        self.endpoint_var.set(prov_data.get("endpoint", ""))
        self.apikey_var.set(prov_data.get("api_key", ""))

    def save_and_close(self):
        try:
            timeout = float(self.timeout_var.get())
        except ValueError:
            messagebox.showerror("Error", "Timeout must be a number.")
            return

        # Save current provider changes
        if hasattr(self, "_current_provider_key") and self._current_provider_key in self.providers:
            self.providers[self._current_provider_key]["endpoint"] = self.endpoint_var.get().strip()
            self.providers[self._current_provider_key]["api_key"] = self.apikey_var.get().strip()

        config.set("timeout", timeout)
        config.set("autostart", self.autostart_var.get())
        config.set("spellcheck", self.spellcheck_var.get())
        config.set("translate", self.translate_var.get())

        # Update active provider
        config.set("ai_provider", self._current_provider_key)
        config.set("providers", self.providers)

        if self.is_welcome:
            config.set("first_run", False)

        # Manage autostart
        try:
            import setup_autostart

            target = setup_autostart.resolve_target()
            if sys.platform == "win32":
                if self.autostart_var.get():
                    setup_autostart.install_windows(target)
                else:
                    setup_autostart.uninstall_windows()
            elif sys.platform == "linux":
                if self.autostart_var.get():
                    setup_autostart.install_linux(target)
                else:
                    setup_autostart.uninstall_linux()
            elif sys.platform == "darwin":
                if self.autostart_var.get():
                    setup_autostart.install_macos(target)
                else:
                    setup_autostart.uninstall_macos()
        except Exception as e:
            print(f"Failed to update autostart: {e}")

        self.root.destroy()
        if self.on_close_callback:
            self.on_close_callback()

    def on_close(self):
        self.root.destroy()
        if self.on_close_callback:
            self.on_close_callback()


def show_settings(is_welcome=False, on_close_callback=None):
    global _settings_window
    with _settings_lock:
        if _settings_window is not None:
            try:
                if _settings_window.root.winfo_exists():
                    _settings_window.root.lift()
                    _settings_window.root.focus_force()
                    return
            except Exception:
                pass

        def _cleanup():
            global _settings_window
            _settings_window = None
            if on_close_callback:
                on_close_callback()

        _settings_window = SettingsWindow(is_welcome, _cleanup)

    _settings_window.root.mainloop()


if __name__ == "__main__":
    show_settings(is_welcome=True)

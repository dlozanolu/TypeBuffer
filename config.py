import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "TypeBuffer"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "first_run": True,
    "timeout": 0.3,
    "autostart": True,
    "active": True,
    "spellcheck": True,
    "translate": True,
    "lang": "en",
    "ai_provider": "openai",
    "providers": {
        "languagetool": {
            "name": "LanguageTool",
            "type": "languagetool",
            "endpoint": "https://api.languagetool.org/v2/check",
            "api_key": "",
            "model": ""
        },
        "openai": {
            "name": "OpenAI",
            "type": "openai",
            "endpoint": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini"
        },
        "claude": {
            "name": "Claude",
            "type": "anthropic",
            "endpoint": "https://api.anthropic.com/v1",
            "api_key": "",
            "model": "claude-3-5-haiku-latest"
        },
        "deepseek": {
            "name": "DeepSeek",
            "type": "openai",
            "endpoint": "https://api.deepseek.com/v1",
            "api_key": "",
            "model": "deepseek-chat"
        }
    }
}


class Config:
    def __init__(self):
        self._data = DEFAULT_CONFIG.copy()
        self._last_mtime: float = 0.0
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                self._last_mtime = CONFIG_FILE.stat().st_mtime
                with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                    loaded = json.load(f)
                    self._data = DEFAULT_CONFIG.copy()
                    self._merge(self._data, loaded)
                    # Enforce timeout boundary (max 3.0 seconds, min 0.1 seconds)
                    t = self._data.get("timeout")
                    if isinstance(t, (int, float)):
                        if t > 3.0:
                            self._data["timeout"] = 3.0
                            self.save()
                        elif t < 0.1:
                            self._data["timeout"] = 0.1
                            self.save()
            except Exception:
                pass
        else:
            self.save()

    def check_reload(self) -> bool:
        """Reload configuration if the file on disk was modified externally."""
        try:
            if CONFIG_FILE.exists():
                mtime = CONFIG_FILE.stat().st_mtime
                if mtime > self._last_mtime:
                    self.load()
                    return True
        except Exception:
            pass
        return False

    def _merge(self, base: Dict[str, Any], new: Dict[str, Any]):
        for k, v in new.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._merge(base[k], v)
            else:
                base[k] = v

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4)
        try:
            if CONFIG_FILE.exists():
                self._last_mtime = CONFIG_FILE.stat().st_mtime
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        val = self._data.get(key, default)
        if key == "timeout" and isinstance(val, (int, float)):
            return min(3.0, max(0.1, float(val)))
        return val

    def set(self, key: str, value: Any):
        if key == "timeout" and isinstance(value, (int, float)):
            value = min(3.0, max(0.1, float(value)))
        self._data[key] = value
        self.save()

    def get_provider(self, provider_id: str) -> Dict[str, Any]:
        providers = self._data.get("providers", {})
        if provider_id in providers:
            return providers[provider_id]
        # Case-insensitive match on key or display name
        pid_lower = str(provider_id).lower()
        for k, v in providers.items():
            if k.lower() == pid_lower or v.get("name", "").lower() == pid_lower:
                return v
        return {}

    def set_provider(self, provider_id: str, name: str, endpoint: str, api_key: str, provider_type: str = "openai", model: str = ""):
        if "providers" not in self._data:
            self._data["providers"] = {}
        self._data["providers"][provider_id] = {
            "name": name,
            "type": provider_type,
            "endpoint": endpoint,
            "api_key": api_key,
            "model": model
        }
        self.save()

    def active_provider(self) -> Dict[str, Any]:
        pid = self.get("ai_provider", "openai")
        return self.get_provider(pid)


config = Config()

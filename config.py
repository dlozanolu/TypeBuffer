import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "TypeBuffer"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "first_run": True,
    "timeout": 1.5,
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
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._merge(self._data, loaded)
            except Exception:
                pass
        else:
            self.save()

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

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def get_provider(self, provider_id: str) -> Dict[str, Any]:
        return self._data.get("providers", {}).get(provider_id, {})

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

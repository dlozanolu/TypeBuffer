import base64
import copy
import ctypes
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

_ENV_DIR = os.environ.get("TYPEBUFFER_CONFIG_DIR")
if _ENV_DIR:
    CONFIG_DIR = Path(_ENV_DIR)
else:
    CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "TypeBuffer"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DPAPI_PREFIX = "dpapi:v1:"

log = logging.getLogger(__name__)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.c_void_p)]


def _win_crypt32():
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _dpapi_protect(secret: str) -> str:
    """Encrypts a secret with Windows DPAPI, bound to the current user account."""
    crypt32, kernel32 = _win_crypt32()
    data = secret.encode("utf-8")
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), "TypeBuffer API key", None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return _DPAPI_PREFIX + base64.b64encode(raw).decode("ascii")


def _dpapi_unprotect(value: str) -> str:
    """Decrypts a 'dpapi:v1:' value produced by _dpapi_protect."""
    crypt32, kernel32 = _win_crypt32()
    raw = base64.b64decode(value[len(_DPAPI_PREFIX):])
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in = _DataBlob(len(raw), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        plain = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return plain.decode("utf-8")


def _protect_secret(secret: str) -> str | None:
    """
    Returns the secret ready for disk: DPAPI-encrypted on Windows, None when
    no protection is available (the caller stores it as plain text).
    """
    if not secret or sys.platform != "win32":
        return None
    try:
        return _dpapi_protect(secret)
    except Exception as exc:
        log.warning("Could not encrypt the API key with DPAPI: %s", exc)
        return None


def _unprotect_secret(value: str) -> str:
    """Inverse of _protect_secret; values without the marker pass through."""
    if not isinstance(value, str) or not value.startswith(_DPAPI_PREFIX):
        return value
    if sys.platform != "win32":
        # Written on Windows by DPAPI; unreadable outside that account/machine.
        return value
    try:
        return _dpapi_unprotect(value)
    except Exception as exc:
        log.warning("Could not decrypt the stored API key: %s", exc)
        return ""

DEFAULT_CONFIG: Dict[str, Any] = {
    "first_run": True,
    "timeout": 0.3,
    "autostart": True,
    "active": True,
    "hotkey_toggle": "ctrl+shift+space",
    "check_updates": True,
    "zen_overlay": False,
    "spellcheck": False,
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
        # deepcopy, not copy: _merge() mutates nested dicts in place, and a
        # shallow copy would write the user's settings (API keys included)
        # into the module-level DEFAULT_CONFIG.
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self._last_mtime: float = 0.0
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                self._last_mtime = CONFIG_FILE.stat().st_mtime
                with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                    loaded = json.load(f)
                    self._data = copy.deepcopy(DEFAULT_CONFIG)
                    self._merge(self._data, loaded)
                    self._unprotect_providers(self._data)
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

    @staticmethod
    def _unprotect_providers(data: Dict[str, Any]) -> None:
        providers = data.get("providers")
        if not isinstance(providers, dict):
            return
        for prov in providers.values():
            if isinstance(prov, dict) and "api_key" in prov:
                prov["api_key"] = _unprotect_secret(prov.get("api_key") or "")

    def _protected_copy(self) -> Dict[str, Any]:
        """Copy of the data with every API key encrypted before hitting disk."""
        data = copy.deepcopy(self._data)
        providers = data.get("providers")
        if isinstance(providers, dict):
            for prov in providers.values():
                if not isinstance(prov, dict):
                    continue
                key = prov.get("api_key") or ""
                if key and not str(key).startswith(_DPAPI_PREFIX):
                    protected = _protect_secret(str(key))
                    if protected:
                        prov["api_key"] = protected
        return data

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
            json.dump(self._protected_copy(), f, indent=4)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass
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

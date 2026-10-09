import json
import sys

import pytest

import config as config_module


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    return config_module.Config()


def test_defaults_are_never_polluted(cfg):
    cfg.set_provider("custom", "Custom", "https://example.com/v1", "sk-123")
    cfg.set("timeout", 0.5)
    cfg.set("lang", "de")
    assert "custom" not in config_module.DEFAULT_CONFIG["providers"]
    assert config_module.DEFAULT_CONFIG["timeout"] == 0.3
    assert config_module.DEFAULT_CONFIG["lang"] == "en"


def test_roundtrip_keeps_values(cfg):
    cfg.set("lang", "fr")
    cfg.set_provider("openai", "OpenAI", "https://api.openai.com/v1", "sk-secret")
    fresh = config_module.Config()
    assert fresh.get("lang") == "fr"
    assert fresh.get_provider("openai")["api_key"] == "sk-secret"
    assert fresh.get_provider("openai")["endpoint"] == "https://api.openai.com/v1"


def test_missing_keys_fall_back_to_defaults(cfg, tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"lang": "de"}), encoding="utf-8")
    fresh = config_module.Config()
    assert fresh.get("lang") == "de"
    assert fresh.get("zen_overlay") is False
    assert fresh.get("hotkey_toggle") == "ctrl+shift+space"
    assert "providers" in fresh._data


def test_timeout_is_clamped(cfg):
    cfg.set("timeout", 99)
    assert cfg.get("timeout") == 3.0
    cfg.set("timeout", -5)
    assert cfg.get("timeout") == 0.1


def test_get_provider_is_case_insensitive(cfg):
    assert cfg.get_provider("OPENAI")["name"] == "OpenAI"
    assert cfg.get_provider("Claude")["type"] == "anthropic"
    assert cfg.get_provider("does-not-exist") == {}


def test_api_key_is_protected_on_disk_and_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config_module, "_protect_secret", lambda secret: "enc:" + secret[::-1])
    monkeypatch.setattr(
        config_module,
        "_unprotect_secret",
        lambda value: value[4:][::-1] if value.startswith("enc:") else value,
    )
    cfg = config_module.Config()
    cfg.set_provider("openai", "OpenAI", "https://api.openai.com/v1", "sk-top-secret")

    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["providers"]["openai"]["api_key"] == "enc:terces-pot-ks"

    reloaded = config_module.Config()
    assert reloaded.get_provider("openai")["api_key"] == "sk-top-secret"


def test_plaintext_key_from_manual_edit_still_loads(cfg, tmp_path):
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    data["providers"]["openai"]["api_key"] = "plain-key"
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    fresh = config_module.Config()
    assert fresh.get_provider("openai")["api_key"] == "plain-key"


def test_dpapi_roundtrip_through_disk(cfg, tmp_path):
    cfg.set_provider("openai", "OpenAI", "https://api.openai.com/v1", "sk-dpapi-test")
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    reloaded = config_module.Config()
    assert reloaded.get_provider("openai")["api_key"] == "sk-dpapi-test"
    if sys.platform == "win32":
        assert "sk-dpapi-test" not in raw

import json

import corrector


def test_detect_translation_basic():
    assert corrector.detect_translation("en: Hola mundo") == ("en", "Hola mundo")
    assert corrector.detect_translation("[fr]: Bonjour") == ("fr", "Bonjour")
    assert corrector.detect_translation("{es]: Hola") == ("es", "Hola")
    assert corrector.detect_translation("EN:Hello") == ("en", "Hello")
    assert corrector.detect_translation("english: hola mundo") == ("english", "hola mundo")


def test_detect_translation_rejects_non_requests():
    assert corrector.detect_translation("hello world") is None
    assert corrector.detect_translation("en:") is None
    assert corrector.detect_translation("xx: hola") is None


def test_is_translation_prefix():
    assert corrector.is_translation_prefix("en:")
    assert corrector.is_translation_prefix("en: partial phrase")
    assert not corrector.is_translation_prefix("xyz: nope")
    assert not corrector.is_translation_prefix("hello")


def test_strip_quotes():
    assert corrector._strip_quotes('"hola"') == "hola"
    assert corrector._strip_quotes("'hola'") == "hola"
    assert corrector._strip_quotes("hola") == "hola"


def test_has_meaningful_content():
    assert corrector._has_meaningful_content("hola")
    assert corrector._has_meaningful_content("123")
    assert not corrector._has_meaningful_content("... !!!")
    assert not corrector._has_meaningful_content("   ")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def _patch_languagetool(monkeypatch, payload):
    monkeypatch.setattr(
        corrector.urllib.request, "urlopen", lambda req, timeout: _FakeResponse(payload)
    )
    monkeypatch.setattr(
        corrector.config,
        "get_provider",
        lambda provider_id: {"endpoint": "http://lt.test/v2/check"},
    )


def test_languagetool_applies_replacements(monkeypatch):
    payload = {
        "matches": [
            {"offset": 0, "length": 4, "replacements": [{"value": "Hello"}]},
            {"offset": 5, "length": 4, "replacements": [{"value": "world"}]},
        ]
    }
    _patch_languagetool(monkeypatch, payload)
    assert corrector._correct_languagetool("Helo wrld", language="en", timeout=1.0) == "Hello world"


def test_languagetool_skips_matches_without_suggestions(monkeypatch):
    payload = {"matches": [{"offset": 0, "length": 1, "replacements": []}]}
    _patch_languagetool(monkeypatch, payload)
    assert corrector._correct_languagetool("x", language="en", timeout=1.0) == "x"


def test_correct_text_reports_missing_key(monkeypatch):
    monkeypatch.setattr(
        corrector.config,
        "get_provider",
        lambda provider_id: {
            "type": "openai",
            "api_key": "",
            "endpoint": "https://api.openai.com/v1",
        },
    )
    monkeypatch.setattr(
        corrector, "_correct_languagetool", lambda text, *, language, timeout: text + " LT"
    )
    reasons = []
    out = corrector.correct_text("hola", provider="openai", language="es", on_error=reasons.append)
    assert out == "hola LT"
    assert reasons and "no API key" in reasons[0]

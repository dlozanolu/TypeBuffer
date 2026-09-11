"""
Spell checker, grammar checker, and translator with pluggable AI providers.

Providers (configured in config.py / the Settings UI):
  - languagetool: free public API (or a local server)
  - openai:     OpenAI-compatible chat/completions
  - claude:     Anthropic Messages API
  - deepseek:   OpenAI-compatible chat/completions
  - custom:     any OpenAI-compatible endpoint you register

Translation mode:
  A phrase starting with a 2-letter language code triggers translation.
  Example: "en: Hola mundo" -> translates "Hola mundo" into English.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from config import config

log = logging.getLogger(__name__)

LT_PUBLIC = "https://api.languagetool.org/v2/check"

# "en: some text" or "[en]: some text" or "{en]: some text" -> translate "some text" to English.
PREFIX_RE = re.compile(r"^(?:\[|\{)?([a-zA-ZáéíóúñÁÉÍÓÚÑ]{2,12})(?:\]|\})?:", re.DOTALL)
TRANSLATE_RE = re.compile(r"^(?:\[|\{)?([a-zA-ZáéíóúñÁÉÍÓÚÑ]{2,12})(?:\]|\})?:\s*(.+)$", re.DOTALL)

LANG_NAMES = {
    # 2-letter codes
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ca": "Catalan", "eu": "Basque",
    "gl": "Galician", "ru": "Russian", "uk": "Ukrainian", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "nl": "Dutch",
    "sv": "Swedish", "no": "Norwegian", "da": "Danish", "fi": "Finnish",
    "pl": "Polish", "cs": "Czech", "tr": "Turkish", "el": "Greek",
    "he": "Hebrew", "hi": "Hindi", "ro": "Romanian", "hu": "Hungarian",
    # 3-letter codes
    "eng": "English", "spa": "Spanish", "esp": "Spanish", "fra": "French",
    "fre": "French", "deu": "German", "ger": "German", "ita": "Italian",
    "por": "Portuguese", "cat": "Catalan", "eus": "Basque", "glg": "Galician",
    "rus": "Russian", "ukr": "Ukrainian", "zho": "Chinese", "chi": "Chinese",
    "jpn": "Japanese", "kor": "Korean", "ara": "Arabic", "nld": "Dutch",
    "dut": "Dutch", "swe": "Swedish", "nor": "Norwegian", "dan": "Danish",
    "fin": "Finnish", "pol": "Polish", "ces": "Czech", "cze": "Czech",
    "tur": "Turkish", "ell": "Greek", "gre": "Greek", "heb": "Hebrew",
    "hin": "Hindi", "ron": "Romanian", "rum": "Romanian", "hun": "Hungarian",
    # Common full names in English and Spanish
    "english": "English", "ingles": "English", "inglés": "English",
    "spanish": "Spanish", "espanol": "Spanish", "español": "Spanish",
    "french": "French", "frances": "French", "francés": "French",
    "german": "German", "aleman": "German", "alemán": "German",
    "italian": "Italian", "italiano": "Italian",
    "portuguese": "Portuguese", "portugues": "Portuguese", "portugués": "Portuguese",
    "catalan": "Catalan", "catalán": "Catalan",
    "russian": "Russian", "ruso": "Russian",
    "chinese": "Chinese", "chino": "Chinese",
    "japanese": "Japanese", "japones": "Japanese", "japonés": "Japanese",
    "korean": "Korean", "coreano": "Korean",
}

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "claude": "claude-3-5-haiku-latest",
    "deepseek": "deepseek-chat",
}


def is_translation_prefix(text: str) -> bool:
    """Check if the text begins with a valid language code prefix like 'en:', '[en]:', or '{es]:'."""
    m = PREFIX_RE.match(text.strip())
    return bool(m and m.group(1).lower() in LANG_NAMES)


def detect_translation(text: str):
    """Return (lang_code, source_text) if text is a translation request, else None."""
    m = TRANSLATE_RE.match(text.strip())
    if not m:
        return None
    code, source = m.group(1).lower(), m.group(2).strip()
    if code in LANG_NAMES and source:
        return code, source
    return None


def _openai_chat(provider: dict, system: str, user_text: str, model: str, timeout: float) -> str:
    endpoint = provider["endpoint"].rstrip("/") + "/chat/completions"
    api_key = provider.get("api_key", "")
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


def _anthropic_chat(provider: dict, system: str, user_text: str, model: str, timeout: float) -> str:
    endpoint = provider["endpoint"].rstrip("/") + "/messages"
    api_key = provider.get("api_key", "")
    body = {
        "model": model,
        "max_tokens": 2048,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    parts = [c.get("text", "") for c in payload.get("content", [])]
    return "".join(parts).strip()


def _call_ai(provider: dict, provider_id: str, system: str, user_text: str, timeout: float) -> str:
    model = provider.get("model") or DEFAULT_MODELS.get(provider_id, "gpt-4o-mini")
    ptype = provider.get("type", "openai")
    if ptype == "anthropic":
        return _anthropic_chat(provider, system, user_text, model, timeout)
    return _openai_chat(provider, system, user_text, model, timeout)


def _strip_quotes(out: str) -> str:
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        return out[1:-1]
    return out


def translate_text(text: str, timeout: float = 8.0) -> str | None:
    """
    Translates text if it matches the "lang: text" pattern.
    Returns the translated string, or None if it is not a translation request.
    """
    detected = detect_translation(text)
    if not detected:
        return None
    code, source = detected
    target = LANG_NAMES[code]

    provider_id = config.get("ai_provider", "openai")
    provider = config.active_provider()
    if provider.get("type") == "languagetool":
        log.warning("Translation requires an AI provider, not LanguageTool.")
        return None

    system = (
        f"You are a professional translator. Translate the user's text into {target}. "
        "Return ONLY the translation, without quotes or explanations."
    )
    try:
        out = _call_ai(provider, provider_id, system, source, timeout)
    except Exception as exc:
        log.warning("Translation failed (%s); leaving original text", exc)
        return None

    out = _strip_quotes(out)
    log.info("Translation (%s): %r -> %r", code, source, out)
    return out or None


def correct_text(
    text: str,
    *,
    provider: str | None = None,
    language: str = "en",
    timeout: float = 8.0,
) -> str:
    text = text or ""
    if not text.strip():
        return text

    provider = provider or config.get("ai_provider", "openai")
    cfg = config.get_provider(provider)

    try:
        if cfg.get("type") == "languagetool":
            return _correct_languagetool(text, language=language, timeout=timeout)
        if cfg.get("type") in ("openai", "anthropic"):
            if not cfg.get("api_key"):
                log.warning("No API key for %r; falling back to LanguageTool", provider)
                return _correct_languagetool(text, language=language, timeout=timeout)
            return _correct_ai(cfg, provider, text, language=language, timeout=timeout)
        log.warning("Unknown provider %r; skipping correction", provider)
        return text
    except Exception as exc:
        log.warning("Spellchecker failed (%s); returning original text", exc)
        return text


def _correct_ai(provider: dict, provider_id: str, text: str, *, language: str, timeout: float) -> str:
    system = (
        "You are an expert spell checker and proofreader.\n"
        "CRITICAL RULES:\n"
        "1. Automatically detect the language of the user's input text.\n"
        "2. Correct ONLY spelling, punctuation, typos, and grammatical errors in that EXACT SAME language.\n"
        "3. NEVER translate the text into English or any other language under any circumstance. "
        "If the input is in Spanish, output in Spanish. If it is in French, output in French. "
        "Translation is strictly forbidden in this mode.\n"
        "4. Do NOT change the meaning, tone, or rewrite sentences.\n"
        "5. Return ONLY the corrected text in its original language, without quotes or explanations."
    )
    out = _call_ai(provider, provider_id, system, text, timeout)
    out = _strip_quotes(out)
    if out != text:
        log.info("%s: %r -> %r", provider_id, text, out)
    return out or text


def _correct_languagetool(text: str, *, language: str, timeout: float) -> str:
    """Applies LanguageTool suggestions over the complete text (sentence context)."""
    endpoint = config.get_provider("languagetool").get("endpoint") or LT_PUBLIC
    data = urllib.parse.urlencode(
        {
            "text": text,
            "language": language,
            "enabledOnly": "false",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    matches = payload.get("matches") or []
    if not matches:
        return text

    out = text
    for m in sorted(matches, key=lambda x: x["offset"], reverse=True):
        reps = m.get("replacements") or []
        if not reps:
            continue
        start = m["offset"]
        end = start + m["length"]
        replacement = reps[0]["value"]
        out = out[:start] + replacement + out[end:]

    if out != text:
        log.info("LanguageTool: %r -> %r", text, out)
    return out

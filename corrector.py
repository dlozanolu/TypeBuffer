"""
Spell and grammar checker with sentence/paragraph context.

Providers:
  - languagetool (default): Public API or local server
  - openai: LLM if OPENAI_API_KEY is present (better style/context)
  - none: no checking
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

LT_PUBLIC = "https://api.languagetool.org/v2/check"
LT_LOCAL = "http://127.0.0.1:8010/v2/check"


def correct_text(
    text: str,
    *,
    provider: str = "languagetool",
    language: str = "en",
    timeout: float = 8.0,
) -> str:
    text = text or ""
    if not text.strip() or provider in ("none", "off", "no"):
        return text

    try:
        if provider == "openai":
            return _correct_openai(text, language=language, timeout=timeout)
        if provider == "languagetool":
            return _correct_languagetool(text, language=language, timeout=timeout)
        log.warning("Unknown provider %r; skipping correction", provider)
        return text
    except Exception as exc:
        log.warning("Spellchecker failed (%s); returning original text", exc)
        return text


def _correct_languagetool(text: str, *, language: str, timeout: float) -> str:
    """Applies LanguageTool suggestions over the complete text (sentence context)."""
    endpoint = os.environ.get("LANGUAGETOOL_URL", LT_PUBLIC)
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

    # Apply backwards to avoid messing up offsets
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


def _correct_openai(text: str, *, language: str, timeout: float) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY is not set; falling back to LanguageTool")
        return _correct_languagetool(text, language=language, timeout=timeout)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    lang_name = {"es": "Spanish", "en": "English", "fr": "French", "de": "German"}.get(
        language, language
    )
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are a spelling and grammar checker for {lang_name}. "
                    "ONLY correct spelling, punctuation, and grammar mistakes "
                    "taking into account the whole sentence or paragraph. "
                    "Do NOT change the meaning, tone, or add new content. "
                    "Return ONLY the corrected text, without quotes or explanations."
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    out = payload["choices"][0]["message"]["content"].strip()
    # Strip accidental surrounding quotes
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1]
    if out != text:
        log.info("OpenAI: %r -> %r", text, out)
    return out or text

"""
Corrector ortográfico/gramatical con contexto de frase o párrafo.

Proveedores:
  - languagetool (default): API pública o servidor local
  - openai: LLM si hay OPENAI_API_KEY (mejor estilo/contexto)
  - none: sin corrección
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
    language: str = "es",
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
        log.warning("Proveedor desconocido %r; se envia sin corregir", provider)
        return text
    except Exception as exc:
        log.warning("Corrector fallo (%s); se envia texto original", exc)
        return text


def _correct_languagetool(text: str, *, language: str, timeout: float) -> str:
    """Aplica sugerencias de LanguageTool sobre el texto completo (contexto de frase)."""
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

    # Aplicar de atrás hacia adelante para no desplazar offsets
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
        log.warning("OPENAI_API_KEY no definida; fallback a LanguageTool")
        return _correct_languagetool(text, language=language, timeout=timeout)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    lang_name = {"es": "español", "en": "English", "fr": "français", "de": "Deutsch"}.get(
        language, language
    )
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"Eres un corrector ortográfico y gramatical en {lang_name}. "
                    "Corrige SOLO errores ortográficos, tildes, puntuación y gramática "
                    "teniendo en cuenta la frase o párrafo completo. "
                    "No cambies el significado, tono ni añadas contenido. "
                    "Devuelve ÚNICAMENTE el texto corregido, sin comillas ni explicaciones."
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
    # Quitar comillas envolventes accidentales
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1]
    if out != text:
        log.info("OpenAI: %r -> %r", text, out)
    return out or text

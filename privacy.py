"""
Log privacy helpers.

Everything the user types is sensitive: it may be a password fragment, a
private message or a contract. TypeBuffer must therefore be able to report
what it is doing without ever writing that content to typebuffer.log.
"""

from __future__ import annotations


def redact(text: str) -> str:
    """Replacement for typed content in logs: keeps diagnostics, drops the text."""
    return f"<{len(text)} chars>"

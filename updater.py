"""
Checks GitHub Releases for a newer version.

Only notifies; it never downloads or installs anything. Any failure is silent,
since a machine with no connection must not be nagged on every start.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request

from version import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/dlozanolu/TypeBuffer/releases/latest"
RELEASES_PAGE = "https://github.com/dlozanolu/TypeBuffer/releases/latest"

log = logging.getLogger(__name__)


def is_packaged_build() -> bool:
    """True for the installed binary, False when running from source."""
    return bool(getattr(sys, "frozen", False))


def parse_version(text: str) -> tuple[int, ...]:
    """Turns 'v1.2.10' into (1, 2, 10). Unparsable parts count as 0."""
    parts: list[int] = []
    for chunk in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def fetch_latest_version(timeout: float = 6.0) -> str | None:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"TypeBuffer/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = payload.get("tag_name")
    return str(tag) if tag else None


def check_for_update(timeout: float = 6.0) -> tuple[str, str] | None:
    """Returns (version, download page) when a newer release exists, else None."""
    try:
        latest = fetch_latest_version(timeout=timeout)
    except Exception as exc:
        log.debug("Update check failed: %s", exc)
        return None

    if not latest or not is_newer(latest, __version__):
        return None

    log.info("Update available: %s (running %s)", latest, __version__)
    return latest.lstrip("vV"), RELEASES_PAGE

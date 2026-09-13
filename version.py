"""Single source of truth for the application version.

The release workflow rewrites this file from the git tag before building, so a
published binary always reports the version it was actually built from.
"""

__version__ = "1.0.2"

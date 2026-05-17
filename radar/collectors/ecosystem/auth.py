"""Credential resolution for ecosystem collectors.

Only GitHub benefits from a token (it lifts the unauthenticated 60 req/hr
limit). The token is read from the environment on demand and never logged,
stored, or exported.
"""

from __future__ import annotations

import os

GITHUB_TOKEN_ENV = "CV_RADAR_GITHUB_TOKEN"


def resolve_github_token() -> str | None:
    """Return the GitHub token from the environment, or ``None`` if unset.

    Matches the existing ``CV_RADAR_DB_PATH`` / ``CV_RADAR_CONFIG_DIR`` env-var
    convention. An empty string is treated as absent.
    """
    return os.environ.get(GITHUB_TOKEN_ENV) or None


__all__ = ["GITHUB_TOKEN_ENV", "resolve_github_token"]

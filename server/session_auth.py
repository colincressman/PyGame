"""Lightweight per-login session tokens for network packet authentication."""

from __future__ import annotations

import secrets
import threading

_tokens: dict[str, str] = {}
_lock = threading.Lock()


def issue_token(player_id: str) -> str:
    """Create and store a fresh session token for *player_id*."""
    token = secrets.token_urlsafe(24)
    with _lock:
        _tokens[player_id] = token
    return token


def verify_token(player_id: str, token: object) -> bool:
    """Return True when *token* matches the current session for *player_id*."""
    if not isinstance(player_id, str) or not isinstance(token, str) or not token:
        return False
    with _lock:
        return _tokens.get(player_id) == token


def revoke_token(player_id: str) -> None:
    """Forget a player's session token after cleanup/disconnect."""
    with _lock:
        _tokens.pop(player_id, None)


def clear_tokens() -> None:
    """Test helper: clear all active tokens."""
    with _lock:
        _tokens.clear()

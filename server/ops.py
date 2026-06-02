"""server/ops.py — Operator and ban list management.

Persisted to server/ops.json:
{
    "ops":  ["Player1", "Admin"],
    "bans": ["Griefer"]
}

To set the first operator, add the player’s name to the "ops" list in
server/ops.json directly (create the file if it doesn’t exist). Operators
can then use /op <player> in-game to promote others.
"""

import os
import json
import threading
_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops.json")
_lock = threading.Lock()
_data: dict = {"ops": [], "bans": []}


def _load() -> None:
    global _data
    if os.path.exists(_PATH):
        try:
            with open(_PATH, "r") as f:
                loaded = json.load(f)
            _data = {
                "ops":  list(loaded.get("ops",  [])),
                "bans": list(loaded.get("bans", [])),
            }
        except Exception:
            pass


def _save() -> None:
    try:
        with open(_PATH, "w") as f:
            json.dump(_data, f, indent=2)
    except Exception as e:
        print(f"[OPS] Failed to save ops.json: {e}")


_load()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def is_op(player_id: str) -> bool:
    with _lock:
        return player_id in _data["ops"]


def is_banned(player_id: str) -> bool:
    with _lock:
        return player_id in _data["bans"]


def op_count() -> int:
    with _lock:
        return len(_data["ops"])


def list_ops() -> list:
    with _lock:
        return list(_data["ops"])


def list_bans() -> list:
    with _lock:
        return list(_data["bans"])


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def add_op(player_id: str) -> None:
    with _lock:
        if player_id not in _data["ops"]:
            _data["ops"].append(player_id)
            _save()
    print(f"[OPS] {player_id} is now an operator.")


def remove_op(player_id: str) -> None:
    with _lock:
        if player_id in _data["ops"]:
            _data["ops"].remove(player_id)
            _save()
    print(f"[OPS] {player_id} is no longer an operator.")


def ban_player(player_id: str) -> None:
    with _lock:
        if player_id not in _data["bans"]:
            _data["bans"].append(player_id)
        # Revoke op if they had it
        if player_id in _data["ops"]:
            _data["ops"].remove(player_id)
        _save()
    print(f"[OPS] {player_id} has been banned.")


def unban_player(player_id: str) -> None:
    with _lock:
        if player_id in _data["bans"]:
            _data["bans"].remove(player_id)
            _save()
    print(f"[OPS] {player_id} has been unbanned.")
        

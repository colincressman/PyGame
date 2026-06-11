import os
import re
import json

SAVE_DIR = os.path.join(os.path.dirname(__file__), "player_saves")
os.makedirs(SAVE_DIR, exist_ok=True)

# Allowed player ID characters — alphanumeric plus hyphens and underscores.
# Rejects any path component that could be used for directory traversal.
_SAFE_ID = re.compile(r'^[A-Za-z0-9_\-]+$')


def default_player_stats():
    """Return a fresh copy of default player stats. Always returns new objects (no shared refs)."""
    return {
        "health": 100,
        "health_max": 100,
        "stamina": 100.0,
        "stamina_max": 100.0,
        "attack_power": 10.0,
        "speed_bonus":    0.0,  # tiles/sec bonus on top of client base speed
        "hp_regen":       0.0,  # HP restored per second (passive regen)
        "sp_regen_bonus": 0.0,  # extra SP/s on top of base 10/s
        "level": 1,
        "exp": 0,
        "exp_next": 100,        # exp required to reach next level
        "stat_points": 0,       # unspent stat upgrade points
        "coins": 0,             # wallet — NOT stored in inventory
        "creative": False,      # creative mode: invincible + free items
        "faction_power": 0.0,
        "first_join_complete": False,
        "inventory": [None] * 48,  # 0-35 bags, 36=head, 37=chest, 38=ring1, 39=ring2, 40=pants, 41=shoes, 42=arms, 43=necklace, 44=back, 45=shield, 46=shoulders, 47=hands
    }


def load_player(player_id):
    """Load player save data from disk. Returns a dict or None if no save exists."""
    if not _SAFE_ID.match(player_id):
        print(f"[SAVE] Rejected unsafe player_id: {repr(player_id)}")
        return None
    path = os.path.join(SAVE_DIR, f"{player_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[SAVE] Failed to load {player_id}: {e}")
        return None
    if not isinstance(raw, dict):
        print(f"[SAVE] Invalid save shape for {player_id}: expected object")
        return None

    stats = {**default_player_stats(), **raw}
    # Legacy saves existed before the first-join gate. Treat missing flag as already complete.
    if "first_join_complete" not in raw:
        stats["first_join_complete"] = True
    inventory = list(stats.get("inventory", []))
    if len(inventory) < 48:
        inventory += [None] * (48 - len(inventory))
    stats["inventory"] = inventory[:48]
    return stats


def save_player(player_id, player_data):
    """Persist player state to disk. Should be called outside any lock."""
    if not _SAFE_ID.match(player_id):
        print(f"[SAVE] Rejected unsafe player_id on save: {repr(player_id)}")
        return
    path = os.path.join(SAVE_DIR, f"{player_id}.json")
    defaults = default_player_stats()
    data = {
        "pos":          player_data.get("pos",          [0, 0]),
        "health":       player_data.get("health",       defaults["health"]),
        "health_max":   player_data.get("health_max",   defaults["health_max"]),
        "stamina":      player_data.get("stamina",      defaults["stamina"]),
        "stamina_max":  player_data.get("stamina_max",  defaults["stamina_max"]),
        "attack_power": player_data.get("attack_power", defaults["attack_power"]),
        "speed_bonus":    player_data.get("speed_bonus",    defaults["speed_bonus"]),
        "hp_regen":       player_data.get("hp_regen",       defaults["hp_regen"]),
        "sp_regen_bonus": player_data.get("sp_regen_bonus", defaults["sp_regen_bonus"]),
        "level":          player_data.get("level",          defaults["level"]),
        "exp":          player_data.get("exp",          defaults["exp"]),
        "exp_next":     player_data.get("exp_next",     defaults["exp_next"]),
        "stat_points":  player_data.get("stat_points",  defaults["stat_points"]),
        "coins":        player_data.get("coins",        defaults["coins"]),
        "faction_power": player_data.get("faction_power", defaults["faction_power"]),
        "first_join_complete": player_data.get("first_join_complete", defaults["first_join_complete"]),
        "inventory":    player_data.get("inventory",    defaults["inventory"]),
        "last_seen":    player_data.get("last_seen"),
    }
    # Persist bed spawn only if set
    if "bed_spawn" in player_data:
        data["bed_spawn"] = player_data["bed_spawn"]
    # Persist player-set home only if set
    if "home_pos" in player_data:
        data["home_pos"] = player_data["home_pos"]
    # Persist cosmetic appearance if set
    if "appearance" in player_data:
        data["appearance"] = player_data["appearance"]
    if "faction" in player_data:
        data["faction"] = player_data["faction"]
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[SAVE] Failed to save {player_id}: {e}")

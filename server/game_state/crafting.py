"""
server/game_state/crafting.py

Validates and executes player craft requests server-side.
Loads recipes.json once at import.  Thread-safe via players_lock.
"""

import json
import os
import random

from server.game_state.progression_data import CRAFT_QUALITY_TIERS
from server.item_data import get_item
from server.shared_lock import players_lock

_recipes: dict = {}


def _load():
    global _recipes
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "recipes.json")
    try:
        with open(path) as f:
            _recipes = {int(k): v for k, v in json.load(f).items()}
        print(f"[CRAFTING] Loaded {len(_recipes)} recipes.")
    except Exception as e:
        print(f"[CRAFTING] Failed to load recipes.json: {e}")


_load()


# ---------------------------------------------------------------------------
# Quality system
# Tiers: (name, cumulative_probability, stat_min_multiplier, stat_max_multiplier)
# ---------------------------------------------------------------------------

def _roll_quality():
    """Return (quality_name, lo_mult, hi_mult) for a random quality tier."""
    r = random.random()
    for tier in CRAFT_QUALITY_TIERS:
        if r <= float(tier["cum_prob"]):
            return tier["name"], float(tier["min_mult"]), float(tier["max_mult"])
    tail = CRAFT_QUALITY_TIERS[-1]
    return tail["name"], float(tail["min_mult"]), float(tail["max_mult"])


def _roll_stats(base_stats: dict, lo: float, hi: float) -> dict:
    """Randomly scale each stat value within [lo, hi] multiplier range."""
    result = {}
    for k, v in base_stats.items():
        mult = random.uniform(lo, hi)
        if isinstance(v, int):
            result[k] = max(1, round(v * mult))
        else:
            result[k] = round(float(v) * mult, 3)
    return result


# ---------------------------------------------------------------------------
# Inventory helpers (operate on a list[slot] in-place)
# ---------------------------------------------------------------------------

def _count(inv: list, item_id: int) -> int:
    return sum(s[1] for s in inv[:36] if s is not None and s[0] == item_id)


def _consume(inv: list, item_id: int, qty: int):
    """Remove qty of item_id from bag slots (0-35) in-place."""
    for i in range(36):
        if qty <= 0:
            break
        s = inv[i]
        if s is None or s[0] != item_id:
            continue
        take = min(qty, s[1])
        s[1] -= take
        qty  -= take
        if s[1] == 0:
            inv[i] = None


def _add(inv: list, item_id: int, qty: int, stackable: bool, max_stack: int) -> bool:
    """Add qty of item_id to bag slots (0-35).  Returns True if all placed."""
    if stackable:
        for i in range(36):
            s = inv[i]
            if s is not None and s[0] == item_id and s[1] < max_stack:
                can  = min(qty, max_stack - s[1])
                s[1] += can
                qty  -= can
                if qty <= 0:
                    return True
    for i in range(36):
        if inv[i] is None:
            inv[i] = [item_id, min(qty, max_stack)]
            qty    -= min(qty, max_stack)
            if qty <= 0:
                return True
    return False   # no room


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def handle_craft(player_id: str, recipe_id, players: dict,
                 nearby_stations: list | None = None) -> bool:
    """Attempt to craft recipe_id for player_id.  Returns True on success."""
    try:
        rid = int(recipe_id)
    except (TypeError, ValueError):
        return False

    recipe = _recipes.get(rid)
    if not recipe:
        return False

    # Station check — reject if recipe requires a station the player isn't near
    required_station = recipe.get("station")
    if required_station:
        if not nearby_stations or required_station not in nearby_stations:
            print(f"[CRAFT] {player_id} missing station '{required_station}'")
            return False

    result_id, result_qty = recipe["result"]
    item_info  = get_item(result_id)
    stackable  = item_info.get("stackable", True)
    max_stack  = item_info.get("max_stack", 99)

    with players_lock:
        player = players.get(player_id)
        if not player:
            return False
        inv = player["inventory"]

        # Verify ingredients
        for ing_id, ing_qty in recipe.get("ingredients", []):
            if _count(inv, ing_id) < ing_qty:
                return False

        # Verify bag has room for result
        free = sum(1 for i in range(36) if inv[i] is None)
        can_stack = stackable and any(
            inv[i] is not None and inv[i][0] == result_id and inv[i][1] < max_stack
            for i in range(36)
        )
        if free == 0 and not can_stack:
            return False

        # Consume, then add
        for ing_id, ing_qty in recipe.get("ingredients", []):
            _consume(inv, ing_id, ing_qty)

        base_stats = item_info.get("stats", {})
        max_dur    = item_info.get("durability")      # None for stackable/non-durable items
        if base_stats:
            # Equipment with stats: roll quality tier and randomise stats
            quality, lo, hi = _roll_quality()
            rolled = _roll_stats(base_stats, lo, hi)
            meta   = {"quality": quality, "stats": rolled}
            if max_dur:
                meta["dur"]     = max_dur
                meta["dur_max"] = max_dur
            for i in range(36):
                if inv[i] is None:
                    inv[i] = [result_id, 1, meta]
                    break
        elif max_dur:
            # Durable item without rolled stats (e.g. tools): attach dur meta only
            meta    = {"dur": max_dur, "dur_max": max_dur}
            quality = "N/A"
            for i in range(36):
                if inv[i] is None:
                    inv[i] = [result_id, 1, meta]
                    break
        else:
            _add(inv, result_id, result_qty, stackable, max_stack)
            quality = "N/A"

        print(f"[CRAFT] {player_id} crafted {item_info.get('name', result_id)} "
              f"({quality if base_stats else 'N/A'})")
        return True

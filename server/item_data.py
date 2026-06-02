"""
server/item_data.py

Shared item metadata loader.  Provides equipment stat bonuses for use
in game_sync (broadcast) and combat (player attack power).
"""

import os

try:
    import orjson as _json   # ~3-5x faster than stdlib json
    _json_loads = _json.loads
    def _json_load(f): return _json.loads(f.read())
except ImportError:
    import json as _json     # fallback if orjson not installed
    _json_loads = _json.loads
    def _json_load(f): return _json.load(f)

_data: dict = {}


def _load():
    global _data
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")
    try:
        with open(path, "rb") as f:
            _data = {int(k): v for k, v in _json_load(f).items()}
    except FileNotFoundError:
        raise FileNotFoundError(
            f"[ITEM DATA] items.json not found at {path} — "
            "server cannot start without item definitions."
        )
    except (ValueError, OSError) as e:
        raise RuntimeError(f"[ITEM DATA] Failed to load items.json: {e}") from e


_load()

_EQUIP_STATS = (
    "attack_power", "health_max", "stamina_max",
    "speed_bonus",  "hp_regen",   "sp_regen_bonus",
    "defense",
)


def get_item(item_id: int) -> dict:
    return _data.get(item_id, {})


def _get_slot_stats(slot) -> dict:
    """Return the effective stats for an inventory slot.

    Slots are either:
      [item_id, qty]              — base stats from items.json
      [item_id, qty, meta_dict]   — rolled stats stored in meta_dict["stats"]

    If the item has durability and it has reached 0, return empty stats
    (broken items provide no bonuses).
    """
    if slot is None:
        return {}
    if len(slot) >= 3 and isinstance(slot[2], dict):
        meta = slot[2]
        # Broken item — durability exhausted but slot not yet cleared
        if meta.get("dur_max") and meta.get("dur", 1) <= 0:
            return {}
        return meta.get("stats", {})
    return _data.get(slot[0], {}).get("stats", {})


def get_equip_bonuses(inventory: list) -> dict:
    """Return summed stat bonuses from items currently in equip slots (36-47)."""
    bonuses = {k: 0.0 for k in _EQUIP_STATS}
    for slot_idx in range(36, 48):
        if slot_idx >= len(inventory):
            break
        item_stats = _get_slot_stats(inventory[slot_idx])
        for k in _EQUIP_STATS:
            bonuses[k] += float(item_stats.get(k, 0))
    return bonuses


# Hotbar occupies inventory indices 27-35 (last row of the 4×9 grid).
_HOTBAR_OFFSET = 27

# Maps equip slot index → the slot_type an item must have to be placed there.
_EQUIP_SLOT_TYPES: dict[int, str] = {
    36: "head",
    37: "chest",
    38: "ring",
    39: "ring",
    40: "pants",
    41: "shoes",
    42: "arms",
    43: "necklace",
    44: "back",
    45: "shield",
    46: "shoulders",
    47: "hands",
}


def get_hotbar_bonus(inventory: list, hotbar_slot: int) -> dict:
    """Return stat bonuses from the currently selected hotbar item.

    hotbar_slot is the visual index 0-8; the actual inventory index is
    27 + hotbar_slot (the last row of the 4x9 inventory grid).
    """
    bonuses = {k: 0.0 for k in _EQUIP_STATS}
    actual_idx = _HOTBAR_OFFSET + hotbar_slot
    if 0 <= hotbar_slot < 9 and actual_idx < len(inventory):
        item_stats = _get_slot_stats(inventory[actual_idx])
        for k in _EQUIP_STATS:
            bonuses[k] += float(item_stats.get(k, 0))
    return bonuses


def is_valid_equip_placement(item_id: int, slot_idx: int) -> bool:
    """Return True if item_id is allowed in equip slot_idx (36-46).

    Items without a slot_type (materials, stackables) are never allowed
    in equip slots.  Weapons are hotbar-only and are also rejected.
    """
    required_type = _EQUIP_SLOT_TYPES.get(slot_idx)
    if required_type is None:
        return True   # not an equip slot, always fine
    item_type = _data.get(item_id, {}).get("slot_type")
    return item_type == required_type


_QUALITY_SELL_MULT = {"Common": 1, "Uncommon": 2, "Rare": 4, "Exquisite": 8}

# ---------------------------------------------------------------------------
# RNG stat rolling — called when giving equipment items
# ---------------------------------------------------------------------------

import random as _random

# Sorted highest-first so the first matching threshold wins.
# Each row: (quality_name, threshold, stat_mult_low, stat_mult_high)
#   Exquisite  3 %  — threshold 0.97
#   Rare      12 %  — threshold 0.85
#   Uncommon  25 %  — threshold 0.60
#   Common    60 %  — threshold 0.00
_ROLL_TIERS = [
    ("Exquisite", 0.97, 1.65, 2.20),
    ("Rare",      0.85, 1.25, 1.65),
    ("Uncommon",  0.60, 1.00, 1.25),
    ("Common",    0.00, 0.85, 1.00),
]


def roll_item_stats(item_id: int) -> dict | None:
    """Roll quality tier and stat values for an equipment item.

    Returns a meta dict ``{"quality": ..., "stats": {...}, "dur": n, "dur_max": n}``
    for non-stackable items that have base stats defined.
    Returns *None* for stackable/material items so they stay as plain [id, qty] slots.
    """
    item_def = _data.get(item_id)
    if not item_def:
        return None
    base_stats = item_def.get("stats", {})
    if not base_stats or item_def.get("stackable", False):
        return None   # only roll for weapons/armor/jewelry

    r = _random.random()
    quality = "Common"
    lo, hi  = 0.85, 1.00
    for q_name, threshold, tlo, thi in _ROLL_TIERS:
        if r >= threshold:
            quality, lo, hi = q_name, tlo, thi
            break

    mult = _random.uniform(lo, hi)
    rolled = {
        k: round(float(v) * mult, 1)
        for k, v in base_stats.items()
        if isinstance(v, (int, float))
    }

    meta: dict = {"quality": quality, "stats": rolled}
    dur = item_def.get("durability")
    if dur:
        meta["dur"]     = int(dur)
        meta["dur_max"] = int(dur)
    return meta


# ---------------------------------------------------------------------------
# Durability helpers
# ---------------------------------------------------------------------------

def drain_durability(inventory: list, slot_idx: int) -> bool:
    """Reduce the durability of the item in *slot_idx* by 1.

    If durability reaches 0 the slot is cleared (item destroyed).
    Returns True if the item was destroyed, False otherwise.
    Items with no durability definition are silently ignored.
    If the slot has no meta yet, durability is lazily initialised from
    the item definition so that items saved before durability was added
    still wear out correctly.
    """
    if slot_idx < 0 or slot_idx >= len(inventory):
        return False
    slot = inventory[slot_idx]
    if slot is None:
        return False
    # Ensure meta dict exists; lazy-init from item definition if needed
    if len(slot) < 3 or not isinstance(slot[2], dict):
        item_def = _data.get(slot[0], {})
        max_dur  = item_def.get("durability")
        if not max_dur:
            return False   # item has no durability — ignore silently
        meta = {"dur": int(max_dur), "dur_max": int(max_dur)}
        if len(slot) < 3:
            slot.append(meta)
        else:
            slot[2] = meta
    meta = slot[2]
    if "dur" not in meta:
        item_def = _data.get(slot[0], {})
        max_dur  = item_def.get("durability")
        if not max_dur:
            return False
        meta["dur"]     = int(max_dur)
        meta["dur_max"] = meta.get("dur_max", int(max_dur))
    meta["dur"] -= 1
    if meta["dur"] <= 0:
        inventory[slot_idx] = None
        return True
    return False


def get_sell_price(slot) -> int:
    """Return the coin value for selling a full inventory slot."""
    if slot is None:
        return 0
    item_id  = slot[0]
    qty      = slot[1]
    base     = _data.get(item_id, {}).get("sell_price", 0)
    meta     = slot[2] if len(slot) >= 3 and isinstance(slot[2], dict) else None
    mult     = _QUALITY_SELL_MULT.get(meta.get("quality", "Common"), 1) if meta else 1
    return base * qty * mult

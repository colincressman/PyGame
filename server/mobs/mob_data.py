"""server/mobs/mob_data.py

Loads all per-mob JSON definitions from data/mobs/ and exposes them as
the MOB_TYPES dict.  This is the single source of truth for mob stats,
spawn rules, and sprite config.  mob_manager.py reads from here instead
of maintaining scattered module-level constants.

Biome name → ID mapping mirrors server/world/resource_nodes.py.
"""
import json
import os

_BIOME_IDS: dict[str, int] = {
    "ocean":      0,
    "beach":      1,
    "swamp":      2,
    "river":      3,
    "plains":     4,
    "forest":     5,
    "desert":     6,
    "alt_desert": 7,
    "tropical":   8,
    "tundra":     9,
    "mountain":   10,
}

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "mobs")
)

MOB_TYPES: dict[str, dict] = {}

for _fname in sorted(os.listdir(_DATA_DIR)):
    if not _fname.endswith(".json"):
        continue
    _mob_type = _fname[:-5]
    with open(os.path.join(_DATA_DIR, _fname), encoding="utf-8") as _f:
        _entry = json.load(_f)
    # Pre-convert biome name list → frozenset of integer IDs
    _entry["biome_ids"] = frozenset(
        _BIOME_IDS[b] for b in _entry.get("spawn_biomes", [])
        if b in _BIOME_IDS
    )
    # Pre-compute squared values used in hot paths
    _entry["aggro_range_sq"]  = _entry.get("aggro_range",  0.0) ** 2
    _entry["flee_range_sq"]   = _entry.get("flee_range",   0.0) ** 2
    _entry["despawn_radius_sq"] = _entry.get("despawn_radius", 50) ** 2
    MOB_TYPES[_mob_type] = _entry

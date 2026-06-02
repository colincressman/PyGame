"""
Biome-driven natural item spawner.

Every SPAWN_INTERVAL seconds the spawner looks at each connected player's
surrounding tiles and seeds floor items matching the local biome.  Items are
spread out (MIN_ITEM_GAP), capped per player radius, and drifted in slowly so
the world never feels cluttered.

Biome IDs  (matches server/world/dyn_chunk_gen.py BIOME_ID_MAP):
  0=ocean  1=beach  2=swamp  3=river  4=plains  5=forest
  6=desert 7=alt_desert 8=tropical 9=tundra 10=mountain
  100-110 = cliff variants (skipped — not in loot table)
"""

import math
import random

from server.game_state.world_items import world_items, world_items_lock, spawn_world_item
from server.shared_lock import players_lock

# ---------------------------------------------------------------------------
# Loot tables — {biome_id: [(item_id, relative_weight), ...]}
#
# Items 3,4,5,6,7,8,9,10,12 are now supplied exclusively by resource nodes
# (Phase 9). The spawner only covers items that have NO node type:
#   bone (11) — desert scavenge; no node type exists for it.
# ---------------------------------------------------------------------------
# bone_pile resource nodes (Phase 9) now handle bone drops in desert biomes.
BIOME_LOOT: dict = {}

SPAWN_RADIUS    = 18    # tiles — circle around each player to consider
MAX_PER_RADIUS  = 12    # ceiling: don't spawn if this many items are already nearby
SPAWN_INTERVAL  = 30.0  # seconds between spawn passes
MIN_ITEM_GAP    = 2.5   # tiles — items must be at least this far apart

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------
_players    = None
_world_data = None
_timer      = 0.0


def set_spawner_refs(refs: dict):
    global _players, _world_data
    _players    = refs["players"]
    _world_data = refs["world_data"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _weighted_choice(table):
    total = sum(w for _, w in table)
    r = random.random() * total
    for item_id, w in table:
        r -= w
        if r <= 0:
            return item_id
    return table[-1][0]


def _count_nearby(px, py):
    rr = SPAWN_RADIUS * SPAWN_RADIUS
    with world_items_lock:
        return sum(
            1 for item in world_items.values()
            if (item["pos"][0] - px) ** 2 + (item["pos"][1] - py) ** 2 <= rr
        )


def _too_close_to_existing(tx, ty):
    gap_sq = MIN_ITEM_GAP * MIN_ITEM_GAP
    with world_items_lock:
        return any(
            (item["pos"][0] - tx) ** 2 + (item["pos"][1] - ty) ** 2 < gap_sq
            for item in world_items.values()
        )


# ---------------------------------------------------------------------------
# Core spawn pass
# ---------------------------------------------------------------------------
def _spawn_pass():
    if not _players or not _world_data:
        return

    with players_lock:
        positions = [list(p.get("pos", [0.0, 0.0])) for p in _players.values()]

    for pos in positions:
        px, py = pos[0], pos[1]

        current = _count_nearby(px, py)
        if current >= MAX_PER_RADIUS:
            continue

        # Trickle in at most 1/3 of the deficit so the world fills gradually
        to_spawn = max(1, (MAX_PER_RADIUS - current) // 3)
        spawned  = 0
        attempts = 0

        while spawned < to_spawn and attempts < 50:
            attempts += 1

            # Pick a random tile within spawn radius, but not too close
            angle = random.random() * 2 * math.pi
            dist  = random.uniform(4.0, SPAWN_RADIUS)
            tx    = int(px + math.cos(angle) * dist)
            ty    = int(py + math.sin(angle) * dist)

            tile = _world_data.get((tx, ty))
            if tile is None:
                continue

            biome_id = tile.get("biome", 0)
            if biome_id not in BIOME_LOOT:
                continue   # ocean, cliffs, etc.

            if _too_close_to_existing(tx, ty):
                continue

            item_id = _weighted_choice(BIOME_LOOT[biome_id])
            spawn_world_item(item_id, [float(tx), float(ty)])
            spawned += 1


# ---------------------------------------------------------------------------
# Public tick — call once per game tick from the main loop
# ---------------------------------------------------------------------------
def spawner_tick(dt: float):
    global _timer
    _timer += dt
    if _timer >= SPAWN_INTERVAL:
        _timer = 0.0
        try:
            _spawn_pass()
        except Exception as e:
            print(f"[SPAWNER ERROR] {e}")

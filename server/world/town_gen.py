"""server/world/town_gen.py

Deterministic procedural town placement with placed-object buildings.
One town per 30×30-chunk grid cell; anchor jittered by a seeded hash.

Town layout (centred at (tx, ty)):
  - 5×5 stone_brick_floor plaza at centre
  - Rectangular road loop around the plaza, with short spurs to each door
  - 4 buildings (5×5 each), arranged at the town corners:
      Merchant   northwest  (tx-8, ty-8)  door S
      Blacksmith northeast  (tx+8, ty-8)  door S
      Healer     southwest  (tx-8, ty+8)  door N
      Innkeeper  southeast  (tx+8, ty+8)  door N
    Each building: stone_brick_wall perimeter, stone_brick_floor interior,
    one door facing the plaza (injected with state="open" so players enter freely).

Buildings are injected into placed_objects once when a player first comes
within NPC_RENDER_DIST.  Subsequent server restarts skip already-occupied
tiles automatically (inject_object is idempotent).
"""

import hashlib
import math

from server.game_state.placed_objects import inject_object as _inject_object
from server.world.npc_shops import get_shop as _get_shop
from server.config import CHUNK_SIZE, TOWN_GRID, NPC_RENDER_DIST

# NPC positions: each NPC stands at their building centre.
# (dx, dy, type, display_name, greeting)
_NPC_OFFSETS = [
    (-8, -8, "merchant",   "Merchant",   "Fine wares for the discerning traveller!"),
    ( 8, -8, "blacksmith", "Blacksmith", "Finest blades this side of the mountains."),
    (-8,  8, "healer",     "Healer",     "I can mend any wound — for a modest fee."),
    ( 8,  8, "innkeeper",  "Innkeeper",  "Rest your weary bones here, friend."),
]


# ── Town anchor maths ────────────────────────────────────────────────────────

def _anchor_for_cell(gx: int, gy: int):
    """Return (anchor_cx, anchor_cy) for grid cell (gx, gy) — deterministic."""
    h  = int(hashlib.md5(f"{gx},{gy}".encode()).hexdigest()[:8], 16)
    jx = (h       % 11) - 5   # uniform in [-5, +5]
    jy = ((h >> 8) % 11) - 5
    return gx * TOWN_GRID + jx, gy * TOWN_GRID + jy


def is_town_chunk(cx: int, cy: int) -> bool:
    """Return True if chunk (cx, cy) is a town-anchor chunk."""
    gx, gy = cx // TOWN_GRID, cy // TOWN_GRID
    return _anchor_for_cell(gx, gy) == (cx, cy)


def get_town_center_tile(cx: int, cy: int):
    """World-tile coords of the town centre given its anchor chunk (cx, cy)."""
    return (cx * CHUNK_SIZE + CHUNK_SIZE // 2,
            cy * CHUNK_SIZE + CHUNK_SIZE // 2)


# ── Building / structure generation ─────────────────────────────────────────

def _building_tiles(cx, cy, door_dir):
    """Yield (tx, ty, obj_type) for a 5×5 building centred at (cx, cy).

    door_dir: 'N' = door on north wall, 'S' = south, 'E' = east, 'W' = west.
    Interior 3×3 → stone_brick_floor.
    Perimeter → stone_brick_wall, except one centre tile → door.
    """
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            yield cx + dx, cy + dy, "stone_brick_floor"
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if -1 <= dx <= 1 and -1 <= dy <= 1:
                continue
            is_door = (
                (door_dir == 'N' and dx == 0 and dy == -2) or
                (door_dir == 'S' and dx == 0 and dy ==  2) or
                (door_dir == 'W' and dy == 0 and dx == -2) or
                (door_dir == 'E' and dy == 0 and dx ==  2)
            )
            yield cx + dx, cy + dy, "door" if is_door else "stone_brick_wall"


def _town_tiles(tx, ty):
    """Yield (tile_x, tile_y, obj_type) for every structure tile in a town.

    Plaza   : 5×5 stone_brick_floor at (tx, ty)
    Roads   : rectangular loop around the plaza, with short spurs to building doors
    Buildings arranged at the town corners:
      Merchant   (tx-8, ty-8)  door S
      Blacksmith (tx+8, ty-8)  door S
      Healer     (tx-8, ty+8)  door N
      Innkeeper  (tx+8, ty+8)  door N
    """
    # Central plaza
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            yield tx + dx, ty + dy, "stone_brick_floor"

    # Road loop around the plaza
    for ax in range(-8, 9):
        yield tx + ax, ty - 3, "stone_brick_floor"
        yield tx + ax, ty + 3, "stone_brick_floor"
    for ay in range(-3, 4):
        yield tx - 8, ty + ay, "stone_brick_floor"
        yield tx + 8, ty + ay, "stone_brick_floor"

    # Door spurs (road → building door)
    for ay in range(-5, -3):
        yield tx - 8, ty + ay, "stone_brick_floor"  # Merchant
        yield tx + 8, ty + ay, "stone_brick_floor"  # Blacksmith
    for ay in range(4, 6):
        yield tx - 8, ty + ay, "stone_brick_floor"  # Healer
        yield tx + 8, ty + ay, "stone_brick_floor"  # Innkeeper

    # Buildings
    yield from _building_tiles(tx - 8, ty - 8, 'S')   # Merchant   (NW)
    yield from _building_tiles(tx + 8, ty - 8, 'S')   # Blacksmith (NE)
    yield from _building_tiles(tx - 8, ty + 8, 'N')   # Healer     (SW)
    yield from _building_tiles(tx + 8, ty + 8, 'N')   # Innkeeper  (SE)


# ── Build-once system ────────────────────────────────────────────────────────

_built_towns: set = set()   # (acx, acy) pairs already built this server run


def _build_town(acx: int, acy: int) -> None:
    """Inject all town structure tiles.  Idempotent — occupied tiles skipped."""
    if (acx, acy) in _built_towns:
        return
    tx, ty = get_town_center_tile(acx, acy)
    seen: set = set()
    count: int = 0
    for wx, wy, obj_type in _town_tiles(tx, ty):
        if (wx, wy) not in seen:
            seen.add((wx, wy))
            if _inject_object(obj_type, wx, wy):
                count += 1
    _built_towns.add((acx, acy))
    if count > 0:
        print(f"[TOWN] Built town at anchor ({acx},{acy}) tile ({tx},{ty})"
              f" — {count} objects placed.")


def ensure_towns_near(px: float, py: float, dist: float = NPC_RENDER_DIST) -> None:
    """Build any unbuilt town structures within *dist* tiles of (px, py).

    Safe to call per-player per chunk-change — returns immediately for
    already-built towns via the _built_towns set check.
    """
    cell_size = TOWN_GRID * CHUNK_SIZE
    gx0 = int(px) // cell_size
    gy0 = int(py) // cell_size
    for dgx in range(-2, 3):
        for dgy in range(-2, 3):
            gx, gy   = gx0 + dgx, gy0 + dgy
            acx, acy = _anchor_for_cell(gx, gy)
            if (acx, acy) in _built_towns:
                continue
            ttx, tty = get_town_center_tile(acx, acy)
            if math.sqrt((ttx - px) ** 2 + (tty - py) ** 2) <= dist:
                _build_town(acx, acy)


# ── NPC list for state packets ───────────────────────────────────────────────

def get_npcs_near(px: float, py: float, dist: float = NPC_RENDER_DIST):
    """Return a list of NPC dicts for all NPCs within *dist* tiles of (px, py).

    Each dict: {id, type, name, greeting, pos: [wx, wy]}.
    """
    cell_size = TOWN_GRID * CHUNK_SIZE
    gx0       = int(px) // cell_size
    gy0       = int(py) // cell_size
    npcs = []
    for dgx in range(-2, 3):
        for dgy in range(-2, 3):
            gx, gy   = gx0 + dgx, gy0 + dgy
            acx, acy = _anchor_for_cell(gx, gy)
            tx, ty   = get_town_center_tile(acx, acy)
            for dx, dy, npc_type, name, greeting in _NPC_OFFSETS:
                wx, wy = tx + dx, ty + dy
                if math.sqrt((wx - px) ** 2 + (wy - py) ** 2) <= dist:
                    npcs.append({
                        "id":       f"{npc_type}_{acx}_{acy}",
                        "type":     npc_type,
                        "name":     name,
                        "greeting": greeting,
                        "pos":      [wx, wy],
                        "shop":     _get_shop(npc_type),
                    })
    return npcs

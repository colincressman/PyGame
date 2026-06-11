"""server/world/dungeon_gen.py

Deterministic Slime Lair placement — one dungeon per DUNGEON_GRID×DUNGEON_GRID
chunk grid cell, anchored at the cell centre.

Structure layout (centred at world tile (tx, ty)):

  WWWWWWWWWWWWWWW   ← dy = −6   (north wall)
  W             W
  W  P       P  W   ← dy = −3   P = stone_brick_wall pillar
  W             W
  W      ★      W   ← dy =  0   ★ = boss spawn point (dungeon centre)
  W             W
  W  P       P  W   ← dy = +3
  W             W
  W             W
  WWWWW   WWWWWWW   ← dy = +6   (south wall; 3-tile entrance gap at centre)

  Width  = 15 tiles (dx −7 … +7)
  Height = 13 tiles (dy −6 … +6)
  Interior floor covers dx −6…+6, dy −5…+5.

Boss spawns at the dungeon centre when a player steps within DUNGEON_TRIGGER_DIST
tiles.  After the boss is defeated the dungeon enters a cooldown before it can
be re-entered.
"""
import math

from server.game_state.placed_objects import inject_object as _inject_object
from server.config import CHUNK_SIZE, DUNGEON_GRID, DUNGEON_TRIGGER_DIST, BOSS_RESPAWN_DELAY

# Per-lair state (server runtime only — not persisted across restarts)
_built_dungeons: set  = set()   # {(anchor_cx, anchor_cy)} structures already injected
_cooldown_until: dict = {}      # (anchor_cx, anchor_cy) → float UNIX timestamp

_ENTRANCE_DX = frozenset({-1, 0, 1})  # tiles in south wall that are left open


# ---------------------------------------------------------------------------
# Anchor maths
# ---------------------------------------------------------------------------

def get_dungeon_anchor(gx: int, gy: int) -> tuple:
    """Return (anchor_cx, anchor_cy) chunk coords for dungeon grid cell (gx, gy)."""
    return (gx * DUNGEON_GRID + DUNGEON_GRID // 2,
            gy * DUNGEON_GRID + DUNGEON_GRID // 2)


def get_dungeon_center_tile(acx: int, acy: int) -> tuple:
    """World-tile centre for the dungeon whose anchor chunk is (acx, acy)."""
    return (acx * CHUNK_SIZE + CHUNK_SIZE // 2,
            acy * CHUNK_SIZE + CHUNK_SIZE // 2)


def get_built_dungeons() -> list[dict]:
    """Return summary data for all dungeons built during this server runtime."""
    dungeons = []
    for acx, acy in sorted(_built_dungeons):
        tx, ty = get_dungeon_center_tile(acx, acy)
        dungeons.append({
            "id": f"{acx}_{acy}",
            "anchor": [acx, acy],
            "pos": [tx, ty],
        })
    return dungeons


def get_dungeon_structure_tiles_in_chunk(cx: int, cy: int) -> set[tuple[int, int]]:
    """Return all deterministic dungeon structure tiles that overlap chunk (cx, cy)."""
    min_tx = cx * CHUNK_SIZE
    min_ty = cy * CHUNK_SIZE
    max_tx = min_tx + CHUNK_SIZE - 1
    max_ty = min_ty + CHUNK_SIZE - 1
    result: set[tuple[int, int]] = set()
    gx0 = cx // DUNGEON_GRID
    gy0 = cy // DUNGEON_GRID
    for dgx in range(-1, 2):
        for dgy in range(-1, 2):
            acx, acy = get_dungeon_anchor(gx0 + dgx, gy0 + dgy)
            tx, ty = get_dungeon_center_tile(acx, acy)
            for wx, wy, _obj_type in _dungeon_tiles(tx, ty):
                if min_tx <= wx <= max_tx and min_ty <= wy <= max_ty:
                    result.add((wx, wy))
    return result


# ---------------------------------------------------------------------------
# Structure generation
# ---------------------------------------------------------------------------

def _dungeon_tiles(tx: int, ty: int):
    """Yield (wx, wy, obj_type) for every structure tile of the lair."""
    W, H = 7, 6   # half-extents of the outer shell

    # Interior floor (all tiles inside the perimeter)
    for dx in range(-W + 1, W):
        for dy in range(-H + 1, H):
            yield tx + dx, ty + dy, "stone_brick_floor"

    # North wall (full)
    for dx in range(-W, W + 1):
        yield tx + dx, ty - H, "stone_brick_wall"

    # South wall (3-tile entrance gap at centre)
    for dx in range(-W, W + 1):
        if dx not in _ENTRANCE_DX:
            yield tx + dx, ty + H, "stone_brick_wall"

    # West and east walls (excluding corners already placed above)
    for dy in range(-H + 1, H):
        yield tx - W, ty + dy, "stone_brick_wall"
        yield tx + W, ty + dy, "stone_brick_wall"

    # Four inner pillars — break line-of-sight, give the boss room to hide
    for ppx, ppy in ((tx - 4, ty - 3), (tx + 4, ty - 3),
                     (tx - 4, ty + 3), (tx + 4, ty + 3)):
        yield ppx, ppy, "stone_brick_wall"


def _build_dungeon(acx: int, acy: int) -> None:
    """Inject all structure tiles for the dungeon at anchor (acx, acy)."""
    if (acx, acy) in _built_dungeons:
        return
    tx, ty = get_dungeon_center_tile(acx, acy)
    seen: set = set()
    count = 0
    for wx, wy, obj_type in _dungeon_tiles(tx, ty):
        if (wx, wy) not in seen:
            seen.add((wx, wy))
            if _inject_object(obj_type, wx, wy, placed_by="dungeon"):
                count += 1
    _built_dungeons.add((acx, acy))
    print(f"[DUNGEON] Slime Lair built at chunk ({acx},{acy}) "
          f"tile ({tx},{ty}) — {count} objects placed.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_dungeons_near(px: float, py: float, dist: float = 200.0) -> None:
    """Build any unbuilt Slime Lairs within *dist* tiles of (px, py).

    Safe to call per-player per chunk-change; returns immediately for already-
    built lairs via the _built_dungeons set check.
    """
    cell_size = DUNGEON_GRID * CHUNK_SIZE
    gx0 = int(px) // cell_size
    gy0 = int(py) // cell_size
    for dgx in range(-2, 3):
        for dgy in range(-2, 3):
            gx, gy   = gx0 + dgx, gy0 + dgy
            acx, acy = get_dungeon_anchor(gx, gy)
            if (acx, acy) in _built_dungeons:
                continue
            ttx, tty = get_dungeon_center_tile(acx, acy)
            if math.sqrt((ttx - px) ** 2 + (tty - py) ** 2) <= dist:
                _build_dungeon(acx, acy)


def get_dungeons_near(px: float, py: float, dist: float = 200.0) -> list:
    """Return dungeon info dicts for all lairs within *dist* tiles of (px, py).

    Each dict: {"id": str, "pos": [tx, ty]}.
    Only built lairs are returned so the client knows the structure exists.
    """
    cell_size = DUNGEON_GRID * CHUNK_SIZE
    gx0 = int(px) // cell_size
    gy0 = int(py) // cell_size
    result = []
    for dgx in range(-2, 3):
        for dgy in range(-2, 3):
            gx, gy   = gx0 + dgx, gy0 + dgy
            acx, acy = get_dungeon_anchor(gx, gy)
            if (acx, acy) not in _built_dungeons:
                continue
            ttx, tty = get_dungeon_center_tile(acx, acy)
            if math.sqrt((ttx - px) ** 2 + (tty - py) ** 2) <= dist:
                result.append({"id": f"{acx}_{acy}", "pos": [ttx, tty]})
    return result


def check_boss_trigger(px: float, py: float, now: float) -> list:
    """Return list of dungeon centre positions [tx, ty] that should spawn the boss.

    A position is returned only when:
      1. The lair has been built (player has explored near it).
      2. The player is within DUNGEON_TRIGGER_DIST tiles of the centre.
      3. The boss cooldown has expired.

    The caller is responsible for the actual spawn call (to serialise with
    mobs_lock and avoid duplicates when multiple players enter simultaneously).
    """
    cell_size = DUNGEON_GRID * CHUNK_SIZE
    gx0 = int(px) // cell_size
    gy0 = int(py) // cell_size
    triggers = []
    for dgx in range(-1, 2):
        for dgy in range(-1, 2):
            gx, gy   = gx0 + dgx, gy0 + dgy
            acx, acy = get_dungeon_anchor(gx, gy)
            if (acx, acy) not in _built_dungeons:
                continue
            ttx, tty = get_dungeon_center_tile(acx, acy)
            dsq = (px - ttx) ** 2 + (py - tty) ** 2
            if dsq <= DUNGEON_TRIGGER_DIST ** 2:
                if now >= _cooldown_until.get((acx, acy), 0.0):
                    triggers.append([float(ttx), float(tty)])
    return triggers


def set_boss_cooldown(dungeon_pos: list, until: float) -> None:
    """Record a respawn cooldown for the lair whose centre is dungeon_pos."""
    tx, ty   = int(dungeon_pos[0]), int(dungeon_pos[1])
    gx       = (tx // CHUNK_SIZE) // DUNGEON_GRID
    gy       = (ty // CHUNK_SIZE) // DUNGEON_GRID
    acx, acy = get_dungeon_anchor(gx, gy)
    _cooldown_until[(acx, acy)] = until
    print(f"[DUNGEON] Lair ({acx},{acy}) boss cooldown set — ready again in "
          f"{BOSS_RESPAWN_DELAY:.0f}s.")

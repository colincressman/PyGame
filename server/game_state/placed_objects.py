"""server/game_state/placed_objects.py

Player-placeable world objects: campfire, crafting_table, furnace.
Persisted to world_chunks_v3/placed_objects.json every 10 s (dirty-flag buffer)
and on graceful shutdown.  Mutations mark the dirty flag; a background thread
flushes periodically so individual operations don't thrash the disk.
"""

import json
import os
import threading
import time
import uuid

from server.shared_lock import placed_objects_lock
from server.item_data import get_effective_health_max, get_item as _get_item
from server.config import CHUNK_DIR as _CHUNK_DIR, RENDER_DIST_TILES as _RENDER_DIST_TILES
from server.game_state.placeable_data import (
    FLOOR_TYPES as _FLOOR_TYPES,
    GROWS_INTO,
    GROW_TIMES,
    ITEM_FOR_TYPE,
    PLACEABLE_ITEMS,
    SOLID_TYPES,
)

# {uid: {"type": str, "pos": [tx, ty], "placed_by": pid}}
placed_objects: dict = {}

# Fast tile-occupancy index: (tx, ty) → uid.  Kept in sync with placed_objects.
# Allows O(1) "is this tile taken?" check instead of O(n) scan.
# Non-floor objects (walls, furniture, etc.)
_tile_index: dict[tuple[int, int], str] = {}
# Floor objects only (stone_brick_floor) — separate layer so furniture can be
# placed on top of floors without "tile occupied" rejection.
_floor_index: dict[tuple[int, int], str] = {}

_SAVE_PATH = os.path.join(_CHUNK_DIR, "placed_objects.json")
_dirty = False
_FLUSH_INTERVAL = 10.0  # seconds between disk writes

# Revision counter bumped whenever a solid/floor object is added, removed, or toggled.
# mob_manager reads this to know when to rebuild its cached solid tile set.
_solid_revision: int = 0


def get_solid_revision() -> int:
    """Return a monotonically-increasing counter; changes whenever solids change."""
    return _solid_revision


def _bump_solid_revision() -> None:
    global _solid_revision
    _solid_revision += 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load():
    global placed_objects, _tile_index, _floor_index
    try:
        with open(_SAVE_PATH) as f:
            placed_objects = json.load(f)
        # Rebuild both indices from loaded data
        _tile_index = {
            (obj["pos"][0], obj["pos"][1]): uid
            for uid, obj in placed_objects.items()
            if obj["type"] not in _FLOOR_TYPES
        }
        _floor_index = {
            (obj["pos"][0], obj["pos"][1]): uid
            for uid, obj in placed_objects.items()
            if obj["type"] in _FLOOR_TYPES
        }
        print(f"[PLACED] Loaded {len(placed_objects)} placed objects.")
    except FileNotFoundError:
        placed_objects = {}
        _tile_index = {}
        _floor_index = {}
    except Exception as e:
        print(f"[PLACED] Load error: {e}")
        placed_objects = {}
        _tile_index = {}
        _floor_index = {}


def _save():
    global _dirty
    try:
        os.makedirs(os.path.dirname(_SAVE_PATH), exist_ok=True)
        with open(_SAVE_PATH, "w") as f:
            json.dump(placed_objects, f)
        _dirty = False
    except Exception as e:
        print(f"[PLACED] Save error: {e}")


def _mark_dirty() -> None:
    """Flag that placed_objects needs to be flushed.  The background thread handles it."""
    global _dirty
    _dirty = True


def flush_now() -> None:
    """Force an immediate disk write regardless of the dirty flag (e.g. on shutdown)."""
    with placed_objects_lock:
        _save()


def _autosave_loop() -> None:
    while True:
        time.sleep(_FLUSH_INTERVAL)
        if _dirty:
            with placed_objects_lock:
                _save()


_autosave_thread = threading.Thread(target=_autosave_loop, daemon=True, name="placed-autosave")
_autosave_thread.start()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_nearby(px: float, py: float, radius_sq: float = float(_RENDER_DIST_TILES ** 2)) -> list:
    """Return list of placed objects within radius_sq tile-distance of (px, py)."""
    with placed_objects_lock:
        return [
            dict(obj, uid=uid)
            for uid, obj in placed_objects.items()
            if (obj["pos"][0] - px) ** 2 + (obj["pos"][1] - py) ** 2 <= radius_sq
        ]


# ---------------------------------------------------------------------------
# Mutators  (caller must already hold players_lock for inventory changes)
# ---------------------------------------------------------------------------

def place_object(pid: str, obj_type: str, pos: list, inventory: list) -> tuple:
    """Remove placeable item from inventory and add to world.

    Returns (True, uid) on success, (False, reason_str) on failure.
    Caller is responsible for calling mark_inventory_dirty(pid) afterwards.
    """
    item_id = ITEM_FOR_TYPE.get(obj_type)
    if item_id is None:
        return False, "unknown type"

    # Find item in bag slots
    found = -1
    for i, slot in enumerate(inventory[:36]):
        if slot is not None and slot[0] == item_id:
            found = i
            break
    if found == -1:
        return False, "no item in inventory"

    tx, ty = int(pos[0]), int(pos[1])

    # O(1) occupancy check via tile index (floors and objects use separate layers)
    with placed_objects_lock:
        is_floor = obj_type in _FLOOR_TYPES
        if is_floor:
            if (tx, ty) in _floor_index:
                return False, "tile occupied"
        else:
            if (tx, ty) in _tile_index:
                return False, "tile occupied"

        # Consume item from inventory
        slot = inventory[found]
        if slot[1] > 1:
            inventory[found] = [slot[0], slot[1] - 1]
        else:
            inventory[found] = None

        uid = str(uuid.uuid4())[:8]
        entry = {"type": obj_type, "pos": [tx, ty], "placed_by": pid}
        if obj_type == "door":
            entry["state"] = "closed"
        elif obj_type == "chest":
            entry["chest_inv"] = [None] * 27
        elif obj_type in GROW_TIMES:
            entry["planted_at"] = time.time()
            entry["grow_time"]  = GROW_TIMES[obj_type]
        placed_objects[uid] = entry
        if is_floor:
            _floor_index[(tx, ty)] = uid
        else:
            _tile_index[(tx, ty)] = uid
        _mark_dirty()
        _bump_solid_revision()

    return True, uid


def inject_object(obj_type: str, tx: int, ty: int, placed_by: str = "town") -> bool:
    """Directly inject a placed object into the world without inventory checks.

    Idempotent — silently skips if the tile is already occupied.
    Returns True if the object was placed, False if the tile was taken.
    Used by procedural systems (town generation, etc.).
    """
    with placed_objects_lock:
        is_floor = (obj_type in _FLOOR_TYPES)
        if is_floor:
            if (tx, ty) in _floor_index:
                return False
        else:
            if (tx, ty) in _tile_index:
                return False
        uid = str(uuid.uuid4())[:8]
        entry = {"type": obj_type, "pos": [tx, ty], "placed_by": placed_by}
        if obj_type == "door":
            entry["state"] = "open"   # town doors start open so players can enter
        placed_objects[uid] = entry
        if is_floor:
            _floor_index[(tx, ty)] = uid
        else:
            _tile_index[(tx, ty)] = uid
        _mark_dirty()
        _bump_solid_revision()
    return True


def remove_object(uid: str, inventory: list, pid: str) -> bool:
    """Remove a placed object and return its item to the owner's inventory.

    Returns True on success.
    Caller must hold players_lock and call mark_inventory_dirty(pid) afterwards.
    """
    with placed_objects_lock:
        obj = placed_objects.get(uid)
        if obj is None:
            return False
        if obj["placed_by"] != pid:
            return False
        # Block pickup of a chest that still contains items
        if obj.get("type") == "chest":
            chest_inv = obj.get("chest_inv", [])
            if any(slot is not None for slot in chest_inv):
                return False

        item_id = ITEM_FOR_TYPE.get(obj["type"])
        tx, ty = obj["pos"][0], obj["pos"][1]
        del placed_objects[uid]
        if obj["type"] in _FLOOR_TYPES:
            _floor_index.pop((tx, ty), None)
        else:
            _tile_index.pop((tx, ty), None)
        _mark_dirty()
        _bump_solid_revision()

    # Return item to inventory: stack with existing slot first, then find empty slot
    if item_id is not None:
        for i in range(36):
            if inventory[i] is not None and inventory[i][0] == item_id:
                inventory[i] = [item_id, inventory[i][1] + 1]
                break
        else:
            for i in range(36):
                if inventory[i] is None:
                    inventory[i] = [item_id, 1]
                    break

    return True


_load()


# ---------------------------------------------------------------------------
# Farming tick
# ---------------------------------------------------------------------------

def tick_growing_plants(now: float) -> list[dict]:
    """Check all placed seeds/saplings; remove those that have matured.

    Returns a list of dicts: [{"node_type": str, "wx": int, "wy": int}]
    for each plant that just matured so the caller can register a planted node.
    """
    matured = []
    with placed_objects_lock:
        for uid, obj in list(placed_objects.items()):
            gt = obj.get("grow_time")
            pa = obj.get("planted_at")
            if gt is None or pa is None:
                continue
            if now - pa >= gt:
                node_type = GROWS_INTO.get(obj["type"])
                if node_type:
                    tx, ty = obj["pos"]
                    matured.append({"node_type": node_type, "wx": tx, "wy": ty})
                del placed_objects[uid]
                _tile_index.pop((obj["pos"][0], obj["pos"][1]), None)
        if matured:
            _mark_dirty()
    return matured


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------

def chest_swap(uid: str, chest_slot: int, player_inv: list, player_slot: int, player_pos: list, merge_dest: str | None = None) -> bool:
    """Swap (or merge) item between a chest slot and a player inventory slot.

    merge_dest: "player" → merge result into player_slot; "chest" → into chest_slot.
    Caller must hold players_lock before calling.  Returns True on success.
    """
    if not isinstance(player_inv, list) or len(player_inv) <= player_slot:
        return False
    if not isinstance(player_pos, list) or len(player_pos) != 2:
        return False
    px, py = player_pos
    with placed_objects_lock:
        obj = placed_objects.get(uid)
        if obj is None or obj.get("type") != "chest":
            return False
        dx = obj["pos"][0] - px
        dy = obj["pos"][1] - py
        if dx * dx + dy * dy > 25.0:   # must be within 5 tiles
            return False
        inv = obj.setdefault("chest_inv", [None] * 27)
        while len(inv) < 27:
            inv.append(None)
        if not (0 <= chest_slot < 27 and 0 <= player_slot < 45):
            return False
        c_item = inv[chest_slot]
        p_item = player_inv[player_slot]
        # Merge stacks when both hold the same stackable item
        if (merge_dest is not None and c_item is not None and p_item is not None
                and c_item[0] == p_item[0]):
            idata = _get_item(c_item[0])
            if idata.get("stackable", False):
                max_stk  = idata.get("max_stack", 64)
                combined = c_item[1] + p_item[1]
                if combined <= max_stk:
                    if merge_dest == "player":
                        player_inv[player_slot] = [c_item[0], combined]
                        inv[chest_slot]         = None
                    else:
                        inv[chest_slot]         = [c_item[0], combined]
                        player_inv[player_slot] = None
                else:
                    if merge_dest == "player":
                        player_inv[player_slot] = [c_item[0], max_stk]
                        inv[chest_slot]         = [c_item[0], combined - max_stk]
                    else:
                        inv[chest_slot]         = [c_item[0], max_stk]
                        player_inv[player_slot] = [c_item[0], combined - max_stk]
                _mark_dirty()
                return True
        inv[chest_slot]          = p_item
        player_inv[player_slot]  = c_item
        _mark_dirty()
    return True

def toggle_door(uid: str) -> str | None:
    """Toggle a door between open and closed. Returns new state, or None if not found."""
    with placed_objects_lock:
        obj = placed_objects.get(uid)
        if obj is None or obj.get("type") != "door":
            return None
        new_state = "open" if obj.get("state", "closed") == "closed" else "closed"
        obj["state"] = new_state
        _mark_dirty()
        _bump_solid_revision()
    return new_state


def use_bed(uid: str, pid: str, players: dict) -> bool:
    """Set the player's bed_spawn and restore full health. Returns True on success."""
    with placed_objects_lock:
        obj = placed_objects.get(uid)
        if obj is None or obj.get("type") != "bed":
            return False
        pos = list(obj["pos"])
    # Update player outside placed_objects_lock to avoid lock inversion
    if pid in players:
        players[pid]["bed_spawn"] = pos
        players[pid]["health"] = get_effective_health_max(players[pid])
        return True
    return False

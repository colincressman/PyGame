import atexit
import json
import os
import threading
import time
import uuid

from server.config import CHUNK_DIR as _CHUNK_DIR
from server.config import CHUNK_SIZE as _CHUNK_SIZE
from server.config import WORLD_ITEM_DESPAWN_SECONDS as _WORLD_ITEM_DESPAWN_SECONDS
from server.shared_lock import players_lock, world_items_lock

world_items = {}        # {uid: {"item_id": int, "pos": [x, y], "qty": int}}
_item_cells: dict[tuple[int, int], set[str]] = {}
_PERSIST_PATH = os.path.join(_CHUNK_DIR, "world_items.json")
_persist_write_lock = threading.Lock()

_PICKUP_RADIUS_SQ = 1.0

_players = None


def set_world_items_refs(refs):
    global _players
    _players = refs["players"]


def _cell_for_pos(pos: list[float]) -> tuple[int, int]:
    return int(pos[0]) // _CHUNK_SIZE, int(pos[1]) // _CHUNK_SIZE


def _index_item(uid: str, item: dict) -> None:
    _item_cells.setdefault(_cell_for_pos(item["pos"]), set()).add(uid)


def _deindex_item(uid: str, item: dict | None) -> None:
    if item is None:
        return
    cell = _cell_for_pos(item["pos"])
    cell_items = _item_cells.get(cell)
    if cell_items is None:
        return
    cell_items.discard(uid)
    if not cell_items:
        _item_cells.pop(cell, None)


def _snapshot_world_items() -> dict[str, dict]:
    with world_items_lock:
        return {
            uid: {
                "item_id": int(item["item_id"]),
                "pos": [float(item["pos"][0]), float(item["pos"][1])],
                "qty": int(item["qty"]),
                "spawned_at": float(item.get("spawned_at", time.time())),
            }
            for uid, item in world_items.items()
        }


def _replace_world_items(snapshot: dict[str, dict]) -> None:
    with world_items_lock:
        world_items.clear()
        _item_cells.clear()
        for uid, item in snapshot.items():
            world_items[uid] = item
            _index_item(uid, item)


def load_persistence() -> None:
    try:
        with open(_PERSIST_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return
    except Exception as exc:
        print(f"[WORLD ITEMS] load error: {exc}")
        return

    snapshot: dict[str, dict] = {}
    if isinstance(raw, dict):
        entries = raw.items()
    elif isinstance(raw, list):
        entries = (
            (entry.get("uid"), entry)
            for entry in raw
            if isinstance(entry, dict)
        )
    else:
        entries = ()

    for uid, entry in entries:
        if not uid or not isinstance(entry, dict):
            continue
        pos = entry.get("pos")
        if not isinstance(pos, list) or len(pos) != 2:
            continue
        try:
            snapshot[str(uid)] = {
                "item_id": int(entry["item_id"]),
                "pos": [float(pos[0]), float(pos[1])],
                "qty": max(1, int(entry.get("qty", 1))),
                "spawned_at": float(entry.get("spawned_at", time.time())),
            }
        except (KeyError, TypeError, ValueError):
            continue

    _replace_world_items(snapshot)


def save_persistence_sync() -> None:
    snapshot = _snapshot_world_items()
    tmp_path = _PERSIST_PATH + ".tmp"
    try:
        with _persist_write_lock:
            os.makedirs(_CHUNK_DIR, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle)
            os.replace(tmp_path, _PERSIST_PATH)
    except Exception as exc:
        print(f"[WORLD ITEMS] save error: {exc}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def save_persistence_async() -> None:
    snapshot = _snapshot_world_items()

    def _write() -> None:
        tmp_path = _PERSIST_PATH + ".tmp"
        try:
            with _persist_write_lock:
                os.makedirs(_CHUNK_DIR, exist_ok=True)
                with open(tmp_path, "w", encoding="utf-8") as handle:
                    json.dump(snapshot, handle)
                os.replace(tmp_path, _PERSIST_PATH)
        except Exception as exc:
            print(f"[WORLD ITEMS] save error: {exc}")
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    threading.Thread(target=_write, daemon=False, name="world-items-persist").start()


def get_nearby_items(px: float, py: float, radius_sq: float) -> list[dict]:
    radius_tiles = int(radius_sq ** 0.5) + 1
    radius_chunks = radius_tiles // _CHUNK_SIZE + 1
    base_cell = (int(px) // _CHUNK_SIZE, int(py) // _CHUNK_SIZE)
    nearby: list[dict] = []
    seen: set[str] = set()
    with world_items_lock:
        for dcx in range(-radius_chunks, radius_chunks + 1):
            for dcy in range(-radius_chunks, radius_chunks + 1):
                for uid in _item_cells.get((base_cell[0] + dcx, base_cell[1] + dcy), ()):
                    if uid in seen:
                        continue
                    item = world_items.get(uid)
                    if item is None:
                        continue
                    dx = item["pos"][0] - px
                    dy = item["pos"][1] - py
                    if dx * dx + dy * dy <= radius_sq:
                        nearby.append({
                            "uid": uid,
                            "item_id": item["item_id"],
                            "pos": item["pos"],
                            "qty": item["qty"],
                        })
                        seen.add(uid)
    return nearby


def spawn_world_item(item_id, pos, qty=1):
    """Add a dropped item to the world. Returns the assigned uid."""
    uid = str(uuid.uuid4())[:8]
    now = time.time()
    with world_items_lock:
        world_items[uid] = {"item_id": item_id, "pos": list(pos), "qty": qty, "spawned_at": now}
        _index_item(uid, world_items[uid])
    save_persistence_async()
    return uid


def prune_expired_items(now: float | None = None, lifetime: float = _WORLD_ITEM_DESPAWN_SECONDS) -> list[str]:
    if now is None:
        now = time.time()
    expired: list[str] = []
    with world_items_lock:
        for uid, item in list(world_items.items()):
            spawned_at = float(item.get("spawned_at", now))
            if now - spawned_at < lifetime:
                continue
            _deindex_item(uid, item)
            world_items.pop(uid, None)
            expired.append(uid)
    if expired:
        save_persistence_async()
    return expired


def _add_to_inventory(inventory, item_id, qty):
    """Stack qty of item_id into inventory in-place."""
    for i, slot in enumerate(inventory):
        if slot is not None and slot[0] == item_id and slot[1] < 99:
            can_add = min(qty, 99 - slot[1])
            inventory[i][1] += can_add
            qty -= can_add
            if qty <= 0:
                return
    for i, slot in enumerate(inventory):
        if slot is None:
            take = min(qty, 99)
            inventory[i] = [item_id, take]
            qty -= take
            if qty <= 0:
                return


def pickup_tick():
    """Check player positions against world items and award any pickups. Call once per game tick."""
    from server.game_state.game_sync import mark_inventory_dirty

    prune_expired_items()

    with players_lock:
        player_list = [
            (pid, list(pdata.get("pos", [0, 0])))
            for pid, pdata in _players.items()
        ]

    pickups = []   # [(uid, pid, item_id, qty)]
    with world_items_lock:
        claimed = set()
        for pid, pos in player_list:
            base_cell = _cell_for_pos(pos)
            for dcx in (-1, 0, 1):
                for dcy in (-1, 0, 1):
                    for uid in tuple(_item_cells.get((base_cell[0] + dcx, base_cell[1] + dcy), ())):
                        if uid in claimed:
                            continue
                        item = world_items.get(uid)
                        if item is None:
                            continue
                        ix, iy = item["pos"]
                        dx = pos[0] - ix
                        dy = pos[1] - iy
                        if dx * dx + dy * dy <= _PICKUP_RADIUS_SQ:
                            pickups.append((uid, pid, item["item_id"], item["qty"]))
                            claimed.add(uid)
        # Remove collected items while holding the lock so clients never see a claimed-but-not-removed drop.
        for uid, _, _, _ in pickups:
            _deindex_item(uid, world_items.get(uid))
            world_items.pop(uid, None)

    if not pickups:
        return

    save_persistence_async()

    _COIN_ITEM_ID = 1
    dirty_players: set[str] = set()
    with players_lock:
        for uid, pid, item_id, qty in pickups:
            if pid in _players:
                if item_id == _COIN_ITEM_ID:
                    _players[pid]["coins"] = _players[pid].get("coins", 0) + qty
                    print(f"[PICKUP] {pid} collected {qty} coin(s) (wallet: {_players[pid]['coins']})")
                else:
                    _add_to_inventory(_players[pid]["inventory"], item_id, qty)
                    print(f"[PICKUP] {pid} picked up {qty}x item {item_id}")
                dirty_players.add(pid)
        for pid in dirty_players:
            mark_inventory_dirty(pid)


def handle_player_pickup(player_id: str, uid: str) -> bool:
    """Explicit pickup request from a client click/key-press.
    Returns True if the item was successfully picked up."""
    from server.game_state.game_sync import mark_inventory_dirty

    _EXPLICIT_RADIUS_SQ = 2.5 * 2.5

    with players_lock:
        player = _players.get(player_id)
        if player is None:
            return False
        pos = list(player.get("pos", [0, 0]))

    with world_items_lock:
        item = world_items.get(uid)
        if item is None:
            return False
        ix, iy = item["pos"]
        dx = pos[0] - ix
        dy = pos[1] - iy
        if dx * dx + dy * dy > _EXPLICIT_RADIUS_SQ:
            return False
        item_id = item["item_id"]
        qty = item["qty"]
        _deindex_item(uid, item)
        del world_items[uid]

    _COIN_ITEM_ID = 1
    with players_lock:
        if player_id not in _players:
            with world_items_lock:
                world_items[uid] = {"item_id": item_id, "pos": [ix, iy], "qty": qty}
                _index_item(uid, world_items[uid])
            save_persistence_async()
            return False
        if item_id == _COIN_ITEM_ID:
            _players[player_id]["coins"] = _players[player_id].get("coins", 0) + qty
        else:
            _add_to_inventory(_players[player_id]["inventory"], item_id, qty)
        mark_inventory_dirty(player_id)

    save_persistence_async()
    return True


load_persistence()
atexit.register(save_persistence_sync)

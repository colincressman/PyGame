import uuid
import threading
from server.shared_lock import players_lock, world_items_lock  # world_items_lock defined in shared_lock
from server.config import CHUNK_SIZE as _CHUNK_SIZE

world_items = {}        # {uid: {"item_id": int, "pos": [x, y], "qty": int}}
# world_items_lock imported from server.shared_lock
_item_cells: dict[tuple[int, int], set[str]] = {}

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
    with world_items_lock:
        world_items[uid] = {"item_id": item_id, "pos": list(pos), "qty": qty}
        _index_item(uid, world_items[uid])
    return uid


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
        # Remove collected items NOW while still holding the lock — eliminates the
        # window where send_game_state could include a "claimed but not yet removed"
        # item, which caused the client-side ghost/flicker effect.
        for uid, _, _, _ in pickups:
            _deindex_item(uid, world_items.get(uid))
            world_items.pop(uid, None)

    if not pickups:
        return

    # Apply inventory / wallet changes (items already removed from world above)
    _COIN_ITEM_ID = 1
    with players_lock:
        for uid, pid, item_id, qty in pickups:
            if pid in _players:
                if item_id == _COIN_ITEM_ID:
                    _players[pid]["coins"] = _players[pid].get("coins", 0) + qty
                    print(f"[PICKUP] {pid} collected {qty} coin(s) (wallet: {_players[pid]['coins']})")
                else:
                    _add_to_inventory(_players[pid]["inventory"], item_id, qty)
                    print(f"[PICKUP] {pid} picked up {qty}x item {item_id}")
                mark_inventory_dirty(pid)


def handle_player_pickup(player_id: str, uid: str) -> bool:
    """Explicit pickup request from a client click/key-press.
    Returns True if the item was successfully picked up."""
    from server.game_state.game_sync import mark_inventory_dirty
    _EXPLICIT_RADIUS_SQ = 2.5 * 2.5   # slightly more lenient than auto-pickup (1 tile)

    with players_lock:
        player = _players.get(player_id)
        if player is None:
            return False
        pos = list(player.get("pos", [0, 0]))

    with world_items_lock:
        item = world_items.get(uid)
        if item is None:
            return False   # already picked up by someone else
        ix, iy = item["pos"]
        dx = pos[0] - ix
        dy = pos[1] - iy
        if dx * dx + dy * dy > _EXPLICIT_RADIUS_SQ:
            return False   # too far away
        # Remove immediately while holding the lock
        item_id = item["item_id"]
        qty     = item["qty"]
        _deindex_item(uid, item)
        del world_items[uid]

    _COIN_ITEM_ID = 1
    with players_lock:
        if player_id not in _players:
            # Player disconnected between the two lock blocks — re-spawn the item
            with world_items_lock:
                world_items[uid] = {"item_id": item_id, "pos": [ix, iy], "qty": qty}
                _index_item(uid, world_items[uid])
            return False
        if item_id == _COIN_ITEM_ID:
            _players[player_id]["coins"] = _players[player_id].get("coins", 0) + qty
        else:
            _add_to_inventory(_players[player_id]["inventory"], item_id, qty)
        mark_inventory_dirty(player_id)
    return True

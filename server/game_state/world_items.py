import uuid
import threading
from server.shared_lock import players_lock, world_items_lock  # world_items_lock defined in shared_lock

world_items = {}        # {uid: {"item_id": int, "pos": [x, y], "qty": int}}
# world_items_lock imported from server.shared_lock

_PICKUP_RADIUS_SQ = 1.0

_players = None


def set_world_items_refs(refs):
    global _players
    _players = refs["players"]


def spawn_world_item(item_id, pos, qty=1):
    """Add a dropped item to the world. Returns the assigned uid."""
    uid = str(uuid.uuid4())[:8]
    with world_items_lock:
        world_items[uid] = {"item_id": item_id, "pos": list(pos), "qty": qty}
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
        for uid, item in list(world_items.items()):
            if uid in claimed:
                continue
            ix, iy = item["pos"]
            for pid, pos in player_list:
                dx = pos[0] - ix
                dy = pos[1] - iy
                if dx * dx + dy * dy <= _PICKUP_RADIUS_SQ:
                    pickups.append((uid, pid, item["item_id"], item["qty"]))
                    claimed.add(uid)
                    break
        # Remove collected items NOW while still holding the lock — eliminates the
        # window where send_game_state could include a "claimed but not yet removed"
        # item, which caused the client-side ghost/flicker effect.
        for uid, _, _, _ in pickups:
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
        del world_items[uid]

    _COIN_ITEM_ID = 1
    with players_lock:
        if player_id not in _players:
            # Player disconnected between the two lock blocks — re-spawn the item
            with world_items_lock:
                world_items[uid] = {"item_id": item_id, "pos": [ix, iy], "qty": qty}
            return False
        if item_id == _COIN_ITEM_ID:
            _players[player_id]["coins"] = _players[player_id].get("coins", 0) + qty
        else:
            _add_to_inventory(_players[player_id]["inventory"], item_id, qty)
        mark_inventory_dirty(player_id)
    return True

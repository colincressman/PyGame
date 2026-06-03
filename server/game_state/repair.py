"""server/game_state/repair.py

Repair logic: restores an item's durability to its dur_max in exchange for
the material cost defined in data/repair.json.
"""

from server.game_state.repair_data import get_repair_cost as _get_repair_cost
from server.item_data import get_item
from server.shared_lock import players_lock


def repair_item(
    player_id: str,
    item_slot: int,
    players: dict,
    nearby_stations: list | None = None,
) -> tuple[bool, str]:
    """
    Repair the item at item_slot by restoring dur to dur_max.

    Returns (True, "") on success or (False, reason) on failure.
    """
    if nearby_stations is not None and "crafting_table" not in nearby_stations:
        return False, "not near crafting_table"

    with players_lock:
        player = players.get(player_id)
        if not player:
            return False, "player not found"
        inv = player["inventory"]

        if not (isinstance(item_slot, int) and 0 <= item_slot < 36):
            return False, f"invalid slot {item_slot}"

        slot = inv[item_slot]
        if slot is None:
            return False, "empty slot"

        meta = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}
        dur = meta.get("dur")
        dur_max = meta.get("dur_max")

        if dur_max is None:
            item_def = get_item(slot[0])
            dur_max = item_def.get("durability")
            dur = dur_max

        if dur_max is None:
            return False, "item not repairable"

        if dur is not None and dur >= dur_max:
            return False, "item already at full durability"

        cost = _get_repair_cost(slot)
        if cost is None:
            return False, "no repair recipe for this item"
        mat_id, mat_qty = cost

        have = sum(s[1] for s in inv[:36] if s is not None and s[0] == mat_id)
        if have < mat_qty:
            mat_name = get_item(mat_id).get("name", f"item {mat_id}")
            return False, f"need {mat_qty}x {mat_name}"

        remaining = mat_qty
        for i in range(36):
            if remaining <= 0:
                break
            s = inv[i]
            if s is None or s[0] != mat_id:
                continue
            take = min(remaining, s[1])
            s[1] -= take
            remaining -= take
            if s[1] == 0:
                inv[i] = None

        if len(slot) > 2 and isinstance(slot[2], dict):
            slot[2]["dur"] = dur_max
        else:
            while len(slot) < 3:
                slot.append({})
            slot[2] = {"dur": dur_max, "dur_max": dur_max}

        item_name = get_item(slot[0]).get("name", f"item {slot[0]}")
        print(f"[REPAIR] {player_id} repaired {item_name} (dur -> {dur_max})")
        return True, ""

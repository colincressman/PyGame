"""server/game_state/repair.py

Repair logic: restores an item's durability to its dur_max in exchange for
2 units of the item's primary material.

Material mapping is determined by item ID range (normal items) or by the
primary part in meta["parts"] (Part Combiner items).
"""

from server.item_data import get_item
from server.shared_lock import players_lock

# Item ID → (material_item_id, qty_required)
# Covers pre-crafted durable items by ID range.
# Range tuples: (lo_inclusive, hi_exclusive) → (mat_id, qty)
_RANGE_REPAIR: list[tuple[tuple[int, int], int, int]] = [
    # Scrap
    ((1000, 1002), 11, 2),   # Scrap weapons → Stone
    ((2000, 2002), 11, 2),   # Scrap tools → Stone
    # Wood/Bone/Stone weapons
    ((1050, 1054), 10, 2),   # Wood/Bone/Stone weapons → Wood
    # Iron
    ((1100, 1103), 100, 2),  # Iron weapons → Iron Bar
    ((2100, 2102), 100, 2),  # Iron tools → Iron Bar
    # Copper
    ((1150, 1153), 101, 2),  # Copper weapons → Copper Bar
    ((2150, 2152), 101, 2),  # Copper tools → Copper Bar
    # Bronze
    ((1200, 1203), 110, 2),  # Bronze weapons → Bronze Bar
    ((2200, 2202), 110, 2),  # Bronze tools → Bronze Bar
    # Steel
    ((1250, 1253), 111, 2),  # Steel weapons → Steel Bar
    ((2250, 2252), 111, 2),  # Steel tools → Steel Bar
    # Gold
    ((1300, 1303), 104, 2),  # Gold weapons → Gold Bar
    ((2300, 2302), 104, 2),  # Gold tools → Gold Bar
    # Crystal
    ((1350, 1353), 26, 2),   # Crystal weapons → Crystal Shard
    ((2350, 2352), 26, 2),   # Crystal tools → Crystal Shard
    # Obsidian
    ((1400, 1403), 27, 2),   # Obsidian weapons → Obsidian Shard
    ((2400, 2402), 27, 2),   # Obsidian tools → Obsidian Shard
    # Wands
    ((1500, 1506), 10, 2),   # Wands → Wood
    # Armor — Iron
    ((3000, 3010), 100, 2),  # Iron head armor
    ((3100, 3110), 100, 2),  # Iron chest
    ((3200, 3210), 100, 2),  # Iron arms
    ((3300, 3310), 100, 2),  # Iron legs
    ((3400, 3410), 100, 2),  # Iron feet
    # Armor — Copper
    ((3010, 3020), 101, 2),
    ((3110, 3120), 101, 2),
    ((3210, 3220), 101, 2),
    ((3310, 3320), 101, 2),
    ((3410, 3420), 101, 2),
    # Armor — Bronze
    ((3020, 3030), 110, 2),
    ((3120, 3130), 110, 2),
    ((3220, 3230), 110, 2),
    ((3320, 3330), 110, 2),
    ((3420, 3430), 110, 2),
    # Armor — Steel
    ((3030, 3040), 111, 2),
    ((3130, 3140), 111, 2),
    ((3230, 3240), 111, 2),
    ((3330, 3340), 111, 2),
    ((3430, 3440), 111, 2),
    # Armor — Gold
    ((3040, 3050), 104, 2),
    ((3140, 3150), 104, 2),
    ((3240, 3250), 104, 2),
    ((3340, 3350), 104, 2),
    ((3440, 3450), 104, 2),
    # Armor — Crystal
    ((3050, 3060), 26, 2),
    ((3150, 3160), 26, 2),
    ((3250, 3260), 26, 2),
    ((3350, 3360), 26, 2),
    ((3450, 3460), 26, 2),
    # Armor — Obsidian
    ((3060, 3070), 27, 2),
    ((3160, 3170), 27, 2),
    ((3260, 3270), 27, 2),
    ((3360, 3370), 27, 2),
    ((3460, 3470), 27, 2),
    # Wooden tools
    ((2050, 2054), 10, 2),   # Wooden/Stone tools → Wood
]

# Part primary item → repair material (for Part Combiner items via meta["parts"])
# Primary part IDs (slot 2): keyed by actual items.json IDs
_PART_TO_MAT: dict[int, tuple[int, int]] = {
    # Blades
    148: (10,  2),   # Paper Blade → Wood
    150: (11,  2),   # Flint Blade → Stone
    151: (11,  2),   # Stone Blade → Stone
    152: (19,  2),   # Bone Blade → Bone
    153: (101, 2),   # Copper Blade → Copper Bar
    154: (102, 2),   # Tin Blade → Tin Bar
    155: (100, 2),   # Iron Blade → Iron Bar
    156: (110, 2),   # Bronze Blade → Bronze Bar
    157: (103, 2),   # Silver Blade → Silver Bar
    158: (104, 2),   # Gold Blade → Gold Bar
    159: (111, 2),   # Steel Blade → Steel Bar
    160: (27,  2),   # Obsidian Blade → Obsidian Shard
    161: (26,  2),   # Crystal Blade → Crystal Shard
    278: (28,  2),   # Slime Blade → Slime Ball
    # Axe Heads
    162: (11,  2),   # Flint Axe Head → Stone
    163: (11,  2),   # Stone Axe Head → Stone
    164: (19,  2),   # Bone Axe Head → Bone
    165: (101, 2),   # Copper Axe Head → Copper Bar
    166: (102, 2),   # Tin Axe Head → Tin Bar
    167: (100, 2),   # Iron Axe Head → Iron Bar
    168: (110, 2),   # Bronze Axe Head → Bronze Bar
    169: (104, 2),   # Gold Axe Head → Gold Bar
    170: (111, 2),   # Steel Axe Head → Steel Bar
    171: (27,  2),   # Obsidian Axe Head → Obsidian Shard
    281: (103, 2),   # Silver Axe Head → Silver Bar
    282: (26,  2),   # Crystal Axe Head → Crystal Shard
    # Pick Heads
    172: (11,  2),   # Flint Pick Head → Stone
    173: (11,  2),   # Stone Pick Head → Stone
    174: (101, 2),   # Copper Pick Head → Copper Bar
    175: (102, 2),   # Tin Pick Head → Tin Bar
    176: (100, 2),   # Iron Pick Head → Iron Bar
    177: (110, 2),   # Bronze Pick Head → Bronze Bar
    178: (104, 2),   # Gold Pick Head → Gold Bar
    179: (111, 2),   # Steel Pick Head → Steel Bar
    180: (27,  2),   # Obsidian Pick Head → Obsidian Shard
    181: (26,  2),   # Crystal Pick Head → Crystal Shard
    283: (19,  2),   # Bone Pick Head → Bone
    284: (103, 2),   # Silver Pick Head → Silver Bar
    # Plates
    149: (26,  2),   # Crystal Plate → Crystal Shard
    182: (101, 2),   # Copper Plate → Copper Bar
    183: (102, 2),   # Tin Plate → Tin Bar
    184: (100, 2),   # Iron Plate → Iron Bar
    185: (110, 2),   # Bronze Plate → Bronze Bar
    186: (103, 2),   # Silver Plate → Silver Bar
    187: (104, 2),   # Gold Plate → Gold Bar
    188: (111, 2),   # Steel Plate → Steel Bar
    189: (27,  2),   # Obsidian Plate → Obsidian Shard
    285: (11,  2),   # Stone Plate → Stone
    286: (19,  2),   # Bone Plate → Bone
}


def _get_repair_cost(slot: list) -> tuple[int, int] | None:
    """Return (material_item_id, qty) or None if item is not repairable."""
    item_id = slot[0]
    meta    = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}

    # Part Combiner item: use primary part from meta["parts"]
    parts = meta.get("parts")
    if parts and len(parts) >= 2:
        primary_part_id = parts[1]
        result = _PART_TO_MAT.get(primary_part_id)
        if result:
            return result

    # Normal item: look up by ID range
    for (lo, hi), mat_id, qty in _RANGE_REPAIR:
        if lo <= item_id < hi:
            return mat_id, qty

    return None


def repair_item(
    player_id: str,
    item_slot: int,
    players: dict,
    nearby_stations: list | None = None,
) -> tuple[bool, str]:
    """
    Repair the item at item_slot by restoring dur to dur_max.
    Consumes 2 of the item's primary material.

    Returns (True, '') on success or (False, reason) on failure.
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
        dur     = meta.get("dur")
        dur_max = meta.get("dur_max")

        # Fall back to items.json durability if meta is absent
        if dur_max is None:
            item_def = get_item(slot[0])
            dur_max  = item_def.get("durability")
            dur      = dur_max  # treat as full since no damage tracking in meta

        if dur_max is None:
            return False, "item not repairable"

        if dur is not None and dur >= dur_max:
            return False, "item already at full durability"

        cost = _get_repair_cost(slot)
        if cost is None:
            return False, "no repair recipe for this item"
        mat_id, mat_qty = cost

        # Count material in bag
        have = sum(s[1] for s in inv[:36] if s is not None and s[0] == mat_id)
        if have < mat_qty:
            mat_name = get_item(mat_id).get("name", f"item {mat_id}")
            return False, f"need {mat_qty}× {mat_name}"

        # Consume material
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

        # Restore durability in meta
        if len(slot) > 2 and isinstance(slot[2], dict):
            slot[2]["dur"] = dur_max
        else:
            # No meta yet — create it
            while len(slot) < 3:
                slot.append({})
            slot[2] = {"dur": dur_max, "dur_max": dur_max}

        item_name = get_item(slot[0]).get("name", f"item {slot[0]}")
        print(f"[REPAIR] {player_id} repaired {item_name} (dur → {dur_max})")
        return True, ""

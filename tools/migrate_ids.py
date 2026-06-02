"""tools/migrate_ids.py — One-time ID migration to the Target ID Scheme.

Run from the workspace root:
    python tools/migrate_ids.py

Writes updated copies of:
  server/items.json
  server/recipes.json
  server/player_saves/*.json   (inventory slots)
  world_chunks_v3/placed_objects.json  (if present — chest inventories)

Does NOT touch chunk files (delete world_chunks_v3/ separately after running).
"""

import json
import os
import sys

# ---------------------------------------------------------------------------
# Complete legacy-ID → target-ID remap
# ---------------------------------------------------------------------------
REMAP: dict[int, int] = {
    # Raw materials — organics (2-11 → 10-19)
    2:   10,   # Wood
    3:   11,   # Stone
    4:   12,   # Stick
    5:   13,   # Herb
    6:   14,   # Mushroom
    7:   15,   # Cactus Spine
    8:   16,   # Snow Crystal
    9:   17,   # Seashell
    10:  18,   # Reed
    11:  19,   # Bone

    # Raw materials — mining (12-19, 28 → 20-27)
    12:  20,   # Coal
    13:  21,   # Iron Ore
    14:  28,   # Slime Ball
    15:  22,   # Copper Ore
    16:  23,   # Tin Ore
    17:  24,   # Silver Ore
    18:  25,   # Gold Ore
    19:  26,   # Crystal Shard
    28:  27,   # Obsidian Shard

    # Processed materials (20-27, 29 → 100-121)
    20:  100,  # Iron Bar
    21:  120,  # Stone Brick
    22:  101,  # Copper Bar
    23:  102,  # Tin Bar
    24:  110,  # Bronze Bar
    25:  103,  # Silver Bar
    26:  104,  # Gold Bar
    27:  111,  # Steel Bar
    29:  121,  # Carbon

    # Stations / placeables (30-40 → 200-254)
    30:  207,  # Campfire
    31:  200,  # Crafting Table
    32:  201,  # Furnace
    33:  250,  # Wood Wall
    34:  251,  # Stone Wall
    35:  252,  # Wooden Door
    36:  220,  # Bed
    37:  253,  # Stone Brick Wall
    38:  254,  # Stone Brick Floor
    39:  202,  # Alloy Forge
    40:  203,  # Chest

    # Weapons — scrap (50-51 → 1000-1001)
    50:  1000, # Scrap Knife
    51:  1001, # Scrap Club

    # Weapons — wood/bone/stone (52-55 → 1050-1053)
    52:  1050, # Wooden Sword
    53:  1051, # Wooden Mace
    54:  1052, # Bone Dagger
    55:  1053, # Stone Mace

    # Weapons — iron (56-58 → 1100-1102)
    56:  1100, # Iron Dagger
    57:  1101, # Iron Sword
    58:  1102, # Iron Mace

    # Weapons — copper (59, 65-66 → 1150-1152)
    59:  1150, # Copper Sword
    65:  1151, # Copper Dagger
    66:  1152, # Copper Mace

    # Weapons — bronze (60, 67-68 → 1200-1202)
    60:  1200, # Bronze Sword
    67:  1201, # Bronze Dagger
    68:  1202, # Bronze Mace

    # Weapons — steel (61, 69-70 → 1250-1252)
    61:  1250, # Steel Sword
    69:  1251, # Steel Dagger
    70:  1252, # Steel Mace

    # Weapons — gold (62, 71-72 → 1300-1302)
    62:  1300, # Gold Shortsword
    71:  1301, # Gold Dagger
    72:  1302, # Gold Mace

    # Weapons — crystal (75-77 → 1350-1352)
    75:  1350, # Crystal Sword
    76:  1351, # Crystal Dagger
    77:  1352, # Crystal Mace

    # Weapons — obsidian (64, 73-74 → 1400-1402)
    64:  1400, # Obsidian Blade
    73:  1401, # Obsidian Dagger
    74:  1402, # Obsidian Mace

    # Wands (63, 78-82 → 1500-1505)
    78:  1500, # Nature Wand
    79:  1501, # Bone Wand
    80:  1502, # Moon Wand
    81:  1503, # Storm Wand
    82:  1504, # Shadow Wand
    63:  1505, # Crystal Wand

    # Tools — scrap (100-101 → 2000-2001)
    100: 2000, # Scrap Axe
    101: 2001, # Scrap Pickaxe

    # Tools — wood/stone (102-103, 105-106 → 2050-2053)
    102: 2050, # Wooden Axe
    103: 2051, # Stone Axe
    105: 2052, # Wooden Pickaxe
    106: 2053, # Stone Pickaxe

    # Tools — iron (104, 107 → 2100-2101)
    104: 2100, # Iron Axe
    107: 2101, # Iron Pickaxe

    # Tools — copper (108-109 → 2150-2151)
    108: 2150, # Copper Axe
    109: 2151, # Copper Pickaxe

    # Tools — bronze (110-111 → 2200-2201)
    110: 2200, # Bronze Axe
    111: 2201, # Bronze Pickaxe

    # Tools — steel (112-113 → 2250-2251)
    112: 2250, # Steel Axe
    113: 2251, # Steel Pickaxe

    # Tools — gold (116, 114 → 2300-2301)
    116: 2300, # Gold Axe
    114: 2301, # Gold Pickaxe

    # Tools — crystal (117, 115 → 2350-2351)
    117: 2350, # Crystal Axe
    115: 2351, # Crystal Pick

    # Tools — obsidian (118-119 → 2400-2401)
    118: 2400, # Obsidian Axe
    119: 2401, # Obsidian Pickaxe

    # Armor — head (150-158 → 3000-3008)
    150: 3000, # Scrap Cap
    151: 3001, # Stone Helm
    152: 3002, # Iron Helm
    153: 3003, # Copper Helm
    154: 3004, # Bronze Helm
    155: 3005, # Steel Helm
    156: 3006, # Gold Crown
    157: 3007, # Crystal Helm
    158: 3008, # Obsidian Helm

    # Armor — chest (160-169 → 3100-3109)
    160: 3100, # Scrap Vest
    161: 3101, # Reed Tunic
    162: 3102, # Bone Vest
    163: 3103, # Iron Chestplate
    164: 3104, # Copper Vest
    165: 3105, # Bronze Vest
    166: 3106, # Steel Vest
    167: 3107, # Gold Chestplate
    168: 3108, # Crystal Chestplate
    169: 3109, # Obsidian Chestplate

    # Armor — arms (170-177 → 3200-3207)
    170: 3200, # Bone Bracers
    171: 3201, # Iron Bracers
    172: 3202, # Copper Bracers
    173: 3203, # Bronze Bracers
    174: 3204, # Steel Bracers
    175: 3205, # Gold Bracers
    176: 3206, # Crystal Bracers
    177: 3207, # Obsidian Bracers

    # Armor — legs (180-189 → 3300-3309)
    180: 3300, # Scrap Leggings
    181: 3301, # Reed Leggings
    182: 3302, # Bone Leggings
    183: 3303, # Copper Leggings
    184: 3304, # Bronze Leggings
    185: 3305, # Steel Leggings
    186: 3306, # Iron Leggings
    187: 3307, # Gold Leggings
    188: 3308, # Crystal Leggings
    189: 3309, # Obsidian Leggings

    # Armor — feet (190-197 → 3400-3407)
    190: 3400, # Leaf Sandals
    191: 3401, # Iron Boots
    192: 3402, # Bronze Boots
    193: 3403, # Steel Boots
    194: 3404, # Copper Boots
    195: 3405, # Gold Boots
    196: 3406, # Crystal Boots
    197: 3407, # Obsidian Boots

    # Armor — back (200-201 → 3500-3501)
    200: 3500, # Leaf Cloak
    201: 3501, # Herb Pouch

    # Armor — necklaces (250-251 → 3650-3651)
    250: 3650, # Shell Necklace
    251: 3651, # Snow Pendant

    # Armor — rings (260-261 → 3600-3601)
    260: 3600, # Crystal Ring
    261: 3601, # Mushroom Ring

    # Consumables (300-302 → 4000-4002)
    300: 4000, # Herb Tea
    301: 4001, # Mushroom Stew
    302: 4002, # Healing Potion
}


def remap_id(old: int) -> int:
    """Return the new ID for old, or old if not in REMAP."""
    return REMAP.get(old, old)


def remap_slot(slot):
    """Remap a single inventory slot [item_id, qty] or [item_id, qty, meta] or None."""
    if slot is None:
        return None
    return [remap_id(slot[0])] + slot[1:]


def remap_inventory(inv: list) -> list:
    """Remap every slot in an inventory list."""
    return [remap_slot(s) for s in inv]


# ---------------------------------------------------------------------------
# items.json
# ---------------------------------------------------------------------------
def migrate_items(path: str):
    with open(path) as f:
        data: dict = json.load(f)

    new_data: dict = {}
    for old_key, entry in data.items():
        new_key = str(remap_id(int(old_key)))
        new_data[new_key] = entry

    # Sort by numeric key for readability
    sorted_data = dict(sorted(new_data.items(), key=lambda kv: int(kv[0])))

    with open(path, "w") as f:
        json.dump(sorted_data, f, indent=4)

    print(f"  items.json: {len(data)} → {len(sorted_data)} entries")
    if len(data) != len(sorted_data):
        print("  WARNING: entry count changed — possible ID collision!")


# ---------------------------------------------------------------------------
# recipes.json
# ---------------------------------------------------------------------------
def migrate_recipes(path: str):
    with open(path) as f:
        data: dict = json.load(f)

    for recipe in data.values():
        # result: [item_id, qty]
        if "result" in recipe:
            recipe["result"][0] = remap_id(recipe["result"][0])
        # ingredients: [[item_id, qty], ...]
        if "ingredients" in recipe:
            for ing in recipe["ingredients"]:
                ing[0] = remap_id(ing[0])

    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    print(f"  recipes.json: {len(data)} recipes updated")


# ---------------------------------------------------------------------------
# player_saves/*.json
# ---------------------------------------------------------------------------
def migrate_player_saves(save_dir: str):
    if not os.path.isdir(save_dir):
        print(f"  player_saves: dir not found, skipping ({save_dir})")
        return

    count = 0
    for fname in os.listdir(save_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(save_dir, fname)
        with open(fpath) as f:
            pdata: dict = json.load(f)

        if "inventory" in pdata:
            pdata["inventory"] = remap_inventory(pdata["inventory"])

        with open(fpath, "w") as f:
            json.dump(pdata, f, indent=4)
        count += 1

    print(f"  player_saves: {count} file(s) updated")


# ---------------------------------------------------------------------------
# world_chunks_v3/placed_objects.json  (chest inventories)
# ---------------------------------------------------------------------------
def migrate_placed_objects(path: str):
    if not os.path.isfile(path):
        print(f"  placed_objects.json: not found, skipping")
        return

    with open(path) as f:
        data: dict = json.load(f)

    for obj in data.values():
        if "chest_inv" in obj and obj["chest_inv"]:
            obj["chest_inv"] = remap_inventory(obj["chest_inv"])

    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    print(f"  placed_objects.json: {len(data)} objects updated")


# ---------------------------------------------------------------------------
# Sanity check: verify no duplicate target IDs
# ---------------------------------------------------------------------------
def _check_remap():
    targets = list(REMAP.values())
    seen = set()
    dupes = []
    for t in targets:
        if t in seen:
            dupes.append(t)
        seen.add(t)
    if dupes:
        print(f"ERROR: duplicate target IDs in REMAP: {dupes}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Workspace root: {root}")
    print()

    _check_remap()

    print("Migrating items.json ...")
    migrate_items(os.path.join(root, "server", "items.json"))

    print("Migrating recipes.json ...")
    migrate_recipes(os.path.join(root, "server", "recipes.json"))

    print("Migrating player saves ...")
    migrate_player_saves(os.path.join(root, "server", "player_saves"))

    print("Migrating placed_objects.json ...")
    migrate_placed_objects(os.path.join(root, "world_chunks_v3", "placed_objects.json"))

    print()
    print("Done. Next steps:")
    print("  1. Update Python source files (resource_nodes, controls, mob_manager, placed_objects, item_art)")
    print("  2. Delete world_chunks_v3/ (chunks embed legacy ore IDs in node yields)")
    print("  3. Restart server — world will regenerate on first player login")

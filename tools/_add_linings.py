"""One-shot script: add lining items (297-309) and recipes (434-446) to data files."""
import json, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "server", "items.json"), encoding="utf-8") as f:
    items_raw = json.load(f)
with open(os.path.join(ROOT, "server", "recipes.json"), encoding="utf-8") as f:
    recipes_raw = json.load(f)

# ── New lining items (IDs 297-309) ────────────────────────────────────────
new_items = {
    "297": {"max_stack": 10, "name": "Paper Lining",    "part_stats": {"dur_bonus":  5, "gem_slots": 1, "slot": "lining", "speed_mult": 1.15, "trait": "padded"},    "sell_price":  2, "stackable": True},
    "298": {"max_stack": 10, "name": "Reed Lining",     "part_stats": {"dur_bonus": 15,                "slot": "lining", "speed_mult": 1.10, "trait": "padded"},    "sell_price":  3, "stackable": True},
    "299": {"max_stack": 10, "name": "Bone Lining",     "part_stats": {"dur_bonus": 25,                "slot": "lining", "speed_mult": 1.05, "trait": None},        "sell_price":  5, "stackable": True},
    "300": {"max_stack": 10, "name": "Copper Lining",   "part_stats": {"dur_bonus": 35,                "slot": "lining", "speed_mult": 1.00, "trait": None},        "sell_price":  7, "stackable": True},
    "301": {"max_stack": 10, "name": "Tin Lining",      "part_stats": {"dur_bonus": 40,                "slot": "lining", "speed_mult": 0.98, "trait": None},        "sell_price":  9, "stackable": True},
    "302": {"max_stack": 10, "name": "Iron Lining",     "part_stats": {"dur_bonus": 50,                "slot": "lining", "speed_mult": 0.95, "trait": "reinforced"},"sell_price": 12, "stackable": True},
    "303": {"max_stack": 10, "name": "Bronze Lining",   "part_stats": {"dur_bonus": 60,                "slot": "lining", "speed_mult": 0.92, "trait": "reinforced"},"sell_price": 17, "stackable": True},
    "304": {"max_stack": 10, "name": "Silver Lining",   "part_stats": {"dur_bonus": 65,                "slot": "lining", "speed_mult": 0.95, "trait": "magical"},   "sell_price": 22, "stackable": True},
    "305": {"max_stack": 10, "name": "Gold Lining",     "part_stats": {"dur_bonus": 55,                "slot": "lining", "speed_mult": 0.97, "trait": "shiny"},     "sell_price": 20, "stackable": True},
    "306": {"max_stack": 10, "name": "Steel Lining",    "part_stats": {"dur_bonus": 80,                "slot": "lining", "speed_mult": 0.88, "trait": "reinforced"},"sell_price": 32, "stackable": True},
    "307": {"max_stack": 10, "name": "Obsidian Lining", "part_stats": {"dur_bonus": 95,                "slot": "lining", "speed_mult": 0.82, "trait": "heavy"},     "sell_price": 40, "stackable": True},
    "308": {"max_stack": 10, "name": "Crystal Lining",  "part_stats": {"dur_bonus": 70, "gem_slots": 1, "slot": "lining", "speed_mult": 1.00, "trait": "magical"}, "sell_price": 25, "stackable": True},
    "309": {"max_stack": 10, "name": "Slime Lining",    "part_stats": {"dur_bonus": 85,                "slot": "lining", "speed_mult": 1.05, "trait": "slimy"},     "sell_price": 18, "stackable": True},
}

for k in new_items:
    if k in items_raw:
        existing = items_raw[k].get("name", "?")
        print(f"CONFLICT: item ID {k} already exists: {existing}")
        sys.exit(1)

# ── New lining recipes (IDs 434-446) ─────────────────────────────────────
# Ingredient IDs (from existing recipes):
#   18=reed, 19=bone, 26=crystal, 27=obsidian, 32=paper, 33=slime
#   100=iron, 101=copper, 102=tin, 103=silver, 104=gold, 110=bronze, 111=steel
new_recipes = {
    "434": {"category": "part", "ingredients": [[32, 1]],  "name": "Paper Lining",    "result": [297, 2], "station": "part_maker"},
    "435": {"category": "part", "ingredients": [[18, 2]],  "name": "Reed Lining",     "result": [298, 2], "station": "part_maker"},
    "436": {"category": "part", "ingredients": [[19, 2]],  "name": "Bone Lining",     "result": [299, 2], "station": "part_maker"},
    "437": {"category": "part", "ingredients": [[101, 1]], "name": "Copper Lining",   "result": [300, 2], "station": "part_maker"},
    "438": {"category": "part", "ingredients": [[102, 1]], "name": "Tin Lining",      "result": [301, 2], "station": "part_maker"},
    "439": {"category": "part", "ingredients": [[100, 1]], "name": "Iron Lining",     "result": [302, 2], "station": "part_maker"},
    "440": {"category": "part", "ingredients": [[110, 1]], "name": "Bronze Lining",   "result": [303, 2], "station": "part_maker"},
    "441": {"category": "part", "ingredients": [[103, 1]], "name": "Silver Lining",   "result": [304, 2], "station": "part_maker"},
    "442": {"category": "part", "ingredients": [[104, 1]], "name": "Gold Lining",     "result": [305, 2], "station": "part_maker"},
    "443": {"category": "part", "ingredients": [[111, 1]], "name": "Steel Lining",    "result": [306, 2], "station": "part_maker"},
    "444": {"category": "part", "ingredients": [[27, 1]],  "name": "Obsidian Lining", "result": [307, 2], "station": "part_maker"},
    "445": {"category": "part", "ingredients": [[26, 2]],  "name": "Crystal Lining",  "result": [308, 1], "station": "part_maker"},
    "446": {"category": "part", "ingredients": [[33, 2]],  "name": "Slime Lining",    "result": [309, 2], "station": "part_maker"},
}

for k in new_recipes:
    if k in recipes_raw:
        print(f"CONFLICT: recipe ID {k} already exists")
        sys.exit(1)

items_raw.update(new_items)
recipes_raw.update(new_recipes)

with open(os.path.join(ROOT, "server", "items.json"), "w", encoding="utf-8") as f:
    json.dump(items_raw, f, indent=2, sort_keys=True)
with open(os.path.join(ROOT, "server", "recipes.json"), "w", encoding="utf-8") as f:
    json.dump(recipes_raw, f, indent=2, sort_keys=True)

print(f"Added {len(new_items)} lining items (297-309) and {len(new_recipes)} recipes (434-446).")
print(f"Total items: {len(items_raw)}, total recipes: {len(recipes_raw)}")

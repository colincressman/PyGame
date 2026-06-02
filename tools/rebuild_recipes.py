"""Rebuild recipes.json: remove stale recipes, add full material part recipes."""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rpath = os.path.join(BASE, 'server', 'recipes.json')
r = json.load(open(rpath))

# ── KEYS TO REMOVE ─────────────────────────────────────────────────────────────
# Dead weapon/tool/armor/wand recipes (result_id no longer in items.json)
DEAD_WEAPON_TOOL_ARMOR = {
    78, 79, 80, 81, 82, 86, 87, 88, 89, 92, 93, 96, 99, 103,
    110, 111, 115, 117, 118, 119, 120, 121, 122, 123, 124, 125,
    126, 127, 128, 129, 130, 131, 132,
}
# Old alloy_forge "part" recipes (IDs now reassigned to real parts)
OLD_ALLOY_PARTS = {140, 141, 142, 143, 144, 145, 146}
# Old Task-8 placeholder part recipes (wrong IDs, being fully replaced)
OLD_TASK8_PARTS = set(range(148, 170))  # 148-169

REMOVE_KEYS = DEAD_WEAPON_TOOL_ARMOR | OLD_ALLOY_PARTS | OLD_TASK8_PARTS
for k in REMOVE_KEYS:
    r.pop(str(k), None)

print(f'After removals: {len(r)} recipes')
print('Key 147 (Part Maker):', r.get('147'))
assert '147' in r, 'Part Maker station recipe missing!'
for k in range(170, 179):
    assert str(k) in r, f'Mold recipe {k} missing!'
print('Molds 170-178 intact')

# ── RAW MATERIAL RECIPES (179-181) ─────────────────────────────────────────────
# Flint: chip 2 Stone together by hand
r['179'] = {'name': 'Flint', 'category': 'resource', 'result': [31, 1],
            'station': 'hand', 'ingredients': [[11, 2]]}
# Paper: weave 2 Reed at crafting table
r['180'] = {'name': 'Paper', 'category': 'resource', 'result': [32, 2],
            'station': 'crafting_table', 'ingredients': [[18, 2]]}
# Slime: press 4 Slime Balls into a usable block of Slime
r['181'] = {'name': 'Slime', 'category': 'resource', 'result': [33, 1],
            'station': 'crafting_table', 'ingredients': [[28, 4]]}

# ── PART MAKER HELPERS ─────────────────────────────────────────────────────────
_next_key = [182]

def pm(name, result_id, result_qty, *ingredients):
    """Add a Part Maker recipe. ingredients: (item_id, qty) pairs."""
    k = str(_next_key[0])
    _next_key[0] += 1
    r[k] = {'name': name, 'category': 'part', 'result': [result_id, result_qty],
             'station': 'part_maker', 'ingredients': list(ingredients)}

# Material shorthand IDs
WOOD=10; STONE=11; REED=18; BONE=19; SLIME_B=28
CRYSTAL=26; OBSIDIAN=27; FLINT=31; PAPER=32; SLIME=33
IRON=100; COPPER=101; TIN=102; SILVER=103; GOLD=104
BRONZE=110; STEEL=111; CARBON=121

# ── BLADES (item IDs 148, 150-161, 278) ───────────────────────────────────────
pm('Paper Blade',      148, 1, (PAPER,   1))
pm('Flint Blade',      150, 1, (FLINT,   2))
pm('Stone Blade',      151, 1, (STONE,   2))
pm('Bone Blade',       152, 1, (BONE,    2))
pm('Copper Blade',     153, 1, (COPPER,  2))
pm('Tin Blade',        154, 1, (TIN,     2))
pm('Iron Blade',       155, 1, (IRON,    2))
pm('Bronze Blade',     156, 1, (BRONZE,  2))
pm('Silver Blade',     157, 1, (SILVER,  2))
pm('Gold Blade',       158, 1, (GOLD,    2))
pm('Steel Blade',      159, 1, (STEEL,   2))
pm('Obsidian Blade',   160, 1, (OBSIDIAN,2))
pm('Crystal Blade',    161, 1, (CRYSTAL, 2))
pm('Slime Blade',      278, 1, (SLIME,   3))

# ── AXE HEADS (item IDs 162-171) ──────────────────────────────────────────────
pm('Flint Axe Head',    162, 1, (FLINT,   3))
pm('Stone Axe Head',    163, 1, (STONE,   3))
pm('Bone Axe Head',     164, 1, (BONE,    3))
pm('Copper Axe Head',   165, 1, (COPPER,  3))
pm('Tin Axe Head',      166, 1, (TIN,     3))
pm('Iron Axe Head',     167, 1, (IRON,    3))
pm('Bronze Axe Head',   168, 1, (BRONZE,  3))
pm('Gold Axe Head',     169, 1, (GOLD,    3))
pm('Steel Axe Head',    170, 1, (STEEL,   3))
pm('Obsidian Axe Head', 171, 1, (OBSIDIAN,3))
pm('Silver Axe Head',   281, 1, (SILVER,  3))
pm('Crystal Axe Head',  282, 1, (CRYSTAL, 3))

# ── PICK HEADS (item IDs 172-181) ─────────────────────────────────────────────
pm('Flint Pick Head',    172, 1, (FLINT,   3))
pm('Stone Pick Head',    173, 1, (STONE,   3))
pm('Copper Pick Head',   174, 1, (COPPER,  3))
pm('Tin Pick Head',      175, 1, (TIN,     3))
pm('Iron Pick Head',     176, 1, (IRON,    3))
pm('Bronze Pick Head',   177, 1, (BRONZE,  3))
pm('Gold Pick Head',     178, 1, (GOLD,    3))
pm('Steel Pick Head',    179, 1, (STEEL,   3))
pm('Obsidian Pick Head', 180, 1, (OBSIDIAN,3))
pm('Crystal Pick Head',  181, 1, (CRYSTAL, 3))
pm('Bone Pick Head',     283, 1, (BONE,    3))
pm('Silver Pick Head',   284, 1, (SILVER,  3))

# ── PLATES (item IDs 149, 182-189) ────────────────────────────────────────────
pm('Crystal Plate',   149, 1, (CRYSTAL, 2))
pm('Copper Plate',    182, 1, (COPPER,  2))
pm('Tin Plate',       183, 1, (TIN,     2))
pm('Iron Plate',      184, 1, (IRON,    2))
pm('Bronze Plate',    185, 1, (BRONZE,  2))
pm('Silver Plate',    186, 1, (SILVER,  2))
pm('Gold Plate',      187, 1, (GOLD,    2))
pm('Steel Plate',     188, 1, (STEEL,   2))
pm('Obsidian Plate',  189, 1, (OBSIDIAN,2))
pm('Stone Plate',     285, 1, (STONE,   3))
pm('Bone Plate',      286, 1, (BONE,    2))
pm('Paper Plate',     287, 1, (PAPER,   1))
pm('Slime Plate',     288, 1, (SLIME,   3))

# ── HANDLES (item IDs 260-268, 279) ───────────────────────────────────────────
pm('Wood Handle',    260, 2, (WOOD,    2))
pm('Bone Handle',    261, 2, (BONE,    2))
pm('Paper Handle',   262, 2, (PAPER,   1))
pm('Copper Handle',  263, 2, (COPPER,  1))
pm('Iron Handle',    264, 2, (IRON,    1))
pm('Bronze Handle',  265, 2, (BRONZE,  1))
pm('Silver Handle',  266, 2, (SILVER,  1))
pm('Gold Handle',    267, 2, (GOLD,    1))
pm('Steel Handle',   268, 2, (STEEL,   1))
pm('Tin Handle',     289, 2, (TIN,     1))
pm('Obsidian Handle',290, 2, (OBSIDIAN,1))
pm('Crystal Handle', 291, 2, (CRYSTAL, 1))
pm('Slime Handle',   279, 2, (SLIME,   2))

# ── CORES (item IDs 269-271) ──────────────────────────────────────────────────
pm('Rough Crystal Core',   269, 1, (CRYSTAL, 1))
pm('Refined Crystal Core', 270, 1, (CRYSTAL, 2), (SILVER, 1))
pm('Crystal Core',         271, 1, (CRYSTAL, 3), (SILVER, 1), (CARBON, 1))

# ── BINDINGS (item IDs 272-277, 280) ──────────────────────────────────────────
pm('Paper Binding',   272, 2, (PAPER,   1))
pm('Reed Binding',    273, 2, (REED,    2))
pm('Copper Binding',  274, 2, (COPPER,  1))
pm('Iron Binding',    275, 2, (IRON,    1))
pm('Bronze Binding',  276, 2, (BRONZE,  1))
pm('Silver Binding',  277, 2, (SILVER,  1))
pm('Tin Binding',     292, 2, (TIN,     1))
pm('Gold Binding',    293, 2, (GOLD,    1))
pm('Steel Binding',   294, 2, (STEEL,   1))
pm('Obsidian Binding',295, 2, (OBSIDIAN,1))
pm('Slime Binding',   280, 2, (SLIME,   1))

print(f'After additions: {len(r)} recipes')
print(f'New part recipes added: keys 182-{_next_key[0]-1}')

# ── SANITY CHECK ───────────────────────────────────────────────────────────────
items = json.load(open(os.path.join(BASE, 'server', 'items.json')))
bad = []
for k, v in r.items():
    rid = v.get('result', [None])[0] if 'result' in v else v.get('result_id')
    if rid and str(rid) not in items:
        bad.append((k, rid, v.get('name', '?')))
if bad:
    print('WARNING - recipes with missing result items:')
    for b in bad:
        print(' ', b)
else:
    print('All recipe result IDs valid')

with open(rpath, 'w') as f:
    json.dump(r, f, indent=2)
print(f'Wrote {rpath}')

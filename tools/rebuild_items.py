"""Rebuild items.json: remove advanced direct-craft items, add full material parts."""
import json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(BASE, 'server', 'items.json')
d = json.load(open(path))

# ── IDs to REMOVE ─────────────────────────────────────────────────────────────
REMOVE_IDS = set(map(str, [
    # Steel/Gold/Crystal/Obsidian weapons
    1250, 1251, 1252, 1300, 1301, 1302, 1350, 1351, 1352, 1400, 1401, 1402,
    # ALL wands (become Part Combiner items)
    1500, 1501, 1502, 1503, 1504, 1505,
    # Steel/Gold/Crystal/Obsidian tools
    2250, 2251, 2300, 2301, 2350, 2351, 2400, 2401,
    # Steel/Gold/Crystal/Obsidian armor
    3005, 3006, 3007, 3008,       # head
    3106, 3107, 3108, 3109,       # chest
    3204, 3205, 3206, 3207,       # arms
    3305, 3307, 3308, 3309,       # legs  (3306=Iron Legs stays)
    3403, 3405, 3406, 3407,       # shoes
    # Old Task-8 placeholder parts — fully replaced below
    150, 151, 152, 153,
    160, 161, 162, 163,
    170, 171, 172, 173, 174, 175,
    180, 181, 182, 183, 184, 185, 188, 189,
    # New part IDs being (re)assigned — clear any stale data
    281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295,
]))

for iid in REMOVE_IDS:
    d.pop(iid, None)

print(f'After removals: {len(d)} items')

# ── NEW RAW MATERIALS ──────────────────────────────────────────────────────────
d['31'] = {'name': 'Flint', 'stackable': True, 'max_stack': 64, 'sell_price': 2}
d['32'] = {'name': 'Paper', 'stackable': True, 'max_stack': 64, 'sell_price': 1}
d['33'] = {'name': 'Slime', 'stackable': True, 'max_stack': 64, 'sell_price': 4}

# ── HELPERS ────────────────────────────────────────────────────────────────────
def mk_blade(name, atk, dur, trait=None, sell=5, gem_slots=0):
    ps = {'slot': 'blade', 'base_atk': atk, 'base_dur': dur, 'trait': trait}
    if gem_slots: ps['gem_slots'] = gem_slots
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell, 'part_stats': ps}

def mk_head(slot, name, atk, dur, trait=None, sell=5):
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell,
            'part_stats': {'slot': slot, 'base_atk': atk, 'base_dur': dur, 'trait': trait}}

def mk_plate(name, def_, hp, dur, trait=None, sell=5, gem_slots=0):
    ps = {'slot': 'plate', 'base_def': def_, 'base_hp': hp, 'base_dur': dur, 'trait': trait}
    if gem_slots: ps['gem_slots'] = gem_slots
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell, 'part_stats': ps}

def mk_handle(name, spd, atk, dur, trait=None, sell=5, gem_slots=0):
    ps = {'slot': 'handle', 'speed_mult': spd, 'atk_bonus': atk, 'dur_bonus': dur, 'trait': trait}
    if gem_slots: ps['gem_slots'] = gem_slots
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell, 'part_stats': ps}

def mk_core(name, spd, atk, dur, sell=5):
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell,
            'part_stats': {'slot': 'core', 'speed_mult': spd, 'atk_bonus': atk,
                           'dur_bonus': dur, 'trait': 'magical'}}

def mk_binding(name, dur, trait=None, sell=3, gem_slots=0):
    ps = {'slot': 'binding', 'dur_bonus': dur, 'trait': trait}
    if gem_slots: ps['gem_slots'] = gem_slots
    return {'name': name, 'stackable': True, 'max_stack': 10, 'sell_price': sell, 'part_stats': ps}

# ── PAPER BLADE (148) ────────────────────────────────────────────────────────
# Papery: fragile but unlocks 2 extra gem slots — the modifier-stacking enabler
d['148'] = mk_blade('Paper Blade',     5,  20, 'papery',   2, gem_slots=2)

# ── BLADES (150-161) ──────────────────────────────────────────────────────────
d['150'] = mk_blade('Flint Blade',    12,  30, 'sharp',       3)
d['151'] = mk_blade('Stone Blade',    15,  60, 'stonebound',  4)  # gets stronger as it wears
d['152'] = mk_blade('Bone Blade',     18,  70,  None,         5)
d['153'] = mk_blade('Copper Blade',   28, 110,  None,         8)
d['154'] = mk_blade('Tin Blade',      22,  85,  None,         7)
d['155'] = mk_blade('Iron Blade',     35, 120,  None,        12)
d['156'] = mk_blade('Bronze Blade',   45, 160, 'dense',      18)  # repairs restore extra durability
d['157'] = mk_blade('Silver Blade',   50, 140, 'magical',    22)
d['158'] = mk_blade('Gold Blade',     50, 140, 'shiny',      25)
d['159'] = mk_blade('Steel Blade',    58, 220, 'sturdy',     30)
d['160'] = mk_blade('Obsidian Blade', 105,260, 'heavy',      45)
d['161'] = mk_blade('Crystal Blade',  80, 280, 'magical',    40)

# ── AXE HEADS (162-171, 281-282) ────────────────────────────────────────────
d['162'] = mk_head('axe_head','Flint Axe Head',    12,  30, 'sharp',       3)
d['163'] = mk_head('axe_head','Stone Axe Head',    15,  60, 'stonebound',  4)
d['164'] = mk_head('axe_head','Bone Axe Head',     18,  70,  None,         5)
d['165'] = mk_head('axe_head','Copper Axe Head',   28, 110,  None,         8)
d['166'] = mk_head('axe_head','Tin Axe Head',      22,  85,  None,         7)
d['167'] = mk_head('axe_head','Iron Axe Head',     35, 120,  None,        12)
d['168'] = mk_head('axe_head','Bronze Axe Head',   45, 160, 'dense',      18)
d['169'] = mk_head('axe_head','Gold Axe Head',     50, 140, 'shiny',      25)
d['170'] = mk_head('axe_head','Steel Axe Head',    58, 220, 'sturdy',     30)
d['171'] = mk_head('axe_head','Obsidian Axe Head', 105,260, 'heavy',      45)
d['281'] = mk_head('axe_head','Silver Axe Head',   50, 140, 'magical',    22)
d['282'] = mk_head('axe_head','Crystal Axe Head',  80, 280, 'magical',    40)

# ── PICK HEADS (172-181, 283-284) ───────────────────────────────────────────
d['172'] = mk_head('pick_head','Flint Pick Head',    12,  30, 'sharp',       3)
d['173'] = mk_head('pick_head','Stone Pick Head',    15,  60, 'stonebound',  4)
d['174'] = mk_head('pick_head','Copper Pick Head',   28, 110,  None,         8)
d['175'] = mk_head('pick_head','Tin Pick Head',      22,  85,  None,         7)
d['176'] = mk_head('pick_head','Iron Pick Head',     35, 120,  None,        12)
d['177'] = mk_head('pick_head','Bronze Pick Head',   45, 160, 'dense',      18)
d['178'] = mk_head('pick_head','Gold Pick Head',     50, 140, 'shiny',      25)
d['179'] = mk_head('pick_head','Steel Pick Head',    58, 220, 'sturdy',     30)
d['180'] = mk_head('pick_head','Obsidian Pick Head', 105,260, 'heavy',      45)
d['181'] = mk_head('pick_head','Crystal Pick Head',  80, 280, 'magical',    40)
d['283'] = mk_head('pick_head','Bone Pick Head',     18,  70,  None,         5)
d['284'] = mk_head('pick_head','Silver Pick Head',   50, 140, 'magical',    22)

# ── PLATES (149, 182-189, 285-288) ──────────────────────────────────────────
d['182'] = mk_plate('Copper Plate',    6,  30, 110,  None,          8)
d['183'] = mk_plate('Tin Plate',       5,  25,  85,  None,          7)
d['184'] = mk_plate('Iron Plate',      8,  40, 120,  None,         12)
d['185'] = mk_plate('Bronze Plate',   10,  50, 160, 'dense',       18)
d['186'] = mk_plate('Silver Plate',    9,  35, 140, 'magical',     22)
d['187'] = mk_plate('Gold Plate',      9,  35, 140, 'shiny',       25)
d['188'] = mk_plate('Steel Plate',    14,  60, 220, 'sturdy',      30)
d['189'] = mk_plate('Obsidian Plate', 28,  50, 260, 'heavy',       45)
d['149'] = mk_plate('Crystal Plate',  16,  75, 280, 'magical',     40)
d['285'] = mk_plate('Stone Plate',     3,  15,  60, 'stonebound',   4)
d['286'] = mk_plate('Bone Plate',      5,  20,  70,  None,          6)
d['287'] = mk_plate('Paper Plate',     1,   5,  20, 'papery',       2, gem_slots=2)
d['288'] = mk_plate('Slime Plate',     7,  30, 200, 'slimy',       18)

# ── HANDLES (260-268, 279, 289-291) ─────────────────────────────────────────
d['260'] = mk_handle('Wood Handle',      1.15,  0,  20, 'light',    3)
d['261'] = mk_handle('Bone Handle',      1.10,  2,  25,  None,      5)
d['262'] = mk_handle('Paper Handle',     1.20,  0,  -5, 'papery',   2, gem_slots=1)
d['263'] = mk_handle('Copper Handle',    1.05,  3,  45,  None,      8)
d['264'] = mk_handle('Iron Handle',      0.90,  5,  55, 'sturdy',  12)
d['265'] = mk_handle('Bronze Handle',    0.95,  6,  65, 'dense',   18)
d['266'] = mk_handle('Silver Handle',    1.00,  8,  60, 'magical', 22)
d['267'] = mk_handle('Gold Handle',      1.12,  5,  35, 'shiny',   25)
d['268'] = mk_handle('Steel Handle',     0.85,  8,  80, 'sturdy',  30)
d['289'] = mk_handle('Tin Handle',       1.08,  2,  40,  None,      6)
d['290'] = mk_handle('Obsidian Handle',  0.80, 12,  90, 'heavy',   35)
d['291'] = mk_handle('Crystal Handle',   1.05, 12,  80, 'magical', 30)

# ── CORES (269-271) ───────────────────────────────────────────────────────────
d['269'] = mk_core('Rough Crystal Core',   1.05, 10,  60, 15)
d['270'] = mk_core('Refined Crystal Core', 1.10, 20,  80, 28)
d['271'] = mk_core('Crystal Core',         1.15, 30, 100, 45)

# ── BINDINGS (272-277, 280, 292-295) ────────────────────────────────────────
d['272'] = mk_binding('Paper Binding',    10, 'papery',    2, gem_slots=1)
d['273'] = mk_binding('Reed Binding',     20, 'light',     3)
d['274'] = mk_binding('Copper Binding',   35,  None,       6)
d['275'] = mk_binding('Iron Binding',     50,  None,      10)
d['276'] = mk_binding('Bronze Binding',   60, 'dense',    15)
d['277'] = mk_binding('Silver Binding',   65, 'magical',  20)
d['292'] = mk_binding('Tin Binding',      40,  None,       7)
d['293'] = mk_binding('Gold Binding',     55, 'shiny',    18)
d['294'] = mk_binding('Steel Binding',    75, 'sturdy',   25)
d['295'] = mk_binding('Obsidian Binding', 90, 'heavy',    35)

# ── SLIME PARTS (278-280) — TiC-inspired; Slime drops from Slime enemies ──────
# Slimy trait: on-hit chance to slow target; naturally high durability
d['278'] = mk_blade('Slime Blade',    20, 200, 'slimy',   20)
d['279'] = mk_handle('Slime Handle',  1.20,  2,  70, 'slimy',  18)
d['280'] = mk_binding('Slime Binding', 80, 'slimy',   15)

print(f'After additions: {len(d)} items')

# ── SANITY CHECKS ─────────────────────────────────────────────────────────────
# Molds 190-198 must be intact
for mid in range(190, 199):
    assert str(mid) in d, f'Missing mold {mid}!'
    name = d[str(mid)].get('name', '')
    assert 'Mold' in name, f'ID {mid} not a mold: {name}'
print('Molds 190-198 intact')

assert '204' in d and d['204']['name'] == 'Part Maker'
print('Part Maker OK')
d['205'] = {'name': 'Part Combiner', 'stackable': False, 'max_stack': 1, 'sell_price': 20, 'placeable': 'part_combiner'}
assert '205' in d and d['205']['name'] == 'Part Combiner'
print('Part Combiner OK')

# Count part types
part_counts = {}
for v in d.values():
    slot = v.get('part_stats', {}).get('slot')
    if slot:
        part_counts[slot] = part_counts.get(slot, 0) + 1
print('Parts by slot:', part_counts)

with open(path, 'w') as f:
    json.dump(d, f, indent=2)
print(f'Wrote {path}')

# Features Plan
> Detailed breakdown of upcoming game systems. Work top-down within each task.
> Mark `[x]` when done.

---

## Quick Notes / Findings

- **Stone brick** (item 21): Made at furnace from 3 stone → 4 bricks. Currently used in zero recipes.
  Add it to: Stone Brick Wall recipe, Stone Brick Floor, possibly higher-tier armor.
- **Bed spawn**: Server-side `use_bed()` already sets `players[pid]["bed_spawn"]`.
  BUT: There is **no player death / respawn system** at all. Health can hit 0 and nothing happens.
  Needs both: death detection loop in game_sync + respawn handler.
- **Defense stat**: No defense field exists yet; damage is subtracted from health raw.

---

## Task 1 — Stone Brick Uses  *(DONE)*

Stone brick is a dead end right now. Fix it:
- [x] Add **Stone Brick Wall ×4** recipe at crafting table (3 stone brick → 4 stone_brick_wall)
- [x] Add **Stone Brick Floor ×4** recipe at crafting table (2 stone brick → 4 stone_brick_floor)
- [x] Update **Stone Helm** recipe: uses 3 Stone Brick + 1 Slime Ball (instead of raw stone)

---

## Task 2 — Player Death & Respawn  ✅ DONE

Currently health can hit 0 with no consequence.

### What to implement:
- [x] **Death detection** in `server/game_state/game_sync.py` send_game_state loop:
  When `me["health"] <= 0` and not already `dead=True`:
    - Set `players[pid]["dead"] = True`
    - Include `{"dead": True}` in self_data payload
- [x] **Respawn handler** in `server/game_state/game_sync.py`:
  On the tick after dead=True: teleport to `bed_spawn` if set, else `[0.0, 0.0]`
  Restore `health = health_max * 0.3` (respawn with 30% HP)
  Clear `dead` flag
- [x] **Save bed_spawn** to player save file in `server/player_save.py`
- [x] **Client death screen** in `client/rendering/hud.py`:
  When `config.player_dead` is True, overlay "You Died — respawning…" in dark red

### Files:
- `server/game_state/game_sync.py`
- `server/player_save.py`
- `client/config.py` — add `player_dead: bool = False`
- `client/networking/handlers.py` — read `dead` field from self_data
- `client/rendering/hud.py` (or wherever HUD is drawn)

---

## Task 3 — Armor Defense Stat  ✅ DONE

Armor currently only boosts `health_max`. Add a proper `defense` stat that reduces incoming damage.

### What to implement:
- [x] Add `"defense": N` to armor items in `server/items.json`:
  - Scrap Cap/Vest/Leggings: 1 each
  - Stone Helm: 3  | Reed Tunic: 2  | Bone Vest: 3  | Iron Helm: 5  | Iron Chestplate: 8
  - Bone Bracers: 2 | Iron Bracers: 3 | Reed Leggings: 2 | Bone Leggings: 3
  - Leaf Sandals: 1 | Iron Boots: 3 | Leaf Cloak: 1 | Iron Chestplate: 8
- [x] `server/item_data.py` — add `defense` to `get_equip_bonuses()` aggregation
- [x] `server/game_state/game_sync.py` — include `defense` in self_data
- [x] `server/network/combat.py` — subtract defense from incoming damage:
  `damage_taken = max(1.0, raw_damage - total_defense)`
  Also in mob attack path in `server/mobs/mob_manager.py`
- [x] `client/config.py` — add `player_defense: int = 0`
- [x] `client/networking/handlers.py` — read defense from self_data
- [x] `client/rendering/hud.py` — Minecraft-style HUD redesign (May 2026): HP bar + SP bar + DEF row + EXP bar stacked above hotbar at full hotbar width; coins right of hotbar; top-right panel removed. `draw_hud(screen, w, h)` signature updated.

---

## Task 4 — Durability System  ✅ DONE

Slots become `[item_id, qty, {"dur": current, "dur_max": max}]` for tools/weapons/armor.
Stackable items (resources) never have durability.

### What to implement:
- [x] Add `"durability": N` to tools/weapons/armor in `server/items.json`
  - Scrap tier: 30 | Wood tier: 60 | Stone/Bone tier: 80 | Iron tier: 120
  - Armor same scale per tier
- [x] `server/game_state/crafting.py` — when crafting a durable item, attach `{"dur": max, "dur_max": max}` meta
- [x] `server/network/tcp_routes.py` gather handler — deduct 1 durability on each tool hit
  At 0: remove item from slot
- [x] `server/network/combat.py` — deduct 1 durability from equipped weapon on hit
  At 0: remove from equip slot
- [x] `server/network/combat.py` (mob→player damage) — deduct 1 from each equipped armor piece
- [x] `server/mobs/mob_manager.py` — mob attack on player also triggers armor durability drain
- [x] **Repair recipe**: at crafting table (Repair tab), item + base mats → item with full durability
  `server/game_state/repair.py` + `_handle_repair_item` in tcp_state_handlers_v2; client `rendering/repair.py`
- [x] **Client display**: draw small durability bar under item icon in inventory + hotbar
  Color: green > yellow > red
- [x] `client/rendering/inventory.py` — add dur bar in `_draw_slot()`

---

## Task 5 — New Ore Materials + Distance-Based Rarity  ✅ DONE

### New ores and progression:

| Ore | Item ID | Bar Item | Bar ID | Min chunk dist | Biomes | Tool required |
|-----|---------|----------|--------|---------------|--------|--------------|
| Copper Ore | 14 (reuse?) → use 22 | Copper Bar | 23 | 8 | mountain, plains | pickaxe |
| Tin Ore | 24 | Tin Bar | 25 | 8 | mountain, desert | pickaxe |
| Silver Ore | 26 | Silver Bar | 27 | 20 | mountain, tundra | pickaxe_stone |
| Gold Ore | 28 | Gold Bar | 29 | 30 | mountain, desert | pickaxe_stone |
| Crystal | 15 (reuse?) → use 15 | Crystal Shard | already 15? | 40 | mountain | pickaxe_iron |
| Obsidian | 16 | Obsidian Shard | 16 | 50 | mountain (volcanic, deep) | pickaxe_iron |

> **Note**: Item IDs 14 and 15 are currently unset (check items.json). Use 22-29 for new raw materials
> to keep the 1-14 range as raw non-metallic resources.

**New bars in items.json**:
- 22: Copper Ore (raw mineral)
- 23: Tin Ore
- 24: Silver Ore
- 25: Gold Ore
- 26: Crystal Shard (mined directly, no smelting)
- 27: Obsidian Shard (mined directly)
- In processed range (20-29): Copper Bar (keep 20=Iron Bar, 21=Stone Brick)
  → shift bars to 22=Copper Bar, 23=Tin Bar, 24=Bronze Bar, 25=Silver Bar, 26=Gold Bar

Actually — cleaner ID scheme:
```
Raw ores (1-19):
  1  = Slime Ball
  2  = Wood Log
  3  = Stone
  4  = Stick
  5  = Herb
  6  = Mushroom
  7  = Cactus Spine
  8  = Snow Crystal
  9  = Seashell
  10 = Reed
  11 = Bone
  12 = Coal
  13 = Iron Ore
  14 = Copper Ore      ← NEW
  15 = Tin Ore         ← NEW
  16 = Silver Ore      ← NEW
  17 = Gold Ore        ← NEW
  18 = Crystal Shard   ← NEW (mined, no smelt needed)
  19 = Obsidian Shard  ← NEW (mined, no smelt needed)

Processed/bars (20-29):
  20 = Iron Bar
  21 = Stone Brick
  22 = Copper Bar      ← NEW
  23 = Tin Bar         ← NEW
  24 = Bronze Bar      ← NEW (alloy: 1 Copper Bar + 1 Tin Bar)
  25 = Silver Bar      ← NEW
  26 = Gold Bar        ← NEW
  27 = Steel Bar       ← NEW (alloy: 1 Iron Bar + 1 Coal)
```

### Progression path:
Scrap → Stone → Copper → Bronze (Cu+Sn) → Iron → Steel (Fe+Coal) → Gold (jewelry) → Crystal/Obsidian (endgame)

### Weapon/Tool/Armor additions per new tier:
Each tier needs weapons (sword, dagger, mace), tools (axe, pickaxe), and armor (head, chest, legs, feet).

| Tier | Weapons | Tools | Armor |
|------|---------|-------|-------|
| Copper | Copper Sword (52+n), Copper Dagger | Copper Axe, Copper Pickaxe | Copper Helm/Vest/Legs |
| Bronze | Bronze Sword, Bronze Mace | Bronze Axe, Bronze Pickaxe | Bronze Helm/Vest/Legs |
| Steel | Steel Sword, Steel Mace | Steel Axe, Steel Pickaxe | Steel Helm/Vest/Legs |
| Gold | Gold Shortsword | Gold Pickaxe (very fast) | Gold Crown, Gold Chestplate |
| Obsidian | Obsidian Blade (high dmg, brittle) | Obsidian Pick (fast) | — |
| Crystal | Crystal Wand (magic dmg?) | — | Crystal Helm |

> **ID ranges for new items**:
> - Items 52-58 = current tier weapons (keep)
> - Items 59-70 = new Copper/Bronze/Steel/Gold/Obsidian/Crystal weapons
> - Items 102-107 = current tier tools (keep)
> - Items 108-120 = new Copper/Bronze/Steel/Gold tools
> - Items 152-163 = current armor (keep)
> - Items 153+ extend for new armor tiers

### Distance-based generation:

In `server/world/resource_nodes.py` — add `"min_dist": N` to node defs:
```python
"copper_ore": {"min_dist": 8,  "hp": 5, "yields": [(14, 1, 2)], "tool": "pickaxe", ...}
"tin_ore":    {"min_dist": 8,  ...}
"silver_ore": {"min_dist": 20, "hp": 7, "tool": "pickaxe_stone", ...}
"gold_ore":   {"min_dist": 30, "hp": 8, "tool": "pickaxe_stone", ...}
"crystal":    {"min_dist": 40, "hp": 10, "tool": "pickaxe_iron", ...}
"obsidian":   {"min_dist": 50, "hp": 12, "tool": "pickaxe_iron", ...}
```

In `generate_resource_nodes(cx, cy, biome_ids)`:
```python
dist = math.sqrt(cx*cx + cy*cy)
# Then per node_type: if dist < defn.get("min_dist", 0): continue
```

Add new tool tier `"pickaxe_iron": {107}` (only iron pickaxe for crystal/obsidian).

### New furnace recipes:
```
Copper Bar  : 2 Copper Ore + 1 Coal
Tin Bar     : 2 Tin Ore + 1 Coal
Bronze Bar  : 1 Copper Bar + 1 Tin Bar   (alloy in furnace)
Silver Bar  : 2 Silver Ore + 1 Coal
Gold Bar    : 2 Gold Ore + 1 Coal
Steel Bar   : 1 Iron Bar + 1 Coal        (alloy in furnace)
```

### Files to touch:
- `server/items.json`             — add 14 new raw/bar items + all new weapons/tools/armor
- `server/recipes.json`           — add ~30 new recipes (smelt, alloy, weapon, tool, armor)
- `server/world/resource_nodes.py`— add 6 new node types + `min_dist` check
- `client/networking/handlers.py` — add new node types to `_NODE_MAX_HP`
- `client/rendering/item_art.py`  — add art for all new items
- `server/game_state/game_sync.py`— (no changes if item IDs are new)
- `client/input/controls.py`      — add new tool IDs to `_TOOL_ITEMS`/`_TOOL_DAMAGE`

**IMPORTANT**: Bump `NODES_VERSION` in `dyn_chunk_gen.py` after updating NODE_TYPES so
existing chunks regenerate their node lists.

---

## Task 6 — Chest System  ✅ DONE

### Design:
- Item 39: Chest (placeable)
- `placed_objects` entry gains `"chest_inv": [null * 27]` (27-slot chest inventory)
- Interaction: F near chest → open/close chest UI overlay
- Chest UI: 3×9 grid similar to inventory bag section
- Drag-and-drop between chest and player inventory

### What to implement:

**Server**:
- [x] Add chest to `PLACEABLE_ITEMS` in `placed_objects.py`: `40: "chest"` *(legacy ID; migrates to 203 in Task 7)*
- [x] On `place_object("chest", ...)` — init `entry["chest_inv"] = [None] * 27`
- [x] New TCP message type `"chest_swap"`:
  `{"type": "chest_swap", "uid": "...", "chest_slot": N, "player_slot": M}`
  Swaps item between chest slot and player slot (server validates proximity)
- [x] `get_nearby()` — include `chest_inv` in payload for open chests
- [x] Save chest_inv with `_save()`

**Client**:
- [x] `config.py` — add `open_chest_uid: str | None = None`
- [x] `controls.py` — F key: if nearby object is chest → set `config.open_chest_uid`
- [x] New `client/rendering/chest.py` — draw chest inventory overlay
  (reuse inventory slot drawing helpers)
- [x] `controls.py` — handle drag/drop between chest UI and player inventory

---

## Item Dictionary — Full Tier Audit (May 2026)

> All items that exist or need to exist. Used as the master reference for IDs, stats, and recipes.
> Stations: `hand` | `crafting_table` | `furnace` | `alloy_forge`
> Slot types: `weapon` | `tool` | `head` | `chest` | `arms` | `pants` | `shoes` | `back`
> Wand slot_type = `weapon`; category = `wand` (distinct art + recipe flavour)

---

### Raw Materials (1–19)
| ID | Name | Source | Sell |
|----|------|--------|------|
| 1  | Coin | dropped/sold | — |
| 2  | Wood | tree | 3 |
| 3  | Stone | stone_deposit | 3 |
| 4  | Stick | hand-craft from Wood | 1 |
| 5  | Herb | herb_patch | 5 |
| 6  | Mushroom | mushroom | 5 |
| 7  | Cactus Spine | cactus | 4 |
| 8  | Snow Crystal | snow_crystal | 8 |
| 9  | Seashell | seashell_bed | 6 |
| 10 | Reed | reed_cluster | 3 |
| 11 | Bone | bone_pile | 5 |
| 12 | Coal | coal_deposit | 4 |
| 13 | Iron Ore | iron_ore | 6 |
| 14 | Slime Ball | slime drop | 2 |
| 15 | Copper Ore | copper_ore node | 8 |
| 16 | Tin Ore | tin_ore node | 8 |
| 17 | Silver Ore | silver_ore node | 12 |
| 18 | Gold Ore | gold_ore node | 18 |
| 19 | Crystal Shard | crystal node | 30 |
| 28 | Obsidian Shard | obsidian node | 40 |
| 29 | Carbon | furnace (coal) | 4 |

### Processed Materials (20–29)
| ID | Name | Recipe | Sell |
|----|------|--------|------|
| 20 | Iron Bar | furnace: 2 Iron Ore + 1 Coal | 14 |
| 21 | Stone Brick | furnace: 3 Stone → 4 bricks | 8 |
| 22 | Copper Bar | furnace: 2 Copper Ore + 1 Coal | 18 |
| 23 | Tin Bar | furnace: 2 Tin Ore + 1 Coal | 18 |
| 24 | Bronze Bar | furnace: 1 Copper Bar + 1 Tin Bar | 30 |
| 25 | Silver Bar | furnace: 2 Silver Ore + 1 Coal | 28 |
| 26 | Gold Bar | furnace: 2 Gold Ore + 1 Coal | 45 |
| 27 | Steel Bar | alloy_forge: 1 Iron Bar + 1 Carbon | 35 |

---

### Weapons (50–82)  — Tiers: Scrap < Wood/Bone/Stone < Iron < Copper < Bronze < Steel < Gold < Crystal/Obsidian + Wands

| ID | Name | Tier | ATK | DUR | Sell | Recipe ingredients | Station |
|----|------|------|-----|-----|------|-------------------|---------|
| 50 | Scrap Knife | scrap | 4 | 40 | 3 | — | hand |
| 51 | Scrap Club | scrap | 7 | 40 | 5 | — | hand |
| 52 | Wooden Sword | wood | 8 | 65 | 20 | 3 Wood + 1 Stick | crafting_table |
| 53 | Wooden Mace | wood | 12 | 65 | 22 | 3 Wood + 1 Stick | crafting_table |
| 54 | Bone Dagger | bone | 15 | 90 | 35 | 2 Bone + 1 Stick | crafting_table |
| 55 | Stone Mace | stone | 22 | 90 | 50 | 3 Stone + 1 Stick | crafting_table |
| 56 | Iron Dagger | iron | 28 | 120 | 48 | 2 Iron Bar + 1 Stick | crafting_table |
| 57 | Iron Sword | iron | 38 | 120 | 60 | 3 Iron Bar + 1 Stick | crafting_table |
| 58 | Iron Mace | iron | 50 | 120 | 75 | 3 Iron Bar + 1 Iron Bar | crafting_table |
| 59 | Copper Sword | copper | 52 | 150 | 90 | 3 Copper Bar + 1 Stick | crafting_table |
| 60 | Bronze Sword | bronze | 65 | 200 | 115 | 3 Bronze Bar + 1 Stick | crafting_table |
| 61 | Steel Sword | steel | 82 | 300 | 145 | 3 Steel Bar + 1 Stick | alloy_forge |
| 62 | Gold Shortsword | gold | 92 | 180 | 170 | 3 Gold Bar + 1 Stick | alloy_forge |
| 63 | Crystal Wand | crystal | 118 | 350 | 260 | 3 Crystal Shard + 1 Silver Bar + 1 Stick | alloy_forge |
| 64 | Obsidian Blade | obsidian | 145 | 280 | 260 | 3 Obsidian Shard + 1 Carbon + 1 Stick | alloy_forge |
| 65 | Copper Dagger | copper | 38 | 150 | 55 | 2 Copper Bar + 1 Stick | crafting_table |
| 66 | Copper Mace | copper | 62 | 150 | 80 | 3 Copper Bar + 1 Bone | crafting_table |
| 67 | Bronze Dagger | bronze | 48 | 200 | 75 | 2 Bronze Bar + 1 Stick | crafting_table |
| 68 | Bronze Mace | bronze | 78 | 200 | 100 | 3 Bronze Bar + 1 Bone | crafting_table |
| 69 | Steel Dagger | steel | 60 | 300 | 110 | 2 Steel Bar + 1 Iron Bar + 1 Stick | alloy_forge |
| 70 | Steel Mace | steel | 98 | 300 | 145 | 3 Steel Bar + 1 Iron Bar + 1 Bone | alloy_forge |
| **71** | **Gold Dagger** | gold | 78 | 200 | 145 | 2 Gold Bar + 1 Stick | alloy_forge |
| **72** | **Gold Mace** | gold | 122 | 180 | 190 | 3 Gold Bar + 1 Iron Bar | alloy_forge |
| **73** | **Obsidian Dagger** | obsidian | 112 | 280 | 210 | 2 Obsidian Shard + 1 Carbon + 1 Stick | alloy_forge |
| **74** | **Obsidian Mace** | obsidian | 168 | 260 | 290 | 3 Obsidian Shard + 2 Carbon | alloy_forge |
| **75** | **Crystal Sword** | crystal | 142 | 350 | 260 | 3 Crystal Shard + 1 Silver Bar + 1 Stick | alloy_forge |
| **76** | **Crystal Dagger** | crystal | 105 | 350 | 220 | 2 Crystal Shard + 1 Silver Bar + 1 Stick | alloy_forge |
| **77** | **Crystal Mace** | crystal | 158 | 330 | 280 | 3 Crystal Shard + 1 Gold Bar | alloy_forge |
| **78** | **Nature Wand** | wand-tier1 | 22 | 80 | 25 | 2 Wood + 2 Herb + 1 Mushroom + 1 Stick | crafting_table |
| **79** | **Bone Wand** | wand-tier2 | 40 | 100 | 45 | 2 Bone + 2 Mushroom + 1 Stick | crafting_table |
| **80** | **Moon Wand** | wand-tier3 | 78 | 200 | 165 | 2 Silver Bar + 1 Snow Crystal + 1 Stick | alloy_forge |
| **81** | **Storm Wand** | wand-tier4 | 108 | 250 | 215 | 2 Gold Bar + 1 Cactus Spine + 1 Stick | alloy_forge |
| **82** | **Shadow Wand** | wand-tier5 | 148 | 300 | 295 | 2 Obsidian Shard + 1 Crystal Shard + 1 Carbon + 1 Stick | alloy_forge |

---

### Tools (100–119)

| ID | Name | Tier | DUR | Sell | Recipe | Station |
|----|------|------|-----|------|--------|---------|
| 100 | Scrap Axe | scrap | 30 | 4 | — | hand |
| 101 | Scrap Pickaxe | scrap | 30 | 4 | — | hand |
| 102 | Wooden Axe | wood | 60 | 8 | 3 Wood + 2 Stick | crafting_table |
| 103 | Stone Axe | stone | 80 | 14 | 3 Stone + 2 Stick | crafting_table |
| 104 | Iron Axe | iron | 120 | 30 | 3 Iron Bar + 2 Stick | crafting_table |
| 105 | Wooden Pickaxe | wood | 60 | 8 | 3 Wood + 2 Stick | crafting_table |
| 106 | Stone Pickaxe | stone | 80 | 14 | 3 Stone + 2 Stick | crafting_table |
| 107 | Iron Pickaxe | iron | 120 | 30 | 3 Iron Bar + 2 Stick | crafting_table |
| 108 | Copper Axe | copper | 150 | 40 | 3 Copper Bar + 2 Stick | crafting_table |
| 109 | Copper Pickaxe | copper | 150 | 40 | 3 Copper Bar + 2 Stick | crafting_table |
| 110 | Bronze Axe | bronze | 200 | 55 | 3 Bronze Bar + 2 Stick | crafting_table |
| 111 | Bronze Pickaxe | bronze | 200 | 55 | 3 Bronze Bar + 2 Stick | crafting_table |
| 112 | Steel Axe | steel | 300 | 80 | 3 Steel Bar + 2 Stick | alloy_forge |
| 113 | Steel Pickaxe | steel | 300 | 80 | 3 Steel Bar + 2 Stick | alloy_forge |
| 114 | Gold Pickaxe | gold | 200 | 95 | 3 Gold Bar + 2 Stick | alloy_forge |
| 115 | Crystal Pick | crystal | 400 | 140 | 3 Crystal Shard + 2 Stick + 1 Silver Bar | alloy_forge |
| **116** | **Gold Axe** | gold | 200 | 95 | 3 Gold Bar + 2 Stick | alloy_forge |
| **117** | **Crystal Axe** | crystal | 400 | 140 | 3 Crystal Shard + 2 Stick + 1 Silver Bar | alloy_forge |
| **118** | **Obsidian Axe** | obsidian | 350 | 170 | 3 Obsidian Shard + 2 Stick + 1 Carbon | alloy_forge |
| **119** | **Obsidian Pickaxe** | obsidian | 350 | 170 | 3 Obsidian Shard + 2 Stick + 1 Carbon | alloy_forge |

---

### Armor — Head (150–159)
| ID | Name | Tier | HP | DEF | DUR | Sell |
|----|------|------|----|-----|-----|------|
| 150 | Scrap Cap | scrap | 5 | 1 | 30 | 2 |
| 151 | Stone Helm | stone | 20 | 3 | 80 | 18 |
| 152 | Iron Helm | iron | 40 | 6 | 120 | 42 |
| 153 | Copper Helm | copper | 32 | 5 | 150 | 55 |
| 154 | Bronze Helm | bronze | 50 | 8 | 200 | 85 |
| 155 | Steel Helm | steel | 68 | 11 | 300 | 120 |
| 156 | Gold Crown | gold | 45 | 7 | 180 | 150 |
| **157** | **Crystal Helm** | crystal | 90 | 13 | 350 | 280 |
| **158** | **Obsidian Helm** | obsidian | 60 | 24 | 300 | 330 |

### Armor — Chest (160–169)
| ID | Name | Tier | HP | DEF | DUR | Sell |
|----|------|------|----|-----|-----|------|
| 160 | Scrap Vest | scrap | 8 | 1 | 30 | 2 |
| 161 | Reed Tunic | reed | 12 | 2 | 60 | 12 |
| 162 | Bone Vest | bone | 20 | 3 | 90 | 22 |
| 163 | Iron Chestplate | iron | 55 | 8 | 120 | 55 |
| 164 | Copper Vest | copper | 45 | 6 | 150 | 70 |
| 165 | Bronze Vest | bronze | 70 | 10 | 200 | 110 |
| 166 | Steel Vest | steel | 95 | 14 | 300 | 160 |
| **167** | **Gold Chestplate** | gold | 60 | 9 | 180 | 175 |
| **168** | **Crystal Chestplate** | crystal | 125 | 16 | 350 | 370 |
| **169** | **Obsidian Chestplate** | obsidian | 90 | 32 | 300 | 450 |

### Armor — Arms (170–179)
| ID | Name | Tier | HP | ATK | DEF | DUR | Sell |
|----|------|------|----|-----|-----|-----|------|
| 170 | Bone Bracers | bone | 12 | 5 | 2 | 90 | 18 |
| 171 | Iron Bracers | iron | 10 | 8 | 3 | 120 | 45 |
| 172 | Copper Bracers | copper | 15 | 10 | 4 | 150 | 55 |
| 173 | Bronze Bracers | bronze | 22 | 14 | 6 | 200 | 80 |
| 174 | Steel Bracers | steel | 30 | 18 | 8 | 300 | 120 |
| **175** | **Gold Bracers** | gold | 25 | 14 | 6 | 180 | 115 |
| **176** | **Crystal Bracers** | crystal | 55 | 24 | 10 | 350 | 215 |
| **177** | **Obsidian Bracers** | obsidian | 38 | 20 | 16 | 300 | 260 |

### Armor — Legs (180–189)
| ID | Name | Tier | HP | DEF | DUR | Sell |
|----|------|------|----|-----|-----|------|
| 180 | Scrap Leggings | scrap | 5 | 1 | 30 | 2 |
| 181 | Reed Leggings | reed | 10 | 2 | 60 | 10 |
| 182 | Bone Leggings | bone | 18 | 3 | 90 | 20 |
| 183 | Copper Leggings | copper | 30 | 5 | 150 | 60 |
| 184 | Bronze Leggings | bronze | 48 | 8 | 200 | 90 |
| 185 | Steel Leggings | steel | 75 | 12 | 300 | 130 |
| 186 | Iron Leggings | iron | 38 | 5 | 120 | 50 |
| **187** | **Gold Leggings** | gold | 48 | 8 | 180 | 158 |
| **188** | **Crystal Leggings** | crystal | 108 | 14 | 350 | 325 |
| **189** | **Obsidian Leggings** | obsidian | 75 | 28 | 300 | 400 |

### Armor — Feet (190–199)
| ID | Name | Tier | HP | SPD | DEF | DUR | Sell |
|----|------|------|----|-----|-----|-----|------|
| 190 | Leaf Sandals | leaf | 6 | +0.05 | 1 | 60 | 5 |
| 191 | Iron Boots | iron | 20 | +0.05 | 4 | 120 | 38 |
| 192 | Bronze Boots | bronze | 30 | +0.06 | 7 | 200 | 75 |
| 193 | Steel Boots | steel | 25 | +0.08 | 6 | 300 | 110 |
| 194 | Copper Boots | copper | 16 | +0.08 | 3 | 150 | 55 |
| **195** | **Gold Boots** | gold | 22 | +0.10 | 5 | 180 | 130 |
| **196** | **Crystal Boots** | crystal | 40 | +0.10 | 8 | 350 | 245 |
| **197** | **Obsidian Boots** | obsidian | 28 | -0.03 | 14 | 300 | 295 |

---

### Mining Rebalance

| Node | HP | Tool required | Stone Pick (dmg=2) | Iron (4) | Copper (5) | Bronze (7) | Steel (8) | Gold (9) | Crystal (12) | Obsidian (18) |
|------|----|--------------|---|---|---|---|---|---|---|---|
| stone_deposit | 20 | pickaxe | 10 hits | 5 | 4 | 3 | 3 | 3 | 2 | 2 |
| coal_deposit | 20 | pickaxe | 10 | 5 | 4 | 3 | 3 | 3 | 2 | 2 |
| iron_ore | 20 | pickaxe_stone | 10 | 5 | 4 | 3 | 3 | 3 | 2 | 2 |
| copper_ore | 25 | pickaxe_stone | 13 | 7 | 5 | 4 | 4 | 3 | 3 | 2 |
| tin_ore | 25 | pickaxe_stone | 13 | 7 | 5 | 4 | 4 | 3 | 3 | 2 |
| silver_ore | 30 | pickaxe_iron | — | 8 | 6 | 5 | 4 | 4 | 3 | 2 |
| gold_ore | 35 | pickaxe_iron | — | 9 | 7 | 5 | 5 | 4 | 3 | 2 |
| crystal | 40 | pickaxe_steel | — | — | — | — | 5 | 5 | 4 | 3 |
| obsidian | 50 | pickaxe_steel | — | — | — | — | 7 | 6 | 5 | 3 |

> Obsidian Pick (2401) deals 18 dmg = 3 hits on obsidian (50 HP). Crystal Pick (2351) = 5 hits.
> HP values raised to prevent instamine even with the highest-damage pick (obsidian, 18 dmg).
> "—" = tool tier insufficient (not that the node can be one-shot).

---

## Target ID Scheme

> The ID layout all new work migrates **to** in Task 7. Nothing in live code uses these yet.
> Legacy items are mapped to target IDs via `tools/migrate_ids.py`.

```
1             Coin  (never changes)

Raw Materials (10–99)
  10–19       Organics:    Wood(10)  Stone(11)  Stick(12)  Herb(13)  Mushroom(14)
                           Cactus Spine(15)  Snow Crystal(16)  Seashell(17)  Reed(18)  Bone(19)
  20–29       Mining:      Coal(20)  Iron Ore(21)  Copper Ore(22)  Tin Ore(23)  Silver Ore(24)
                           Gold Ore(25)  Crystal Shard(26)  Obsidian Shard(27)  Slime Ball(28)  [29 spare]
  30–49       Future world drops
  50–69       Gems (boss drops — source TBD):
                Fire Gem(50)  Ice Gem(51)  Life Gem(52)  Swift Gem(53)
                Fortune Gem(54)  Shadow Gem(55)  Auto-Smelt Gem(56)  [57–69 reserved]
  70–99       Reserved

Processed Materials (100–149)
  100–109     Basic bars:  Iron Bar(100)  Copper Bar(101)  Tin Bar(102)
                           Silver Bar(103)  Gold Bar(104)
  110–119     Alloys:      Bronze Bar(110)  Steel Bar(111)
  120–129     Special:     Stone Brick(120)  Carbon(121)
  130–149     Reserved

Crafting Parts (150–199)
  150–159     Handles:     Wood Handle(150)  Bone Handle(151)
                           Metal Handle(152)  Refined Handle(153)
  160–169     Blades:      Iron Blade(160)  Bronze Blade(161)  Steel Blade(162)  Crystal Blade(163)
  170–179     Heads:       Iron Axe Head(170)  Steel Axe Head(171)  Obsidian Axe Head(172)
                           Iron Pick Head(173)  Steel Pick Head(174)  Obsidian Pick Head(175)
  180–187     Armor parts: Iron Plate(180)  Steel Plate(181)  Crystal Plate(182)  Obsidian Plate(183)
                           Padding(184)  Clasp(185)  Gold Plate(186)  Bronze Plate(187)
  188–189     Wand cores:  Rough Crystal(188)  Refined Crystal(189)  Shadow Core(189)*
  190–199     Molds (consumed on combine, crafted cheaply at crafting table):
                Sword Mold(190)  Dagger Mold(191)  Axe Mold(192)  Pickaxe Mold(193)
                Helm Mold(194)  Chest Mold(195)  Arms Mold(196)
                Leg Mold(197)  Feet Mold(198)  [199 reserved]

Stations & Placeables (200–299)
  200–219     Stations:    Crafting Table(200)  Furnace(201)  Alloy Forge(202)
                           Chest(203)  Part Maker(204)  Part Combiner(205)  Embedder(206)
  220–249     Furniture:   Bed(220)
  250–299     Reserved

Weapons (1000–1999)
  1000–1049   Scrap/starter:    Scrap Knife(1000)  Scrap Club(1001)
  1050–1099   Wood/Bone/Stone:  Wooden Sword(1050)  Wooden Mace(1051)  Bone Dagger(1052)  Stone Mace(1053)
  1100–1149   Iron:             Iron Dagger(1100)  Iron Sword(1101)  Iron Mace(1102)
  1150–1199   Copper:           Copper Sword(1150)  Copper Dagger(1151)  Copper Mace(1152)
  1200–1249   Bronze:           Bronze Sword(1200)  Bronze Dagger(1201)  Bronze Mace(1202)
  1250–1299   Steel:            Steel Sword(1250)  Steel Dagger(1251)  Steel Mace(1252)
  1300–1349   Gold:             Gold Shortsword(1300)  Gold Dagger(1301)  Gold Mace(1302)
  1350–1399   Crystal:          Crystal Sword(1350)  Crystal Dagger(1351)  Crystal Mace(1352)
  1400–1449   Obsidian:         Obsidian Blade(1400)  Obsidian Dagger(1401)  Obsidian Mace(1402)
  1500–1549   Wands:            Nature Wand(1500)  Bone Wand(1501)  Moon Wand(1502)
                                Storm Wand(1503)  Shadow Wand(1504)  Crystal Wand(1505)
  1550–1999   Reserved

Tools (2000–2999)
  2000–2049   Scrap:      Scrap Axe(2000)  Scrap Pickaxe(2001)
  2050–2099   Wood/Stone: Wooden Axe(2050)  Stone Axe(2051)  Wooden Pickaxe(2052)  Stone Pickaxe(2053)
  2100–2149   Iron:       Iron Axe(2100)  Iron Pickaxe(2101)
  2150–2199   Copper:     Copper Axe(2150)  Copper Pickaxe(2151)
  2200–2249   Bronze:     Bronze Axe(2200)  Bronze Pickaxe(2201)
  2250–2299   Steel:      Steel Axe(2250)  Steel Pickaxe(2251)
  2300–2349   Gold:       Gold Axe(2300)  Gold Pickaxe(2301)
  2350–2399   Crystal:    Crystal Axe(2350)  Crystal Pickaxe(2351)
  2400–2449   Obsidian:   Obsidian Axe(2400)  Obsidian Pickaxe(2401)
  2450–2999   Reserved

Armor (3000–3699)           10 slots per tier per slot type
  3000–3099   Head          (scrap/stone/iron/copper/bronze/steel/gold/crystal/obsidian)
  3100–3199   Chest
  3200–3299   Arms
  3300–3399   Legs
  3400–3499   Feet
  3500–3599   Back / Cloaks
  3600–3649   Rings
  3650–3699   Necklaces

Consumables (4000–4099)
  4000–4019   Drinks:  Herb Tea(4000) ...
  4020–4099   Reserved
```

---

## Task 7 — ID Migration  ✅ DONE

One-time migration to the Target ID Scheme. After this, no more cramped ID ranges.

### Steps:
- [x] Write `tools/migrate_ids.py` — reads items.json + recipes.json, applies remap dict, writes both
- [x] `client/rendering/item_art.py` — remap all `_ITEM_FNS` dict keys
- [x] `server/world/resource_nodes.py` — remap `yields` IDs + `TOOL_ITEMS` / `TOOL_DAMAGE` keys
- [x] `client/input/controls.py` — remap `_TOOL_ITEMS` / `_TOOL_DAMAGE` keys
- [x] `server/mobs/mob_manager.py` — remap `DROP_ITEM_ID` and any loot tables
- [x] `server/game_state/placed_objects.py` — remap station item IDs in `PLACEABLE_ITEMS`
- [x] **Delete `world_chunks_v3/`** — saved chunks may embed legacy item IDs in node yields;
  easiest fix is to wipe and let them regenerate on next login

---

## Task 8 — Part Maker  *(after ID Migration)*  ✅ DONE

A normal recipe station — all recipes visible, no mystery. Converts raw materials into named
components consumed by the Part Combiner.

### Server:
- [x] Add Part Maker item (ID 204) to `items.json` + `placed_objects.py`
- [x] Add all part items (IDs 150–189) to `items.json` with `"part_stats"` field
- [x] Add all Mold items (IDs 190–198) to `items.json` (stackable, max_stack 10, cheaply crafted)
- [x] Add all Part Maker recipes to `recipes.json` with `"station": "part_maker"`
- [x] Add Mold recipes to `recipes.json` with `"station": "crafting_table"` (2 Clay → each mold type)

### Client:
- [x] Add `part_maker` branch to `_recipes_for_popup` in `crafting.py`
- [x] Item art: simple flat icons for all parts (thin rectangles, use `_bar_item` variants)

### Parts produced:
| Target ID | Name | Recipe (at Part Maker) | Qty out |
|---|---|---|---|
| 150 | Wood Handle | 2 Wood | 2 |
| 151 | Bone Handle | 2 Bone | 2 |
| 152 | Metal Handle | 1 Iron Bar | 2 |
| 153 | Refined Handle | 1 Steel Bar | 2 |
| 160 | Iron Blade | 2 Iron Bar | 1 |
| 161 | Bronze Blade | 2 Bronze Bar | 1 |
| 162 | Steel Blade | 2 Steel Bar | 1 |
| 163 | Crystal Blade | 2 Crystal Shard + 1 Silver Bar | 1 |
| 170 | Iron Axe Head | 3 Iron Bar | 1 |
| 171 | Steel Axe Head | 3 Steel Bar | 1 |
| 172 | Obsidian Axe Head | 3 Obsidian Shard + 1 Carbon | 1 |
| 173 | Iron Pick Head | 3 Iron Bar | 1 |
| 174 | Steel Pick Head | 3 Steel Bar | 1 |
| 175 | Obsidian Pick Head | 3 Obsidian Shard + 1 Carbon | 1 |
| 180 | Iron Plate | 2 Iron Bar | 1 |
| 181 | Steel Plate | 2 Steel Bar | 1 |
| 182 | Crystal Plate | 2 Crystal Shard | 1 |
| 183 | Obsidian Plate | 2 Obsidian Shard | 1 |
| 184 | Padding | 3 Reed | 2 |
| 185 | Clasp | 1 Iron Bar | 3 |
| 190 | Rough Crystal | 1 Crystal Shard | 1 |
| 191 | Refined Crystal | 2 Crystal Shard + 1 Silver Bar | 1 |
| 192 | Shadow Core | 2 Obsidian Shard + 1 Carbon | 1 |

---

## Task 9 — Part Combiner  *(after Part Maker)*  ✅ DONE

Inspired by Tinkers' Construct. **Every combination produces a working item** — no failure state.
The Mold declares what you’re building. The three parts determine its stats.
The same Sword can be fast-and-fragile or slow-and-unstoppable based on part choices.

### Slot layout:
```
[ Mold ]  +  [ Head / Blade / Plate ]  +  [ Handle / Core ]  +  [ Binding / Padding / Clasp ]
```
- **Mold** (slot 1) — consumed on combine. Declares output type (Sword, Axe, Chest Mold, etc.).
  Cheap to craft at crafting table: 2 Clay → 1 Mold (any type).
- **Head/Blade/Plate** (slot 2) — primary material. Contributes base ATK or DEF + base DUR.
- **Handle/Core** (slot 3) — secondary material. Modifies speed and DUR; can add a trait.
- **Binding/Padding/Clasp** (slot 4) — finishing material. Flat DUR bonus + optional trait.

### Part stat schema (`"part_stats"` field added to each part in items.json):

**Blades / Heads / Plates** — slot 2:
| Part | base_atk | base_def | base_dur | trait |
|---|---|---|---|---|
| Iron Blade / Axe Head / Plate | 35 | 8 | 120 | — |
| Bronze Blade / Plate | 45 | 10 | 160 | — |
| Steel Blade / Plate | 58 | 14 | 220 | — |
| Gold Blade / Plate | 50 | 9 | 140 | shiny |
| Crystal Blade / Plate | 80 | 16 | 280 | magical |
| Obsidian Blade / Plate | 105 | 28 | 260 | heavy |

**Handles / Cores** — slot 3:
| Part | speed_mult | atk_bonus | dur_bonus | trait |
|---|---|---|---|---|
| Wood Handle | ×1.15 | 0 | +20 | light |
| Bone Handle | ×1.10 | +2 | +25 | — |
| Metal Handle | ×0.90 | +5 | +55 | sturdy |
| Refined Handle | ×0.85 | +8 | +80 | sturdy |
| Rough Crystal | ×1.05 | +10 | +60 | magical |
| Refined Crystal | ×1.10 | +20 | +80 | magical |
| Shadow Core | ×1.0 | +25 | +70 | shadow |

**Bindings / Padding / Clasps** — slot 4:
| Part | dur_bonus | trait |
|---|---|---|
| Padding (Reed) | +30 | light |
| Iron Clasp | +50 | — |
| Silver Clasp | +60 | magical |
| Obsidian Clasp (future) | +80 | heavy |

### Stat formula:
```python
atk        = slot2.base_atk + slot3.atk_bonus          # weapons/tools only
defense    = slot2.base_def                              # armor only
health_max = slot2.base_hp                               # armor only
dur        = slot2.base_dur + slot3.dur_bonus + slot4.dur_bonus
speed_mult = slot3.speed_mult
traits     = [p.trait for p in [slot2, slot3, slot4] if p.trait]
item_type  = MOLD_TYPE_MAP[mold_id]                     # "sword", "axe", "chestplate", etc.
base_id    = MOLD_BASE_ITEM_ID[mold_id]                 # existing item ID for slot_type + art
```

### Result stored as meta_dict override:
```json
[base_item_id, 1, {"atk": 66, "dur": 275, "dur_max": 275, "speed_mult": 0.9,
                   "traits": ["sturdy"], "parts": [190, 162, 152, 185]}]
```
Stat read order: `meta_dict` values **override** `items.json` defaults at equip/combat time.
This means old alloy-forge items still work unchanged; only Part Combiner items carry overrides.

### Display:
- Name generated: `"{dominant_material} {base_name}"` e.g. `"Steel Sword"`, `"Crystal Axe"`
  (dominant = highest-tier material used, derived from `parts` list)
- Traits shown in tooltip: `[Sturdy]`, `[Magical]`, `[Light]`
- Multi-trait: `[Magical, Sturdy]`

### Skill hook (future):
A `Crafting` skill level unlocks more part slots or bonus trait slots— no failure state to change, the progression comes from better parts and more customization.

### Server:
- [x] Add Part Combiner item (ID 205) to `items.json` + `placed_objects.py`
- [x] Add `"part_stats"` field to all part items in `items.json`
- [x] Add all Mold items (IDs 190–198) to `items.json` (stackable, max_stack 10)
- [x] Add Mold recipes to `recipes.json` (crafting_table: 2 Clay → any mold)
- [x] New TCP route `"combine_parts"`: `{mold_slot, head_slot, handle_slot, binding_slot}`
- [x] `server/game_state/part_combiner.py` — stat formula above, produce meta_dict item
- [x] `server/item_data.py` — `get_equip_bonuses()` reads `meta_dict` values first, falls back to items.json
- [x] Response: `{"type": "combine_result", "item": [base_id, 1, meta], "msg": str}` *(inventory sync used instead — no separate route needed)*

### Client:
- [x] New `client/rendering/combiner.py` — 4-slot grid (Mold | Head | Handle | Binding) + Combine button
- [x] Live **preview panel**: as slots are filled, show projected stats (ATK/DEF/DUR/Speed/Traits)
  This is the discovery mechanic — players learn by experimenting with the preview
- [x] Result popup: *"Forged: Crystal Sword [Magical, Light]"* — `controls.py` shows toast via `show_toast()`
- [x] Inventory tooltip updated to show combined-item stats/traits from meta_dict
  (`meta["atk"]`, `meta["defense"]`, `meta["traits"]`, `meta["mining_tier"]`, `meta["speed_mult"]`)
  Speed shown as "Speed +N%" / "Speed -N%" via `_build_tooltip_surface` in `inventory.py`

---

## Task 9.5 — Farming System & Mining Tier Rebalance  ✅ DONE

### Farming system (permanent resource nodes + seed drops):
- [x] `server/world/resource_nodes.py` — `"permanent": True` flag on all ore nodes; permanently
  depleted nodes tracked in `_permanently_depleted` set; `tick_respawns()` skips them
- [x] `"seed_drop": (item_id, chance)` on each node type → harvesting drops a plantable seed
- [x] `_planted_nodes` dict: planted seeds grow into full resource nodes after a `grow_time` (seconds)
- [x] `register_planted_node()` / `get_planted_node()` / `get_planted_snapshot()` helpers
- [x] Seed items added to `server/items.json` (IDs 34–42): Tree Sapling (34) + one seed per ore type
- [x] Client renders growing nodes and planted seeds via `config.planted_nodes` broadcast

### Mining tier system (pickaxe tiers for combined picks):
- [x] Pick head items (IDs 172–181, 283–284) carry `"mining_tier"` and `"base_mining"` in
  `part_stats` (not `base_atk`); `base_mining` rebased to match pre-crafted pick damage per tier
- [x] `server/world/resource_nodes.py` — `tool_satisfies(item, tool_type)` and
  `tool_mining_damage(item, tool_type)` handle both pre-crafted picks (by ID set) and
  combined picks (by `meta["mining_tier"]` rank comparison)
- [x] `client/input/controls.py` — `_has_tool()` and `_best_tool_damage()` updated to check
  combined pick `meta["mining_tier"]` via `_PICK_TIER_RANK` rank comparison
- [x] `server/game_state/part_combiner.py` — pick heads produce `mining_damage` + `mining_tier`
  in meta (not `attack_power`); handle `atk_bonus` not added to pick formula
- [x] All ore HP raised to prevent instamine: stone 20, coal 20, iron 20, copper 25, tin 25,
  silver 30, gold 35, crystal 40, obsidian 50

---

## Task 10 — Embedder & Gems  ✅ DONE

The Embedder takes one item + one gem and writes a `"gem"` key into the item's `meta_dict` in-place.
One gem per item. No stacking. Future: Gem Extractor station removes gem (destroys it).

### Meta_dict format:
```json
[item_id, qty, {"dur": 280, "dur_max": 300, "gem": "fire"}]
```

### Display:
- Name suffix: `Iron Sword` → `Iron Sword [Fire]`
- Item art: small colored dot rendered on top of existing sprite

### Gem list (IDs 50–56 target; boss drop source TBD):
| ID | Name | Gem color | Weapon effect | Tool effect | Armor effect |
|---|---|---|---|---|---|
| 50 | Fire Gem | orange | 10% chance burn DoT on hit | — | resist fire |
| 51 | Ice Gem | cyan | slow target 0.5 s on hit | — | resist slows |
| 52 | Life Gem | red | +5% lifesteal | — | +8 health_max |
| 53 | Swift Gem | yellow | +0.05 speed while held | +0.05 speed | +0.05 speed |
| 54 | Fortune Gem | gold | +10% mob coin drops | +15% node yield qty | — |
| 55 | Shadow Gem | purple | +15% crit chance | — | +4 defense |
| 56 | Auto-Smelt Gem | grey | — | Pickaxe auto-smelts ore on break | — |

### Server:
- [x] Add Embedder item (ID 206) to `items.json` + `placed_objects.py`
- [x] Add all gem items (IDs 50–56) to `items.json` with `stackable: true, max_stack: 10`
- [x] New TCP route `"embed_gem"`: `{item_slot, gem_slot}`
  Validates: item non-stackable, no existing `"gem"` in meta. Writes field, consumes gem.
  → `server/game_state/embedder.py` + `_handle_embed_gem` in `tcp_state_handlers_v2.py`
- [x] Repair station: `server/game_state/repair.py` + `_handle_repair_item` wired in handler

### Client:
- [x] New `client/rendering/embedder.py` — 2-slot UI (item + gem) + Embed button
- [x] New `client/rendering/repair.py` — scrollable bag grid + repair cost display + REPAIR button
- [x] `item_art.py` — gem art exists for all 7 gems (IDs 50–56) via `_gem_item()`
- [x] `inventory.py` — gem dot overlay at bottom-right of slot art when `meta["gem_trait"]` set (lines 145-158)
- [x] Inventory tooltip: appends `[Fire]` / `[Ice]` etc. to item name via `meta.get("gem")` (line 211)

---

## Roadmap

> Ordered by priority. Work top-down. ✅ = done, — = no hard dependency.

| Priority | Task | Est. | Notes |
|---|---|---|---|
| ✅ | ~~Chests (Task 6)~~ | — | done |
| ✅ | ~~ID Migration (Task 7)~~ | — | done |
| ✅ | ~~Part Maker (Task 8)~~ | — | done |
| ✅ | ~~Part Combiner (Task 9)~~ | — | done |
| ✅ | ~~Death & Respawn (Task 2)~~ | — | done |
| ✅ | ~~Armor Defense (Task 3)~~ | — | done |
| ✅ | ~~Durability (Task 4)~~ | — | fully done incl. repair UI and server repair handler |
| ✅ | ~~Farming & Mining Tier (Task 9.5)~~ | — | done |
| ✅ | ~~Creative Mode~~ | — | Creative inventory tab (all items, scrollable), mob damage immunity, HUD badge, `/creative [player]` op command |
| ✅ | ~~Op/Admin System~~ | — | `server/ops.py`, `/op`, `/deop`, `/ban`, `/unban`, `/give`, `/restart`, `/shutdown`, `/heal`, `/repair`, `/tp` (all op-only); `/tprequest`, `/tpaccept`, `/tpdeny` (any player); ban reject on UDP login; quality-colored slot borders |
| ✅ | ~~Node persistence fix~~ | — | `daemon=False` + `atexit.register(_save_persistence_sync)` already in `resource_nodes.py` |
| ✅ | ~~Combined items quality ranges~~ | — | `_roll_quality` already called in `part_combiner.py`; quality in meta |
| ✅ | ~~Combine result popup~~ | — | `controls.py` shows "Forged: {name} [{traits}]" toast via `show_toast()` |
| ✅ | ~~Combiner slot tooltips~~ | — | `combiner.py` lines 511-519 call `_draw_tooltip` on hover |
| ✅ | ~~Embedder & Gems (Task 10)~~ | — | server embedder + repair handlers, client UI, items 50-56, gem dot on slots, gem name in tooltip |
| ✅ | ~~Biome tree types~~ | — | pine (tundra/mountain), jungle (tropical), palm (beach) in `resource_nodes.py`; client art + collision all wired |
| ✅ | ~~Item art pass~~ | — | sword/dagger/mace/axe/pick/wand/rapier/katana/scimitar/hammer all have distinct silhouette functions |
| ✅ | ~~Launcher~~ | — | Pure-pygame launcher in `client/client.py` — Tkinter not needed |
| ✅ | ~~Defense value on HUD~~ | — | Minecraft-style bottom HUD (May 2026): DEF row + HP + SP + EXP bars stacked above hotbar; coins right of hotbar; top-right panel removed |
| ✅ | ~~`speed_mult` in inventory tooltip~~ | — | "Speed +N%" line added to `_build_tooltip_surface` in `inventory.py` |
| ✅ | ~~Day/Night Cycle~~ | — | Epoch-based `world_time` (600s/day) in `game_sync.py`; `draw_day_night_overlay` (cos curve, alpha 0→160) in `display.py`; called before HUD in `client.py` |
| ✅ | ~~Night-only mob spawns~~ | — | `_is_night` guard (`wt<6` or `wt>18`) added to both spawn blocks in `mob_manager.update_mobs`; `get_world_time()` imported from `game_sync` |
| ✅ | ~~Bed: sleep through night~~ | — | `_sleeping_players` set + `set_player_sleeping` + `_skip_to_morning` in `game_sync.py`; solo/duo=1, 3+ players=majority; `wake_up` TCP route; `draw_sleep_overlay` + WASD wake in client |
| ✅ | ~~Skeleton Mob~~ | — | `MAX_SKELETONS=5`, biome-gated desert/tundra, separate spawn cap; per-mob `drop_id`+`windup_time`; LPC walk spritesheet (9 frames 64×64) loaded in `mobs.py` |
| ✅ | ~~Quick-equip~~ | — | Right-click bag equippable → `inv_swap` to correct equip slot; right-click equip slot → first free bag slot; ring uses slot 38→39 fallback |
| ✅ | ~~Auto-stack on pickup~~ | — | Already implemented in `world_items._add_to_inventory()` — fills partial stacks before opening new slots |
| ✅ | ~~Light holes in night overlay~~ | — | `client/rendering/light_sources.py` (NEW) — `apply_light_holes()` punches `BLEND_RGBA_MIN` holes; campfire=5-tile radius; cached by `(radius_px, max_alpha)`; wired into `draw_day_night_overlay` |
| ✅ | ~~Forest Spider mob~~ | — | `mob_manager.py` — `MAX_SPIDERS=6`, biomes=forest/swamp, `SPIDER_WEB_SLOW=3.5s`, drops Spider Silk (57); procedural sprite in `mobs.py`; SKELETON_DROP_ID bug fixed (11→19) |
| ✅ | ~~Weather system~~ | — | `server/game_state/weather.py` (NEW) Markov chain; `client/rendering/weather.py` (NEW) rain/snow/fog; `get_weather()` in state packet |
| ✅ | ~~Desert Scorpion + Poison~~ | — | `mob_manager.py` — `MAX_SCORPIONS=4`, biomes=desert/alt_desert, poisons on lunge; `server/game_state/status_effects.py` (NEW); `client/rendering/status_effects.py` (NEW) green tint; Scorpion Venom item (58) |
| ✅ | ~~Chat system~~ | — | `server/network/tcp_state_handlers_v2.py` — `_handle_chat`+`broadcast_chat`; `client/rendering/chat.py` — Minecraft-style history panel, fading messages, sender colours, system messages |
| ✅ | ~~Cave Bat~~ | — | `mob_manager.py` — `MAX_BATS=8`, night-only, any non-water biome, `BAT_LUNGE_SPEED=18`, skips landing pause; procedural dark-purple sprite with wings |
| ✅ | ~~Snow Yeti~~ | — | `mob_manager.py` — `MAX_YETIS=3`, biomes=tundra/mountain, `slam_charge` AOE state (1 s wind-up, 2-tile radius), drops Yeti Fur (61); white ellipse sprite |
| ✅ | ~~Passive Animals (Rabbit + Deer)~~ | — | `mob_manager.py` — `MAX_RABBITS=10`+`MAX_DEER=8`, `flee` AI state, `ANIMAL_DEAGGRO_RANGE=10`; Raw Meat (59) + Cooked Meat (60) campfire recipe (473) added |
| ✅ | ~~Boss: Slime King~~ | — | `mob_manager.py` — `SLIME_KING_HP=1000`, 3-phase (mini-slimes @66%, AOE splash @33%); `drain_events()` + `_pending_events` for boss chat; Slime Crown (3510 back-slot) |
| ✅ | ~~Minimap~~ | — | `client/rendering/minimap.py` (NEW) — 128×128 corner panel, biome colours, fog-of-war `visited_chunks`, mob dots; `config.visited_chunks: set` added; wired after `draw_chat()` |
| ✅ | ~~Biome-gated enemies (Phase 13+)~~ | — | All 7 mob types done: Skeleton (desert/tundra), Forest Spider (forest/swamp), Desert Scorpion (desert), Cave Bat (night/all), Snow Yeti (tundra/mountain), Rabbit (beach/plains), Deer (plains/forest); Slime King = rare world boss |
| ✅ | ~~Server performance audit~~ | — | `tools/server_audit.py` benchmark; 5 fixes: single-pass type count, solid-cache + dirty flag (`get_solid_revision()`), O(9) wall lookup, remove duplicate planted-snapshot call, cache player list. 0.378 ms → 0.267 ms/tick (29% faster) |
| ✅ | ~~Slime Lair Dungeon~~ | — | `server/world/dungeon_gen.py` — deterministic placement (1 per 400-tile grid cell); 15×13 stone_brick_wall shell, stone_brick_floor interior, 3-tile entrance gap, 4 inner pillars; `spawn_boss_at()` in mob_manager replaces random timer; 8-tile trigger radius; 5-min respawn cooldown; minimap red markers |

---

## Phase 14 — Advanced Combat

| Priority | Task | Notes |
|---|---|---|
| ✅ | ~~Boss: Slime King gem drops~~ | Slime King death drops `random.randint(50,56)` gem alongside Slime Crown |
| ✅ | ~~Towns + NPCs (Phase 11)~~ | `town_gen.py` — 5×5 stone-brick buildings (wall+floor+door), 3×3 plaza, cardinal paths, 4 NPCs per town; `inject_object()` in `placed_objects.py`; buildings built on server startup + lazy per-player chunk entry; `game_sync` sends `npcs` list; `client/rendering/npcs.py` procedural sprites + name labels + greeting bubbles |
| ✅ | ~~Particle system (Phase 15)~~ | `client/rendering/particles.py` — `emit_hit` (8 red sparks), `emit_pickup` (5 gold), `emit_levelup` (24 rainbow), `emit_craft` (6 white); triggered from `handlers.py` on knockback / level-up / world-item disappear |
| ✅ | ~~Dodge Roll~~ | `Space+dir` → 0.25 s i-frame, 3× speed, 20 stamina, ghost trail; server marks `invulnerable`; roll squish animation |
| ✅ | ~~Controls Rebind Screen~~ | ESC→Pause→Controls; `config.keybinds` dict (11 actions); `controls_settings.py` panel; listening mode; fixed non-rebindable rows |
| 1 | **Block / Parry** | Hold `RMB` → 60% damage reduction; perfect-parry window (0.15 s) = full negate + stagger |
| 2 | **Combo Chain** | 4-hit chain within 0.8 s; multiplier 1.0× → 1.8× at hit 4; HUD combo counter |
| ✅ | ~~**NPC dialogue / shops**~~ | F-key → `try_open_npc_shop()`; `npc_shops.py` defs + buy/sell handlers; `tcp_state_handlers_v2` `shop_buy`/`shop_sell`; `npc_shop.py` panel with Buy/Sell tabs; `town_gen` sends shop data |
| ✅ | ~~**Gem effects on hit**~~ | `combat.py` reads `gem_trait` after hit; Fire burn DoT, Ice slow (mob speed 40%), Life 5% lifesteal, Shadow ×2 crit (15%), Poison DoT; ticks in `status_effects.py` (player) + `mob_manager.py` (mob) |
| ✅ | ~~**World seed config**~~ | `WORLD_SEED = 42` in `server/config.py`; `dyn_chunk_gen.py` imports it as `SEED` |
| ✅ | ~~**Character Customisation**~~ | `player_appearance` dict in `config.py` + `player_save.py` persistence; `player.py` — dynamic body/head folder (male/female/muscular/teen), hair layer (`hair/{style}/adult/`), wing bg/fg layers (`body/wings/{type}/adult/bg|fg/walk/{colour}.png`), skin_tint; `char_creator.py` NEW panel (C key) — body toggle, 20 hair styles, 8 wing types, 15 wing colours, 5 auras; `particles.py` `emit_aura()` called every frame; server `update_appearance` handler syncs to all clients |

---

## Design Decisions

| Question | Decision |
|---|---|
| Crystal/Obsidian smelt into bars? | No — used raw as crafting components |
| Gold tier role? | Speed/jewelry focus; softer combat stats than steel |
| Furnace renamed to Smelter? | No — stays Furnace |
| Parts: ghost items or real inventory items? | Real items in inventory → chests needed first |
| Part Combiner fail state? | No failure — Tinkers'-style: every combo produces a working item; stats determined by parts |
| Mold concept | Mold (slot 1, consumed) declares output type; crafted cheaply from Clay at crafting table |
| Embedder: new item IDs or in-place meta? | Modify in-place via `meta_dict["gem"]` |
| Multiple gems per item? | No — one gem per item; Gem Extractor removes it (destroys gem) |
| Gem sources? | Boss drops — bosses not yet implemented |
| Repair system? | Full repair costs ~50% original crafting materials |
| Op bootstrap rule? | If no ops exist, any player can `/op` (no args) to self-promote as first op |
| Creative mode access? | Op-only via `/creative [player]`; creative players see a third inventory tab with all items |
| TP system? | `/tprequest` → target receives chat prompt → `/tpaccept` or `/tpdeny`; ops can `/tp` directly |


# TODO — Game Systems Roadmap
> Preparing the multiplayer server/client for combat, inventory, mobs, and persistence.
> Work top-down within each phase — each phase is a prerequisite for the next.
> Mark items `[x]` when complete.

---

## Phase 1: Player Data Persistence
> Foundation for everything. The server needs memory of each player across sessions.

- [x] **Create player save system** (`server/player_saves/`)
  - On UDP assign (new or rejoin), load `server/player_data/{player_id}.json` if it exists
  - File stores: `pos`, `health`, `health_max`, `stamina`, `stamina_max`, `attack_power`, `level`, `inventory`
  - On `cleanup_player`, write current player state to disk before removing from memory

- [x] **Add full stats fields to `players` dict on registration** (`server/network/udp_routes.py`)
  - Currently only: `{"pos", "health", "level", "last_seen"}`
  - Add: `health_max`, `stamina`, `stamina_max`, `attack_power`
  - Populate from save file on rejoin, or use defaults for new players

- [x] **Create item definitions file** (`server/items.json`)
  - `{"1": {"name": "Slime Ball", "stackable": true, "max_stack": 99}, ...}`
  - Single source of truth for item metadata used by both server and client

---

## Phase 2: Game State Protocol
> The TCP game-state channel is currently a no-op on the client. This makes it real.
> Note: `send_json`/`recv_json` and socket storage are fine. The only missing piece is that
> the game loop never iterates `clients["game_state"]` — it only sends to `clients["world"]`.

- [x] **Wire game state channel into the game loop** (`server/server.py`)
  - Add a second per-tick iterator alongside the world chunk one:
    `for player_id, sock in valid_state_clients: executor.submit(send_game_state, player_id, sock)`
  - Inject `clients["game_state"]` reference into `sync.py` via `set_sync_refs()`

- [x] **Define game state message schema**
  - Per-tick payload sent to each player:
    `{"self": {health, stamina, attack_power, inventory_dirty}, "players": {id: {pos, health}}, "mobs": [...], "world_items": [...]}`
  - Keep minimal for now; extend as each phase adds data

- [x] **Implement server-side `send_game_state`** (`server/game_state/sync.py`)
  - Mirror of `send_if_changed` but for game state — same executor pattern, already proven
  - Sends: own full stats, nearby other players (from `players` dict), empty mobs/items for now
  - Uses `send_json(sock, {...})` — transport is already correct

- [x] **Implement client-side `handle_state`** (`client/networking/handlers.py`)
  - Currently reads data but does `pass`
  - Parse incoming JSON; write stats to `config` and entity lists to a shared state dict

---

## Phase 3: HUD & Player Stats
> Requires Phase 2 — client needs authoritative stats from server to display.

- [x] **Add player stat fields to `client/config.py`**
  - `player_health = 100`, `player_health_max = 100`
  - `player_stamina = 100.0`, `player_stamina_max = 100.0`
  - `player_attack_power = 10.0`
  - Written by `handle_state` each tick

- [x] **Implement HUD renderer** (`client/rendering/hud.py`)
  - Health bar: top-right, green; turns yellow below 30%
  - Stamina bar: below health, blue; turns yellow below 30%
  - Called from main render loop after world/entity rendering

- [x] **Implement stamina consumption client-side** (`client/input/controls.py`)
  - Sprint (Shift): drain 1/frame, speed = sprint_speed
  - Stealth (Ctrl): drain 0.5/frame, speed = stealth_speed, reduces damage taken
  - Normal: regen 0.1/frame
  - Block mode switch if stamina < minimum threshold
  - Server gets the movement and validates; stamina is client-predicted, server-corrected

---

## Phase 4: Inventory System
> Requires Phase 1 (server stores inventory in save files) and Phase 2 (delivery channel).

- [x] **Add inventory to server player data**
  - `players[player_id]["inventory"]` = list of 36 `[item_id, qty]` or `null` entries
  - Initialized to 36 nulls for new players; loaded from save file on rejoin

- [x] **Send inventory to client on connect** (via game state channel)
  - First game-state message after connect includes the full 36-slot inventory snapshot
  - Subsequent ticks only send changed slots (`inventory_dirty` flag + diff)

- [x] **Add inventory state to `client/config.py`**
  - `player_inventory = [None] * 36` — each entry is `[item_id, qty]` or `None`
  - Updated on initial load and on server-pushed diffs

- [x] **Implement inventory UI** (`client/rendering/inventory.py`)
  - 36-slot grid (4 rows × 9 cols), toggled by E key
  - Last 9 slots (27–35) rendered as hotbar at bottom of screen at all times
  - Item sprites loaded from `client/assets/items/{item_id}.png`
  - Quantity number in bottom-left corner of occupied slots
  - Selected hotbar slot highlighted; arrow keys or scroll wheel to cycle

---

## Phase 5: Dropped Items in World
> Requires Phase 2 (game state channel) and Phase 4 (inventory to receive items into).

- [x] **Add world items to server state** (`server/game_state/world_items.py`)
  - `world_items = {}` — `{uuid: {"item_id": int, "pos": [x,y], "qty": int}}`
  - Items added here when mobs die; removed when a player picks them up

- [x] **Include world items in per-player game state broadcasts**
  - Filter to items within player's render distance each tick

- [x] **Pickup detection on server** (run each tick in game loop)
  - If any player pos is within ~32px of a world item: add qty to player inventory, delete item, flag inventory dirty

- [x] **Render dropped items on client** (`client/rendering/display.py`)
  - Parse `world_items` from game state
  - Draw item sprite at world position with camera offset

---

## Phase 6: Combat
> Requires Phase 2 (event delivery), Phase 5 (mobs have health in game state).

- [x] **Add attack input on client** (`client/input/controls.py`)
  - Spacebar triggers attack if cooldown elapsed (0.5s client-side)
  - Send `{"type": "attack", "player_id": ..., "direction": "up/down/left/right", "pos": [x,y]}` to server (UDP)
  - Play 7-frame directional attack animation client-side

- [x] **Add attack sprites** (`client/assets/player/attack/`)
  - Port directional attack frames from PythonRPG-main Player_Sprites
  - 7 frames x 4 directions

- [x] **Add attack event handler on server** (`server/network/udp_routes.py` or new file)
  - Receive attack events
  - Find all mobs/players within 64px in a 90 degree cone of the attack direction
  - Apply `attacker.attack_power` damage to each target
  - Apply 5px knockback in attack direction
  - Increment attacker's `attack_power` by 0.001

---

## Phase 7: Mob System
> Requires Phase 2 (mobs in game state), Phase 5 (drops), Phase 6 (mobs take damage).

- [x] **Create server-side mob system** (`server/mobs/`)
  - `SlimeMob` class with three states: wander (>200px), aggro (<=200px), melee (<=48px)
  - Wander: pick random target within 200px, move toward it, reset on collision
  - Aggro: track player position, move toward player
  - Melee: attack player on reach, 5s cooldown, 10 damage
  - Stats: 100 HP, 10 attack, 5s attack cooldown; always drops item ID 1 (slime ball) on death

- [x] **Run mob AI tick in server game loop** (`server/server.py`)
  - Each tick: call `update_mobs()` -- advances state machine, moves mobs, resolves attacks
  - Max 10 concurrent slimes; 2% spawn chance per tick if under cap

- [x] **Include mobs in per-player game state broadcasts**
  - Each player receives mob `{id, pos, health, type}` for mobs within render distance

- [x] **Mob death and drops**
  - On mob health <= 0: spawn a world item (item ID 1) at mob position, remove mob from active list

- [x] **Remote player attack animation** — server broadcasts `attack_event` via UDP; client plays
  7-frame slash sprite on remote `RemotePlayer` objects

- [x] **Slime → player knockback** — server sends `knockback_vel` in game-state TCP; client applies
  as a decaying velocity over ~0.25 s (see `Proposal.md` for planned smoothing improvements)

- [x] **Player → mob knockback** — `combat.py` applies 1.5-tile push on hit mobs; lock-inversion
  deadlock between `combat.py` and `mob_manager.py` resolved by separating nested lock acquisitions

- [x] **Knockback feel** — abrupt snap, slime overlap, no hit feedback (see `Proposal.md`)
  - [x] Fix 1: client-side velocity knockback (0.25 s constant-velocity push)
  - [x] Fix 2: server-side mob separation push (MOB_SEP_DIST=0.8, MOB_SEP_FORCE=3.0)
  - [x] Fix 3: hit flash on player sprite (0.2 s red BLEND_RGBA_MULT tint)
- [x] Fix 4 (stretch): slime pre-attack charge telegraph (windup→lunge→return)

---

## Phase 8: Crafting, Quality & Economy
> Requires Phase 4 (inventory) and Phase 1 (item definitions).

- [x] **Crafting system** (`server/game_state/crafting.py`, `client/rendering/crafting.py`)
  - Press C to open crafting panel; tabbed by category (weapon / armor / trinket / all)
  - `server/recipes.json` defines 11 recipes with ingredient lists and result items (IDs 13–23)
  - Client: scrollable recipe list with availability dots, ingredient have/need display, CRAFT button
  - Server validates ingredients, consumes them, adds result to first free inventory slot

- [x] **Quality tiers with random stat rolling** (`server/game_state/crafting.py`, `client/rendering/`)
  - Equipment receives a random quality on craft: Common / Uncommon / Rare / Exquisite
  - Stat multiplier rolled within each tier's range; stored in item slot as `[id, 1, {"quality":..., "stats":{...}}]`
  - Inventory tooltip shows quality name in tier colour and all rolled stat values
  - Crafting panel shows stat ranges per quality tier in a 2-column compact layout

- [x] **Hotbar weapon bonus** (`server/item_data.py`, `server/game_state/game_sync.py`, `server/network/combat.py`)
  - Active hotbar slot's stats (attack_power etc.) apply additively in combat and game_sync broadcast
  - Client sends `hotbar_slot` in every UDP position update; server stores and reads it each tick

- [x] **Item selling from inventory** (`server/item_data.py`, `server/network/tcp_routes.py`, `client/`)
  - Right-click any item in the inventory panel to sell the entire stack for coins
  - Sell price = `base_price × qty × quality_mult` (Common 1×, Uncommon 2×, Rare 4×, Exquisite 8×)
  - `server/items.json` stores `sell_price` for all 23 items; coins (item 2) have sell_price=0
  - Inventory tooltip shows "Right-click to sell: Xc" in gold for items with value > 0

- [x] **Character stat allocation screen** (`client/rendering/stat_screen.py`)
  - Press P to open; shows current stats with [+] buttons to spend stat points
  - `spend_stat` message sent to server; server validates, applies upgrade, and broadcasts new stats

---

## World Generation: Decouple Biomes from Elevation ✅

- [x] **Remove `h` from `biome_profiles` distance matching** — profiles are pure 4D `[t, m, c, e]`
  - Mountains excluded from profile table entirely; driven by `mountain_signal > MOUNTAIN_SIGNAL` ridge only
  - Distance calc sums 4 terms `(t−p0)²+(m−p1)²+(c−p2)²+(e−p3)²`; `h` plays no role in biome choice
- [x] **Elevation overrides applied after climate biome** — ocean/lake/beach thresholds first, then ridge → mountain, then 4D profile match
- [x] **Raw `h` stored as elevation** — `elevations[i,j] = floor(h / STEP) * STEP`; no per-biome renormalization
- [x] **Regenerated world** — `CHUNK_DIR = "world_chunks_v3"` (old chunks untouched, new dir forces regen)

---

## Y-Directional Depth Sorting

- [x] **Sort all sprites by their Y position each frame** (`client/rendering/`, `client/client.py`)
  - All drawable entities (local player, remote players, mobs, tall nodes) collected into
    `_draw_list` as `(sort_y, draw_fn)` tuples each frame, then sorted and blitted in order
  - Tall nodes (trees, cacti, deposits) use sprite-bottom as sort_y; small nodes drawn immediately
  - Gives correct depth layering: entities walk behind/in-front-of trees naturally

---

## Standalone Fixes ✅

- [x] **Prevent player spawning in water** (`server/network/udp_routes.py`)
  - `_safe_spawn_pos()` with `_WATER_BIOMES = frozenset({0, 3})` (ocean + river)
  - Spiral scan from requested position until a non-water tile is found; used for all new players

- [x] **Realistic stamina exhaustion** (`client/input/controls.py`)
  - `_exhausted` flag set when stamina hits 0; cleared when stamina recovers past threshold
  - Sprinting and stealthing blocked while exhausted (`not _exhausted` guard)
  - HUD stamina bar turns red while exhausted

- [x] **Ground item pickup** (`server/game_state/world_items.py`, `server/server.py`)
  - `pickup_tick()` runs each game tick; awards any world item within proximity to a player
  - Auto-collection on approach — no explicit F key required

---

## Phase 9: Resource Gathering — Mining & Chopping ✅

- [x] **Tool items** — Scrap/Wooden/Stone/Iron Axe (100–103), Wooden/Stone/Iron Pickaxe (110–112)
  - Procedurally drawn art via `item_art.py`; tool tier determines gather damage
- [x] **Resource nodes in chunk generation** (`server/world/dyn_chunk_gen.py`, NODES_VERSION=8)
  - Trees, stick piles, stone/coal/iron deposits, herb patches, cacti, reeds, seashells, mushrooms, snow crystals, bone piles
  - Node density balanced per biome; mountains halved to reduce visual clutter
- [x] **Node collision & Y-sort** (`client/rendering/display.py`)
  - Trees, cacti, deposits block player movement; collision radius per node type
  - Tall nodes (trees, cacti, deposits) Y-depth-sorted with all other entities each frame
- [x] **Server-side gather action** (`server/network/tcp_routes.py`)
  - `gather` TCP route: validates range (1.5 tiles), tool requirement, applies TOOL_DAMAGE, drops yields on depletion, schedules respawn
- [x] **Client gather input** — Space bar (smart action: tool → consume → attack)
  - Optimistic hit progress bar updated immediately on key press
- [x] **Tool + node visual polish**
  - Deposit cluster art (multi-rock, 1.4–1.5× tile); cactus red tint on damage tick
  - Node size overrides: tree=3.2×, cactus=1.8×, deposits=1.4–1.5×

---

## Phase 9.5: Content & Item System Expansion ✅

- [x] **Item ID renumbering** — logical groups with gaps for future additions
  - Materials 1–14, Weapons 50–99, Tools 100–149, Armor 150–249, Trinkets 250–299, Consumables 300+
- [x] **Iron tier** — Iron Sword/Mace/Dagger (54–56), Iron Helm/Chest/Bracers/Boots (151,162,171,191)
- [x] **Pants & shoes slots** — Reed/Bone Leggings (180–181), Leaf Sandals/Iron Boots (190–191)
- [x] **Trinket expansion** — Snow Pendant (251), Mushroom Ring (261); all with procedural art
- [x] **Consumable system** — Herb Tea/Mushroom Stew/Healing Potion (300–302); Space bar to use
  - Server `use_item` TCP route: validates consumable, applies heal capped at health_max
- [x] **Crafting recipes updated** — 52 recipes across all tiers (weapons 1–7, tools 10–16, armor 20–32, trinkets 40–43, food 50–52)
- [x] **Space bar smart action key** — context priority: tool+node → consumable → attack
  - F key reserved for future ground-item pickup

---

## Phase 10: Placeable Objects, Smelting & Station Crafting

> The raw material loop exists. This phase adds player-placeable stations (campfire, crafting
> table, furnace), smelting/cooking recipes gated to those stations, and a crafting UI that
> shows which recipes are available based on what's nearby.

### 10A — New item IDs & materials

- [x] **Iron Bar** (ID 100) — `server/items.json`
  - Intermediate material; produced only at a furnace
- [x] **Stone Brick** (ID 120) — `server/items.json`
  - Intermediate material; produced only at a crafting table
- [x] **Campfire item** (ID 200), **Crafting Table item** (ID 200), **Furnace item** (ID 201)
  - Craftable items held in inventory; using them (Space) places the object in the world
  - Recipes (no station required): Campfire: `Wood×5`; Crafting Table: `Wood×8 + Stone×4`;
    Furnace: `Stone×10 + Coal×2`

### 10B — Placeable objects system (server)

- [x] **`server/game_state/placed_objects.py`** — new module
  - `placed_objects: dict` — `{uid: {"type": str, "pos": [tx, ty], "placed_by": pid}}`
  - `place_object(pid, obj_type, pos)` — validates tile is empty + player has item in inventory,
    removes item, adds entry; returns uid
  - `remove_object(uid)` — drops the item back at position
  - Persisted alongside chunk data: `world_chunks/placed_{cx}_{cy}.json`; loaded lazily
  - Types: `"campfire"`, `"crafting_table"`, `"furnace"`, `"alloy_forge"`, `"part_maker"`, `"part_combiner"`

- [x] **Broadcast placed objects** (`server/game_state/game_sync.py`)
  - Include `"placed_objects"` in game-state payload: objects within render distance
  - Client stores in `config.placed_objects = {}`

- [x] **TCP route: `place_object`** (`server/network/tcp_routes.py`)
  - `{"type": "place_object", "obj_type": "campfire", "pos": [tx, ty]}`
  - Server validates: player within 1 tile of target pos, item in inventory, tile passable
  - Removes item from inventory, calls `place_object()`, broadcasts update

- [x] **TCP route: `remove_object`** (`server/network/tcp_routes.py`)
  - `{"type": "remove_object", "uid": "..."}` — only owner (or anyone?) can remove
  - Removes from world, drops item at position as a world_item

### 10C — Station-gated crafting

- [x] **`"station"` field in `server/recipes.json`**
  - `null` (or absent) — craftable anywhere in inventory
  - `"crafting_table"` — must be within 2 tiles of a placed crafting table
  - `"furnace"` — must be within 2 tiles of a placed furnace
  - `"campfire"` — must be within 2 tiles of a placed campfire

- [x] **Station check in `server/game_state/crafting.py`**
  - `handle_craft()` receives `"nearby_stations": [str, ...]` from the client message
  - Reject the craft if the recipe's station is not in that list

- [x] **Smelting recipes** (station: `"furnace"`)
  - All ore bars (iron, copper, tin, silver, gold, bronze, steel, etc.) smelted at furnace

- [x] **Cooking recipes** (station: `"campfire"`)
  - Campfire-only recipes implemented (mushroom stew, etc.)

- [x] **Iron Bar recipes** — updated in `server/recipes.json`
  - All iron/copper/bronze/steel tier recipes require bars; station: `"crafting_table"`

### 10D — Client crafting UI update

- [x] **Detect nearby stations** (`client/input/controls.py` or `client/state/`)
  - Scans `config.placed_objects` for entries within range; stored in `config.nearby_stations`

- [x] **Station tabs in crafting panel** (`client/rendering/crafting.py`)
  - Tab bar filtering by station type; grayed-out tabs when station not nearby
  - Recipes filtered to active tab

- [x] **Send `nearby_stations` with craft request**
  - `{"type": "craft", "recipe_id": N, "nearby_stations": ["furnace", ...]}`

### 10E — Client rendering

- [x] **Draw placed objects** (`client/rendering/display.py`)
  - Placed object sprites rendered from `config.placed_objects`; drawn in world tile layer

- [x] **Place action** (`client/input/controls.py`)
  - Placeable items in hotbar can be placed with Space; sends `place_object` TCP message

---

## Phase 10.5: Creative Mode & Op/Admin System  ✅ DONE

> Server operator controls and a creative sandbox mode for testing/admin use.

- [x] **`server/ops.py`** — persistent op and ban lists in `server/ops.json`
  - `is_op()`, `add_op()`, `remove_op()`, `is_banned()`, `ban_player()`, `unban_player()`
  - Bootstrap rule: if no ops exist, any player can `/op` (no args) to become first op

- [x] **Op-gated commands** (`server/network/commands.py`)
  - `/op [player]`, `/deop <player>` — grant / revoke operator status
  - `/creative [player]` — toggle creative mode for self or another player
  - `/give <player> <id> [qty]` — give any item to any online player (stats auto-rolled)
  - `/ban <player>`, `/unban <player>` — ban/unban; banned player is immediately kicked
  - `/restart` — saves all players, broadcasts warning, respawns server process
  - `/shutdown` — saves all players, broadcasts warning, exits
  - `/heal [player]`, `/repair [player]`, `/tp <player>` — op-only utility commands

- [x] **Any-player TP request system**
  - `/tprequest <player>` — sends chat notification to target; pending stored server-side
  - `/tpaccept` — teleports the requester to the accepting player
  - `/tpdeny` — notifies requester that request was denied

- [x] **Ban enforcement on login** (`server/network/udp_routes.py`)
  - UDP login check: if player name is banned, send `{"type": "banned"}` response and drop
  - Client displays ban reason for 5 s then exits cleanly (`client/client.py`)

- [x] **Creative inventory tab** (`client/rendering/inventory.py`)
  - Third tab visible only when `config.player_creative` is True
  - Scrollable grid of all items; clicking grants item via `give_item` TCP message
  - Tab is hidden and scroll resets when creative is revoked

- [x] **Creative mob immunity** (`server/mobs/mob_manager.py`)
  - Melee damage skipped for any player with `"creative": True` in player data

- [x] **Creative HUD badge** (`client/rendering/hud.py`)
  - Gold ✦ CREATIVE badge shown below HP/SP panel when `config.player_creative`

- [x] **Quality-colored slot borders** (`client/rendering/inventory.py`)
  - Common = grey, Uncommon = green, Rare = blue, Exquisite = purple

- [x] **RNG stat rolling on item give** (`server/item_data.py`, `server/network/tcp_routes.py`)
  - `roll_item_stats(item_id)` rolls quality tier + stat multiplier for all gear
  - Called automatically in `_give_item()` for non-stackable items (creative tab + `/give`)

---

## Phase 11: Towns, NPCs & Dialogue

> The world needs social spaces. This phase adds procedural towns, static NPCs with dialogue,
> and the hooks for shops and quests.

- [X] **Procedural town placement** (`server/world/dyn_chunk_gen.py` or new `world/town_gen.py`)
  - During world gen, seed a list of town anchor points (every ~30 chunks, on land biomes)
  - Each anchor expands a 7×7 tile "town" footprint: stone path tiles, building outlines,
    well at center, lighting placeholder
  - Store town data in a separate `server/towns/{cx}_{cy}.json` per anchor chunk
  - Town biome tiles override normal grass/forest tiles; client renders them as stone/brick

- [X] **NPC data file** (`server/npcs.json`)
  - `{"1": {"name": "Merchant", "type": "shop", "sprite": "merchant", "dialogue": ["Welcome!", "Buy something?"]}, ...}`
  - Each town has a fixed roster: Merchant, Blacksmith, Inn Keeper, Healer
  - NPC positions are tile-relative to the town anchor

- [X] **NPC broadcast** (`server/game_state/sync.py`)
  - Include NPCs within render distance in game-state payload: `"npcs": [{id, pos, type, name}]`
  - NPCs are static (no movement); only pos + type needed

- [ ] **NPC rendering** (`client/rendering/npcs.py` — new file)
  - Draw NPC sprite at world position with name label above (same style as remote players)
  - NPC sprites: `client/assets/npcs/{type}.png` — at minimum merchant, blacksmith, innkeeper, healer

- [ ] **Dialogue system** (`client/rendering/dialogue.py` — new file)
  - Press `E` near an NPC to open a dialogue box (chat bubble style, centered bottom-third)
  - Dialogue is a list of strings cycled with `Space`; last line closes or opens a sub-menu
  - Interaction sends `{"type": "npc_interact", "npc_id": "..."}` to server; server responds
    with the NPC's dialogue array + shop inventory if type == "shop"

- [ ] **Respawn at inn** (`server/network/tcp_routes.py` + `client/rendering/dialogue.py`)
  - Inn keeper offers "Rest" option: sets player's `respawn_point` to the inn's tile position
  - On player death (HP ≤ 0): instead of disconnecting, broadcast `death` event; client shows
    a "You died" overlay; player respawns at `respawn_point` with 50% HP and loses 10% of coins

---

## Phase 12: Shops & Economy

> Requires Phase 11 (NPCs exist). Turns the coin economy into a meaningful loop.

- [X] **Shop inventory per NPC** (`server/npcs.json`)
  - Each shop NPC has `"sells": [item_id, ...]` and `"buys": [item_id, ...]` arrays
  - Merchant: sells potions, arrows; buys almost everything
  - Blacksmith: sells iron tools/weapons; buys ores and ingots at 80% sell_price

- [X] **Shop UI** (`client/rendering/shop.py` — new file)
  - Two-column layout: left = shop's stock (item, qty, price), right = player's inventory
  - Left-click a shop item to buy (deduct coins, add to inventory)
  - Left-click a player item to sell (add coins, remove from inventory)
  - Server validates both operations via new `"shop_buy"` and `"shop_sell"` TCP routes

- [ ] **Dynamic shop stock** (stretch goal)
  - Shop restock timer: every 5 minutes, random 1–3 items in stock refresh
  - "Limited stock" items (qty=1) make rare items feel special

- [ ] **Player market** (`server/game_state/market.py` — new file, stretch goal)
  - Global listing board accessible at a Market NPC in large towns
  - Any player can list an item at a set price; any player can buy it
  - Listings persist to `server/market_listings.json`; server mediates transfers on purchase

---

## Phase 13: More Mobs & Enemy Variety

> Each mob needs its own sprite sheet, AI behavior, and drop table.
> Add one mob at a time — all share the `mob_manager.py` state machine base.

- [x] **Skeleton** (`server/mobs/mob_manager.py` + `client/assets/mobs/skeleton/`)
  - Biome: desert, graveyard (plains at night eventually)
  - Stats: 80 HP, 8 attack, faster than slime (`speed=2.0`), drops `Bone` (new item)
  - AI: same wander/aggro/windup/lunge as slime but shorter `WINDUP_TIME=0.3 s`
  - Immune to knockback (heavy mob variant — resists push)
  - **Done (May 2026):** `MAX_SKELETONS=5`, biome-gated to desert/tundra (IDs 6+9), separate spawn cap+interval, per-mob `drop_id`+`windup_time`; LPC walk spritesheet loaded in `mobs.py` (9 frames, 64×64, 8 FPS)

- [x] **Forest Spider** (`server/mobs/mob_manager.py` + `client/rendering/mobs.py`)
  - Biome: forest(5), swamp(2); Stats: 50 HP, 6 atk, speed=2.8; drops Spider Silk (item 57)
  - Lunge hit applies `slowed` debuff 3.5 s via `pending_slow` dict; procedural sprite (dark purple + 8 legs)
  - **Done (May 2026):** `MAX_SPIDERS=6`, `_spawn_spider_near()`, night-gated; item 57 added to `items.json`

- [x] **Desert Scorpion** (`server/mobs/mob_manager.py` + `client/rendering/mobs.py`)
  - Biome: desert(6), alt_desert(7); Stats: 120 HP, 12 atk, speed=1.8; drops Scorpion Venom (item 58)
  - Lunge hit applies `poisoned` (2 dmg/s × 5 s) via `pending_poison` dict; green pulsing tint on client HUD
  - **Done (May 2026):** `MAX_SCORPIONS=4`, `_spawn_scorpion_near()`; `server/game_state/status_effects.py` (NEW); `client/rendering/status_effects.py` (NEW); item 58 in `items.json`

- [x] **Cave Bat** (any non-water biome, night-only)
  - Stats: 30 HP, 4 attack, fly-by dash AI
  - Drops nothing; exists to make nights dangerous
  - AI: fast dash (`BAT_LUNGE_SPEED=18`), skips landing pause, returns to origin; no poison/slow
  - **Done (May 2026):** `MAX_BATS=8`, `BAT_AGGRO_RANGE=5.0`; `_spawn_bat_near()`; night-gated; procedural sprite in `mobs.py`

- [x] **Snow Yeti** (tundra/mountain biomes 9+10)
  - Stats: 300 HP, 25 attack, slow movement, drops `Yeti Fur` (item 61)
  - AI: `slam_charge` state — 1 s wind-up, then deals damage in 2-tile radius AOE; 8 s cooldown
  - **Done (May 2026):** `MAX_YETIS=3`, `YETI_SLAM_RADIUS=2.0`, `YETI_SLAM_COOLDOWN=8.0`; `_spawn_yeti_near()`; Yeti Fur (61) in `items.json`; white ellipse sprite

- [x] **Passive Animals** (rabbit — beach/plains; deer — plains/forest)
  - No combat AI; `flee` state when player enters `flee_range_sq`; deaggro at `ANIMAL_DEAGGRO_RANGE=10.0`
  - Drop `Raw Meat` (item 59); Cooked Meat (60) crafted at campfire
  - **Done (May 2026):** `MAX_RABBITS=10`, `MAX_DEER=8`; `_spawn_rabbit_near()`, `_spawn_deer_near()`; flee AI state; items 59/60/61 + recipe 473

- [x] **Boss: Slime King** (rare spawn — 1 per server at a time)
  - Stats: 1000 HP, 30 attack, drops `Slime Crown` (item 3510, back-slot +15% speed +2 DEF)
  - AI: 3-phase — Phase 1 (>66% HP): normal lunge; Phase 2 (<66%): spawns 2 mini-slimes on hit; Phase 3 (<33%): AOE splash to all nearby players on lunge hit
  - Server broadcasts `boss_spawned`/`boss_defeated` system chat via `drain_events()` + `broadcast_chat`
  - **Done (May 2026):** `SLIME_KING_HP=1000`, `_slime_king_active` guard (1 per server); `_pending_events` + `drain_events()`; 3-phase logic in lunge state; crown sprite with 3-gem tiara; `server.py` polls events and calls `broadcast_chat`

---

## Phase 14: Advanced Combat System

> Makes combat feel like a skill-based game rather than just swinging into mobs.

- [x] **Dodge roll** (`client/input/controls.py` + `server/network/udp_routes.py`)
  - Space+dir → 0.25 s i-frame burst, 3× speed, 20 stamina cost, 1 s cooldown, ghost trail particles
  - Roll squish animation (`player.py`); LMB=attack, RMB=block (future), Space=roll
  - **Done (May 2026)**

- [x] **Controls Rebind Screen** (`client/rendering/controls_settings.py` NEW)
  - ESC → Pause Menu → Controls button; `config.keybinds` dict with 11 rebindable actions
  - Clickable key buttons, yellow listening mode, fixed non-rebindable rows (Attack=LMB, Block=RMB)
  - All K_* constants in `controls.py` and `controls_movement_v2.py` replaced with `config.keybinds[...]`
  - **Done (May 2026)**

- [ ] **Block / Parry** (`client/input/controls.py`)
  - Hold `RMB` to block: reduces all incoming damage by 60%, drains 5 stamina/s while held
  - "Perfect parry" window: if block is activated within 0.15 s of an incoming hit, the hit is
    completely negated and the attacker is staggered for 0.5 s (cannot attack or move)
  - Server stores `block_time` timestamp per player; combat.py checks the window on each hit

- [ ] **Combo chain** (`client/input/controls.py` + `server/network/combat.py`)
  - Attacks within 0.8 s of the previous hit count as a chain; `combo_count` increments (max 4)
  - Each hit in chain does `base_dmg × (1 + combo_count × 0.2)` — 4th hit does 180% damage
  - After 4 hits or after 0.8 s gap, combo resets
  - Client shows the combo counter as a small HUD number that fades out

- [ ] **Ranged attacks — Bow** (`client/input/controls.py` + `server/network/combat.py`)
  - New hotbar item type `slot_type: "ranged"` — `Bow` (requires arrows in inventory)
  - Hold `Space` to charge (up to 1.0 s), release to fire; damage = `base × charge_fraction`
  - Server spawns a `projectile` entity: `{id, owner, pos, vel, damage, range}`; updates position
    each tick; on player/mob intersection within `PROJECTILE_RADIUS=0.3`: deal damage, remove
  - Client renders projectiles as a small sprite with rotation matching velocity vector

- [ ] **Magic / Staff** (stretch goal)
  - New resource: `Mana` (same bar system as stamina; max 100, regen 5/s)
  - New hotbar item type `slot_type: "staff"` — `Fire Staff`, `Ice Staff`
  - `Space` fires a slow high-damage projectile; uses 30 mana
  - Fire: sets target on fire (5 damage/s, 3 s); Ice: applies `frozen` (immobilized 1.5 s)

- [x] **Status effects system** (`server/game_state/status_effects.py` — NEW; `client/rendering/status_effects.py` — NEW)
  - `tick_status_effects(players, dt)` ticks `poison_timer` down, applies `poison_dps × dt` damage each server tick
  - `apply_poison(pid, players, duration, dps)` — sets timer (max of existing/new), immune in creative mode
  - `pending_slow` dict in `mob_manager.py` handles spider web-slow; `pending_poison` handles scorpion poison
  - Client: `config.poison_timer` + `draw_status_effects()` pulsing green tint
  - **Done (May 2026):** poison implemented; fire/freeze are future additions

---

## Phase 15: More Sprites & Visual Polish

> Art is the most player-visible change. Prioritize highest-impact items first.

- [ ] **Mob sprite sheets** — Each mob needs 4-directional walk (4 frames) + attack (4 frames)
  - Minimum required: skeleton, spider, scorpion (can recolour/modify existing slime sheets)
  - Store at `client/assets/mobs/{mob_type}/walk_{dir}_{frame}.png`
  - Mob renderer (`client/rendering/mobs.py`) already reads `mob["type"]` — just add new sprite loader paths

- [ ] **Player sprite customization** (`client/rendering/player.py`)
  - Player sprite is currently a single fixed sheet
  - Add 3 base "body" variants (human, elf, orc) selectable at character creation
  - Outfit overlay: render `client/assets/player/outfits/{chest_item_id}.png` on top of base body each frame
  - Equipping a chestpiece visually changes the player sprite (client-side overlay blend)

- [ ] **NPC sprites** (`client/assets/npcs/`)
  - Static 1-frame sprites for: merchant, blacksmith, innkeeper, healer
  - Idle animation (2 frames, 1 s cycle) to make towns feel alive

- [ ] **Animated tiles** (`client/rendering/display.py` + `server/world/`)
  - Water tiles: 4-frame ripple animation (loop every 0.6 s); tie to global `pygame.time.get_ticks()`
  - Lava tiles (if added): same but orange
  - Grass tiles: occasional 2-frame sway triggered by proximity to player movement

- [ ] **Particle system** (`client/rendering/particles.py` — new file)
  - `Particle`: pos, vel, lifetime, colour, size (shrinks to 0 over lifetime)
  - `ParticleSystem`: list of particles, `emit(pos, count, spread, colour)`, `update(dt)`, `draw(surf)`
  - Emit events: hit flash (red sparks), item pickup (gold sparkle), level-up (rainbow burst),
    crafting success (white puff), death (grey smoke), dodge trail (white ghost smear)

- [x] **Day/night cycle** (`server/game_state/sync.py` + `client/rendering/display.py`)
  - Server tracks `world_time` (0.0–24.0, advances 0.02 per tick → 10-min real-time day)
  - Client receives `world_time`; renderer overlays a dark semi-transparent surface:
    `alpha = 0` at noon, `alpha = 160` at midnight (smooth sine curve)
  - Torch items / town fires create small radial "light holes" in the darkness overlay
  - **Done (May 2026):** epoch-based `world_time` in `game_sync.py` (`_WORLD_DAY_SECONDS=600`); `draw_day_night_overlay` added to `display.py`; called before HUD in `client.py`
  - **Light holes done (May 2026):** `client/rendering/light_sources.py` (NEW) — `apply_light_holes(overlay)` punches soft radial holes via `BLEND_RGBA_MIN`; campfire=5-tile radius; hole cache keyed on `(radius_px, max_alpha)`; `config.camera_offset_x/y` set each frame

- [x] **Minimap** (`client/rendering/minimap.py` — NEW)
  - 128×128 top-right corner panel; `MM_TILE_PX=2` → shows 64×64 tile area around player
  - Biome colour palette (11 biomes), fog-of-war via `config.visited_chunks` (marks ±3 chunks)
  - Player dot (white) always centred; mob dots (red / green for animals / gold for boss)
  - Rebuilds surface only when player crosses a tile boundary; semi-transparent dark background
  - **Done (May 2026):** `minimap.py` created, `config.visited_chunks: set` added, `draw_minimap()` wired into `client.py` after `draw_chat()`

- [x] **Night-only mob spawns** (`server/mobs/mob_manager.py`)
  - Slimes and skeletons only spawn when `world_time < 6.0` or `world_time > 18.0`
  - Existing mobs on map are unaffected; only new spawns are gated
  - **Done (May 2026):** `_get_world_time()` imported from `game_sync`; `_is_night` check added to both spawn blocks in `update_mobs`

- [x] **Bed: sleep through night** (`server/game_state/game_sync.py`, `server/network/tcp_state_handlers_v2.py`, `client/`)
  - Press E on a bed at night → player marked sleeping; world_time snaps to 6:00 when threshold met
  - Solo/duo: 1 sleeper triggers skip immediately; 3+ players: strict majority (>50%) required
  - Client shows dark overlay + "Zzz" + "Press WASD to wake up"; movement blocked while sleeping
  - **Done (May 2026):** `_sleeping_players` set + `set_player_sleeping` + `_skip_to_morning` in `game_sync.py`; `_handle_wake_up` route in `tcp_state_handlers_v2.py`; `draw_sleep_overlay` in `display.py`; movement gated in `controls_movement_v2.py`

- [x] **Weather system** (`server/game_state/weather.py` — NEW; `client/rendering/weather.py` — NEW)
  - Markov-chain state machine: clear/cloudy/rain/snow/fog; weighted transitions; 60–240 s per state
  - `get_weather()` added to every game-state packet; `config.weather` read by client handler
  - Client: rain=200 diagonal drops, snow=150 sin-wobble flakes, fog/cloudy=semi-transparent overlay
  - **Done (May 2026):** both files created; `config.weather` + handler wired; `draw_weather()` called from `client.py`

---

## Phase 16: Dungeons & Endgame Content

> High-difficulty zones that reward coordinated multiplayer and provide endgame progression.

- [ ] **Dungeon instancing system** (`server/world/dungeon_gen.py` — new file)
  - Dungeons are separate chunk zones (chunk IDs prefixed `dungeon_`) not in the overworld grid
  - Procedurally generated: 20×20 tile room connected by 3-tile corridors, 5–10 rooms per dungeon
  - Entrance: a special tile placed in the overworld near mountain/cave biomes
  - Entering the entrance tile teleports all nearby players into a shared dungeon instance

- [ ] **Dungeon mob density**
  - Dungeon rooms spawn 3–8 mobs of a type appropriate to the dungeon's biome theme
  - Mobs do not respawn once cleared; room is "cleared" when all mobs dead
  - Cleared rooms persist until the dungeon instance resets (server restart or 30 min timer)

- [ ] **Boss room** (final room of each dungeon)
  - Contains a single boss mob (Slime King, Skeleton Lord, etc.)
  - Door to boss room only opens when all prior rooms are cleared
  - On boss death: spawn a chest with guaranteed rare/exquisite drop + unique boss material

- [ ] **Dungeon chest** (`server/game_state/world_items.py`)
  - `Chest` is a special world object; interacting sends `"open_chest"` TCP message
  - Server rolls loot table based on dungeon tier (tier 1: common/uncommon; tier 2: rare; tier 3: exquisite)
  - Chest opens once per player (server tracks which players have looted each chest)

---

## Phase 17: Multiplayer Social Features

> Makes the game feel like a world shared with real people.

- [ ] **Player-to-player trading** (`server/network/tcp_routes.py` + `client/rendering/trade.py`)
  - Press `T` while targeting another player (within 2 tiles) to send a trade request
  - Both players see a split trade UI: drag items from inventory to offer slots; both click "Confirm"
  - Server holds trade in escrow, validates both players have the items, then swaps

- [ ] **Party system** (`server/game_state/sync.py` + client)
  - Press `Y` near a player to send a party invite; up to 4 players
  - Party members: share XP gain when within 10 tiles, see each other on minimap regardless of distance,
    can't deal PvP damage to each other
  - Party leader can initiate a dungeon-enter vote

- [x] **Chat system** (`server/network/tcp_state_handlers_v2.py` + `client/rendering/chat.py`)
  - Press `Enter` to focus chat input; `Enter` again to send; `Esc` to cancel
  - Global chat broadcast; chat history fades after 10 s; Minecraft-style panel bottom-left
  - **Done (prior sprint):** `broadcast_chat` + `_handle_chat` on server; `draw_chat` + `config.chat_messages` on client; sender colours + system message support

- [ ] **PvP & safe zones**
  - Town tiles are flagged `safe_zone: true` in town data; combat.py rejects attacks against players
    standing in a safe zone
  - Wilderness is open PvP by default; add a `/pvp off` toggle to opt out (both players must opt in)
  - On PvP kill: attacker gains 10% of victim's held coins; victim drops equipped weapon in world

---

## Phase 18: Player Progression & Skills

> Deepens the sense of character growth beyond just stat increments.

- [ ] **Skill tree** (`server/player_saves/` + `client/rendering/skill_tree.py`)
  - Press `K` to open skill tree; 3 columns (Warrior / Ranger / Mage), each with 5 tiers of nodes
  - Spending a skill point unlocks a passive bonus or new ability (e.g. Tier 1 Warrior: +10% melee dmg)
  - Earn 1 skill point per level; max level 50; `skill_tree` stored in player save as `{node_id: true}`
  - Server reads unlocked skills in combat.py and applies modifiers to damage/stamina/cooldowns

- [ ] **Class selection** (character creation, one-time choice)
  - Three starting classes: Warrior (more HP, melee bonuses), Ranger (more stamina, ranged bonuses),
    Mage (mana resource, magic bonuses)
  - Class modifies base stats and unlocks class-specific skill tree nodes
  - Stored as `"class": "warrior"` in player save; cannot be changed after creation

- [ ] **Achievements** (`server/achievements.py` — new file)
  - Define achievements as conditions: `"First Blood"` (kill first mob), `"Explorer"` (visit 50 chunks),
    `"Treasure Hunter"` (open 10 chests), `"Crafter"` (craft 20 items)
  - Server checks conditions in relevant event handlers; awards achievement to player on first trigger
  - Client shows a toast notification (top-right banner, 3 s display) when an achievement is unlocked

- [ ] **Loot rarity overhaul** (`server/game_state/crafting.py` + `server/items.json`)
  - Add two new tiers: `Legendary` (multiplier 2.5–4.0×) and `Set` (fixed named stats, set bonuses)
  - Set items: when ≥ 2 set pieces are equipped, a bonus activates (e.g. "Slime Set" = +20% speed)
  - Server checks equipped slots for set membership each tick; adds to broadcast stats

---

## Phase 19: Quality of Life & Polish

> Small improvements that make the game feel finished.

- [ ] **Minimap** (`client/rendering/minimap.py` — new file)
  - Fixed 128×128 pixel panel in the top-right corner; fog-of-war with visited tiles revealed
  - Biome colours: ocean=dark blue, plains=yellow-green, forest=dark green, mountain=grey, desert=tan
  - Player dot (white), party members (green), mobs (red), NPCs (yellow), dungeon entrance (purple)
  - Fog cleared by exploring; `visited_chunks` set stored in `client/config.py`

- [ ] **Settings menu** (`client/rendering/settings.py` — new file)
  - Press `Esc` to open; tabs: Graphics, Audio, Controls, Network
  - Graphics: resolution select, fullscreen toggle, tile scale slider (1×/2×)
  - Audio: master/music/sfx volume sliders (for when sound is added)
  - Controls: keybind remapping table (currently fixed; this makes them configurable)
  - Settings persisted to `client/settings.json`

- [x] **Auto-stack on pickup** (`server/game_state/world_items.py`)
  - When adding an item to inventory, first try to fill existing stacks before using an empty slot
  - Partial pickup: if inventory is full but an existing stack has room, fill the stack first
  - **Already implemented:** `_add_to_inventory()` in `world_items.py` fills partial stacks before opening new slots

- [x] **Quick-equip** (`client/input/controls.py` + `client/rendering/inventory.py`)
  - Right-click an equippable item in the grid: auto-move to the correct equip slot (or swap with current)
  - Right-click an equipped item: auto-move to first free grid slot
  - **Done (May 2026):** right-click handler in `controls.py` branches on slot index and `_ITEM_SLOT_TYPES`; ring slots use 38→39 fallback

- [ ] **Sound effects** (`client/audio/` — new directory)
  - Use `pygame.mixer` (already in pygame); load `.ogg` files for: footstep, sword swing, mob hit,
    mob death, item pickup, UI click, craft success, level-up
  - `AudioManager` singleton: `play(sound_id)`, `set_volume(channel, vol)`
  - Placeholder: free CC0 sounds from opengameart.org

- [ ] **Background music** (`client/audio/music.py`)
  - `pygame.mixer.music` for streaming background tracks
  - Track list by biome: plains (calm), forest (mysterious), dungeon (tense), town (ambient)
  - Crossfade 1 s when biome changes (detect via player chunk biome in game state)

---

## Technical Debt & Infrastructure

> Non-feature work that improves stability, security, and maintainability.

- [ ] **Mob persistence on disk** (`server/mobs/mob_manager.py`)
  - On clean server shutdown, write `server/mob_state.json` with all active mob data
  - On startup, load it if present (skip if stale > 10 min); prevents mob wipe on quick restart

- [ ] **Server-side world bounds** (`server/network/udp_routes.py`)
  - Define `WORLD_RADIUS` (e.g. 500 tiles); reject any position update outside it
  - Teleport-cheat mitigation: if new pos is > `max_speed × dt × 2.0` tiles from last pos, ignore

- [ ] **UDP rate limiting** (`server/network/udp_routes.py`)
  - Track `last_udp_time` per player; drop packets arriving faster than 1 / (TICK_RATE × 2)
  - Prevents malicious clients from saturating the server with movement spam

- [ ] **Connection keepalive timeout** (`server/cleanup.py`)
  - Players with `last_seen` > 30 s ago should be cleaned up even if the TCP socket is still open
  - Heartbeat: client sends `{"type": "ping"}` every 5 s; server updates `last_seen`

- [ ] **Chunk LRU eviction** (`server/world/`)
  - `world_data` dict grows indefinitely as players explore
  - Implement an LRU cache (max 256 chunks): evict least-recently-accessed chunk when over limit
  - Evicted chunks are still on disk; reloaded on next access

- [ ] **Input validation on all TCP routes** (`server/network/tcp_routes.py`)
  - All `data["field"]` accesses should use `.get()` with a safe default or an explicit validation step
  - Malformed packets currently raise `KeyError` and crash the handler thread

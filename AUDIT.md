# Codebase Audit
Generated after current sprint. Each file graded A–F.

**Grade scale**
- **A** — Clean, idiomatic, minimal technical debt
- **B** — Mostly good; minor issues or missed opportunities
- **C** — Functional but notable problems (complexity, duplication, missing guards)
- **D** — Works but has serious structural or safety problems
- **F** — Has a blocking bug, security vulnerability, or is not fit for purpose

---

## SERVER

### server/__init__.py · A
Empty package marker. Correct.

---

### server/config.py · A (23 lines)
Clean constant definitions. All values are documented. No issues.

---

### server/shared_lock.py · A (28 lines)
Single source of truth for all threading locks. Correct import pattern — modules import
exactly the locks they need. No issues.

---

### server/item_data.py · A (166 lines)
**Strengths:**
- `orjson` fast-path with stdlib fallback.
- `_get_slot_stats()` handles both raw and meta slots, correctly returns `{}` for broken items.
- `get_equip_bonuses()`, `get_hotbar_bonus()` are clean, well-scoped helpers.
- `is_valid_equip_placement()` guards equip-slot swaps server-side.
- `drain_durability()` is properly defensive (checks len, type, presence of `dur` key).
- `get_sell_price()` applies quality multipliers correctly.

**Minor nits:**
- `_EQUIP_SLOT_TYPES` and `_EQUIP_SLOTS` in `game_sync.py` are partially duplicated — centralise in `item_data.py`.
- No `__all__` but not required for a server module.

---

### server/player_save.py · B+ (75 lines)
**Fixed this sprint:** Added `_SAFE_ID` regex validation on `player_id` to prevent
path-traversal (OWASP A01). Before the fix `save_player("../../etc/shadow", ...)` would have
written outside `player_saves/`.

**Remaining nit:**
- Save is plain `json.dump` without `indent`; resulting files are single-line, hard to inspect
  manually. Low priority but consider `indent=2` for debuggability.

---

### server/cleanup.py · A (68 lines)
Clean disconnect logic: removes from all three client dicts, closes sockets outside lock,
saves player outside lock. Calls `_sync_invalidate` and `_game_sync_invalidate` correctly.
No issues.

---

### server/server.py · B+ (178 lines)
**Strengths:**
- `ThreadPoolExecutor` with per-player future tracking (`_world_futures`, `_state_futures`)
  prevents duplicate sends under lag — good design.
- `timeBeginPeriod(1)` on Windows for accurate 120 Hz loop.
- Deferred game_state injection via `set_*_refs()` avoids circular imports.

**Improvements:**
- `game_loop()` catches exceptions per-subsystem but prints bare `str(e)` with no traceback.
  Use `traceback.print_exc()` so stack frames aren't silently dropped.
- `time.sleep(1 / TICK_RATE)` is not self-correcting — tick wall-time creep accumulates.
  Should track elapsed time and subtract from sleep duration.

---

## server/game_state/

### crafting.py · A (189 lines)
**Strengths:**
- Clear quality system (`_roll_quality`, `_roll_stats`) with tier probabilities and
  multiplier ranges.
- `_count` / `_consume` helpers are tight and correct.
- `handle_craft()` correctly validates: recipe exists, station proximity, sufficient
  ingredients, then consumes and returns item with full meta (stats, dur, quality).

**Nit:** `_roll_stats` does not special-case integer-valued stats that should remain integers
after rolling (e.g. `gem_slots`). Any float key in `base_stats` could produce a float
`gem_slots`. Guard with `isinstance(v, int)` → `round()` already done, but `gem_slots`
should always be int — consider explicit integer cast for slot-count fields.

---

### embedder.py · A (99 lines)
Clean. Validates: item has gem_slots ≥ 1, no gem already embedded, gem ID is valid.
Applies gem trait and marks dirty. No issues.

---

### game_sync.py · B (178 lines)
**Strengths:**
- Dirty-flag inventory coalescing prevents unnecessary state broadcasts.
- `tick_player_deaths()` correctly handles death/respawn with timed delay.
- `send_game_state()` snapshots player under lock then computes outside — minimal lock hold.
- **Performance fix (this sprint):** Removed duplicate `_get_planted_snapshot()` call that was
  being immediately overwritten.
- Now imports and calls `ensure_dungeons_near`, `check_boss_trigger`, `get_dungeons_near`
  (from `dungeon_gen`); `"dungeons"` key added to state packet payload.

**Issues:**
- `_EQUIP_SLOTS = (36, 37, 40, 41, 42, 44)` is redefined inside `send_game_state()` on
  every call. Should be a module-level constant (or imported from `item_data.py`).
- The `_equip_ids()` inner function is redefined on every call — hoist it.
- No unit test coverage for the respawn-delay edge case.

---

### item_spawner.py · B (139 lines)
Functional. Handles world node respawns (trees, ores). Grow timers and `GROWS_INTO` map
are defined in `placed_objects.py`, a reasonable separation.

**Issues:**
- Hard-coded `_SPAWN_TABLE` duplicates some data from `items.json` (item name comments).
  Not a bug but increases maintenance surface.

---

### part_combiner.py · A (270 lines)
**Strengths:**
- Clean three-dict design (`_MOLD_MAP`, `_MOLD_WEAPON_NAME`, `_MOLD_SLOT2_TYPE`).
  Adding a new mold requires editing exactly three lines + a recipe entry.
- Now correctly handles 16 molds including Rapier/Hammer/Wand/Cloak added this sprint.
- `_compute_meta()` cleanly derives stats from part_stats dicts.
- Armor path (plate + lining + binding) is clearly separated from weapon path.

**Nit:** `_ARMOR_MOLD_IDS` is a `frozenset` — good. But it is repeated in both
`part_combiner.py` and `client/rendering/combiner.py`. One truth source would be cleaner
(e.g., derive from `_MOLD_MAP` where `is_armor=True`).

---

### placed_objects.py · B (363 lines)
**Strengths:**
- `_tile_index` for O(1) occupancy lookup — correct optimisation.
- Background flush thread with dirty flag avoids per-operation disk writes.
- Chest slot swap, door toggle, bed use are all cleanly separated.

**Issues:**
- `PLACEABLE_ITEMS` and `ITEM_FOR_TYPE` duplicate item→station associations that arguably
  belong in `items.json` (`"placeable_as": "crafting_table"`). Current approach is fine
  but fragile when adding new station types.
- `chest_swap()` does not validate that both slot indices are in range — can raise
  `IndexError` on a malformed client message. Add bounds check.

---

### repair.py · B (251 lines)
Functional. Repair cost formula is defensible. Material cost lookup is clean.

**Issues:**
- `_REPAIR_MATS` hard-codes material item IDs alongside their names. If a future sprint
  rekeys material item IDs, this will silently break. Consider comments with item names
  or a `get_item()` name lookup for logging.

---

### sync.py · A (61 lines)
Clean hash-based delta world sync. `invalidate_player` correctly evicts player from both
`last_chunk_hashes` and `delta_cache`. No issues.

---

### world_items.py · B (87 lines)
Functional. Handles dropped items (pickup radius, stack merge). No issues.

**Nit:** The pickup radius (`1.2` tiles) is a hard-coded float. Should be a named constant.

---

## server/mobs/

### mob_manager.py · B (1 200+ lines)
**Strengths:**
- Full state machine: wander → aggro → windup → lunge → landing → return_to_origin + new
  `slam_charge` (Yeti AOE) and `flee` (passive animals).
- 9 mob types: slime, skeleton, spider, scorpion, bat, yeti, rabbit, deer, slime_king.
- Per-mob constants: `drop_id`, `windup_time`, `lunge_speed`, `aggro_range`; no code duplication.
- `drain_events()` public API for async boss-event broadcast without coupling to server.py.
- `_biome_at()` helper; biome-gated spawns for each mob type.
- `_slime_king_active` flag enforces 1-boss-at-a-time globally.
- **Performance fixes (this sprint):** Single-pass type count (replaces 8 `sum()` calls);
  solid-cache with `_solid_revision` dirty flag (O(9) lookup, previously O(n_walls) per mob);
  player list built once before all spawn checks.
- **Boss spawn refactor:** `spawn_boss_at(pos)` public function replaces random-timer spawn.
  `_boss_dungeon_pos` tracks which dungeon owns the active boss. `boss_defeated` event now
  includes `dungeon_pos` so `server.py` can set the respawn cooldown.

**Issues:**
- Still using module-level scalar globals for all mob constants — a `MobType` dataclass or
  JSON-driven definition table would make adding new enemy types much faster.
- `_players` mutable reference dict accessed under `mobs_lock` but not `players_lock` — race
  risk on simultaneous disconnect. Grab pid→pos snapshot under `players_lock` at start of tick.
- Mob counts don't scale with connected player count; `MAX_*` are fixed constants.
- `pending_spawns` list allocated inside every tick even when empty.

---

## server/network/

### combat.py · B (118 lines)
Clean attack handler. Validates attacker, computes damage from stats and equipped weapon,
applies knockback, handles death event. `drain_durability` called on the weapon slot.

**Issue:** No server-side validation of attack direction/position plausibility (speed
hacking would let a player hit targets at unlimited range). Rate-limit or distance-check
player vs target position.

---

### listener.py · A (40 lines)
Minimal accept loop; spawns threads for each connection. Reuses the executor correctly.

---

### net_utils.py · A (36 lines)
`send_json` / `recv_json` with size prefix framing. `orjson` used throughout.
No issues.

---

### tcp_routes.py · B (490 lines)
**Strengths:**
- Robust message receive loop: size check, chunk accumulation, `10 MB` cap.
- `inv_swap` validates both slot bounds and equip type compatibility.
- `craft` delegates to `handle_craft` correctly.
- `spend_stat` only allows known stat keys via `_UPGRADES` whitelist.

**Issues:**
- `handle_state()` is a 400-line monolith handling every message type inline. Should be
  split into a dispatcher pattern (`_HANDLERS: dict[str, Callable]`) for readability and
  testability.
- `_give_item()` does not validate `item_id` against `items.json` — an attacker who
  somehow triggers a crafting result with a bogus item_id would silently create an item
  with no definition. Add `if not get_item(item_id):` guard.
- `player_id` from handshake is used as a dict key and in log strings but is never
  sanitized in `handle_world` / `handle_state`. A very long or specially crafted player_id
  could bloat logs. Apply the same `_SAFE_ID` check used in `player_save.py`.

---

### udp_routes.py · B (249 lines)
**Strengths:**
- `_UDP_MIN_INTERVAL` rate-limiting per client prevents movement flooding.
- `_safe_spawn_pos()` spirals out to find dry land for new players.
- Out-of-order packet rejection via sequence number.

**Issues:**
- `player_id` from UDP payload is also unsanitized — same issue as tcp_routes. Apply
  `_SAFE_ID` check before using player_id as a dict key.
- No authentication: any client that knows another player's `player_id` can send movement
  packets on their behalf. Consider a session token assigned at join.

---

## server/world/

### dyn_chunk_gen.py · A (576 lines)
**Strengths:**
- V3 generator: domain warp + ridge noise + spline curves + biome climate system.
- `@njit` / `@prange` Numba JIT on inner loops — production-quality performance.
- `orjson` fast-path for chunk I/O.
- `queued_chunks` dedup prevents redundant generation.

**Issues:**
- `SEED = 42` is a hard-coded module constant. A world seed per-game is standard;
  this needs to be configurable.
- `np` import at module level — if `numba` is not installed the server will error at import
  even before generating a chunk. The `try/except ImportError` around `numba` is present
  but `numpy` has no fallback. Add a fallback check.

---

### resource_nodes.py · B (455 lines)
Comprehensive node system: all tree / ore / herb types, grow timers, depleted snapshot,
harvest reward tables. Clean.

**Issue:** `_NODE_MAX_HP` is duplicated in `client/networking/handlers.py`. These must
be kept in sync manually. The client should receive node HP from the server or share a
common definition file.

---

### autosave.py · A (28 lines)
Simple periodic chunk flush thread. No issues.

### chunk_utils.py · A (14 lines)
Small coord-to-chunk helpers. No issues.

### town_gen.py · A (NEW)
Deterministic town placement on a 30-chunk grid. Hash-jitter anchors, four 5×5 stone-brick
buildings with open door + 3-tile paths + 3×3 plaza. `ensure_towns_near()` is idempotent
(checks `_built_towns` set). `get_npcs_near()` returns NPC list for state packets.

No issues.

---

### dungeon_gen.py · A (NEW)
Deterministic Slime Lair placement on a 25-chunk grid (400-tile pitch between lairs).
`ensure_dungeons_near()` builds the 15×13 stone-brick shell + floor on first player approach.
`check_boss_trigger()` returns trigger positions when a player is within 8 tiles of centre.
`set_boss_cooldown()` writes a 5-minute respawn gate after boss defeat.

All public functions are side-effect-free reads except `_build_dungeon()` (idempotent via
`_built_dungeons` set). No issues.

---

## CLIENT

### client.py · C (678 lines) ⚠ BOM
**Issues:**
- **UTF-8 BOM** at byte 0 (`\xef\xbb\xbf`). Python 3 can handle this at runtime but it
  causes issues with some tools and `ast.parse()`. Save the file as UTF-8 **without** BOM.
- Main game loop is ~500 lines inline — should be split into `_handle_events()`,
  `_update()`, `_render()` functions.
- Broad `except Exception` blocks around subsystems swallow tracebacks silently. Use
  `traceback.print_exc()` so errors surface during development.
- No frame-time accumulation: `clock.tick(FPS)` is called but `dt` is not always used
  for physics integration — some movement code may be frame-rate-dependent.

---

### client/config.py · B (194 lines)
Large but acceptable. All game constants in one place.

**Issue:** Some constants are duplicated on the server side (e.g. `TILE_SIZE`, `WORLD_RADIUS`).
A shared `constants.py` importable by both sides would prevent drift.

---

### client/shared_lock.py · A (5 lines)
Thin wrapper re-exporting `data_lock`. Fine.

---

## client/input/

### controls.py · C (957 lines)
**Issues:**
- **Single 957-line file handles all input** — keyboard shortcuts, mouse clicks, building
  mode, attack, hotbar, inventory drag, station interaction, menu. Should be split by
  subsystem: `controls_movement.py`, `controls_inventory.py`, `controls_building.py`.
- `_TOOL_ITEMS` and `_NODE_TOOL` dicts duplicate server-side data from
  `resource_nodes.py`. Drift between server and client tool requirements is a known bug
  source.
- `_TOOL_DAMAGE` is another server-duplicate. These should come from the server in the
  initial handshake payload.

---

## client/networking/

### handlers.py · B (398 lines)
Handles all incoming server messages cleanly. Inventory sync, state update, chunk receive,
mob updates, world item spawns, node updates.

**Issues:**
- `_NODE_MAX_HP` is redefined here, duplicating `resource_nodes.py`. See note above.
- The `RemotePlayer` class is defined here (50 lines) instead of in a dedicated module.
  At 398 lines total the file is approaching the limit of comfortable readability.

### protocols.py · A (48 lines)
Clean framing helpers. No issues.

### sockets.py · A (16 lines)
Minimal connect-with-retry. No issues.

---

## client/rendering/

### ui_theme.py · A (44 lines)
Canonical colour palette. All constants documented. **Now imported by all popup files.**
No issues.

---

### display.py · C (576 lines)
**Issues:**
- **`from config import *`** (star import) pollutes the module namespace and makes it
  impossible to tell at a glance where a name comes from. Replace with explicit imports.
- `toggle_fullscreen()` re-initialises `pygame.display` with `pygame.display.quit()` /
  `pygame.display.init()` — this destroys and recreates the display context, which is
  fragile on some drivers. Use `pygame.display.set_mode()` flags directly.
- World rendering mixes tile draw, entity draw, and ghost-object draw in one function;
  consider separating into `draw_terrain()`, `draw_entities()`, `draw_overlay()`.

---

### inventory.py · B (634 lines)
**Improvements this sprint:** Slot background standardised to `ui_theme.SLOT_BG` (was
`(55, 55, 55)`). Now imports `ui_theme`.

**Remaining issues:**
- `_draw_slot()` is called for both bag slots and equip slots but with different context
  objects — a `selected` bool that sometimes represents different selection states.
  The function signature is getting complex.
- Tooltip building (`_build_tooltip_surface`) is ~120 lines inline; could be extracted.
- `from config import *` at module top (via `display.py` imports) — see display.py note.

---

### crafting.py · B (525 lines)
**Improvements this sprint:** Panel chrome now uses `_T.BG_FILL`, `_T.BORDER`,
`_T.TITLE_BAR`. CRAFT button uses `_T.BTN_*`. Imports `ui_theme`.

**Remaining issues:**
- `_STATION_META` maps station types to `(title, colour)` tuples where colour is used for
  the station-specific title text accent. This is the last per-station colour divergence
  from the theme. Consider whether all stations should share `_T.TITLE_TXT` or keep the
  per-station accent.
- Tab bar `sel_bg = (44, 52, 64)` and `(18, 18, 22)` for selected/unselected tabs are
  still hardcoded. Should use `_T.TITLE_BAR` (selected) and `_T.BG_FILL` (inactive).
- `draw_station_popup()` is 100 lines; extracting `_draw_tab_bar()` (already exists) and
  `_draw_detail()` (already extracted) is good. Could further extract `_draw_list_area()`.

---

### combiner.py · A (569 lines)
**Improvements this sprint:**
- Local colour block removed. All colour references now use `_T.*` constants.
- Molds 210 (Rapier), 211 (Hammer), 212 (Wand), 213 (Cloak) added to `_MOLD_HINT`,
  `_MOLD_BASE`, `_MOLD_SLOT2`.

No remaining issues.

---

### embedder.py · A (397 lines)
**Improvements this sprint:** Local colour block removed. All colour references now
use `_T.*` constants.

No remaining issues.

---

### chest.py · B (183 lines)
**Improvements this sprint:** Imports `ui_theme`. Panel chrome uses `_T.*`.

**Remaining nit:** Chest grid uses `9 × 4 = 36` slots but chest capacity is configurable
per-object in `placed_objects.py`. If capacity ever differs from 36 the UI will silently
clip or show empty slots. Pass capacity as a parameter.

---

### stat_screen.py · B (133 lines)
**Improvements this sprint:** Imports `ui_theme`. Button hover uses `_T.BTN_HOV`.

**Remaining nit:** Stat upgrade button labels are hardcoded strings that must match the
`_UPGRADES` keys in `tcp_routes.py`. A mismatch would silently fail (server rejects unknown
stat key). Centralise the stat key list.

---

### repair.py · B (337 lines)
**Improvements this sprint:** Imports `ui_theme`. Slot background now uses `_T.SLOT_BG` /
`_T.SLOT_BD` for empty/normal slots. Selected slot highlight uses `_T.BTN_BD` border.

**Remaining nit:** The repair cost formula (material qty × sell_price) is duplicated
between `client/rendering/repair.py` and `server/game_state/repair.py`. Client uses it for
display-only preview; any drift would show wrong costs in the UI. Ideal fix: server sends
computed cost in the repair quote message.

---

### menu.py · A (81 lines)
**Improvements this sprint:** All button colours use `_T.NAV_BG`, `_T.NAV_HOV`,
`_T.NAV_BD`. Hint text uses `_T.HINT_TXT`.

No remaining issues.

---

### hud.py · B (213 lines)
HP/SP bars, level bar, and toast notifications are clean.

**Issues:**
- Toast queue maximum depth is not bounded — rapid server messages could queue many toasts.
  Cap at `_MAX_TOASTS = 5` and discard oldest.
- Bar widths are computed from `WINDOW_WIDTH` captured at module init. On window resize
  the bars will be incorrectly positioned until the module's font/layout constants are
  re-evaluated. Pass `ww, wh` as parameters or recompute each frame.

---

### item_art.py · C (2266 lines)
**Issues:**
- **2266-line monolith.** Should be split into:
  - `item_art_weapons.py` — sword/axe/pickaxe/wand draw functions
  - `item_art_armor.py` — helm/chest/arms/legs/boots draw functions
  - `item_art_materials.py` — ore, bar, gem, food draw functions
  - `item_art_tools.py` — tool draw functions
  - `item_art.py` — dispatcher that imports and calls the above
- No per-sprite caching in the draw functions themselves — callers (combiner, crafting,
  inventory) must manage `_art_cache` externally. A centralised `get_item_surface(id, sz)`
  cache in `cache.py` would simplify all callers.
- Many draw functions share nearly-identical code (draw a circle outline + fill + highlight)
  that could be extracted into a `_draw_gem(surf, col)` helper.

---

### equipment_layers.py · B (375 lines)
LPC equipment sprite compositing. Clean, well-structured.

**Issue:** `_LAYER_ORDER` list defines render order for equipment sprites. This list
must be kept in sync with LPC sprite sheet definitions. A mismatch shows the wrong
layer on top. Consider a data-driven approach (read from a YAML/JSON that also drives
asset generation).

---

### player.py · B (362 lines)
Player sprite drawing with walk/attack animation.

**Issue:** Frame timing uses `dt` from the game loop but `dt` accuracy depends on
`clock.tick()` precision. No issue in practice but animation speed will be frame-rate-
dependent if the server ever changes `TICK_RATE`. Mirror the animation timer on
`time.time()` instead for absolute consistency.

---

### mobs.py · B (333 lines)
Handles rendering for 9 mob types. Procedural sprites for bat, yeti, rabbit, deer, slime_king
drawn with `pygame.draw` at first call and cached as module-level surfaces. Skeleton uses LPC
walk sheet (9 frames × 4 dirs, 64×64 px). Health bar overlay, hit-flash animation states.

**Issues:**
- Frame-timing via `dt` still frame-rate-dependent (same note as `player.py`).
- Procedural sprite draw code is inline in `_ensure_loaded()` — could be split into
  per-mob `_make_*_surf()` helpers for readability.
- No shadow/depth sorting — tall mobs (yeti) can occlude ground items at same y.

---

### minimap.py · B (155 lines)  *updated (May/June 2026)*
128×128 top-right corner panel. Fog-of-war via `config.visited_chunks` (set of `(cx,cy)`).
Biome colour palette covers all 11 biomes. Player dot centred. Mob dots: gold=boss,
green=animals, red=others. **Dungeon markers (this sprint):** dark-red 7×7 squares for each
nearby Slime Lair from `config.dungeons`. Rebuilds surface only when player crosses a tile
boundary.

**Issues:**
- `_rebuild()` iterates all tiles in the 64×64 view area every time the player moves 1 tile;
  could be made incremental (shift + draw only the newly-visible strip).
- `visited_chunks` grows unbounded in long sessions — a set is fine for now but should be
  capped or serialised to disk if persistent fog-of-war is desired later.

---

### lpc.py · B (157 lines)
LPC sprite sheet slicing helpers. Clean.

**Issue:** Sprite sheet paths are hard-coded strings relative to the `assets/` directory.
Should be loaded from a manifest to support mod support or asset packs.

---

### cache.py · C (10 lines)
Barely exists — just a placeholder. The actual art caching is scattered across individual
rendering modules. **Should be expanded** into a proper centralised image cache used by
all rendering modules. Centralising here would eliminate the 5+ duplicate `_art_cache`
dicts spread across `combiner.py`, `embedder.py`, `crafting.py`, `repair.py`, `chest.py`.

---

## client/state/

### player.py · A (4 lines)
Minimal player state initializer. Fine.

### reset.py · B (97 lines)
Clears all client state on disconnect. Comprehensive.

**Nit:** `reset_all()` is called on both disconnect and initial startup — if new state
fields are added elsewhere, they must also be added here. Consider deriving the reset
from the same `config` defaults that initialise the fields.

### world.py · A (14 lines)
Thin world state holder. Fine.

---

## client/utils/

### logging.py · B (11 lines)
Basic log helper. Fine but currently unused in most modules (they call `print()` directly).
Adopting this consistently would make log level control possible.

---

## DATA FILES

### server/items.json · B (309 items after sprint)
- Consistent schema across all 309 items.
- `part_stats` entries are well-structured with `slot`, `base_atk`/`base_def`, `trait`.
- **Gap:** No `back` armour items at the Iron/Copper/Bronze tier (only Steel+). The new
  Back Mold (213) produces Steel Cape (3504) as base, which is correct for Part Combiner
  (Steel+ tier), but players with only CT access have no Back armour until tier 4.
  Consider adding Iron/Copper/Bronze back armour as CT craftable items.

### server/recipes.json · A (214 recipes after sprint)
- **Sprint fixes applied:** 98 incorrect Part Maker complete-item recipes removed.
  3 duplicate CT recipes removed. 11 new recipes added (2 parts, 9 CT coverage gaps).
- All 6 trinkets (Gold Chain, Iron Cross, Sun Amulet, Holy Pendant, Silver Chain,
  Shadow Star) now have CT recipes.
- Copper Axe, Iron Cape, Bronze Cloak now have CT recipes.
- All Part Maker recipes now produce parts only (blades, handles, bindings, molds, cores).
- No duplicate result IDs detected.

---

## PRIORITY IMPROVEMENT PLAN

### Tier 1 — Security / Correctness (do first)
1. ~~`player_save.py`: Path traversal via player_id~~ **FIXED this sprint**
2. `tcp_routes.py`: Sanitize `player_id` from handshake with `_SAFE_ID` regex
3. `udp_routes.py`: Sanitize `player_id` from UDP payload with `_SAFE_ID` regex
4. `placed_objects.py > chest_swap()`: Validate slot indices are in bounds
5. `combat.py`: Add distance check on attack — reject if attacker and target are
   more than ~3 tiles apart (anti-cheat)

### Tier 2 — Architecture
6. `controls.py`: Split by subsystem (movement / inventory / building / interaction)
7. `tcp_routes.py > handle_state()`: Replace inline if/elif with a `_HANDLERS` dispatch dict
8. `item_art.py`: Split into 4 domain files + dispatcher
9. `cache.py`: Expand into a proper centralised `get_item_surface(id, sz)` cache
10. `mob_manager.py`: Extract `MobType` dataclass so adding new enemy types doesn't
    require duplicating the state machine

### Tier 3 — Data Coherence
11. Share `_NODE_MAX_HP` / `_NODE_TOOL` between server and client (server sends in
    handshake, or move to a shared JSON)
12. Share `TILE_SIZE`, `WORLD_RADIUS`, `_EQUIP_SLOTS` between server and client
    (single `shared_constants.py`)
13. Centralise `_UPGRADES` stat key list so client stat screen and server handler
    cannot drift

### Tier 4 — Polish
14. `server.py > game_loop()`: Self-correcting sleep (subtract elapsed from target interval)
15. `hud.py`: Cap toast queue depth; pass `ww, wh` per-frame
16. `display.py`: Replace `from config import *` with explicit imports
17. `dyn_chunk_gen.py`: Make `SEED` configurable (per-world seed in config or CLI arg)
18. `player_save.py`: Use `indent=2` in `json.dump` for human-readable saves
19. `item_art.py`: Centralise gem drawing into `_draw_gem(surf, col)` helper
20. `equipment_layers.py`: Move `_LAYER_ORDER` to a data file

---

## SESSION SUMMARY (current sprint)

| Area | Changes |
|------|---------|
| items.json | +2 items: Back Mold (213), Crystal Binding (296) |
| recipes.json | -98 wrong recipes, +11 new recipes → 214 total |
| server/game_state/part_combiner.py | +mold 213 (Back Mold) in all three dicts |
| client/rendering/combiner.py | +molds 210-213 in _MOLD_HINT/_MOLD_BASE/_MOLD_SLOT2; colours → ui_theme |
| client/rendering/crafting.py | Mold range updated to (208,214); binding range (292,297); panel chrome → ui_theme; CRAFT button → ui_theme |
| client/rendering/embedder.py | Colours → ui_theme |
| client/rendering/menu.py | Colours → ui_theme (NAV_*) |
| client/rendering/stat_screen.py | BTN_HOV/BTN_BG/BTN_DIS_BG → ui_theme |
| client/rendering/chest.py | Panel chrome → ui_theme |
| client/rendering/inventory.py | Slot BG/BD → ui_theme.SLOT_BG/SLOT_BD |
| client/rendering/repair.py | Slot colours → ui_theme |
| server/player_save.py | SECURITY: path traversal fix (_SAFE_ID validation) |

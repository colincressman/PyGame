# Codebase Audit — PyGame_M
> Skips: `archive/`, `backup/`  
> Grade scale: A (excellent) → F (non-functional)

---

## SERVER

---

### `server/server.py` — Grade: A-

Significantly cleaned up since initial audit. Uses `TICK_RATE` from `server/config.py` in the game loop, all subsystem references are properly injected, `mock_state_data` stub removed.

- `ThreadPoolExecutor(max_workers=MAX_PLAYERS)` — pool sized to the actual player cap.
- Per-player `_world_futures` and `_state_futures` dicts track in-flight sends — a new send is skipped if the previous hasn’t completed, preventing duplicate queuing under lag.

> **To reach A:** No material issues.

---

### `server/config.py` — Grade: B+

Clean, well-organized, easy to read. No actionable issues.

> **To reach A:** The file itself is fine. The one remaining gap is that `HOST` and port numbers are duplicated between `server/config.py` and `client/config.py` with no shared source of truth — a mismatch would require updating both files.

---

### `server/network/listener.py` — Grade: A

Simple and correct TCP accept loop. `SO_REUSEADDR` is set. Server socket is stored in `_listener_sockets[port]` and `stop_listener(port)` closes it cleanly — no socket leak. `accept_loop` catches `OSError` and exits gracefully when the socket is closed.

---

### `server/network/tcp_routes.py` — Grade: A-

Updated this session with equip slot validation on `inv_swap`.

- **Equip slot type validation**: before swapping slots, server calls `is_valid_equip_placement` for both directions (item going into slot A, item going into slot B). Invalid swaps are silently rejected. Prevents server-side bypass of client validation.
- `handle_world` only keeps a keepalive-style loop — no blocking issues for current design.

---

### `server/network/udp_routes.py` — Grade: A-

All critical issues from the previous audit are fixed:

- **Format inconsistency resolved.** `player_positions` is now always written as `{'pos': ..., 'vel': ..., 'timestamp': ..., 'seq': ...}`.
- **Duplicate ID assignment resolved.** `pending_udp_assignments.discard(player_id)` is called immediately after the direct `assign_id` response.
- **`clients["udp"]` and `player_positions` updates** are inside `clients_lock` and `players_lock` respectively.
- **Per-client rate limiting.** Packets arriving faster than `1 / (TICK_RATE * 2)` seconds are silently dropped.
- **World bounds validation.** Any `pos` outside `±WORLD_RADIUS` tiles is rejected.

> **To reach A:** No material issues.

---

### `server/network/net_utils.py` — Grade: A

Clean, correct length-prefixed framing. `MAX_MESSAGE_SIZE = 10 MB` cap prevents runaway allocation. Uses `orjson` for fast serialization. `send_json` now raises on failure so callers can detect and handle broken connections.

---

### `server/cleanup.py` — Grade: A-

Fully implemented. `set_cleanup_refs` is called by `server.py` at startup; `cleanup_player` correctly handles all data structures, saves to disk outside all locks, and closes sockets safely. No significant issues.

> **To reach A:** No material issues.

---

### `server/game_state/sync.py` — Grade: A-

Clean delta-based world sync using MD5 checksums. `last_sent_hashes` is correctly protected by `hashes_lock` on both read and write paths — no race condition.

> **To reach A:** MD5 is correct but slow for large chunks. Replace with a non-cryptographic hash (e.g. `xxhash`) for a 10–20× speedup on checksum computation.

---

### `server/game_state/players.py` and `server/game_state/mock_data.py`

Both files deleted. The dead-code player management layer and hardcoded stub no longer exist.

---

### `server/world/visible.py` — Grade: A

Correctly handles the `pos['pos']` dict format. `player_positions` is now always the dict format (since `udp_routes.py` was fixed), so the `pos['pos']` access is safe. Lock window is correctly minimised by building `chunk_to_keys` before acquiring `world_data_lock`.

`_CHUNK_OFFSETS` and `_TILE_OFFSETS` are pre-computed once at module load time and reused every call — eliminates the 31 K iterations per player per call.

---

### `server/world/update.py` — Grade: A-

Clean, correct. `queue_chunks_near_players` now stores `(dist_sq, cx, cy)` in the heap for every candidate chunk, using the minimum distance across all players. `process_chunk_queue` pops in true distance order — no more first-player-wins. `world_data` mutations are visible to `visible.py` via shared reference (works correctly).

> **To reach A:** No material issues.

---

### `server/world/autosave.py` — Grade: A-

Fixed since initial audit. `set_world_data_ref` is called by `server.py` at startup with the live `world_data` dict; `autosave_world` now saves real data. Lock window is correctly minimised. No significant issues.

> **To reach A:** No material issues.

---

### `server/world/dyn_chunk_gen.py` — Grade: B

The core world generation file. The Numba JIT work is solid. Previous lock and heap issues have been fixed.

- `queue_chunks_near_players` now wraps all `queued_chunks`/`chunk_queue` accesses inside `chunk_lock` — no race.
- `process_chunk_queue` is called sequentially from the single game-loop thread, so the unlocked `heapq.heappop` there is safe in practice.
- `io.py` now also handles corrupt JSON — the two implementations are consistent.

Real remaining concern: elevation is computed from `h` (the height noise) but `h` is also a 5th dimension in the biome profile matching — biome type and elevation are coupled. A mountain biome near the threshold has misleading elevation values. This is the decoupled-biome item tracked in todo.md.

> **To reach A:** Implement the biome/elevation decoupling from todo.md (separate `t,m` climate axes from `h` elevation axis). Also switch chunk saves to `orjson` for faster I/O on large worlds.

---

### `server/world/chunk_utils.py` — Grade: A-

Simple, clean, correct. No issues.

> **To reach A:** No material issues.

---

### `server/world/io.py` — Grade: A

`load_chunk` catches `json.JSONDecodeError` and `OSError` and prints them. `save_chunk` uses an atomic write pattern: writes to a `.tmp` file then calls `os.replace()`, preventing half-written chunks on crash. Both error-handling paths are clean.

---

### `server/shared_lock.py` — Grade: A

All game-state locks now defined in one place: `world_data_lock`, `players_lock`, `clients_lock`, `hashes_lock`, `mobs_lock`, `world_items_lock`. `mob_manager.py` and `world_items.py` import their locks from here rather than defining new ones — locking hierarchy is visible in a single file, import-order issues eliminated.

---

### `server/network/combat.py` — Grade: A-

Handles attack damage and knockback for both players and mobs. Generally well-structured.

- **Lock ordering is correct**: acquires `players_lock` alone, then releases before acquiring `mobs_lock` alone — no nested lock inversion.
- `ATK_RANGE=2.0` tiles uses a squared-distance comparison — correct and efficient.
- The 90° cone uses a dot-product threshold (`_COS45`) — **not** `atan2` — clean and branchless.
- `attack_power` capped at `MAX_ATK_POWER = 500.0` — no unbounded growth.
- Stamina drain skipped when already at 0.

> **To reach A:** No material issues.

---

### `server/mobs/mob_manager.py` — Grade: B+

Completely redesigned attack pattern this session. Now follows standard 2D action-game conventions.

- **Standard charge-attack state machine**: `aggro → windup → lunge → landing → return_to_origin`. Target committed at windup START so the player has the full telegraph to dodge; lunge overshoots past the player by `LUNGE_OVERSHOOT=1.0` tile; `LANDING_PAUSE=0.2 s` punish window; per-tick hit detection during lunge path (not just at endpoint).
- **Deferred melee pattern** correctly avoids lock-inversion deadlock.
- `ATTACK_RANGE=2.0` (was 3.0), `WINDUP_TIME=0.45 s` (was 0.65 s), return speed 2× chase speed — feels responsive.
- No mob persistence (lost on restart).
- World-boundary clamping added (±`WORLD_RADIUS` tiles) — mobs can no longer escape the world edge.
- Spawn now uses `SPAWN_INTERVAL` cooldown (`_next_spawn_time`) instead of `random.random() < SPAWN_CHANCE` per tick — prevents burst spawning when population drops suddenly.

> **To reach A:** Persist mob state to `server/mob_state.json` on clean shutdown and reload on start.

---

### `server/game_state/game_sync.py` — Grade: A

- **Inventory dirty flag** eliminates per-tick inventory hashing. `mark_inventory_dirty` called on all mutations; cleared on next send. Clean.
- Throttled to **60 Hz** (tick_counter % 2). Correct.
- `mobs` snapshot is taken inside `with mobs_lock:` — TOCTOU concern is resolved.
- `world_items` snapshot inside `with world_items_lock:`. Correct.
- `_inventory_dirty` and `_inventory_sent` are now protected by `_inventory_lock` on all read/write paths — thread-safe across TCP handler and game-state sender threads.

---

*(See `server/network/net_utils.py — Grade: A-` entry above — this file has a single canonical entry.)*

---

### `server/item_data.py` — Grade: A

- `get_hotbar_bonus` correctly reads `inventory[27 + hotbar_slot]` (hotbar row).
- `is_valid_equip_placement` cleanly validates slot types for both client-bypass prevention.
- `_EQUIP_STATS`, `_EQUIP_SLOT_TYPES`, `_HOTBAR_OFFSET` are all module-level constants — single source of truth.
- `get_sell_price`, `get_item`, `get_equip_bonuses`, `get_hotbar_bonus` cover all callsites cleanly.
- `_load()` raises `FileNotFoundError` / `RuntimeError` on failure — a missing `items.json` halts startup loudly rather than silently producing empty lookups.

---

### `server/items.json` / `server/recipes.json` — Grade: A-

`items.json`: 23 items, all with `stackable`, `max_stack`, optional `stats`, `sell_price`, and now `slot_type` for all 11 equipment items (IDs 13–23). `slot_type` is the authority for equip slot validation on both server and client.
`recipes.json`: 11 recipes. Format is consistent. No issues.

> **To reach A:** No material issues. Future items and recipes can just be appended.

---

### `server/game_state/crafting.py` — Grade: A-

- Quality tier rolling is clean and self-contained.
- `_consume` / `_add` / `_count` helpers are correct.
- `handle_craft` validates ingredients, checks free slot, rolls quality, writes result. No issues.

> **To reach A:** No material issues.

---

### `client/rendering/crafting.py` — Grade: B

- `_QUALITY_TIERS`, `_QUALITY_ABBR`, `_STAT_ABBR` defined at module level — correct after bug fix (were missing on first run, causing `NameError`).
- Panel size (520×320) is fixed — will clip on very small windows. Not currently a concern.
- `_can_craft` only checks bag slots 0–35, not equip slots — correct behaviour (you craft from your bag).

> **To reach A:** Make the panel layout responsive to `WINDOW_WIDTH`/`WINDOW_HEIGHT` so it doesn’t clip on non-standard resolutions.

---

### `client/rendering/stat_screen.py` — Grade: A-

Character stat allocation screen opened with `[P]`.

- `draw_stat_screen` returns `'spend:<stat_key>'` or `None` — clean caller interface.
- `_fonts()` lazy initialises once — correct.
- Close hint previously said `[C]` (now fixed to `[P]`).

> **To reach A:** No material issues.

---

### `client/rendering/inventory.py` — Grade: A-

Updated this session with equipment slot type enforcement.

- **`_ITEM_SLOT_TYPES`** dict loaded from `items.json` alongside names/sell prices in a single pass.
- **`_EQUIP_SLOT_TYPES`** maps slot indices 36–44 to their required `slot_type` strings — mirrors server.
- **`can_drop_in_slot(item_id, target_slot)`** exported function: regular slots (0–35) always accept; equip slots require matching `slot_type`; items with no `slot_type` (materials, stackables) rejected from equip slots.
- `_draw_tooltip` handles both plain stacks and quality-rolled equipment cleanly.
- Sell hint shown only when `sell_value > 0` — correct.
- Panel is fixed size — will clip on very small windows (low priority).
- **Tooltip cache** added: `_tooltip_cache` dict + `_tooltip_key()` + `_build_tooltip_surface()` — surface only rebuilt when hovered slot content changes. No per-frame allocation.

> **To reach A:** Make the panel layout responsive (same note as `crafting.py`).

---

---

### `client/client.py` — Grade: A-

- `get_radial_sorted_chunks` is imported and used for client-side chunk render prioritisation.
- Each of the 3 `run_chunk_renderer` threads now receives its own `tile_cache = {}` — no shared mutable surface dict across threads.
- `chunk_queue` and `world_data` remain module-level mutable objects — acceptable but makes unit testing harder.

> **To reach A:** No material issues.

---

### `client/config.py` — Grade: B+

- `PLAYER_SPEED`, `SPRINT_SPEED`, `STEALTH_SPEED` are defined here and imported in `controls.py` — not hardcoded.
- Still contains mutable module-level game state (`players_data`, `world_data`, `chunk_cache`, etc.) mitigated by `reset_client_state()` mutating in-place.
- Dead `running`, `show_map`, and `map_needs_redraw` module-level variables removed — `state["running"]`, `state["show_map"]`, `state["map_needs_redraw"]` are the canonical truth sources.
- `WORLD_MAX_TILES = 2000` added — used by `controls.py` to clamp player position (must match `WORLD_RADIUS` in `server/config.py`).

> **To reach A:** Consider splitting into `constants.py` (HOST, ports, sizes — never mutated) and `state.py` (all the mutable per-session values), which would make `reset_client_state()` trivially correct.

---

### `client/shared_lock.py` — Grade: A-

Fine, minimal. Three locks is appropriate.

> **To reach A:** No material issues.

---

### `client/networking/handlers.py` — Grade: A-

- `handle_state` is fully functional; all stat fields parsed and written to `config`.
- `send_and_receive_udp` is implemented and handles rejoin.
- `from state.player import player_data` moved to module-level imports — no circular dependency exists (`state/player.py` only imports from `config`).
- `pos_buffer` has `maxlen=3` so extrapolation range is bounded.
- `_MAX_EXTRAP_TIME = 0.3 s` clamp added to `get_render_pos` — players freeze rather than sliding away if the server goes silent.

> **To reach A:** No material issues.

---

### `client/networking/protocols.py` — Grade: A-

`socket.timeout` and `ConnectionError` are correctly re-raised so callers can detect disconnects. Other exceptions return `None` — minor silent-failure case.

- `MAX_MESSAGE_SIZE = 10 MB` guard added on the receive side — matches `server/network/net_utils.py`.
- Now uses `orjson` (with stdlib `json` fallback if not installed) — consistent with server and ~3-5x faster parsing.

> **To reach A:** No material issues.

---

### `client/networking/sockets.py` — Grade: A-

Clean retry logic with good error messages. No issues.

---

### `client/rendering/display.py` — Grade: A

`render_chunk` and `generate_minimap_surface` are well-structured.

- `_MISSING_TILE_SURFACE` is a module-level lazy-init singleton via `_get_missing_tile_surface()` — created once, reused forever.
- `tile_cache` keyed by `tile_type` only (not by world position) — correct and memory-efficient.
- `_BIOME_COLORS` dict caches the per-biome average colour computed by `pygame.transform.scale` — computed once per biome type, never re-sampled on subsequent map opens.

---

### `client/rendering/cache.py` — Grade: A-

Simple and correct distance-based cache eviction. No issues.

> **To reach A:** No material issues.

---

### `client/input/controls.py` — Grade: A-

- Movement diagonal normalization is implemented correctly.
- Speed constants (`PLAYER_SPEED`, `SPRINT_SPEED`, `STEALTH_SPEED`) are imported from `config.py` — not hardcoded.
- **Equip slot drop validation** added: `can_drop_in_slot` checked for both dragged item → target and existing item → source before any swap.
- **World bounds clamping** added: after updating `pos`, both axes clamped to `±WORLD_MAX_TILES` — player cannot walk beyond the world edge.

> **To reach A:** No material issues.

---

### `client/state/player.py` — Grade: A-

Clean two-line module. Start position uses `PLAYER_START_X` / `PLAYER_START_Y` from `config.py` — no magic numbers. No issues.

> **To reach A:** No material issues.

---

### `client/state/world.py` — Grade: A-

`get_radial_sorted_chunks` is used in `client.py` for prioritising which chunks to schedule for rendering. Simple, correct, no issues.

> **To reach A:** No material issues. The function could be inlined into `client.py` since it has exactly one callsite, but keeping it separate for testability is fine.

---

### `client/state/reset.py` — Grade: A-

Fully functional. Uses `import state.player as _player_module` and mutates dicts in-place so all references stay valid. `ping`, `last_ping_sent`, `awaiting_ping` are defined in `config.py`. Outboxes drained, animation state reset, session_id incremented by the caller. No significant issues.

> **To reach A:** No material issues.

---

### `client/utils/logging.py` — Grade: A-

Clean, correct, simple. `log_error` / `log_info` are sensible helpers.

> **To reach A:** No material issues. Could add log rotation (cap `client_log.txt` size) but that's a stretch goal.

---

### `client/utils/compression.py`

File deleted (was an empty placeholder).

---
---

## ROOT / MISC

---

### `requirements.txt` — Grade: A-

All five direct runtime dependencies pinned to exact installed versions (`==`). `Cython` and the dead `cliff_detection.pyx` / `setup.py` have been removed.

> **To reach A:** No material issues.

---

## Summary Table

| File | Grade | Biggest Issue / To-reach-A |
|---|---|---|
| server/server.py | A- | ThreadPoolExecutor(8) vs MAX_PLAYERS(100); no backpressure on executor |
| server/config.py | B+ | Minor: HOST/port duplicated vs client config |
| server/network/listener.py | A | Store socket for clean shutdown |
| server/network/tcp_routes.py | A- | No material issues |
| server/network/udp_routes.py | A- | No per-client rate limiting; no world bounds validation |
| server/network/net_utils.py | A | `send_json` swallows exceptions silently |
| server/network/combat.py | A- | `attack_power` unbounded (no cap) |
| server/cleanup.py | A- | No material issues |
| server/game_state/sync.py | A- | MD5 is slow; consider xxhash |
| server/game_state/game_sync.py | A | `_inventory_dirty` set accessed from multiple threads without lock |
| server/game_state/crafting.py | A- | No issues |
| server/item_data.py | A | Silent fallback on missing items.json |
| server/items.json | A- | No issues |
| server/recipes.json | A- | No issues |
| server/mobs/mob_manager.py | B+ | No mob persistence (lost on restart) |
| server/world/visible.py | A | Cache static chunk-key offset layout |
| server/world/update.py | A- | First-player-wins chunk priority in multiplayer |
| server/world/autosave.py | A- | No material issues |
| server/world/dyn_chunk_gen.py | B | Biome/elevation coupling (tracked in todo.md) |
| server/world/chunk_utils.py | A- | No issues |
| server/world/io.py | A | Non-atomic writes (no write-then-rename) |
| server/shared_lock.py | A | `mobs_lock` / `world_items_lock` defined in other modules |
| client/client.py | A- | `tile_cache` shared across 3 render threads (GIL-safe but racy) |
| client/config.py | B+ | Flat mutable state; consider constants.py + state.py split |
| client/shared_lock.py | A- | No issues |
| client/networking/handlers.py | A- | No material issues |
| client/networking/protocols.py | A- | No MAX_MESSAGE_SIZE guard; uses stdlib json vs server orjson |
| client/networking/sockets.py | A- | No issues |
| client/rendering/display.py | A | Minimap resamples tile images on every open |
| client/rendering/cache.py | A- | No issues |
| client/rendering/crafting.py | B | Panel clips on small windows |
| client/rendering/stat_screen.py | A- | No issues |
| client/rendering/inventory.py | A- | Panel clips on small windows |
| client/input/controls.py | A- | No material issues |
| client/state/player.py | A- | No issues |
| client/state/world.py | A- | No issues |
| client/state/reset.py | A- | No issues |
| client/utils/logging.py | A- | No issues |
| requirements.txt | A- | No issues |


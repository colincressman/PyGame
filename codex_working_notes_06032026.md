# Codex Working Notes 2026-06-03

This file is a rolling architecture reference for future audit / refactor passes.
It is intentionally practical: what files matter, what they own, and where the
main maintenance pressure still lives.

## Source Of Truth

- `todo_06022026.md`
  - Main active roadmap and audit backlog.
- `README.md`
  - Human-facing current-state overview.

## Server Map

- `server/server.py`
  - Main server process entrypoint and loop wiring.

- `server/network/tcp_state_handlers_v2.py`
  - Main TCP dispatcher for stateful client actions.
  - Good place to look first for inventory/crafting/shop packet handling.

- `server/network/combat.py`
  - Player melee combat, PvP hit checks, mob hit resolution, gem on-hit effects.

- `server/network/projectiles.py`
  - Wand projectile simulation and projectile effects.
  - Now reads `data/projectiles.json`.
  - PvP wand projectile hits were added on 2026-06-04.

- `server/game_state/game_sync.py`
  - Builds authoritative game-state payloads.
  - Also owns dedicated mob replication state/cache (`mob_sync`) after the 2026-06-04 multiplayer overhaul.
  - Hot path: nearby items, placed objects, projectiles, planted-node deltas, plus per-client mob replication cache.

- `server/game_state/status_effects.py`
  - Shared status-effect application and ticking helpers.
  - Now reads `data/status_effects.json`.

- `server/game_state/placed_objects.py`
  - Placeables, doors, beds, stations, chest storage, farming growth, persistence.

- `server/world/dyn_chunk_gen.py`
  - Chunk generation, disk load/save, biome IDs, cliff IDs, node attachment.
  - Now also tracks bounded server-side loaded chunk residency and evicts older distant chunks with an LRU-style last-touch policy.

- `server/world/resource_nodes.py`
  - Deterministic node generation, node HP, respawn, planted nodes, depletion persistence.
  - Runtime logic now reads shared node/world-type registries, blocks natural nodes inside town/dungeon footprints, and uses planted-node delta updates.
  - Planted permanent pickaxe nodes now regrow after harvest instead of being consumed forever.

- `server/world/visible.py`
  - Visible-chunk payload builder.
  - Still does more per-call work than it needs to.

- `server/mobs/mob_manager.py`
  - Main mob tick loop: AI state machine, separation, mob combat, drops, and some per-player combat side effects.
  - Still large, but no longer owns the mob factory/config layer directly.

- `server/mobs/mob_defs.py`
  - Data-driven mob config helpers, spawn-position selection, spawned-mob construction, and boss construction.
  - First extraction pass taken out of `mob_manager.py` on 2026-06-05.

## Client Map

- `client/client.py`
  - Launcher, thread startup, loading flow, main loop, draw ordering, map/minimap submission.
  - Contains several frame-time-sensitive scans.

- `client/config.py`
  - Mutable runtime/session state singleton.
  - Still broad, but immutable defaults were split out on 2026-06-05.

- `client/client_constants.py`
  - Immutable client defaults and shared constants.
  - New home for window defaults, movement constants, keybind defaults, appearance defaults, and client data-path constants.

- `client/networking/handlers.py`
  - TCP/UDP receive handlers and client-side world/state application.
  - `RemotePlayer` has moved out to `client/state/remote_player.py`.
  - Applies `mob_sync` spawn/update/despawn packets into persistent `RemoteMob` entities.
  - Still owns node respawn/base-cache logic, and now applies planted-node snapshot/delta updates separately.

- `client/state/remote_player.py`
  - Remote-player interpolation and presentation state.
  - Now uses server-authored timing plus adaptive interpolation delay so close PvP targets render more responsively than distant players.

- `client/state/remote_mob.py`
  - Persistent remote-mob buffering / interpolation state.
  - Current reference implementation for entity smoothing: timestamp-offset buffering, limited extrapolation, and dedicated lifecycle updates.

- `client/input/controls.py`
  - Main input event router.
  - Inventory/chest drag-drop, chat capture, shop input, and building/world-click logic now live in sibling modules under `client/input/`.

- `client/input/controls_movement_v2.py`
  - Movement, sprint/stealth/roll, node collision, cactus damage.

- `client/rendering/display.py`
  - World/background rendering, node drawables, placed objects, minimap surface generation, projectile drawing.
  - Also owns fullscreen toggling behavior and related window-size state updates.

- `client/rendering/status_effects.py`
  - Screen overlay cues for active debuffs.
  - Now reads `data/status_effects.json`.

- `client/rendering/projectile_data.py`
  - Client loader for `data/projectiles.json`.

## Shared Data Registries Already Moved Out Of Code

- `data/tools.json`
- `data/resource_nodes.json`
- `data/placeables.json`
- `data/gems.json`
- `data/progression.json`
- `data/projectiles.json`
- `data/status_effects.json`
- `data/repair.json`
- `data/molds.json`
- `data/world_types.json`
- `data/shops/*.json`
- `data/mobs/*.json`

## Important Active Gaps

### Efficiency

- `client/client.py`
  - Minimap path copies `full_world_data.items()` when the map is open.
  - Placement and nearby-station checks now use tile/chunk indexes in `client/config.py`.
  - Minimap and broader world-state submission are still the more important remaining client-side hot paths.

- `server/world/visible.py`
  - Rebuilds per-call chunk tile key lists before assembling visible chunk payloads.

- `server/game_state/game_sync.py`
  - Mob lifecycle sync is much healthier now, and planted nodes no longer resend full snapshots every interval.
  - Remaining likely future work is broader payload benchmarking and any additional per-subsystem delta extraction that proves worth it.

- `server/mobs/mob_manager.py`
  - AI/state behavior is still monolithic even though the replication side is now much cleaner.
  - Separation is no longer all-pairs, but the runtime AI/combat loop is still one of the bigger server-side files.

### Modularity

- `client/input/controls.py`
  - Much smaller after subsystem extraction, but still owns station/interaction/menu flow and remains worth trimming further.

- `client/networking/handlers.py`
  - Node cache logic likely should move out next.

- `server/mobs/mob_manager.py`
  - The mob config/factory layer has already been extracted, so the next modularization win would be splitting runtime behavior/combat/post-resolution helpers rather than redoing spawn definitions.

### Good Practice / Correctness

- Durability coverage was completed on 2026-06-04:
  - wands
  - shields
  - pauldrons
  - gloves
  - inventory-dirty sync for incoming-damage wear now updates the client immediately

- `client/rendering/display.py`
  - Fullscreen toggling is now stable after ignoring `VIDEORESIZE` while fullscreen is active and remembering the prior windowed size.
  - Exiting true `pygame.FULLSCREEN` can still feel slow on Windows; a borderless desktop-window experiment reduced transition cost but did not center reliably.

- Multiplayer replication was heavily reworked on 2026-06-04:
  - Mobs moved from a generic nearby snapshot list into explicit `mob_sync` lifecycle packets (`reset`, `spawns`, `updates`, `despawns`).
  - Mobs now send server-authored velocity/timestamps and replicate on a faster dedicated cadence.
  - Remote players still use UDP transport, but now smooth against server-authored timing and adaptive delay.
  - Practical outcome:
    - mobs are now smoother than the old player path and serve as the current gold-standard replication model
    - remote players were subsequently tuned so PvP-range targets appear sharper than distant players without losing general smoothness

- README drift has been a recurring issue; keep `README.md` and `todo_06022026.md` aligned.

- Runtime logging changed on 2026-06-05:
  - hot-path debug prints are now quiet by default
  - `PYGAME_M_DEBUG_LOGS=1` restores verbose debug diagnostics
  - `PYGAME_M_CONSOLE_LOGS=1` restores routine client info logs to the console

## Useful Mental Model

When debugging a gameplay bug:

1. Check if it is server-authoritative or client-presentation only.
2. For items/equipment/stats, inspect:
   - `server/item_data.py`
   - `server/network/combat.py`
   - `server/network/tcp_state_handlers_v2.py`
3. For nodes/world interactions, inspect:
   - `server/world/resource_nodes.py`
   - `client/networking/handlers.py`
   - `client/input/controls.py`
4. For rendering mismatches, inspect:
   - `client/rendering/display.py`
   - `client/rendering/player.py`
   - `client/rendering/item_art.py`

## Next Recommended Refactor Batches

1. Optimize minimap/world-state hot paths
2. Benchmark chunk I/O, serialization, and remaining world-state payload costs
3. Continue modularizing the runtime side of `server/mobs/mob_manager.py` if mob behavior work resumes
4. Add hostile-mob light avoidance if gameplay/base-safety tuning is the next design target
5. If multiplayer tuning resumes, prefer extending the current replicated-entity model rather than reintroducing broad snapshot buckets

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
  - Wand projectile simulation and projectile-on-mob effects.
  - Now reads `data/projectiles.json`.

- `server/game_state/game_sync.py`
  - Builds authoritative game-state payloads.
  - Hot path: nearby items, mobs, placed objects, projectiles, planted nodes.

- `server/game_state/status_effects.py`
  - Shared status-effect application and ticking helpers.
  - Now reads `data/status_effects.json`.

- `server/game_state/placed_objects.py`
  - Placeables, doors, beds, stations, chest storage, farming growth, persistence.

- `server/world/dyn_chunk_gen.py`
  - Chunk generation, disk load/save, biome IDs, cliff IDs, node attachment.

- `server/world/resource_nodes.py`
  - Deterministic node generation, node HP, respawn, planted nodes, depletion persistence.
  - Runtime logic now reads shared node/world-type registries, but the module is still a useful hotspot for depletion/respawn behavior audits.

- `server/world/visible.py`
  - Visible-chunk payload builder.
  - Still does more per-call work than it needs to.

- `server/mobs/mob_manager.py`
  - Spawn, AI state machine, mob combat, drops, separation, and some per-player combat side effects.
  - Large and still a strong modularization candidate.

## Client Map

- `client/client.py`
  - Launcher, thread startup, loading flow, main loop, draw ordering, map/minimap submission.
  - Contains several frame-time-sensitive scans.

- `client/config.py`
  - Client constants and mutable runtime state singleton.
  - Convenient, but still overloaded.

- `client/networking/handlers.py`
  - TCP/UDP receive handlers and client-side world/state application.
  - `RemotePlayer` has moved out to `client/state/remote_player.py`.
  - Still owns node respawn/base-cache logic.

- `client/state/remote_player.py`
  - Remote-player interpolation and presentation state.

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
  - Still scans all world items and all mobs per player for nearby-state payloads.
  - Sends full planted-node snapshot every state packet.

- `server/mobs/mob_manager.py`
  - Mob separation remains O(n^2) over live mobs.

### Modularity

- `client/input/controls.py`
  - Much smaller after subsystem extraction, but still owns station/interaction/menu flow and remains worth trimming further.

- `client/config.py`
  - Mutable session state and constants should eventually separate.

- `client/networking/handlers.py`
  - Node cache logic likely should move out next.

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

- README drift has been a recurring issue; keep `README.md` and `todo_06022026.md` aligned.

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

1. Split `client/rendering/item_art.py`
2. Separate mutable client state from constants
3. Extract mob-manager behavior into smaller modules
4. Optimize minimap/world-state hot paths

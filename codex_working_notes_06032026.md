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
  - Still hardcodes node registry and biome constants.

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
  - TCP/UDP receive handlers plus `RemotePlayer` interpolation class.
  - Also owns node respawn/base-cache logic.

- `client/input/controls.py`
  - Largest mixed input/UI handler.
  - Handles inventory, chest, shop, stations, pickup mode, char creator, and more.

- `client/input/controls_movement_v2.py`
  - Movement, sprint/stealth/roll, node collision, cactus damage.

- `client/rendering/display.py`
  - World/background rendering, node drawables, placed objects, minimap surface generation, projectile drawing.
  - Contains duplicate `draw_placed_objects()` definitions.

- `client/rendering/status_effects.py`
  - Screen overlay cues for active debuffs.
  - Now reads `data/status_effects.json`.

- `client/rendering/projectile_data.py`
  - Client loader for `data/projectiles.json`.

## Shared Data Registries Already Moved Out Of Code

- `data/tools.json`
- `data/gems.json`
- `data/progression.json`
- `data/projectiles.json`
- `data/status_effects.json`
- `data/repair.json`
- `data/molds.json`
- `data/shops/*.json`
- `data/mobs/*.json`

## Important Active Gaps

### Efficiency

- `client/client.py`
  - Minimap path copies `full_world_data.items()` when the map is open.
  - Placement and station checks still scan `world_nodes` / `placed_objects`.

- `client/rendering/display.py`
  - Projectile glow surface is recreated per projectile per frame.

- `server/world/visible.py`
  - Rebuilds per-call chunk tile key lists before assembling visible chunk payloads.

- `server/game_state/game_sync.py`
  - Still scans all world items and all mobs per player for nearby-state payloads.
  - Sends full planted-node snapshot every state packet.

- `server/mobs/mob_manager.py`
  - Mob separation remains O(n^2) over live mobs.

### Modularity

- `client/input/controls.py`
  - Best candidate for further splitting.

- `client/config.py`
  - Mutable session state and constants should eventually separate.

- `client/networking/handlers.py`
  - `RemotePlayer` should move out; node cache logic likely should too.

- `server/world/resource_nodes.py`
  - Node definitions still belong in JSON.

- `server/world/dyn_chunk_gen.py` + `client/config.py`
  - Biome/cliff constants still duplicated and should move to shared data.

### Good Practice / Correctness

- Durability coverage is incomplete:
  - wands
  - shields
  - pauldrons
  - gloves

- `client/rendering/display.py`
  - duplicate helper definitions should be cleaned up.

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

1. `Resource node registry JSON` + `Shared biome/cliff constants`
2. `Placeable/station/farming registry JSON`
3. Split `client/input/controls.py`
4. Add client lookup indexes for nodes/objects/stations

# PyGame Multiplayer RPG

A Python/Pygame multiplayer action RPG with a custom server/client stack, chunked world generation, crafting, durability, NPC shops, equipment rolling, dungeons, and a growing set of data-driven registries.

## Current State

This project is no longer a small prototype. The active game already includes:

- real-time multiplayer with TCP + UDP
- dedicated replicated-entity smoothing for mobs and adaptive smoothing for remote players
- procedural world generation with chunk persistence
- combat, block/parry, dodge roll, stamina, durability, and status effects
- equipment, crafting, repair, gem embedding, and part combining
- NPC towns, shops, beds, weather, minimap, chat, and character appearance
- data-driven registries for mobs, tools, resource nodes, placeables, gems, progression, projectiles, status effects, repair costs, shops, molds, and shared world-type constants

## Project Layout

```text
PyGame_M/
├── client/                  # Pygame client, rendering, input, networking, local state
├── server/                  # Game server, world systems, combat, persistence
├── data/                    # Shared JSON registries and game data
├── tests/                   # Focused regression tests
├── todo_06022026.md         # Main active roadmap / audit todo list
├── codex_working_notes_06032026.md
└── README.md
```

High-signal areas:

- `client/client.py`: launcher, session lifecycle, main render/update loop
- `client/config.py`: mutable client runtime/session state seeded from `client/client_constants.py`
- `client/client_constants.py`: immutable client defaults and shared constants
- `client/input/controls.py`: main input router; inventory, chat, shop, and building handlers have been split into sibling modules under `client/input/`
- `server/game_state/game_sync.py`: authoritative state packet assembly plus dedicated mob replication
- `client/state/remote_mob.py`: persistent remote-mob buffering / smoothing
- `client/state/remote_player.py`: buffered remote-player smoothing and PvP responsiveness tuning
- `server/mobs/mob_manager.py`: mob lifecycle, AI tick flow, separation, and combat side effects
- `server/mobs/mob_defs.py`: data-driven mob config helpers and spawned/boss mob construction
- `server/world/dyn_chunk_gen.py`: chunk generation, load/save, cliff assignment
- `server/world/resource_nodes.py`: node generation, depletion, respawn, planting

## Running

### Server

```bash
cd server
python -m server.server
```

### Client

```bash
cd ..
python client/client.py
```

The in-game launcher handles player name, host, FPS cap, and resolution.

## Data-Driven Systems

Recent modularization work moved several formerly hardcoded systems into JSON:

- `data/mobs/`
- `data/tools.json`
- `data/gems.json`
- `data/progression.json`
- `data/projectiles.json`
- `data/status_effects.json`
- `data/repair.json`
- `data/molds.json`
- `data/resource_nodes.json`
- `data/placeables.json`
- `data/world_types.json`
- `data/shops/`

Remaining larger extraction targets are still concentrated in oversized code modules rather than these core gameplay registries.

## Known Architectural Pressure Points

The most important current cleanup opportunities are:

- `client/rendering/item_art.py` is still very large and should be split by item domain
- minimap/world-state paths still do avoidable rebuild and copy work
- `server/world/visible.py` still has avoidable repeated payload-building work
- `server/mobs/mob_manager.py` still has a large runtime AI/combat loop even after the new `server/mobs/mob_defs.py` extraction

The next main workstream is `Priority 6` server/world performance:

- visible-chunk payload construction
- nearby entity/item query costs
- chunk I/O / cache benchmarking
- remaining network/persistence benchmarking
- chunk I/O / cache benchmarking

Recent `Priority 6` wins already landed:

- server-side world chunk sync no longer rebuilds payloads for chunks already known by the client
- server now keeps a bounded in-memory chunk cache instead of letting explored chunk residency grow forever
- planted nodes now use snapshot-once plus delta sync, and planted ore deposits regrow after harvest instead of disappearing forever
- default runtime debug spam is now much lower, with opt-in environment flags for verbose diagnostics

## Multiplayer Notes

Recent work substantially changed multiplayer feel and stability:

- large shared-state sync pressure was reduced by splitting heavy world state from time-sensitive entity updates
- mobs now use explicit `spawn/update/despawn`-style replication with dedicated sync cadence, server-authored velocity/timestamps, and persistent client-side smoothing
- remote players still use UDP movement, but now smooth against server-authored timing and use adaptive interpolation so close PvP targets render more responsively than distant/non-combat players

Result:

- multiplayer world state remains stable with multiple players online
- mobs are now a high-quality reference implementation for entity smoothing
- remote players remain smooth while feeling sharper in PvP range

## Runtime Notes

- Verbose runtime diagnostics are now quiet by default during normal play.
- Set `PYGAME_M_DEBUG_LOGS=1` to restore verbose server/client debug diagnostics.
- Set `PYGAME_M_CONSOLE_LOGS=1` to restore routine client info logs to the console.

See [todo_06022026.md](C:/Users/colin/OneDrive/Desktop/Projects/PyGame_Working/PyGame_M/todo_06022026.md:1) for the active roadmap and [codex_working_notes_06032026.md](C:/Users/colin/OneDrive/Desktop/Projects/PyGame_Working/PyGame_M/codex_working_notes_06032026.md:1) for the rolling architecture reference.

## Notes

- World/chunk persistence currently uses the active chunk directory from server config.
- Some tests are dependency-sensitive because the runtime must have `pygame` available.
- `todo_06022026.md` is the active roadmap / audit source of truth, and `codex_working_notes_06032026.md` is the rolling architecture reference.

# PyGame Multiplayer RPG

A Python/Pygame multiplayer action RPG with a custom server/client stack, chunked world generation, crafting, durability, NPC shops, equipment rolling, dungeons, and a growing set of data-driven registries.

## Current State

This project is no longer a small prototype. The active game already includes:

- real-time multiplayer with TCP + UDP
- procedural world generation with chunk persistence
- combat, block/parry, dodge roll, stamina, durability, and status effects
- equipment, crafting, repair, gem embedding, and part combining
- NPC towns, shops, beds, weather, minimap, chat, and character appearance
- data-driven registries for mobs, tools, gems, progression, projectiles, status effects, repair costs, shops, and molds

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
- `client/config.py`: client constants plus mutable session state
- `client/input/controls.py`: large mixed UI/input handler
- `server/game_state/game_sync.py`: authoritative state packet assembly
- `server/mobs/mob_manager.py`: mob lifecycle and AI
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
- `data/shops/`

The next big extraction targets are resource nodes, placeables/farming, and shared biome/cliff constants.

## Known Architectural Pressure Points

The most important current cleanup opportunities are:

- `client/input/controls.py` is still too large and cross-cutting
- `client/config.py` still mixes constants with mutable session state
- some client-side world interactions still scan `world_nodes` / `placed_objects` linearly
- `server/world/visible.py` and `server/game_state/game_sync.py` still have avoidable repeated payload-building work

See [todo_06022026.md](C:/Users/colin/OneDrive/Desktop/Projects/PyGame_Working/PyGame_M/todo_06022026.md:1) for the active roadmap and [codex_working_notes_06032026.md](C:/Users/colin/OneDrive/Desktop/Projects/PyGame_Working/PyGame_M/codex_working_notes_06032026.md:1) for the rolling architecture reference.

## Notes

- World/chunk persistence currently uses the active chunk directory from server config.
- Some tests are dependency-sensitive because the runtime must have `pygame` available.
- Old planning docs exist, but `todo_06022026.md` should be treated as the main source of truth.

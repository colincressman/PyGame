# Feature Implementation Plan
> Agent working file — updated as each task progresses.
> Tackle ONE task at a time, top-down.

---

## Task 1 — Username Login System  ✅ COMPLETE
> Players should connect by their chosen username, not by join order.
> Duplicate names get a numeric suffix (Bob → Bob_2).
> Usernames shown above remote players in-world.

### Changes made
| File | What changed |
|------|-------------|
| `client/networking/handlers.py` | Always sends `desired_name` in initial UDP packet |
| `server/network/udp_routes.py` | Uses `desired_name` as player_id; suffixes on collision |
| `server/game_state/game_sync.py` | Adds `name` field to `others` dict in game state |
| `client/networking/handlers.py` | Stores remote player name from game_state |
| `client/networking/handlers.py` | `RemotePlayer` stores `.name` field |
| `client/rendering/player.py` | `draw_remote_player()` renders name above sprite |

---

## Task 2 — Chat Window  ✅ COMPLETE
> Press T to open chat input at bottom-left (Minecraft style).
> Enter sends message; Escape cancels without sending.
> Last 10 messages shown with fade-out.
> Chat input box blocks all game input while open.

### Changes made
| File | What changed |
|------|-------------|
| `client/config.py` | Added `chat_open`, `chat_input`, `chat_messages` state |
| `client/rendering/chat.py` | **NEW** — chat box renderer |
| `client/input/controls.py` | T key opens chat; Enter/Escape handled; input blocked |
| `client/client.py` | Calls `draw_chat()` every frame |
| `client/networking/handlers.py` | Reads `{"type":"chat"}` packets from TCP state stream; adds to `chat_messages` |
| `server/network/tcp_state_handlers_v2.py` | Handles `{"type":"chat","text":"..."}` — validates, broadcasts |
| `server/network/game_sync_chat.py` | **NEW** — thread-safe chat queue + broadcast helper |

---

## Task 3 — Server Commands  ✅ COMPLETE
> Chat messages starting with `/` are processed as commands on the server.
> Commands are player-specific (no admin level distinction for now).
> 
> Supported commands:
> | Command | Effect |
> |---------|--------|
> | `/heal` | Restore HP to max |
> | `/repair` | Restore durability on all inventory items |
> | `/creative` | Toggle creative mode (on/off) |
> | `/give <id> [qty]` | Give yourself an item (creative mode only) |
> | `/tp <player>` | Teleport to another player |
> | `/help` | List available commands |

### Changes made
| File | What changed |
|------|-------------|
| `server/network/commands.py` | **NEW** — command parser + handlers |
| `server/network/tcp_state_handlers_v2.py` | Chat handler calls `process_command()` when text starts with `/` |

---

## Task 4 — Creative Mode  ✅ COMPLETE
> Toggle with `/creative`.  
> Creative players: invincible (immune to mob/pvp damage).  
> Creative inventory tab in the E-menu showing all items — click to receive.

### Changes made
| File | What changed |
|------|-------------|
| `server/player_save.py` | `default_player_stats()` includes `"creative": False` |
| `server/network/combat.py` | Skip damage if target player has `creative=True` |
| `server/game_state/game_sync.py` | Sends `creative` flag to client in game state |
| `client/config.py` | Added `player_creative = False` |
| `client/networking/handlers.py` | Reads `creative` flag from game state |
| `client/rendering/hud.py` | Shows "✦ CREATIVE" badge when creative is active |
| `client/rendering/inventory.py` | Adds a CREATIVE tab; shows items grouped by category |
| `server/mobs/mob_manager.py` | Skip melee damage if target player has `creative=True` |
| `client/config.py` | Added `creative_scroll = 0` for creative tab scroll state |
| `client/networking/handlers.py` | Resets `inventory_tab` to "bag" if creative revoked mid-session |
| `client/input/controls.py` | Mousewheel scrolls creative tab; click calls `creative_tab_click` → `give_item` |
| `server/network/tcp_state_handlers_v2.py` | Handles `give_item` (creative-only guard) |

---

## Overall Progress
- [x] Task 1 — Username login
- [x] Task 2 — Chat window
- [x] Task 3 — Server commands
- [x] Task 4 — Creative mode

## Notes / Risks
- Chat is sent via the TCP state channel (already has send/recv loop) — no new socket needed.
- Commands are server-authoritative: client just sends text, server does the work.
- Creative inventory needs all 348 items — rendered as a scrollable grid; no separate UI file needed, extends existing `inventory.py`.
- Combat skip: `server/network/combat.py` checks `players[target].get("creative")` before applying damage — same pattern used for death check.

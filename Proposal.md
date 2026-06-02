# Proposal: Knockback Feel Improvements

> Current state: knockback is abrupt (instant position snap at ~20 Hz), slimes can overlap the player, and there's no visual signal that you're being hit.

---

## Problem Breakdown

### 1. Abrupt Position Snap
The server computes a knockback offset and includes it in the next game-state TCP packet. The client applies it as a one-shot position jump. Because game-state packets arrive at ~20 Hz, the player teleports backward with no animation continuity.

### 2. Slime Overlap
After delivering melee damage, the slime is not pushed away. On the next tick it's still overlapping the player, sometimes dealing multiple hits in rapid succession (the 5-second cooldown helps, but the visual overlap is still jarring).

### 3. No Hit Feedback
Nothing on screen signals that damage occurred — no flash, no shake, no sound cue. The player just finds themselves further back with less health.

---

## Proposed Fixes

### Fix 1 — Client-Side Knockback Velocity (replaces position snap)

**What to change**

- **Server (`game_sync.py`)**: Send `knockback_vel: [vx, vy]` (tiles/sec) instead of `knockback: [dx, dy]` (tile offset).  
  Example magnitude: `1.5 tiles / 0.25 s = 6.0 tiles/sec`.

- **Client (`handle_state` in `handlers.py`)**: Instead of adding the offset directly to `player_data["pos"]`, store it as a decaying velocity:
  ```python
  kb = self_data.get("knockback_vel")
  if kb:
      player_data["knockback_vel"] = kb        # [vx, vy]
      player_data["knockback_decay"] = 0.25    # seconds of decay
  ```

- **Client game loop (`client.py`)**: Each frame, before movement input is applied:
  ```python
  kd = player_data.get("knockback_decay", 0)
  if kd > 0:
      kv = player_data.get("knockback_vel", [0, 0])
      player_data["pos"][0] += kv[0] * dt
      player_data["pos"][1] += kv[1] * dt
      player_data["knockback_decay"] = max(0, kd - dt)
      # Scale velocity down linearly (or exponentially for a snappier feel)
      t = player_data["knockback_decay"] / 0.25
      player_data["knockback_vel"] = [kv[0] * t, kv[1] * t]
  ```

**Result**: The player slides backward over ~0.25 s and decelerates naturally, rather than teleporting.

---

### Fix 2 — Server-Side Mob Separation Push

**What to change** (`server/mobs/mob_manager.py`):

After the mob AI tick, check each mob's distance to every player. If `dist < MIN_SEPARATION` (e.g. 0.8 tiles), push the mob away:

```python
MIN_SEPARATION = 0.8
for mob in mob_list:
    for pid, pdata in _players.items():
        pp = pdata["pos"]
        mx, my = mob["pos"]
        px, py = pp
        ddx, ddy = mx - px, my - py
        dist = sqrt(ddx*ddx + ddy*ddy)
        if 0 < dist < MIN_SEPARATION:
            nx, ny = ddx / dist, ddy / dist
            push = (MIN_SEPARATION - dist) * 0.5  # share the push
            mob["pos"][0] += nx * push
            mob["pos"][1] += ny * push
```

This runs inside `mobs_lock` only — no player lock needed since we read `_players` positions without writing them.

**Result**: Slimes can no longer stand inside the player. The push is small and continuous so it doesn't feel like a hard collision stop.

---

### Fix 3 — Hit Flash on Player Sprite

**What to change** (`client/rendering/player.py` + `client/client.py`):

When `knockback_vel` is received, set a `hit_flash_timer` in `player_data` (e.g. 0.2 s). During `draw_player`, if the timer is active, blit the sprite then overlay a semi-transparent red surface:

```python
# In client.py, after handling knockback_vel:
player_data["hit_flash_timer"] = 0.2

# In rendering/player.py, draw_player:
if player_data.get("hit_flash_timer", 0) > 0:
    flash = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    flash.fill((220, 0, 0, 110))
    screen.blit(flash, screen_pos)
    player_data["hit_flash_timer"] -= dt
```

**Result**: A brief red tint signals the hit clearly without blocking gameplay visuals.

---

### Fix 4 — Slime Pre-Attack Telegraph (stretch goal)

Add a `charging` state to slimes (~0.4 s wind-up before the melee hit). During this window the slime plays `frame 2` (mouth-open) held in place. The melee damage fires at the *end* of the wind-up, not the start.

- Server: add `mob["charge_start"]` timestamp; replace immediate `pending_melee.append(...)` with `if now - charge_start >= CHARGE_DURATION: fire hit`.
- Client: slime renders with a distinct frame (or a yellow outline) during the charge window — visible in the UDP broadcast `"state": "charging"` field.

**Result**: Players can read the attack and dodge, turning the combat from "you just got hit" into "you saw that coming."

---

## Implementation Order

| Priority | Fix | Effort | Status |
|---|---|---|---|
| 1 | Client-side knockback velocity (Fix 1) | ~1 hr — 3 files | ✅ Done |
| 2 | Mob separation push (Fix 2) | ~20 min — 1 file | ✅ Done |
| 3 | Hit flash (Fix 3) | ~20 min — 2 files | ✅ Done |
| 4 | Slime charge telegraph (Fix 4) | ~2 hrs — server + client | ✅ Done |

---

# Proposal: Network Efficiency

> Audit performed after implementing crafting, quality tiers, and the sell system.
> All changes below have been implemented.

## Problem Breakdown

### 1. Game State Sent at 120 Hz Per Player
`send_game_state` was submitted to the thread pool every server tick (TICK_RATE=120). Each call
does JSON serialisation of ~14 fields + mobs + world items. The client receives game state in a
loop with `time.sleep(1/60)` — the extra 60 sends/sec per player were pure waste.

### 2. Inventory Hash Recalculated Every Tick
Even with no changes, the old code called `json.dumps(inventory)` to compute an MD5 hash of the
full 45-slot inventory (≈900 bytes of JSON) every tick, just to check if it had changed.

### 3. stdlib `json` Used Everywhere for Hot Paths
Both the server TCP/UDP paths and the client UDP receive loop used `json.dumps/loads`.
`orjson` is 3–5× faster and is already in `requirements.txt`.

### 4. Unused `stamina` Field in Every Payload
The server was sending `"stamina": ...` in `self_data` every tick but the client never read it
(client simulates stamina locally).

---

## Fixes Applied

### Fix A — Throttle Game State to 20 Hz (`server/server.py`)
```python
if tick_counter % 6 == 0:   # 20 Hz (120 / 6)
    executor.submit(send_game_state, player_id, sock)
```
**Result:** 6× reduction in TCP game state messages per player.

### Fix B — Inventory Dirty Flag (`server/game_state/game_sync.py`, `server/network/tcp_routes.py`)
- Replaced MD5 hash with `_inventory_dirty: set` and `_inventory_sent: set`.
- `mark_inventory_dirty(player_id)` called from `tcp_routes` after every inv mutation (swap/craft/sell).
- Inventory only included in the payload when the flag is set, then the flag is cleared.

**Result:** O(1) dirty check instead of O(45 × ~20 bytes) JSON encode per tick.

### Fix C — orjson Everywhere (`server/network/net_utils.py`, `server/network/udp_routes.py`, `client/networking/handlers.py`)
- `net_utils.py`: replaced `json.dumps(...).encode()` / `json.loads(...)` with `orjson.dumps` / `orjson.loads`.
- `udp_routes.py`: all four JSON encode/decode points switched to orjson.
- `handlers.py`: all UDP send/receive points switched to orjson; stale `json` import removed.

**Result:** ~3–5× faster serialisation on the hottest paths (UDP broadcast loop, TCP state sends).

### Fix D — Remove Dead `stamina` Field
Removed `"stamina"` from `self_data` in `game_sync.py`.

**Result:** ~10 bytes saved per payload; no behaviour change.

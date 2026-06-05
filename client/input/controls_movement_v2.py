import math
import time

import pygame

import config
from input.placeable_data import WALKABLE_TYPES as _WALKABLE_PLACEABLE_TYPES
from input.resource_node_data import BLOCKING_NODES, NODE_COLLISION_CY, NODE_COLLISION_R
from status_effect_data import STATUS_EFFECTS
from config import PLAYER_SPEED, SPRINT_SPEED, STEALTH_SPEED, WORLD_MAX_TILES

# Stamina drain / regen rates per second
_SPRINT_DRAIN = 12.0   # drains full bar in ~8s
_STEALTH_DRAIN = 6.0   # drains full bar in ~17s
_REGEN_RATE = 4.0      # refills full bar in ~25s
_EXHAUST_RECOVER = 30.0  # must recover to this % of max before sprint/sneak re-enables
_exhausted = False       # True after stamina hits 0; clears when enough stamina is recovered

# Dodge roll constants
_ROLL_DURATION    = 0.25    # seconds of i-frame + speed burst
_ROLL_SPEED       = PLAYER_SPEED * 3   # 18 tiles/sec
_ROLL_COST        = 20.0    # stamina spent instantly on roll start
_ROLL_COOLDOWN    = 1.0     # seconds before next roll
_GHOST_INTERVAL   = 0.05   # seconds between ghost particle emissions
_PLAYER_SLOW_MULT = float(STATUS_EFFECTS.get("slow", {}).get("player_move_mult", 0.5))

# Roll runtime state
_rolling          = False
_roll_dx          = 0.0    # normalised direction
_roll_dy          = 0.0
_roll_timer       = 0.0    # seconds remaining in current roll
_ghost_timer      = 0.0    # countdown until next ghost emission


def start_roll(dx: float, dy: float):
    """Initiate a dodge roll in direction (dx, dy)  — called from event handler.

    dx, dy should already be normalised (from the held movement keys).
    Returns True if the roll was started, False if conditions were not met.
    """
    global _rolling, _roll_dx, _roll_dy, _roll_timer, _ghost_timer
    if _rolling:
        return False
    if config.roll_cooldown > 0.0:
        return False
    if config.player_stamina < _ROLL_COST:
        return False
    if _exhausted:
        return False
    # Consume stamina and start roll
    config.player_stamina = max(0.0, config.player_stamina - _ROLL_COST)
    _rolling      = True
    _roll_dx      = dx
    _roll_dy      = dy
    _roll_timer   = _ROLL_DURATION
    _ghost_timer  = 0.0
    config.rolling = True
    return True

# ---------------------------------------------------------------------------
# Node collision & cactus damage
# ---------------------------------------------------------------------------
_PLAYER_R = 0.32
_PLAYER_FEET_Y = 0.75
_cactus_timer = 0.0
_CACTUS_HIT_INTERVAL = 1.0


def _node_collisions(px, py, dt):
    """Push (px, py) out of blocking node circles. Returns (new_px, new_py, in_cactus)."""
    global _cactus_timer
    in_cactus = False
    feet_py = py + _PLAYER_FEET_Y
    for _node_id, node in config.iter_world_nodes_near(px, feet_py, 1.0):
        ntype = node.get("type", "")
        if ntype not in BLOCKING_NODES:
            continue
        nr = NODE_COLLISION_R.get(ntype, 0.35)
        cx = node["wx"] + 0.5
        cy = node["wy"] + NODE_COLLISION_CY.get(ntype, 0.5)
        min_dist = _PLAYER_R + nr
        if abs(px - cx) > min_dist + 0.1 or abs(feet_py - cy) > min_dist + 0.1:
            continue
        ddx = px - cx
        ddy = feet_py - cy
        dist = math.sqrt(ddx * ddx + ddy * ddy)
        if dist < min_dist:
            if ntype == "cactus":
                in_cactus = True
            if dist < 0.0001:
                ddx, ddy, dist = 1.0, 0.0, 1.0
            nx, ny = ddx / dist, ddy / dist
            px = cx + nx * min_dist
            feet_py = cy + ny * min_dist
    py = feet_py - _PLAYER_FEET_Y

    # Placed objects: circle-vs-AABB so adjacent tiles share edges with no gap.
    # Each placed object occupies exactly its 1×1 tile; we find the closest
    # point on that box to the player centre and push the circle out.
    # The hitbox is shifted 0.5 tiles (32 px) down to sit at the player's feet.
    _PO_FEET_Y = 0.5
    fpy = py + _PO_FEET_Y          # shifted probe y; px unchanged
    for _uid, obj in config.iter_placed_objects_near(px, fpy, 1.0):
        otype = obj.get("type", "")
        if otype in _WALKABLE_PLACEABLE_TYPES:
            continue
        if otype == "door" and obj.get("state", "closed") == "open":
            continue
        ox = obj["pos"][0]
        oy = obj["pos"][1]
        # Broad-phase skip
        if px  < ox - _PLAYER_R or px  > ox + 1.0 + _PLAYER_R:
            continue
        if fpy < oy - _PLAYER_R or fpy > oy + 1.0 + _PLAYER_R:
            continue
        # Closest point on tile AABB to player centre
        near_x = max(ox, min(px,  ox + 1.0))
        near_y = max(oy, min(fpy, oy + 1.0))
        ddx = px  - near_x
        ddy = fpy - near_y
        dist_sq = ddx * ddx + ddy * ddy
        if dist_sq >= _PLAYER_R * _PLAYER_R:
            continue
        if dist_sq < 1e-8:
            # Player centre is inside the tile — push out on shortest overlap axis
            ol  = px  - ox;            or_ = (ox + 1.0) - px
            ot  = fpy - oy;            ob_ = (oy + 1.0) - fpy
            m   = min(ol, or_, ot, ob_)
            if   m == ol:  px  = ox - _PLAYER_R
            elif m == or_: px  = ox + 1.0 + _PLAYER_R
            elif m == ot:  fpy = oy - _PLAYER_R
            else:          fpy = oy + 1.0 + _PLAYER_R
        else:
            dist = math.sqrt(dist_sq)
            px  = near_x + (ddx / dist) * _PLAYER_R
            fpy = near_y + (ddy / dist) * _PLAYER_R
    py = fpy - _PO_FEET_Y
    return px, py, in_cactus


def handle_movement(state, keys, dt):
    global _exhausted, _cactus_timer, _rolling, _roll_timer, _ghost_timer

    # ── Tick roll cooldown ────────────────────────────────────────────────────
    config.roll_cooldown = max(0.0, config.roll_cooldown - dt)

    # ── Execute active roll ───────────────────────────────────────────────────
    if _rolling:
        _roll_timer -= dt
        if _roll_timer <= 0.0:
            _rolling       = False
            config.rolling = False
            config.roll_cooldown = _ROLL_COOLDOWN
        else:
            # Move at fixed speed in locked direction; still resolve wall/object collisions
            state["player_data"]["pos"][0] += _roll_dx * _ROLL_SPEED * dt
            state["player_data"]["pos"][1] += _roll_dy * _ROLL_SPEED * dt
            state["player_data"]["pos"][0] = max(
                -WORLD_MAX_TILES, min(WORLD_MAX_TILES, state["player_data"]["pos"][0])
            )
            state["player_data"]["pos"][1] = max(
                -WORLD_MAX_TILES, min(WORLD_MAX_TILES, state["player_data"]["pos"][1])
            )
            _rpx, _rpy, _ = _node_collisions(
                state["player_data"]["pos"][0],
                state["player_data"]["pos"][1],
                dt,
            )
            state["player_data"]["pos"][0] = _rpx
            state["player_data"]["pos"][1] = _rpy
            # Emit ghost-trail particles
            _ghost_timer -= dt
            if _ghost_timer <= 0.0:
                _ghost_timer = _GHOST_INTERVAL
                from rendering.particles import emit_roll as _emit_roll
                _emit_roll(
                    state["player_data"]["pos"][0],
                    state["player_data"]["pos"][1],
                )
        return  # skip normal movement/stamina logic while rolling

    # Block all movement input while chat / any text field is open.
    if config.chat_open:
        return

    # While sleeping, block all movement. Any WASD press wakes the player.
    if config.sleeping:
        _kb = config.keybinds
        if (keys[_kb["move_up"]] or keys[_kb["move_left"]]
                or keys[_kb["move_down"]] or keys[_kb["move_right"]]):
            config.sleeping = False
            config.state_outbox.put({"type": "wake_up"})
        return

    # ── Block (sentinel -2=RMB, -1=LMB, >0=keyboard key) ────────────────────
    _blk_key = config.keybinds.get("block", -2)
    if _blk_key == -2:
        _blocking_input = pygame.mouse.get_pressed()[2]
    elif _blk_key == -1:
        _blocking_input = pygame.mouse.get_pressed()[0]
    elif _blk_key > 0:
        _blocking_input = keys[_blk_key]
    else:
        _blocking_input = False
    if _blocking_input and not _rolling:
        if not config.is_blocking:
            config.is_blocking      = True
            config.block_start_time = time.time()
    else:
        config.is_blocking = False

    sp = config.player_stamina
    sp_max = config.player_stamina_max

    if sp <= 0.0:
        _exhausted = True
    elif _exhausted and sp >= _EXHAUST_RECOVER / 100.0 * sp_max:
        _exhausted = False

    _kb = config.keybinds
    sprinting = keys[_kb["sprint"]] and sp > 0.0 and not _exhausted and not config.is_blocking
    stealthy  = keys[_kb["crouch"]] and sp > 0.0 and not _exhausted and not sprinting and not config.is_blocking
    config.is_stealthy = stealthy

    if sprinting:
        speed = SPRINT_SPEED + config.player_speed_bonus
        config.player_stamina = max(0.0, sp - _SPRINT_DRAIN * dt)
    elif stealthy:
        speed = STEALTH_SPEED + config.player_speed_bonus
        config.player_stamina = max(0.0, sp - _STEALTH_DRAIN * dt)
    elif config.is_blocking:
        speed = PLAYER_SPEED + config.player_speed_bonus   # walk speed while blocking
        config.player_stamina = max(0.0, sp - 5.0 * dt)   # 5 stamina/s drain
    else:
        speed = PLAYER_SPEED + config.player_speed_bonus
        config.player_stamina = min(sp_max, sp + (_REGEN_RATE + config.player_sp_regen_bonus) * dt)

    if config.player_slow_timer > 0:
        speed *= _PLAYER_SLOW_MULT

    dx = keys[_kb["move_right"]] - keys[_kb["move_left"]]
    dy = keys[_kb["move_down"]]  - keys[_kb["move_up"]]

    config.is_moving = (dx != 0 or dy != 0)
    config.is_running = config.is_moving and sprinting

    if config.is_moving and not config.is_attacking:
        if abs(dy) >= abs(dx):
            config.player_facing = "down" if dy > 0 else "up"
        else:
            config.player_facing = "right" if dx > 0 else "left"

    if dx != 0 or dy != 0:
        length = (dx ** 2 + dy ** 2) ** 0.5
        dx /= length
        dy /= length
        if not config.is_attacking:
            state["player_data"]["pos"][0] += dx * speed * dt
            state["player_data"]["pos"][1] += dy * speed * dt
        state["player_data"]["pos"][0] = max(-WORLD_MAX_TILES, min(WORLD_MAX_TILES, state["player_data"]["pos"][0]))
        state["player_data"]["pos"][1] = max(-WORLD_MAX_TILES, min(WORLD_MAX_TILES, state["player_data"]["pos"][1]))

    px, py, in_cactus = _node_collisions(
        state["player_data"]["pos"][0],
        state["player_data"]["pos"][1],
        dt,
    )
    state["player_data"]["pos"][0] = px
    state["player_data"]["pos"][1] = py

    if in_cactus:
        _cactus_timer -= dt
        if _cactus_timer <= 0.0:
            _cactus_timer = _CACTUS_HIT_INTERVAL
            config.state_outbox.put({"type": "cactus_hit"})
            config.hit_flash_timer = 0.25
    else:
        _cactus_timer = 0.0

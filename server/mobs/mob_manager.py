# server/mobs/mob_manager.py
"""
Data-driven mob AI and lifecycle management.

States
------
wander          — mob picks a random nearby target and ambles toward it
aggro           — a player is within the mob JSON aggro_range; mob chases; holds at attack_range
windup          — stopped at attack range, telegraphing charge (yellow flash)
lunge           — charging at locked target point
return_to_origin — bouncing back to where the windup started

Spawn caps and spawn cadence are read from MOB_TYPES, which is expected to be populated from the mob JSON folder.
"""
import math
import random
import threading
import time
import uuid
from server.shared_lock import mobs_lock  # canonical lock — defined in shared_lock
from server.config import (
    WORLD_RADIUS, TICK_RATE,
    SPAWN_RATE_COEFF,
    MOB_SPAWN_RADIUS   as SPAWN_RADIUS,
    MOB_SPAWN_MIN_DIST as SPAWN_MIN_DIST,
    MOB_KNOCKBACK      as MELEE_KNOCKBACK,
    MAX_MOB_LEVEL      as MAX_SLIME_LEVEL,
    MOB_SEP_DIST, MOB_SEP_FORCE, STEALTH_AGGRO_MULT,
    LEVEL_DIST_SCALE, EXP_CURVE_BASE,
    KNOCKBACK_DECAY,
    PARRY_WINDOW       as _PARRY_WINDOW,
    PARRY_STAGGER_DUR  as _PARRY_STAGGER_DUR,
    BLOCK_DAMAGE_MULT  as _BLOCK_DAMAGE_MULT,
    BASE_SP_REGEN      as _BASE_SP_REGEN,
    COIN_DROP_MIN_MULT as _COIN_DROP_MIN_MULT,
    COIN_DROP_MAX_MULT as _COIN_DROP_MAX_MULT,
    DAY_START_HOUR     as _DAY_START_HOUR,
    DAY_END_HOUR       as _DAY_END_HOUR,
)
from server.item_data import (
    drain_defensive_gear_durability as _drain_defensive_gear_durability,
    get_equip_bonuses as _get_equip_bonuses,
)
from server.game_state.status_effect_data import STATUS_EFFECTS as _STATUS_EFFECTS
from server.game_state.status_effects import apply_status_effect as _apply_status_effect, tick_effects_on_entity as _tick_effects_on_entity
from server.mobs.mob_data import MOB_TYPES
from server.world.world_types import WATER_BIOMES
# NOTE: get_world_time is imported lazily inside update_mobs() to avoid
# the circular import that would arise from mob_manager ↔ game_sync at module level.

# ---------------------------------------------------------------------------
# Constants (engine-level -- not per-mob, not in JSON)
# ---------------------------------------------------------------------------
SPAWN_INTERVAL  = 1.0 / (SPAWN_RATE_COEFF * TICK_RATE)  # base spawn cadence
COIN_ITEM_ID    = 1       # coin (economy currency)
_MOB_OBJ_MIN_DSQ   = (0.35 + 0.40) ** 2
# SPAWN_RADIUS, SPAWN_MIN_DIST, MELEE_KNOCKBACK, MAX_SLIME_LEVEL, MOB_SEP_DIST, MOB_SEP_FORCE,
# STEALTH_AGGRO_MULT — all imported from server.config above

# ---------------------------------------------------------------------------
# Data-driven mob defaults and helpers
# ---------------------------------------------------------------------------
DEFAULT_MOB_TYPE = next((k for k, v in MOB_TYPES.items() if v.get("behavior") == "melee"), next(iter(MOB_TYPES), None))
DEFAULT_MOB = MOB_TYPES.get(DEFAULT_MOB_TYPE, {})
BOSS_MOB_TYPE = next((k for k, v in MOB_TYPES.items() if v.get("behavior") == "boss"), None)

DESPAWN_RADIUS    = DEFAULT_MOB.get("despawn_radius", 50)
DESPAWN_RADIUS_SQ = DESPAWN_RADIUS ** 2

WANDER_RADIUS   = DEFAULT_MOB.get("wander_radius", 6.25)
WANDER_IDLE_MIN = DEFAULT_MOB.get("wander_idle_min", 2.0)
WANDER_IDLE_MAX = DEFAULT_MOB.get("wander_idle_max", 5.0)

AGGRO_RANGE          = DEFAULT_MOB.get("aggro_range", 3.0)
AGGRO_RANGE_SQ       = AGGRO_RANGE ** 2
DEAGGRO_RANGE        = DEFAULT_MOB.get("deaggro_range", 7.0)
ANIMAL_DEAGGRO_RANGE = DEFAULT_MOB.get("deaggro_range", 7.0)
_MOB_SLOW_MULT = float(_STATUS_EFFECTS.get("slow", {}).get("mob_move_mult", 0.4))


def _mark_inventory_dirty(player_id: str) -> None:
    from server.game_state.game_sync import mark_inventory_dirty
    mark_inventory_dirty(player_id)

_next_spawn_times: dict[str, float] = {
    mob_type: 0.0
    for mob_type, cfg in MOB_TYPES.items()
    if cfg.get("max_count", 0) > 0 and cfg.get("behavior") != "boss"
}


def _mob_cfg(mob_or_type):
    mob_type = mob_or_type.get("type") if isinstance(mob_or_type, dict) else mob_or_type
    return MOB_TYPES.get(mob_type, DEFAULT_MOB)


def _mob_special(mob_or_type):
    return _mob_cfg(mob_or_type).get("special", {})


def _mob_behavior(mob_or_type):
    return _mob_cfg(mob_or_type).get("behavior", "melee")


def _is_passive_mob(mob_or_type):
    return _mob_behavior(mob_or_type) in ("passive", "flee", "animal")


def _cfg_float(cfg, key, default=0.0):
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return float(default)

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
mobs: dict       = {}      # {mob_id: MobData dict}
_boss_active:         bool  = False  # at most one configured boss per server
_boss_dungeon_pos:          list | None = None  # dungeon centre that spawned the boss
_pending_events:            list  = []     # {"type": ...} dicts drained by drain_events()
# mobs_lock imported from server.shared_lock (defined once, re-exported here for backward compat)

_players          = None    # injected reference
_spawn_world_item = None    # injected callback
_world_data       = None    # injected reference to server world tile dict

# ---------------------------------------------------------------------------
# Solid-object cache  (rebuilt only when placed_objects changes)
# ---------------------------------------------------------------------------
# _solid_tile_set: set of (int_tx, int_ty) coords of blocking placed objects
# _floor_positions: frozenset of (int_tx, int_ty) coords of stone_brick_floor tiles
# _cached_solid_rev: last seen _solid_revision from placed_objects.py
_solid_tile_set:    set       = set()
_floor_positions:   frozenset = frozenset()
_cached_solid_rev:  int       = -1  # -1 forces rebuild on first tick


def set_mob_refs(refs: dict):
    global _players, _spawn_world_item, _world_data
    _players          = refs["players"]
    _spawn_world_item = refs["spawn_world_item"]
    _world_data       = refs.get("world_data")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _dist(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def _normalize(dx, dy):
    d = math.sqrt(dx * dx + dy * dy)
    if d == 0:
        return 0.0, 0.0
    return dx / d, dy / d


def _new_wander_target(pos):
    angle  = random.uniform(0, 2 * math.pi)
    radius = random.uniform(1.0, WANDER_RADIUS)
    return [pos[0] + math.cos(angle) * radius,
            pos[1] + math.sin(angle) * radius]


def _apply_exp(pid: str, exp_gain: int):
    """Award exp and handle level-up. Must be called while holding players_lock."""
    if pid not in _players:
        return
    p = _players[pid]
    # Ensure EXP fields exist — handles saves created before this feature
    p.setdefault("exp", 0)
    p.setdefault("exp_next", 100)
    p.setdefault("stat_points", 0)
    p["exp"] += exp_gain
    while p["exp"] >= p["exp_next"]:
        p["exp"] -= p["exp_next"]
        p["level"] = p.get("level", 1) + 1
        new_level = p["level"]
        p["exp_next"] = EXP_CURVE_BASE * new_level * (new_level + 1)  # Skyrim-style quadratic curve
        # Bonus stat points at level milestones
        if new_level % 10 == 0:
            pts = 5
        elif new_level % 5 == 0:
            pts = 3
        else:
            pts = 1
        p["stat_points"] = p.get("stat_points", 0) + pts
        # Full restore on level-up
        p["health"]  = p.get("health_max",  100)
        p["stamina"] = p.get("stamina_max", 100.0)
        print(f"[LEVEL UP] {pid} → Lv{new_level} (+{pts} stat pt{'s' if pts > 1 else ''})")


def _is_water(pos):
    """Return True if the tile at pos is a water biome (ocean or river)."""
    if _world_data is None:
        return False
    tile = _world_data.get((int(pos[0]), int(pos[1])))
    if tile is None:
        return False
    return (tile.get("biome") if isinstance(tile, dict) else tile) in WATER_BIOMES


def _biome_at(pos):
    """Return the biome ID at pos, or None if unknown."""
    if _world_data is None:
        return None
    tile = _world_data.get((int(pos[0]), int(pos[1])))
    if tile is None:
        return None
    return tile.get("biome") if isinstance(tile, dict) else tile


def _is_obj_blocked(x, y, solid_tile_set):
    """Return True if (x,y) overlaps a solid placed object.

    Uses a pre-built set of integer tile coords for O(9) lookup instead of
    a linear scan over every wall (was O(n_walls)).
    """
    ix = int(x)
    iy = int(y)
    for dtx in (-1, 0, 1):
        for dty in (-1, 0, 1):
            tx = ix + dtx
            ty = iy + dty
            if (tx, ty) in solid_tile_set:
                cx = tx + 0.5
                cy = ty + 0.5
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) < _MOB_OBJ_MIN_DSQ:
                    return True
    return False



def _spawn_biome_allowed(pos, cfg):
    biome_ids = cfg.get("biome_ids")
    if not biome_ids:
        return True
    return _biome_at(pos) in biome_ids


def _find_spawn_pos(player_pos, cfg, floor_positions: frozenset):
    attempts = int(cfg.get("spawn_attempts", cfg.get("spawn_attempts_near_player", 15)))
    avoid_water = cfg.get("spawn_avoid_water", True)
    avoid_floor = cfg.get("spawn_avoid_floor", True)

    for _ in range(attempts):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]

        if avoid_water and _is_water(pos):
            continue
        if not _spawn_biome_allowed(pos, cfg):
            continue
        if avoid_floor and (int(pos[0]), int(pos[1])) in floor_positions:
            continue
        return pos

    return None


def _scaled_mob_level(player_pos, cfg):
    if cfg.get("fixed_level") is not None:
        return int(cfg["fixed_level"])
    if _is_passive_mob(cfg):
        return 1
    dist = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    return max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))


def _build_spawned_mob(mob_type, pos, player_pos):
    cfg = _mob_cfg(mob_type)
    level = _scaled_mob_level(player_pos, cfg)
    passive = _is_passive_mob(cfg)

    hp = round(_cfg_float(cfg, "hp", 1.0) * (1.0 + _cfg_float(cfg, "hp_scale_per_level", 0.0) * (level - 1)))
    damage = 0.0 if passive else round(_cfg_float(cfg, "damage", 0.0) * (1.0 + _cfg_float(cfg, "damage_scale", 0.0) * (level - 1)), 2)
    speed = _cfg_float(cfg, "speed", 1.0) * (1.0 + _cfg_float(cfg, "speed_scale", 0.0) * (level - 1))

    idle_min = _cfg_float(cfg, "wander_idle_min", WANDER_IDLE_MIN)
    idle_max = _cfg_float(cfg, "wander_idle_max", WANDER_IDLE_MAX)

    mob = {
        "type":          mob_type,
        "behavior":      cfg.get("behavior", "melee"),
        "pos":           pos,
        "health":        hp,
        "health_max":    hp,
        "level":         level,
        "damage":        damage,
        "speed":         speed,
        "windup_time":   _cfg_float(cfg, "windup", 0.0),
        "exp_reward":    int(cfg.get("exp", 0)) * level,
        "drop_id":       cfg.get("drop_id"),
        "state":         "idle",
        "idle_timer":    random.uniform(idle_min, idle_max),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
        "aggro_range_sq": _cfg_float(cfg, "aggro_range", AGGRO_RANGE) ** 2,
        "deaggro_range": _cfg_float(cfg, "deaggro_range", DEAGGRO_RANGE),
        "despawn_radius_sq": _cfg_float(cfg, "despawn_radius", DESPAWN_RADIUS) ** 2,
    }

    flee_range = cfg.get("flee_range")
    if flee_range is not None:
        mob["flee_range_sq"] = float(flee_range) ** 2

    if "slam_range" in cfg.get("special", {}):
        mob["last_slam"] = 0.0

    return mob


def _spawn_mob_near(mob_type, player_pos, floor_positions: frozenset = frozenset()):
    cfg = _mob_cfg(mob_type)
    pos = _find_spawn_pos(player_pos, cfg, floor_positions)
    if pos is None:
        return
    mobs[str(uuid.uuid4())[:8]] = _build_spawned_mob(mob_type, pos, player_pos)


def spawn_boss_at(pos: list) -> bool:
    """Spawn the configured boss mob at world position *pos*.

    Called by game_sync when a player enters the boss dungeon.
    Must be called while holding mobs_lock.
    Returns True if spawned, False if the boss is already active.
    """
    global _boss_active, _boss_dungeon_pos
    if _boss_active or BOSS_MOB_TYPE is None:
        return False
    mob_id = str(uuid.uuid4())[:8]
    spawn_pos = list(pos)
    cfg = _mob_cfg(BOSS_MOB_TYPE)
    mobs[mob_id] = {
        "type":          BOSS_MOB_TYPE,
        "behavior":      cfg.get("behavior", "melee"),
        "pos":           list(pos),
        "health":        cfg["hp"],
        "health_max":    cfg["hp"],
        "level":         cfg.get("fixed_level", 1),
        "damage":        cfg.get("damage", 0.0),
        "speed":         cfg.get("speed", 0.0),
        "windup_time":   cfg.get("windup", 0.0),
        "exp_reward":    cfg.get("exp", 0),
        "drop_id":       cfg.get("drop_id"),
        "state":         "idle",
        "idle_timer":    cfg.get("spawn_idle", 0.0),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
        "aggro_range_sq": cfg.get("aggro_range", AGGRO_RANGE) ** 2,
        "deaggro_range": cfg.get("deaggro_range", DEAGGRO_RANGE),
        "despawn_radius_sq": cfg.get("despawn_radius", DESPAWN_RADIUS) ** 2,
    }
    _boss_active = True
    _boss_dungeon_pos  = list(spawn_pos)
    _pending_events.append({"type": "boss_spawned", "name": _mob_cfg(BOSS_MOB_TYPE).get('name', (BOSS_MOB_TYPE or "boss").replace("_", " ").title()),
                             "pos": list(spawn_pos)})
    print(f"[BOSS] {_mob_cfg(BOSS_MOB_TYPE).get('name', BOSS_MOB_TYPE)} awakened in dungeon at {spawn_pos}")
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def update_mobs(dt: float):
    """Advance all mob AI. Call once per game tick with elapsed seconds."""
    if _players is None:
        return

    # Lazy import to break the game_sync ↔ mob_manager circular dependency.
    from server.game_state.game_sync import get_world_time as _get_world_time

    now = time.time()

    # Snapshot player positions to avoid holding players_lock too long
    from server.shared_lock import players_lock
    with players_lock:
        player_snapshot = {
            pid: list(pdata.get("pos", [0, 0]))
            for pid, pdata in _players.items()
        }
        stealth_snapshot = {
            pid: pdata.get("stealthy", False)
            for pid, pdata in _players.items()
        }

    dead = []
    pending_melee:   list = []        # (pid, dmg, mob_pos) triples applied after releasing mobs_lock
    pending_exp:     list = []        # (pid, exp_amount) triples applied after releasing mobs_lock
    pending_slow:    dict[str, float] = {}  # pid → max slow duration; deduplicates multi-mob contact
    pending_poison:  dict[str, tuple] = {}  # pid → (duration, dps) from scorpion hits
    pending_despawn: list = []        # mob_ids that despawned silently (no drops/exp)
    pending_spawns:  list = []        # callables deferred until after main mob-loop (dict-safe)

    # Rebuild the solid-tile set only when placed_objects has changed (revision bump).
    # This avoids an O(n_placed × 120 Hz) scan each tick.
    global _solid_tile_set, _floor_positions, _cached_solid_rev
    try:
        from server.game_state.placed_objects import (
            placed_objects as _po_dict, placed_objects_lock as _po_lock,
            SOLID_TYPES as _PO_SOLID, get_solid_revision as _get_solid_rev
        )
        _cur_rev = _get_solid_rev()
        if _cur_rev != _cached_solid_rev:
            with _po_lock:
                _solid_tile_set = {
                    (obj["pos"][0], obj["pos"][1])
                    for obj in _po_dict.values()
                    if obj["type"] in _PO_SOLID
                    and not (obj["type"] == "door" and obj.get("state") == "open")
                }
                _floor_positions = frozenset(
                    (obj["pos"][0], obj["pos"][1])
                    for obj in _po_dict.values()
                    if obj["type"] == "stone_brick_floor"
                )
            _cached_solid_rev = _cur_rev
    except Exception:
        pass   # keep whatever was cached last tick

    with mobs_lock:
        # --- Spawn (cooldown-regulated to prevent burst spawning) ---
        _wt       = _get_world_time()
        _is_night = _wt < _DAY_START_HOUR or _wt > _DAY_END_HOUR
        _tc: dict = {}
        for _m in mobs.values():
            _t = _m["type"]
            _tc[_t] = _tc.get(_t, 0) + 1

        _player_vals = list(player_snapshot.values()) if player_snapshot else []
        if _player_vals:
            for _mob_type, _cfg in MOB_TYPES.items():
                _max_count = int(_cfg.get("max_count", 0))
                if _max_count <= 0 or _cfg.get("behavior") == "boss":
                    continue
                if _cfg.get("spawn_night_only", False) and not _is_night:
                    continue
                if _cfg.get("spawn_cap_per_player", _mob_type == DEFAULT_MOB_TYPE):
                    _max_count *= max(1, len(player_snapshot))
                if _tc.get(_mob_type, 0) >= _max_count:
                    continue
                if now < _next_spawn_times.get(_mob_type, 0.0):
                    continue
                _spawn_mob_near(_mob_type, random.choice(_player_vals), _floor_positions)
                _next_spawn_times[_mob_type] = now + SPAWN_INTERVAL * _cfg.get("spawn_interval_mult", 1.0)
        # Boss mobs are spawned explicitly through spawn_boss_at().

        # --- Update each mob ---
        for mob_id, mob in mobs.items():
            if mob["health"] <= 0:
                dead.append(mob_id)
                continue

            pos = mob["pos"]

            # --- Despawn mobs whose JSON says they are night-only when day breaks ---
            _cfg = _mob_cfg(mob)
            if not _is_night and _cfg.get("spawn_night_only", False):
                dead.append(mob_id)
                pending_despawn.append(mob_id)
                continue

            # --- Despawn if too far from all players ---
            if player_snapshot:
                min_dsq = min(
                    (pos[0] - pp[0]) ** 2 + (pos[1] - pp[1]) ** 2
                    for pp in player_snapshot.values()
                )
                if min_dsq > mob.get("despawn_radius_sq", DESPAWN_RADIUS_SQ):
                    dead.append(mob_id)
                    pending_despawn.append(mob_id)
                    continue

            # --- Decay knockback velocity (exponential) ---
            kb_vel = mob.get("knockback_vel")
            if kb_vel:
                pos[0] += kb_vel[0] * dt
                pos[1] += kb_vel[1] * dt
                decay = max(0.0, 1.0 - KNOCKBACK_DECAY * dt)
                kb_vel[0] *= decay
                kb_vel[1] *= decay
                if kb_vel[0] * kb_vel[0] + kb_vel[1] * kb_vel[1] < 0.01:
                    mob.pop("knockback_vel", None)

            # --- Decay hit flash ---
            if mob.get("hit_flash", 0.0) > 0:
                mob["hit_flash"] = max(0.0, mob["hit_flash"] - dt)

            # --- Tick configured status effects ---
            _tick_effects_on_entity(mob, dt, death_credit="_burn", flash_on_tick=True)

            # Snapshot position before state-based movement for water-tile blocking
            prev_x, prev_y = pos[0], pos[1]

            state = mob.get("state", "wander")

            # --- Stagger: briefly frozen after a player perfect-parry ---
            if mob.get("stagger_timer", 0.0) > 0:
                mob["stagger_timer"] = max(0.0, mob["stagger_timer"] - dt)
                continue  # skip all movement and attacks while staggered

            # --- Windup: stopped, telegraphing attack ---
            if state == "windup":
                mob["windup_timer"] = mob.get("windup_timer", mob.get("windup_time", 0.0)) - dt
                if mob["windup_timer"] <= 0:
                    mob["state"]     = "lunge"
                    mob["lunge_hit"] = False
                continue  # no movement during windup

            # --- Lunge: charge toward lunge_target ---
            if state == "lunge":
                tp = mob.get("lunge_target", pos)
                ddx, ddy = tp[0] - pos[0], tp[1] - pos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                # Per-tick hit check — if player is in the mob’s path, they get hit
                if not mob.get("lunge_hit", False):
                    tpid = mob.get("target_player")
                    if tpid and tpid in player_snapshot:
                        if _dist(pos, player_snapshot[tpid]) < _mob_cfg(mob).get("lunge_hit_radius", 0.7):
                            pending_melee.append((tpid, mob.get("damage", _mob_cfg(mob).get("damage", 0.0)), list(pos), mob_id))
                            mob["lunge_hit"] = True
                            _special = _mob_special(mob)
                            if "poison_duration" in _special and "poison_dps" in _special:
                                pending_poison[tpid] = (_special["poison_duration"], _special["poison_dps"])
                            if "web_slow_on_hit" in _special:
                                pending_slow[tpid] = max(pending_slow.get(tpid, 0.0), _special["web_slow_on_hit"])
                            if "slow_on_hit" in _special:
                                pending_slow[tpid] = max(pending_slow.get(tpid, 0.0), _special["slow_on_hit"])
                            if _special.get("phase2_spawn_type"):
                                _hp_pct = mob.get("health", 0) / max(mob.get("health_max", 1), 1)
                                if _hp_pct < _special.get("phase2_hp_pct", 0.5) and not mob.get("phase2_spawned_this_lunge"):
                                    _spos = list(pos)
                                    _spawn_type = _special["phase2_spawn_type"]
                                    _spawn_count = int(_special.get("phase2_spawn_count", 2))
                                    for _ in range(_spawn_count):
                                        pending_spawns.append(lambda _pp=_spos, _mt=_spawn_type: _spawn_mob_near(_mt, _pp, _floor_positions))
                                    mob["phase2_spawned_this_lunge"] = True
                            if "phase3_hp_pct" in _special and "phase3_aoe_radius" in _special:
                                _hp_pct = mob.get("health", 0) / max(mob.get("health_max", 1), 1)
                                if _hp_pct < _special["phase3_hp_pct"]:
                                    for _apid, _appos in player_snapshot.items():
                                        if _apid != tpid and _dist(pos, _appos) < _special["phase3_aoe_radius"]:
                                            pending_melee.append((_apid, mob.get("damage", 0.0) * _special.get("phase3_damage_mult", 0.5), list(pos), None))
                if d < 0.2:  # reached endpoint
                    mob["state"]         = "landing"
                    mob["landing_timer"] = _mob_cfg(mob).get("landing_pause", 0.2)
                    mob["last_attack"]   = now
                else:
                    _lunge_spd = _mob_cfg(mob).get("lunge_speed", 12.0)
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * _lunge_spd * dt
                    pos[1] += ny * _lunge_spd * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Landing: brief pause at endpoint (punish window) ---
            if state == "landing":
                # Bats fly straight through — no landing pause
                if _mob_cfg(mob).get("landing_pause", 0.2) <= 0:
                    mob["state"] = "return_to_origin"
                    continue
                mob["landing_timer"] = mob.get("landing_timer", _mob_cfg(mob).get("landing_pause", 0.2)) - dt
                if mob["landing_timer"] <= 0:
                    mob["state"] = "return_to_origin"
                continue

            # --- Return to origin after lunge ---
            if state == "return_to_origin":
                origin = mob.get("origin_pos", pos)
                ddx, ddy = origin[0] - pos[0], origin[1] - pos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                if d < 0.3:
                    mob["state"] = "idle"
                    mob["idle_timer"] = random.uniform(_mob_cfg(mob).get("wander_idle_min", WANDER_IDLE_MIN), _mob_cfg(mob).get("wander_idle_max", WANDER_IDLE_MAX))
                    pos[0] = origin[0]   # snap to exact spawn point
                    pos[1] = origin[1]
                    mob.pop("lunge_target", None)
                    mob.pop("lunge_hit",    None)
                    mob.pop("phase2_spawned_this_lunge", None)
                else:
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * _mob_cfg(mob).get("lunge_speed", 12.0) * dt
                    pos[1] += ny * _mob_cfg(mob).get("lunge_speed", 12.0) * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                continue

            # --- Configured AOE slam charge (entered from aggro) ---
            if state == "slam_charge":
                _special = _mob_special(mob)
                mob["slam_timer"] = mob.get("slam_timer", _special.get("slam_charge", 0.0)) - dt
                if mob["slam_timer"] <= 0:
                    _slam_pos = list(pos)
                    for _apid, _appos in player_snapshot.items():
                        if _dist(_slam_pos, _appos) <= _special.get("slam_radius", 0.0):
                            pending_melee.append((_apid, mob.get("damage", _mob_cfg(mob).get("damage", 0.0)), _slam_pos, None))
                    mob["last_slam"] = now
                    mob["state"]     = "idle"
                    mob["idle_timer"] = random.uniform(1.5, 3.0)
                continue

            # ── Find closest player (shared by flee / aggro / wander / idle) ──
            closest_pid     = None
            closest_dist_sq = float("inf")
            for pid, ppos in player_snapshot.items():
                _ddx = pos[0] - ppos[0]
                _ddy = pos[1] - ppos[1]
                _dsq = _ddx * _ddx + _ddy * _ddy
                if _dsq < closest_dist_sq:
                    closest_dist_sq = _dsq
                    closest_pid     = pid

            # --- Flee: passive animals run away from the closest player ---
            if state == "flee":
                if not player_snapshot or closest_dist_sq > (mob.get("deaggro_range", ANIMAL_DEAGGRO_RANGE) ** 2):
                    mob["state"] = "wander"
                    continue
                if closest_pid:
                    ppos = player_snapshot[closest_pid]
                    dx   = pos[0] - ppos[0]   # direction AWAY from player
                    dy   = pos[1] - ppos[1]
                    d    = math.sqrt(dx * dx + dy * dy) or 1.0
                    nx, ny = dx / d, dy / d
                    spd = mob.get("speed", 3.0)
                    pos[0] += nx * spd * dt
                    pos[1] += ny * spd * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                        mob["state"] = "wander"
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Aggro: actively chase the target player ---
            if state == "aggro":
                tp = mob.get("target_player")
                if not tp or tp not in player_snapshot:
                    mob["state"]         = "wander"
                    mob["target_player"] = None
                    continue
                tppos = player_snapshot[tp]
                da    = _dist(pos, tppos)
                if da > mob.get("deaggro_range", DEAGGRO_RANGE):
                    mob["state"]         = "wander"
                    mob["target_player"] = None
                    continue
                _special = _mob_special(mob)
                if "slam_range" in _special:
                    if da <= _special["slam_range"] and now - mob.get("last_slam", 0.0) >= _special.get("slam_cooldown", 0.0):
                        mob["state"]      = "slam_charge"
                        mob["slam_timer"] = _special.get("slam_charge", 0.0)
                        continue
                if da <= _mob_cfg(mob).get("attack_range", 2.0) and now - mob.get("last_attack", 0.0) >= _mob_cfg(mob).get("attack_cooldown", 2.5):
                    # Inline windup using the tracked target
                    dx_, dy_ = tppos[0] - pos[0], tppos[1] - pos[1]
                    d_   = math.sqrt(dx_ * dx_ + dy_ * dy_) or 1.0
                    nx_, ny_ = dx_ / d_, dy_ / d_
                    mob["state"]         = "windup"
                    mob["windup_timer"]  = mob.get("windup_time", _mob_cfg(mob).get("windup", 0.0))
                    mob["origin_pos"]    = list(pos)
                    _overshoot = _mob_cfg(mob).get("lunge_overshoot", 1.0)
                    if _mob_cfg(mob).get("scale_lunge_overshoot", False):
                        _overshoot *= 1.0 + 0.3 * (mob.get("level", 1) - 1)
                    mob["lunge_target"]  = [
                        pos[0] + nx_ * (d_ + _overshoot),
                        pos[1] + ny_ * (d_ + _overshoot),
                    ]
                    mob["facing"] = ("right" if nx_ > abs(ny_) else
                                     "left"  if -nx_ > abs(ny_) else
                                     "down"  if ny_ > 0 else "up")
                    continue
                # Move toward player
                dx, dy = tppos[0] - pos[0], tppos[1] - pos[1]
                d = math.sqrt(dx * dx + dy * dy) or 1.0
                nx, ny = dx / d, dy / d
                spd = mob.get("speed", _mob_cfg(mob).get("speed", 1.0)) * (_MOB_SLOW_MULT if mob.get("slow_timer", 0.0) > 0 else 1.0)
                pos[0] += nx * spd * dt
                pos[1] += ny * spd * dt
                if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                    pos[0], pos[1] = prev_x, prev_y
                else:
                    mob["facing"] = ("right" if nx > abs(ny) else
                                     "left"  if -nx > abs(ny) else
                                     "down"  if ny > 0 else "up")
                continue

            # --- Wander: amble slowly toward a chosen point near origin ---
            if state == "wander":
                _is_passive = _is_passive_mob(mob)
                if _is_passive:
                    _fl_sq = mob.get("flee_range_sq", 0.0)
                    if closest_pid and closest_dist_sq <= _fl_sq:
                        mob["state"] = "flee"
                        continue
                else:
                    _aggro_sq = mob.get("aggro_range_sq", AGGRO_RANGE_SQ)
                    if closest_pid and closest_dist_sq <= _aggro_sq:
                        mob["state"]         = "aggro"
                        mob["target_player"] = closest_pid
                        continue
                tgt = mob.get("wander_target", mob.get("origin_pos", pos))
                ddx, ddy = tgt[0] - pos[0], tgt[1] - pos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                if d < 0.3:
                    mob["state"]      = "idle"
                    mob["idle_timer"] = random.uniform(_mob_cfg(mob).get("wander_idle_min", WANDER_IDLE_MIN), _mob_cfg(mob).get("wander_idle_max", WANDER_IDLE_MAX))
                else:
                    spd = mob.get("speed", _mob_cfg(mob).get("speed", 1.0)) * (_MOB_SLOW_MULT if mob.get("slow_timer", 0.0) > 0 else 1.0)
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * spd * dt
                    pos[1] += ny * spd * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                        mob["state"]      = "idle"
                        mob["idle_timer"] = random.uniform(_mob_cfg(mob).get("wander_idle_min", WANDER_IDLE_MIN), _mob_cfg(mob).get("wander_idle_max", WANDER_IDLE_MAX))
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Idle: rest, then pick next wander target ---
            _is_passive_idle = _is_passive_mob(mob)
            if _is_passive_idle:
                _fl_sq_idle = mob.get("flee_range_sq", 0.0)
                if closest_pid and closest_dist_sq <= _fl_sq_idle:
                    mob["state"] = "flee"
                    continue
            else:
                _aggro_sq_idle = mob.get("aggro_range_sq", AGGRO_RANGE_SQ)
                if closest_pid and closest_dist_sq <= _aggro_sq_idle:
                    mob["state"]         = "aggro"
                    mob["target_player"] = closest_pid
                    continue

            idle_t = mob.get("idle_timer", 0.0) - dt
            if idle_t <= 0:
                origin = mob.get("home_pos", pos)
                for _ in range(5):  # retry to avoid water
                    angle = random.uniform(0, 2 * math.pi)
                    r     = random.uniform(_mob_cfg(mob).get("wander_radius", WANDER_RADIUS) * 0.3, _mob_cfg(mob).get("wander_radius", WANDER_RADIUS))
                    tgt   = [origin[0] + math.cos(angle) * r,
                             origin[1] + math.sin(angle) * r]
                    if not _is_water(tgt):
                        mob["wander_target"] = tgt
                        mob["state"]         = "wander"
                        break
                mob["idle_timer"] = random.uniform(_mob_cfg(mob).get("wander_idle_min", WANDER_IDLE_MIN), _mob_cfg(mob).get("wander_idle_max", WANDER_IDLE_MAX))
            else:
                mob["idle_timer"] = idle_t

        # Execute deferred spawns, such as configured phase-spawn effects
        for _spawn_fn in pending_spawns:
            _spawn_fn()

        # --- Mob-mob separation — prevent stacking (idle/wander only) ---
        _ATTACK_STATES = frozenset({"windup", "lunge", "landing", "return_to_origin"})
        live_ids = [mid for mid in mobs if mobs[mid]["health"] > 0]
        for i in range(len(live_ids)):
            for j in range(i + 1, len(live_ids)):
                ma = mobs[live_ids[i]]
                mb = mobs[live_ids[j]]
                # skip if either mob is mid-attack — separation would deflect lunges
                if ma.get("state") in _ATTACK_STATES or mb.get("state") in _ATTACK_STATES:
                    continue
                ddx = ma["pos"][0] - mb["pos"][0]
                ddy = ma["pos"][1] - mb["pos"][1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                if 0 < d < MOB_SEP_DIST:
                    push = MOB_SEP_FORCE * (MOB_SEP_DIST - d) / MOB_SEP_DIST * dt
                    nx, ny = ddx / d, ddy / d
                    ma["pos"][0] += nx * push
                    ma["pos"][1] += ny * push
                    mb["pos"][0] -= nx * push
                    mb["pos"][1] -= ny * push

        # --- Mob-player separation + contact slowdown ---
        for mob_id in live_ids:
            mob = mobs[mob_id]
            attacking = mob.get("state") in _ATTACK_STATES
            for pid, ppos in player_snapshot.items():
                ddx = mob["pos"][0] - ppos[0]
                ddy = mob["pos"][1] - ppos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                # only push when idle/wandering — attacking mobs ignore this border
                if not attacking and 0 < d < MOB_SEP_DIST:
                    push = MOB_SEP_FORCE * (MOB_SEP_DIST - d) / MOB_SEP_DIST * dt
                    nx, ny = ddx / d, ddy / d
                    mob["pos"][0] += nx * push
                    mob["pos"][1] += ny * push
                _contact_slow = _mob_special(mob).get("slow_contact")
                _slow_range = _mob_special(mob).get("slow_range", 0.0)
                if _contact_slow and d < _slow_range:
                    if pid not in pending_slow or pending_slow[pid] < _contact_slow:
                        pending_slow[pid] = _contact_slow

        # --- Clamp all mob positions to world boundary ---
        for mob in mobs.values():
            p = mob["pos"]
            p[0] = max(-WORLD_RADIUS, min(WORLD_RADIUS, p[0]))
            p[1] = max(-WORLD_RADIUS, min(WORLD_RADIUS, p[1]))

        # --- Remove dead mobs and drop items ---
    global _boss_active, _boss_dungeon_pos
    despawn_set = set(pending_despawn)
    for mob_id in dead:
        drop_pos    = list(mobs[mob_id]["pos"])
        killed_by   = mobs[mob_id].get("killed_by")
        exp_reward  = mobs[mob_id].get("exp_reward", 0)
        mob_level   = mobs[mob_id].get("level", 1)
        mob_drop_id = mobs[mob_id].get("drop_id")
        mob_type    = mobs[mob_id].get("type", DEFAULT_MOB_TYPE)
        del mobs[mob_id]
        if mob_id in despawn_set:
            continue  # silent despawn — no drops, no exp, no log
        if mob_type == BOSS_MOB_TYPE:
            _boss_active = False
            _pending_events.append({"type": "boss_defeated", "name": _mob_cfg(BOSS_MOB_TYPE).get('name', (BOSS_MOB_TYPE or "boss").replace("_", " ").title()),
                                    "dungeon_pos": list(_boss_dungeon_pos) if _boss_dungeon_pos else None})
            _boss_dungeon_pos = None
        if killed_by:
            pending_exp.append((killed_by, exp_reward))
            if mob_drop_id is not None:
                _spawn_world_item(mob_drop_id, drop_pos, qty=1)
            # Bosses can also drop a random item range from special.gem_drop_range
            if mob_type == BOSS_MOB_TYPE:
                gem_id = random.randint(_mob_special(mob_type).get("gem_drop_range", [50, 56])[0], _mob_special(mob_type).get("gem_drop_range", [50, 56])[1])
                _spawn_world_item(gem_id, [drop_pos[0] + 0.5, drop_pos[1] + 0.5], qty=1)
            _spawn_world_item(COIN_ITEM_ID, drop_pos, qty=random.randint(mob_level * _COIN_DROP_MIN_MULT, mob_level * _COIN_DROP_MAX_MULT))
            print(f"[MOB] {mob_type.title()} {mob_id} (Lv{mob_level}) died — dropped items at {drop_pos}")

    # Apply all per-tick player updates: regen and combat events
    from server.shared_lock import players_lock
    with players_lock:
        # Per-player regen
        for pdata in _players.values():
            sp_max  = pdata.get("stamina_max", 100.0)
            sp_rate = _BASE_SP_REGEN + pdata.get("sp_regen_bonus", 0.0)
            pdata["stamina"] = min(sp_max, pdata.get("stamina", sp_max) + sp_rate * dt)
            hp_regen = pdata.get("hp_regen", 0.0)
            if hp_regen > 0:
                equip_hp_bonus = int(_get_equip_bonuses(pdata.get("inventory", [])).get("health_max", 0))
                hp_max = pdata.get("health_max", 100) + equip_hp_bonus
                pdata["health"] = min(hp_max, pdata.get("health", 0.0) + hp_regen * dt)
        # Contact slow from proximity to mobs
        for pid, slow_dur in pending_slow.items():
            if pid in _players:
                _apply_status_effect(_players[pid], "slow", duration=slow_dur)
        dirty_players: set[str] = set()
        for pid, dmg, mob_pos, attacker_mid in pending_melee:
            if pid not in _players:
                continue
            # Skip damage if player is in creative mode or currently dodge-rolling
            if _players[pid].get("creative", False):
                continue
            if _players[pid].get("invulnerable", False):
                continue
            defense = _get_equip_bonuses(_players[pid].get("inventory", []))["defense"]
            # Diminishing-returns formula: defense/(defense+50) gives reduction%
            # 50 def → 50%, 100 def → 66.7%, 200 def → 80%  — never fully negates
            actual_dmg = max(1.0, dmg * (1.0 - defense / (defense + 50.0)))
            # ── Block / Parry ──────────────────────────────────────────────────────
            if _players[pid].get("blocking", False):
                _block_age = now - _players[pid].get("block_start", 0.0)
                if attacker_mid is not None and attacker_mid in mobs and _block_age < _PARRY_WINDOW:
                    # Perfect parry: negate damage + stagger the attacker mob
                    actual_dmg = 0.0
                    mobs[attacker_mid]["stagger_timer"] = _PARRY_STAGGER_DUR
                    if mobs[attacker_mid].get("state") in ("windup", "lunge", "landing"):
                        mobs[attacker_mid]["state"] = "return_to_origin"
                else:
                    # Normal block: 60% damage reduction
                    actual_dmg = max(0.0, actual_dmg * _BLOCK_DAMAGE_MULT)
            if actual_dmg <= 0.0:
                continue
            _players[pid]["health"] = max(0.0, _players[pid]["health"] - actual_dmg)
            print(f"[MOB] Mob hit {pid} for {actual_dmg:.1f} dmg (def {defense:.0f}) "
                  f"(hp now {_players[pid]['health']:.1f})")
            _drain_defensive_gear_durability(_players[pid].get("inventory", []))
            dirty_players.add(pid)
            # Knockback: push player away from the mob
            pp = _players[pid]["pos"]
            ddx = pp[0] - mob_pos[0]
            ddy = pp[1] - mob_pos[1]
            dist = math.sqrt(ddx * ddx + ddy * ddy)
            if dist > 0:
                nx, ny = ddx / dist, ddy / dist
            else:
                nx, ny = 0.0, 1.0
            kb = [nx * MELEE_KNOCKBACK, ny * MELEE_KNOCKBACK]
            _players[pid]["pos"][0] += kb[0]
            _players[pid]["pos"][1] += kb[1]
            _players[pid]["knockback"] = kb   # picked up by game_sync next tick
            if attacker_mid is not None and attacker_mid in mobs:
                _slow_hit = _mob_special(mobs[attacker_mid]).get("slow_on_hit")
                if _slow_hit:
                    _apply_status_effect(_players[pid], "slow", duration=_slow_hit)
        # Apply configured poison effects
        for pid, (dur, dps) in pending_poison.items():
            if pid in _players and not _players[pid].get("creative", False):
                _apply_status_effect(_players[pid], "poison", duration=dur, potency=dps)
                print(f"[MOB] Poisoned {pid} for {dur}s at {dps} dps")
        for pid, exp_amount in pending_exp:
            _apply_exp(pid, exp_amount)
        for pid in dirty_players:
            _mark_inventory_dirty(pid)

def drain_events() -> list:
    """Return and clear all pending mob events (boss_spawned, boss_defeated, etc.).
    Thread-safe — call from the server game-loop after update_mobs().
    """
    with mobs_lock:
        evts = list(_pending_events)
        _pending_events.clear()
    return evts

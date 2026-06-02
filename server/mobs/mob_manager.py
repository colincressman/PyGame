# server/mobs/mob_manager.py
"""
Slime mob AI and lifecycle management.

States
------
wander          — mob picks a random nearby target and ambles toward it
aggro           — a player is within AGGRO_RANGE; mob chases; holds at _S["attack_range"]
windup          — stopped at attack range, telegraphing charge (yellow flash)
lunge           — charging at locked target point
return_to_origin — bouncing back to where the windup started

Spawn cap: MAX_SLIMES concurrent mobs, one spawn per SPAWN_INTERVAL seconds.
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
    DEFAULT_BURN_DPS   as _DEFAULT_BURN_DPS,
    DAY_START_HOUR     as _DAY_START_HOUR,
    DAY_END_HOUR       as _DAY_END_HOUR,
)
from server.item_data import get_equip_bonuses as _get_equip_bonuses, drain_durability as _drain_durability
from server.mobs.mob_data import MOB_TYPES
# NOTE: get_world_time is imported lazily inside update_mobs() to avoid
# the circular import that would arise from mob_manager ↔ game_sync at module level.

# ---------------------------------------------------------------------------
# Constants (engine-level -- not per-mob, not in JSON)
# ---------------------------------------------------------------------------
SPAWN_INTERVAL  = 1.0 / (SPAWN_RATE_COEFF * TICK_RATE)  # base spawn cadence
COIN_ITEM_ID    = 1       # coin (economy currency)
WATER_BIOMES    = frozenset({0, 3})  # biome IDs: 0=ocean, 3=river
_MOB_OBJ_MIN_DSQ   = (0.35 + 0.40) ** 2
# SPAWN_RADIUS, SPAWN_MIN_DIST, MELEE_KNOCKBACK, MAX_SLIME_LEVEL, MOB_SEP_DIST, MOB_SEP_FORCE,
# STEALTH_AGGRO_MULT — all imported from server.config above

# ---------------------------------------------------------------------------
# Per-mob shorthands derived from MOB_TYPES
# ---------------------------------------------------------------------------
_S  = MOB_TYPES["slime"]
_SK = MOB_TYPES["skeleton"]
_SP = MOB_TYPES["spider"]
_SC = MOB_TYPES["scorpion"]
_B  = MOB_TYPES["bat"]
_Y  = MOB_TYPES["yeti"]
_R  = MOB_TYPES["rabbit"]
_D  = MOB_TYPES["deer"]
_BK = MOB_TYPES["slime_king"]

MAX_SLIMES    = _S["max_count"]
MAX_SKELETONS = _SK["max_count"]
MAX_SPIDERS   = _SP["max_count"]
MAX_SCORPIONS = _SC["max_count"]
MAX_BATS      = _B["max_count"]
MAX_YETIS     = _Y["max_count"]
MAX_RABBITS   = _R["max_count"]
MAX_DEER      = _D["max_count"]
MAX_BOSS      = _BK["max_count"]

SKELETON_SPAWN_INTERVAL  = SPAWN_INTERVAL * _SK["spawn_interval_mult"]
SPIDER_SPAWN_INTERVAL    = SPAWN_INTERVAL * _SP["spawn_interval_mult"]
SCORPION_SPAWN_INTERVAL  = SPAWN_INTERVAL * _SC["spawn_interval_mult"]
BAT_SPAWN_INTERVAL       = SPAWN_INTERVAL * _B["spawn_interval_mult"]
YETI_SPAWN_INTERVAL      = SPAWN_INTERVAL * _Y["spawn_interval_mult"]
RABBIT_SPAWN_INTERVAL    = SPAWN_INTERVAL * _R["spawn_interval_mult"]
DEER_SPAWN_INTERVAL      = SPAWN_INTERVAL * _D["spawn_interval_mult"]

SLIME_SLOW_RANGE   = _S["special"]["slow_range"]
SLIME_SLOW_CONTACT = _S["special"]["slow_contact"]
SLIME_SLOW_HIT     = _S["special"]["slow_on_hit"]

SPIDER_WEB_SLOW          = _SP["special"]["web_slow_on_hit"]
SCORPION_POISON_DURATION = _SC["special"]["poison_duration"]
SCORPION_POISON_DPS      = _SC["special"]["poison_dps"]

YETI_SLAM_RANGE    = _Y["special"]["slam_range"]
YETI_SLAM_COOLDOWN = _Y["special"]["slam_cooldown"]
YETI_SLAM_RADIUS   = _Y["special"]["slam_radius"]
YETI_SLAM_CHARGE   = _Y["special"]["slam_charge"]

DESPAWN_RADIUS    = _S["despawn_radius"]
DESPAWN_RADIUS_SQ = DESPAWN_RADIUS ** 2

WANDER_RADIUS   = _S["wander_radius"]
WANDER_IDLE_MIN = _S["wander_idle_min"]
WANDER_IDLE_MAX = _S["wander_idle_max"]

AGGRO_RANGE          = _S["aggro_range"]
AGGRO_RANGE_SQ       = _S["aggro_range_sq"]
DEAGGRO_RANGE        = _S["deaggro_range"]
ANIMAL_DEAGGRO_RANGE = _R["deaggro_range"]

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
mobs: dict       = {}      # {mob_id: MobData dict}
_next_spawn_time:           float = 0.0
_next_skeleton_spawn_time:  float = 0.0
_next_spider_spawn_time:    float = 0.0
_next_scorpion_spawn_time:  float = 0.0
_next_bat_spawn_time:       float = 0.0
_next_yeti_spawn_time:      float = 0.0
_next_rabbit_spawn_time:    float = 0.0
_next_deer_spawn_time:      float = 0.0
_slime_king_active:         bool  = False  # at most one Slime King per server
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


def _spawn_slime_near(player_pos, floor_positions: frozenset = frozenset()):
    for _ in range(10):  # retry to avoid spawning in water or on floor tiles
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if not _is_water(pos):
            tx, ty = int(pos[0]), int(pos[1])
            if (tx, ty) not in floor_positions:
                break
    else:
        return  # all attempts landed in water or on floor; skip this spawn
    # Level scales with distance from world origin — farther = harder
    # 100 tiles per level: level 1 near origin, level 10 at ~1000 tiles
    dist = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp = round(_S["hp"] * (1.0 + _S["hp_scale_per_level"] * (level - 1)))
    mob_id = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "slime",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         level,
        "damage":        round(_S["damage"] * (1.0 + _S["damage_scale"] * (level - 1)), 2),
        "speed":         _S["speed"] * (1.0 + _S["speed_scale"] * (level - 1)),
        "windup_time":   _S["windup"],
        "exp_reward":    _S["exp"] * level,
        "drop_id":       _S["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),      # permanent spawn anchor; wander stays within WANDER_RADIUS of this
        "origin_pos":    list(pos),      # pre-attack position; reset each windup, returned to after lunge
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
    }


def _spawn_skeleton_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a skeleton near player_pos, only in desert or tundra biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _SK["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return  # no valid biome position found nearby
    dist       = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level      = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp     = round(_SK["hp"] * (1.0 + _SK["hp_scale_per_level"] * (level - 1)))
    mob_id     = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "skeleton",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         level,
        "damage":        round(_SK["damage"] * (1.0 + _SK["damage_scale"] * (level - 1)), 2),
        "speed":         _SK["speed"],
        "windup_time":   _SK["windup"],
        "exp_reward":    _SK["exp"] * level,
        "drop_id":       _SK["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
    }


def _spawn_spider_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Forest Spider near player_pos, only in swamp or forest biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _SP["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return
    dist       = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level      = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp     = round(_SP["hp"] * (1.0 + _SP["hp_scale_per_level"] * (level - 1)))
    mob_id     = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "spider",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         level,
        "damage":        round(_SP["damage"] * (1.0 + _SP["damage_scale"] * (level - 1)), 2),
        "speed":         _SP["speed"],
        "windup_time":   _SP["windup"],
        "exp_reward":    _SP["exp"] * level,
        "drop_id":       _SP["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
    }


def _spawn_scorpion_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Desert Scorpion near player_pos, only in desert biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _SC["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return
    dist       = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level      = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp     = round(_SC["hp"] * (1.0 + _SC["hp_scale_per_level"] * (level - 1)))
    mob_id     = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "scorpion",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         level,
        "damage":        round(_SC["damage"] * (1.0 + _SC["damage_scale"] * (level - 1)), 2),
        "speed":         _SC["speed"],
        "windup_time":   _SC["windup"],
        "exp_reward":    _SC["exp"] * level,
        "drop_id":       _SC["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
    }


def _spawn_bat_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Cave Bat near player_pos — any non-water biome (night-only, checked by caller)."""
    for _ in range(10):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if not _is_water(pos):
            tx, ty = int(pos[0]), int(pos[1])
            if (tx, ty) not in floor_positions:
                break
    else:
        return
    dist       = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level      = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp     = round(_B["hp"] * (1.0 + _B["hp_scale_per_level"] * (level - 1)))
    mob_id     = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":           "bat",
        "pos":            pos,
        "health":         mob_hp,
        "health_max":     mob_hp,
        "level":          level,
        "damage":         round(_B["damage"] * (1.0 + _B["damage_scale"] * (level - 1)), 2),
        "speed":          _B["speed"],
        "windup_time":    _B["windup"],
        "exp_reward":     _B["exp"] * level,
        "drop_id":        _B["drop_id"],
        "state":          "idle",
        "idle_timer":     random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":       list(pos),
        "origin_pos":     list(pos),
        "target_player":  None,
        "last_attack":    0.0,
        "facing":         "down",
        "aggro_range_sq": _B["aggro_range"] ** 2,
    }


def _spawn_yeti_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Snow Yeti near player_pos, only in tundra or mountain biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _Y["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return
    dist       = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    level      = max(1, min(MAX_SLIME_LEVEL, base_level + random.randint(-1, 1)))
    mob_hp     = round(_Y["hp"] * (1.0 + _Y["hp_scale_per_level"] * (level - 1)))
    mob_id     = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "yeti",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         level,
        "damage":        round(_Y["damage"] * (1.0 + _Y["damage_scale"] * (level - 1)), 2),
        "speed":         _Y["speed"],
        "windup_time":   _Y["windup"],
        "exp_reward":    _Y["exp"] * level,
        "drop_id":       _Y["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "last_slam":     0.0,
        "facing":        "down",
    }


def _spawn_rabbit_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Rabbit near player_pos — plains or beach biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _R["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return
    mob_hp = round(_R["hp"])
    mob_id = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "rabbit",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         1,
        "damage":        0.0,
        "speed":         _R["speed"],
        "windup_time":   0.0,
        "exp_reward":    _R["exp"],
        "drop_id":       _R["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
        "flee_range_sq": _R["flee_range"] ** 2,
    }


def _spawn_deer_near(player_pos, floor_positions: frozenset = frozenset()):
    """Spawn a Deer near player_pos — forest or plains biomes."""
    for _ in range(15):
        angle  = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos    = [player_pos[0] + math.cos(angle) * radius,
                  player_pos[1] + math.sin(angle) * radius]
        if _is_water(pos):
            continue
        if _biome_at(pos) not in _D["biome_ids"]:
            continue
        tx, ty = int(pos[0]), int(pos[1])
        if (tx, ty) not in floor_positions:
            break
    else:
        return
    mob_hp = round(_D["hp"])
    mob_id = str(uuid.uuid4())[:8]
    mobs[mob_id] = {
        "type":          "deer",
        "pos":           pos,
        "health":        mob_hp,
        "health_max":    mob_hp,
        "level":         1,
        "damage":        0.0,
        "speed":         _D["speed"],
        "windup_time":   0.0,
        "exp_reward":    _D["exp"],
        "drop_id":       _D["drop_id"],
        "state":         "idle",
        "idle_timer":    random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX),
        "home_pos":      list(pos),
        "origin_pos":    list(pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
        "flee_range_sq": _D["flee_range"] ** 2,
    }


def spawn_boss_at(pos: list) -> bool:
    """Spawn the Slime King at world position *pos* (the dungeon centre).

    Called by game_sync when a player enters a Slime Lair.
    Must be called while holding mobs_lock.
    Returns True if spawned, False if the boss is already active.
    """
    global _slime_king_active, _boss_dungeon_pos
    if _slime_king_active:
        return False
    mob_id = str(uuid.uuid4())[:8]
    spawn_pos = list(pos)
    mobs[mob_id] = {
        "type":          "slime_king",
        "pos":           spawn_pos,
        "health":        _BK["hp"],
        "health_max":    _BK["hp"],
        "level":         _BK["fixed_level"],
        "damage":        _BK["damage"],
        "speed":         _BK["speed"],
        "windup_time":   _BK["windup"],
        "exp_reward":    _BK["exp"],
        "drop_id":       _BK["drop_id"],
        "state":         "idle",
        "idle_timer":    _BK["spawn_idle"],
        "home_pos":      list(spawn_pos),
        "origin_pos":    list(spawn_pos),
        "target_player": None,
        "last_attack":   0.0,
        "facing":        "down",
    }
    _slime_king_active = True
    _boss_dungeon_pos  = list(spawn_pos)
    _pending_events.append({"type": "boss_spawned", "name": "Slime King",
                             "pos": list(spawn_pos)})
    print(f"[BOSS] Slime King awakened in dungeon at {spawn_pos}")


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
        global _next_spawn_time, _next_skeleton_spawn_time, _next_spider_spawn_time, _next_scorpion_spawn_time
        global _next_bat_spawn_time, _next_yeti_spawn_time, _next_rabbit_spawn_time, _next_deer_spawn_time
        _wt       = _get_world_time()
        _is_night = _wt < _DAY_START_HOUR or _wt > _DAY_END_HOUR
        # Single-pass type count (replaces 8 separate O(n) sum() calls)
        _tc: dict = {}
        for _m in mobs.values():
            _t = _m["type"]
            _tc[_t] = _tc.get(_t, 0) + 1
        slime_count    = _tc.get("slime",    0)
        skeleton_count = _tc.get("skeleton", 0)
        spider_count   = _tc.get("spider",   0)
        scorpion_count = _tc.get("scorpion", 0)
        bat_count      = _tc.get("bat",      0)
        yeti_count     = _tc.get("yeti",     0)
        rabbit_count   = _tc.get("rabbit",   0)
        deer_count     = _tc.get("deer",     0)
        # Build player list once; reused by every spawn eligibility check below
        _player_vals = list(player_snapshot.values()) if player_snapshot else []
        if _is_night and slime_count < MAX_SLIMES * max(1, len(player_snapshot)) and _player_vals and now >= _next_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_slime_near(ref_pos, _floor_positions)
            _next_spawn_time = now + SPAWN_INTERVAL
        if _is_night and skeleton_count < MAX_SKELETONS and _player_vals and now >= _next_skeleton_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_skeleton_near(ref_pos, _floor_positions)
            _next_skeleton_spawn_time = now + SKELETON_SPAWN_INTERVAL
        if _is_night and spider_count < MAX_SPIDERS and _player_vals and now >= _next_spider_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_spider_near(ref_pos, _floor_positions)
            _next_spider_spawn_time = now + SPIDER_SPAWN_INTERVAL
        if _is_night and scorpion_count < MAX_SCORPIONS and _player_vals and now >= _next_scorpion_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_scorpion_near(ref_pos, _floor_positions)
            _next_scorpion_spawn_time = now + SCORPION_SPAWN_INTERVAL
        # Bats — night only, any biome
        if _is_night and bat_count < MAX_BATS and _player_vals and now >= _next_bat_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_bat_near(ref_pos, _floor_positions)
            _next_bat_spawn_time = now + BAT_SPAWN_INTERVAL
        # Yetis — always (they live in cold biomes; day/night irrelevant for them)
        if yeti_count < MAX_YETIS and _player_vals and now >= _next_yeti_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_yeti_near(ref_pos, _floor_positions)
            _next_yeti_spawn_time = now + YETI_SPAWN_INTERVAL
        # Passive animals — always, daytime preferred (but we don't gate on day)
        if rabbit_count < MAX_RABBITS and _player_vals and now >= _next_rabbit_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_rabbit_near(ref_pos, _floor_positions)
            _next_rabbit_spawn_time = now + RABBIT_SPAWN_INTERVAL
        if deer_count < MAX_DEER and _player_vals and now >= _next_deer_spawn_time:
            ref_pos = random.choice(_player_vals)
            _spawn_deer_near(ref_pos, _floor_positions)
            _next_deer_spawn_time = now + DEER_SPAWN_INTERVAL
        # NOTE: Slime King boss is no longer spawned by a random timer here.
        # It spawns when a player enters a Slime Lair (see dungeon_gen + game_sync).

        # --- Update each mob ---
        for mob_id, mob in mobs.items():
            if mob["health"] <= 0:
                dead.append(mob_id)
                continue

            pos = mob["pos"]

            # --- Despawn hostile mobs when day breaks ---
            _NIGHT_ONLY = frozenset({"slime", "skeleton", "spider", "scorpion", "bat"})
            if not _is_night and mob.get("type") in _NIGHT_ONLY:
                dead.append(mob_id)
                pending_despawn.append(mob_id)
                continue

            # --- Despawn if too far from all players ---
            if player_snapshot:
                min_dsq = min(
                    (pos[0] - pp[0]) ** 2 + (pos[1] - pp[1]) ** 2
                    for pp in player_snapshot.values()
                )
                if min_dsq > DESPAWN_RADIUS_SQ:
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

            # --- Decay slow timer ---
            if mob.get("slow_timer", 0.0) > 0:
                mob["slow_timer"] = max(0.0, mob["slow_timer"] - dt)

            # --- Tick burn DoT ---
            if mob.get("burn_timer", 0.0) > 0:
                mob["burn_timer"] = max(0.0, mob["burn_timer"] - dt)
                mob["health"]     = max(0.0, mob.get("health", 0.0) - mob.get("burn_dps", _DEFAULT_BURN_DPS) * dt)
                mob["hit_flash"]  = max(mob.get("hit_flash", 0.0), 0.08)
                if mob["health"] <= 0 and not mob.get("killed_by"):
                    mob["killed_by"] = "_burn"

            # Snapshot position before state-based movement for water-tile blocking
            prev_x, prev_y = pos[0], pos[1]

            state = mob.get("state", "wander")

            # --- Stagger: briefly frozen after a player perfect-parry ---
            if mob.get("stagger_timer", 0.0) > 0:
                mob["stagger_timer"] = max(0.0, mob["stagger_timer"] - dt)
                continue  # skip all movement and attacks while staggered

            # --- Windup: stopped, telegraphing attack ---
            if state == "windup":
                mob["windup_timer"] = mob.get("windup_timer", _S["windup"]) - dt
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
                        if _dist(pos, player_snapshot[tpid]) < _S["lunge_hit_radius"]:
                            pending_melee.append((tpid, mob.get("damage", _S["damage"]), list(pos), mob_id))
                            mob["lunge_hit"] = True
                            # Type-specific on-hit effects
                            _mob_type = mob.get("type", "slime")
                            if _mob_type == "scorpion":
                                pending_poison[tpid] = (SCORPION_POISON_DURATION, SCORPION_POISON_DPS)
                            elif _mob_type == "spider":
                                pending_slow[tpid] = max(pending_slow.get(tpid, 0.0), SPIDER_WEB_SLOW)
                            elif _mob_type == "slime_king":
                                # Phase-based effects on direct hit
                                _hp_pct = mob.get("health", 0) / max(mob.get("health_max", 1), 1)
                                if _hp_pct < _BK["phase2_hp_pct"] and not mob.get("phase2_spawned_this_lunge"):
                                    # Phase 2+: spawn 2 mini-slimes near hit point
                                    _spos = list(pos)
                                    pending_spawns.append(
                                        lambda _pp=_spos: _spawn_slime_near(_pp, _floor_positions))
                                    pending_spawns.append(
                                        lambda _pp=_spos: _spawn_slime_near(_pp, _floor_positions))
                                    mob["phase2_spawned_this_lunge"] = True
                                if _hp_pct < _BK["phase3_hp_pct"]:
                                    # Phase 3: AOE splash to all nearby players
                                    for _apid, _appos in player_snapshot.items():
                                        if _apid != tpid and _dist(pos, _appos) < _BK["phase3_aoe_radius"]:
                                            pending_melee.append(
                                                (_apid,
                                                 mob.get("damage", _BK["damage"]) * 0.5,
                                                 list(pos),
                                                 None))
                if d < 0.2:  # reached endpoint
                    mob["state"]         = "landing"
                    mob["landing_timer"] = _S["landing_pause"]
                    mob["last_attack"]   = now
                else:
                    _lunge_spd = _B["lunge_speed"] if mob.get("type") == "bat" else _S["lunge_speed"]
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
                if mob.get("type") == "bat":
                    mob["state"] = "return_to_origin"
                    continue
                mob["landing_timer"] = mob.get("landing_timer", _S["landing_pause"]) - dt
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
                    mob["idle_timer"] = random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX)
                    pos[0] = origin[0]   # snap to exact spawn point
                    pos[1] = origin[1]
                    mob.pop("lunge_target", None)
                    mob.pop("lunge_hit",    None)
                    mob.pop("phase2_spawned_this_lunge", None)
                else:
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * _S["lunge_speed"] * dt
                    pos[1] += ny * _S["lunge_speed"] * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                continue

            # --- Yeti AOE slam charge (entered from aggro) ---
            if state == "slam_charge":
                mob["slam_timer"] = mob.get("slam_timer", YETI_SLAM_CHARGE) - dt
                if mob["slam_timer"] <= 0:
                    _slam_pos = list(pos)
                    for _apid, _appos in player_snapshot.items():
                        if _dist(_slam_pos, _appos) <= YETI_SLAM_RADIUS:
                            pending_melee.append((_apid, mob.get("damage", _Y["damage"]), _slam_pos, None))
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
                if not player_snapshot or closest_dist_sq > (ANIMAL_DEAGGRO_RANGE ** 2):
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
                if da > DEAGGRO_RANGE:
                    mob["state"]         = "wander"
                    mob["target_player"] = None
                    continue
                _mob_type_ag = mob.get("type", "slime")
                # Yeti uses AOE slam instead of regular lunge
                if _mob_type_ag == "yeti":
                    if da <= YETI_SLAM_RANGE and now - mob.get("last_slam", 0.0) >= YETI_SLAM_COOLDOWN:
                        mob["state"]      = "slam_charge"
                        mob["slam_timer"] = YETI_SLAM_CHARGE
                        continue
                elif da <= _S["attack_range"] and now - mob.get("last_attack", 0.0) >= _S["attack_cooldown"]:
                    # Inline windup using the tracked target
                    dx_, dy_ = tppos[0] - pos[0], tppos[1] - pos[1]
                    d_   = math.sqrt(dx_ * dx_ + dy_ * dy_) or 1.0
                    nx_, ny_ = dx_ / d_, dy_ / d_
                    mob["state"]         = "windup"
                    mob["windup_timer"]  = mob.get("windup_time", _S["windup"])
                    mob["origin_pos"]    = list(pos)
                    # Bats use a large overshoot for fly-through feel
                    if _mob_type_ag == "bat":
                        _overshoot = _B["lunge_overshoot"]
                    else:
                        _overshoot = _S["lunge_overshoot"] * (1.0 + 0.3 * (mob.get("level", 1) - 1))
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
                spd = mob.get("speed", _S["speed"]) * (0.4 if mob.get("slow_timer", 0.0) > 0 else 1.0)
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
                _is_passive = mob.get("type") in ("rabbit", "deer")
                if _is_passive:
                    _fl_sq = mob.get("flee_range_sq", _R["flee_range"] ** 2)
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
                    mob["idle_timer"] = random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX)
                else:
                    spd = mob.get("speed", _S["speed"]) * (0.4 if mob.get("slow_timer", 0.0) > 0 else 1.0)
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * spd * dt
                    pos[1] += ny * spd * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_tile_set):
                        pos[0], pos[1] = prev_x, prev_y
                        mob["state"]      = "idle"
                        mob["idle_timer"] = random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX)
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Idle: rest, then pick next wander target ---
            _is_passive_idle = mob.get("type") in ("rabbit", "deer")
            if _is_passive_idle:
                _fl_sq_idle = mob.get("flee_range_sq", _R["flee_range"] ** 2)
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
                    r     = random.uniform(WANDER_RADIUS * 0.3, WANDER_RADIUS)
                    tgt   = [origin[0] + math.cos(angle) * r,
                             origin[1] + math.sin(angle) * r]
                    if not _is_water(tgt):
                        mob["wander_target"] = tgt
                        mob["state"]         = "wander"
                        break
                mob["idle_timer"] = random.uniform(WANDER_IDLE_MIN, WANDER_IDLE_MAX)
            else:
                mob["idle_timer"] = idle_t

        # Execute deferred spawns (e.g., Slime King phase 2 mini-slimes)
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
                if d < SLIME_SLOW_RANGE and mob.get("type") in ("slime", "slime_king"):
                    if pid not in pending_slow or pending_slow[pid] < SLIME_SLOW_CONTACT:
                        pending_slow[pid] = SLIME_SLOW_CONTACT

        # --- Clamp all mob positions to world boundary ---
        for mob in mobs.values():
            p = mob["pos"]
            p[0] = max(-WORLD_RADIUS, min(WORLD_RADIUS, p[0]))
            p[1] = max(-WORLD_RADIUS, min(WORLD_RADIUS, p[1]))

        # --- Remove dead mobs and drop items ---
    global _slime_king_active, _boss_dungeon_pos
    despawn_set = set(pending_despawn)
    for mob_id in dead:
        drop_pos    = list(mobs[mob_id]["pos"])
        killed_by   = mobs[mob_id].get("killed_by")
        exp_reward  = mobs[mob_id].get("exp_reward", _S["exp"])
        mob_level   = mobs[mob_id].get("level", 1)
        mob_drop_id = mobs[mob_id].get("drop_id", _S["drop_id"])
        mob_type    = mobs[mob_id].get("type", "slime")
        del mobs[mob_id]
        if mob_id in despawn_set:
            continue  # silent despawn — no drops, no exp, no log
        if mob_type == "slime_king":
            _slime_king_active = False
            _pending_events.append({"type": "boss_defeated", "name": "Slime King",
                                    "dungeon_pos": list(_boss_dungeon_pos) if _boss_dungeon_pos else None})
            _boss_dungeon_pos = None
        if killed_by:
            pending_exp.append((killed_by, exp_reward))
            if mob_drop_id is not None:
                _spawn_world_item(mob_drop_id, drop_pos, qty=1)
            # Slime King also drops a random gem (items 50–56)
            if mob_type == "slime_king":
                gem_id = random.randint(_BK["gem_drop_range"][0], _BK["gem_drop_range"][1])
                _spawn_world_item(gem_id, [drop_pos[0] + 0.5, drop_pos[1] + 0.5], qty=1)
            _spawn_world_item(COIN_ITEM_ID, drop_pos, qty=random.randint(mob_level * _COIN_DROP_MIN_MULT, mob_level * _COIN_DROP_MAX_MULT))
            print(f"[MOB] {mob_type.title()} {mob_id} (Lv{mob_level}) died — dropped items at {drop_pos}")

    # Apply all per-tick player updates: regen, slow decay, combat events
    from server.shared_lock import players_lock
    with players_lock:
        # Per-player regen and slow decay
        for pdata in _players.values():
            sp_max  = pdata.get("stamina_max", 100.0)
            sp_rate = _BASE_SP_REGEN + pdata.get("sp_regen_bonus", 0.0)
            pdata["stamina"] = min(sp_max, pdata.get("stamina", sp_max) + sp_rate * dt)
            hp_regen = pdata.get("hp_regen", 0.0)
            if hp_regen > 0:
                equip_hp_bonus = int(_get_equip_bonuses(pdata.get("inventory", [])).get("health_max", 0))
                hp_max = pdata.get("health_max", 100) + equip_hp_bonus
                pdata["health"] = min(hp_max, pdata.get("health", 0.0) + hp_regen * dt)
            st = pdata.get("slow_timer", 0.0)
            if st > 0:
                pdata["slow_timer"] = max(0.0, st - dt)
        # Contact slow from proximity to mobs
        for pid, slow_dur in pending_slow.items():
            if pid in _players:
                _players[pid]["slow_timer"] = max(
                    _players[pid].get("slow_timer", 0.0), slow_dur
                )
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
            print(f"[MOB] Slime hit {pid} for {actual_dmg:.1f} dmg (def {defense:.0f}) "
                  f"(hp now {_players[pid]['health']:.1f})")
            # Drain 1 durability from each equipped armor piece on mob hit
            for eq_idx in range(36, 45):
                _drain_durability(_players[pid].get("inventory", []), eq_idx)
            # Knockback: push player away from the slime
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
            # Only apply slime-specific slow when the attacker is actually a slime
            if (attacker_mid is not None
                    and mobs.get(attacker_mid, {}).get("type") == "slime"):
                _players[pid]["slow_timer"] = max(
                    _players[pid].get("slow_timer", 0.0), SLIME_SLOW_HIT
                )
        # Apply scorpion poison (inline to avoid double-acquiring players_lock)
        for pid, (dur, dps) in pending_poison.items():
            if pid in _players and not _players[pid].get("creative", False):
                _players[pid]["poison_timer"] = max(_players[pid].get("poison_timer", 0.0), dur)
                _players[pid]["poison_dps"]   = dps
                print(f"[MOB] Scorpion poisoned {pid} for {dur}s at {dps} dps")
        for pid, exp_amount in pending_exp:
            _apply_exp(pid, exp_amount)

def drain_events() -> list:
    """Return and clear all pending mob events (boss_spawned, boss_defeated, etc.).
    Thread-safe — call from the server game-loop after update_mobs().
    """
    with mobs_lock:
        evts = list(_pending_events)
        _pending_events.clear()
    return evts

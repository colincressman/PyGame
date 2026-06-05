"""Mob configuration helpers and factory functions.

This module owns the data-driven parts of mob setup so the runtime tick loop in
mob_manager.py can stay focused on simulation and combat flow.
"""

import math
import random

from server.config import (
    LEVEL_DIST_SCALE,
    MAX_MOB_LEVEL,
    MOB_SPAWN_MIN_DIST as SPAWN_MIN_DIST,
    MOB_SPAWN_RADIUS as SPAWN_RADIUS,
)
from server.game_state.status_effect_data import STATUS_EFFECTS as _STATUS_EFFECTS
from server.mobs.mob_data import MOB_TYPES


DEFAULT_MOB_TYPE = next(
    (k for k, v in MOB_TYPES.items() if v.get("behavior") == "melee"),
    next(iter(MOB_TYPES), None),
)
DEFAULT_MOB = MOB_TYPES.get(DEFAULT_MOB_TYPE, {})
BOSS_MOB_TYPE = next((k for k, v in MOB_TYPES.items() if v.get("behavior") == "boss"), None)

DESPAWN_RADIUS = DEFAULT_MOB.get("despawn_radius", 50)
DESPAWN_RADIUS_SQ = DESPAWN_RADIUS ** 2
WANDER_RADIUS = DEFAULT_MOB.get("wander_radius", 6.25)
WANDER_IDLE_MIN = DEFAULT_MOB.get("wander_idle_min", 2.0)
WANDER_IDLE_MAX = DEFAULT_MOB.get("wander_idle_max", 5.0)
AGGRO_RANGE = DEFAULT_MOB.get("aggro_range", 3.0)
AGGRO_RANGE_SQ = AGGRO_RANGE ** 2
DEAGGRO_RANGE = DEFAULT_MOB.get("deaggro_range", 7.0)
ANIMAL_DEAGGRO_RANGE = DEFAULT_MOB.get("deaggro_range", 7.0)
MOB_SLOW_MULT = float(_STATUS_EFFECTS.get("slow", {}).get("mob_move_mult", 0.4))


def cfg_float(cfg, key, default=0.0):
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def mob_cfg(mob_or_type):
    mob_type = mob_or_type.get("type") if isinstance(mob_or_type, dict) else mob_or_type
    return MOB_TYPES.get(mob_type, DEFAULT_MOB)


def mob_special(mob_or_type):
    return mob_cfg(mob_or_type).get("special", {})


def mob_behavior(mob_or_type):
    return mob_cfg(mob_or_type).get("behavior", "melee")


def is_passive_mob(mob_or_type):
    return mob_behavior(mob_or_type) in ("passive", "flee", "animal")


def spawn_biome_allowed(pos, cfg, biome_at):
    biome_ids = cfg.get("biome_ids")
    if not biome_ids:
        return True
    return biome_at(pos) in biome_ids


def find_spawn_pos(player_pos, cfg, floor_positions, is_water, biome_at):
    attempts = int(cfg.get("spawn_attempts", cfg.get("spawn_attempts_near_player", 15)))
    avoid_water = cfg.get("spawn_avoid_water", True)
    avoid_floor = cfg.get("spawn_avoid_floor", True)

    for _ in range(attempts):
        angle = random.uniform(0, 2 * math.pi)
        radius = random.uniform(SPAWN_MIN_DIST, SPAWN_RADIUS)
        pos = [
            player_pos[0] + math.cos(angle) * radius,
            player_pos[1] + math.sin(angle) * radius,
        ]

        if avoid_water and is_water(pos):
            continue
        if not spawn_biome_allowed(pos, cfg, biome_at):
            continue
        if avoid_floor and (int(pos[0]), int(pos[1])) in floor_positions:
            continue
        return pos

    return None


def scaled_mob_level(player_pos, cfg):
    if cfg.get("fixed_level") is not None:
        return int(cfg["fixed_level"])
    if is_passive_mob(cfg):
        return 1
    dist = math.sqrt(player_pos[0] ** 2 + player_pos[1] ** 2)
    base_level = max(1, int(dist / LEVEL_DIST_SCALE))
    return max(1, min(MAX_MOB_LEVEL, base_level + random.randint(-1, 1)))


def build_spawned_mob(mob_type, pos, player_pos):
    cfg = mob_cfg(mob_type)
    level = scaled_mob_level(player_pos, cfg)
    passive = is_passive_mob(cfg)

    hp = round(cfg_float(cfg, "hp", 1.0) * (1.0 + cfg_float(cfg, "hp_scale_per_level", 0.0) * (level - 1)))
    damage = 0.0 if passive else round(
        cfg_float(cfg, "damage", 0.0) * (1.0 + cfg_float(cfg, "damage_scale", 0.0) * (level - 1)),
        2,
    )
    speed = cfg_float(cfg, "speed", 1.0) * (1.0 + cfg_float(cfg, "speed_scale", 0.0) * (level - 1))

    idle_min = cfg_float(cfg, "wander_idle_min", WANDER_IDLE_MIN)
    idle_max = cfg_float(cfg, "wander_idle_max", WANDER_IDLE_MAX)

    mob = {
        "type": mob_type,
        "behavior": cfg.get("behavior", "melee"),
        "pos": pos,
        "vel": [0.0, 0.0],
        "health": hp,
        "health_max": hp,
        "level": level,
        "damage": damage,
        "speed": speed,
        "windup_time": cfg_float(cfg, "windup", 0.0),
        "exp_reward": int(cfg.get("exp", 0)) * level,
        "drop_id": cfg.get("drop_id"),
        "state": "idle",
        "idle_timer": random.uniform(idle_min, idle_max),
        "home_pos": list(pos),
        "origin_pos": list(pos),
        "target_player": None,
        "last_attack": 0.0,
        "facing": "down",
        "aggro_range_sq": cfg_float(cfg, "aggro_range", AGGRO_RANGE) ** 2,
        "deaggro_range": cfg_float(cfg, "deaggro_range", DEAGGRO_RANGE),
        "despawn_radius_sq": cfg_float(cfg, "despawn_radius", DESPAWN_RADIUS) ** 2,
    }

    flee_range = cfg.get("flee_range")
    if flee_range is not None:
        mob["flee_range_sq"] = float(flee_range) ** 2

    if "slam_range" in cfg.get("special", {}):
        mob["last_slam"] = 0.0

    return mob


def build_boss_mob(pos):
    cfg = mob_cfg(BOSS_MOB_TYPE)
    return {
        "type": BOSS_MOB_TYPE,
        "behavior": cfg.get("behavior", "melee"),
        "pos": list(pos),
        "vel": [0.0, 0.0],
        "health": cfg["hp"],
        "health_max": cfg["hp"],
        "level": cfg.get("fixed_level", 1),
        "damage": cfg.get("damage", 0.0),
        "speed": cfg.get("speed", 0.0),
        "windup_time": cfg.get("windup", 0.0),
        "exp_reward": cfg.get("exp", 0),
        "drop_id": cfg.get("drop_id"),
        "state": "idle",
        "idle_timer": cfg.get("spawn_idle", 0.0),
        "home_pos": list(pos),
        "origin_pos": list(pos),
        "target_player": None,
        "last_attack": 0.0,
        "facing": "down",
        "aggro_range_sq": cfg.get("aggro_range", AGGRO_RANGE) ** 2,
        "deaggro_range": cfg.get("deaggro_range", DEAGGRO_RANGE),
        "despawn_radius_sq": cfg.get("despawn_radius", DESPAWN_RADIUS) ** 2,
    }

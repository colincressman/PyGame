"""Server-side projectile management for wand spells."""

import math
import random
import threading
import time
import uuid

from server.game_state.status_effects import apply_status_effect
from server.item_data import (
    drain_defensive_gear_durability,
    get_effective_health_max,
    get_equip_bonuses,
)
from server.network.projectile_data import PROJECTILE_ELEMENTS, PROJECTILE_GLOBALS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_PROJ_SPEED = float(PROJECTILE_GLOBALS.get("speed", 10.0))
_PROJ_MAX_RANGE = float(PROJECTILE_GLOBALS.get("max_range", 14.0))
_PROJ_HIT_RADIUS = float(PROJECTILE_GLOBALS.get("hit_radius", 0.75))
_PROJ_HIT_R_SQ = _PROJ_HIT_RADIUS ** 2
_WAND_COOLDOWN = float(PROJECTILE_GLOBALS.get("cooldown", 0.55))

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_projectiles: list[dict] = []
_proj_lock = threading.Lock()

_player_last_cast: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def _mark_inventory_dirty(player_id: str) -> None:
    from server.game_state.game_sync import mark_inventory_dirty
    mark_inventory_dirty(player_id)


def can_fire(player_id: str) -> bool:
    """Return True when the player's wand cooldown has expired."""
    with _cooldown_lock:
        return time.time() >= _player_last_cast.get(player_id, 0.0)


def fire_projectile(
    player_id: str,
    ox: float,
    oy: float,
    dx: float,
    dy: float,
    element: str,
    damage: float,
) -> bool:
    """Spawn a new projectile if the player is not on cooldown."""
    mag = math.sqrt(dx * dx + dy * dy)
    if mag < 0.001:
        return False

    with _cooldown_lock:
        now = time.time()
        if now < _player_last_cast.get(player_id, 0.0):
            return False
        _player_last_cast[player_id] = now + _WAND_COOLDOWN

    vx = dx / mag * _PROJ_SPEED
    vy = dy / mag * _PROJ_SPEED

    proj = {
        "uid": str(uuid.uuid4())[:8],
        "owner": player_id,
        "pos": [ox, oy],
        "vel": [vx, vy],
        "element": element if element in PROJECTILE_ELEMENTS else "arcane",
        "damage": float(damage),
        "traveled": 0.0,
    }
    with _proj_lock:
        _projectiles.append(proj)
    return True


def tick_projectiles(dt: float, players: dict, mobs: dict) -> None:
    """Advance all projectiles by *dt* seconds and resolve collisions."""
    from server.shared_lock import players_lock as _players_lock
    from server.mobs.mob_manager import mobs_lock as _mobs_lock

    dead_uids: set[str] = set()

    with _proj_lock:
        snapshot = list(_projectiles)

    for proj in snapshot:
        if proj["uid"] in dead_uids:
            continue
        step = _PROJ_SPEED * dt
        proj["pos"][0] += proj["vel"][0] * dt
        proj["pos"][1] += proj["vel"][1] * dt
        proj["traveled"] += step
        if proj["traveled"] >= _PROJ_MAX_RANGE:
            dead_uids.add(proj["uid"])

    for proj in snapshot:
        if proj["uid"] in dead_uids:
            continue
        px, py = proj["pos"]
        elem = proj["element"]
        edata = PROJECTILE_ELEMENTS.get(elem, PROJECTILE_ELEMENTS.get("arcane", {}))

        with _players_lock:
            hit_player_id: str | None = None
            hit_player: dict | None = None

            for pid, pdata in players.items():
                if pid == proj["owner"]:
                    continue
                if pdata.get("health", 0) <= 0:
                    continue
                if pdata.get("creative", False) or pdata.get("invulnerable", False):
                    continue
                ppos = pdata.get("pos", [0.0, 0.0])
                tx = float(ppos[0]) + 0.5
                ty = float(ppos[1]) + 0.5
                if (tx - px) ** 2 + (ty - py) ** 2 < _PROJ_HIT_R_SQ:
                    hit_player_id = pid
                    hit_player = pdata
                    break

            if hit_player is not None:
                dead_uids.add(proj["uid"])
                dmg = proj["damage"] * edata.get("damage_mult", 1.0)

                if elem == "shadow" and random.random() < edata.get("crit_chance", 0.0):
                    dmg *= edata.get("crit_mult", 2.0)

                defense = get_equip_bonuses(hit_player.get("inventory", []))["defense"]
                damage_taken = max(1.0, dmg - defense)

                if hit_player.get("blocking", False):
                    _block_age = time.time() - hit_player.get("block_start", 0.0)
                    if _block_age < 0.15:
                        continue
                    damage_taken = max(0.0, damage_taken * 0.4)

                if damage_taken <= 0.0:
                    continue

                hit_player["health"] = max(0.0, hit_player.get("health", 100.0) - damage_taken)
                drain_defensive_gear_durability(hit_player.get("inventory", []))
                _mark_inventory_dirty(hit_player_id)

                if elem == "fire":
                    apply_status_effect(
                        hit_player,
                        "burn",
                        duration=edata.get("status_duration"),
                        potency=edata.get("status_dps"),
                    )
                elif elem == "ice":
                    apply_status_effect(
                        hit_player,
                        "slow",
                        duration=edata.get("status_duration"),
                    )
                elif elem == "nature":
                    heal_amt = damage_taken * float(edata.get("lifesteal", 0.5))
                    owner = players.get(proj["owner"])
                    if owner:
                        owner["health"] = min(
                            owner.get("health", 0.0) + heal_amt,
                            get_effective_health_max(owner),
                        )
                elif elem == "poison":
                    apply_status_effect(
                        hit_player,
                        "poison",
                        duration=edata.get("status_duration"),
                        potency=edata.get("status_dps", 3.0),
                    )
                continue

        with _mobs_lock:
            hit_mob_id: str | None = None
            hit_mob: dict | None = None

            for mid, mob in list(mobs.items()):
                if mob.get("health", 0) <= 0:
                    continue
                mx, my = mob["pos"]
                if (mx - px) ** 2 + (my - py) ** 2 < _PROJ_HIT_R_SQ:
                    hit_mob_id = mid
                    hit_mob = mob
                    break

            if hit_mob is None:
                continue

            dead_uids.add(proj["uid"])
            dmg = proj["damage"] * edata.get("damage_mult", 1.0)

            if elem == "shadow" and random.random() < edata.get("crit_chance", 0.0):
                dmg *= edata.get("crit_mult", 2.0)

            hit_mob["health"] = max(0.0, hit_mob.get("health", 100.0) - dmg)
            hit_mob["hit_flash"] = 0.2
            if hit_mob["health"] <= 0 and not hit_mob.get("killed_by"):
                hit_mob["killed_by"] = proj["owner"]

            if elem == "fire":
                apply_status_effect(
                    hit_mob,
                    "burn",
                    duration=edata.get("status_duration"),
                    potency=edata.get("status_dps"),
                )
            elif elem == "ice":
                apply_status_effect(
                    hit_mob,
                    "slow",
                    duration=edata.get("status_duration"),
                )
            elif elem == "lightning":
                chain_r_sq = float(edata.get("chain_radius", 3.5)) ** 2
                chain_count = int(edata.get("chain_count", 2))
                chain_dmg = dmg * float(edata.get("chain_damage_mult", 0.6))
                chained = 0
                for mid2, mob2 in mobs.items():
                    if chained >= chain_count:
                        break
                    if mid2 == hit_mob_id or mob2.get("health", 0) <= 0:
                        continue
                    m2x, m2y = mob2["pos"]
                    hmx, hmy = hit_mob["pos"]
                    if (m2x - hmx) ** 2 + (m2y - hmy) ** 2 < chain_r_sq:
                        mob2["health"] = max(0.0, mob2.get("health", 100.0) - chain_dmg)
                        if mob2["health"] <= 0 and not mob2.get("killed_by"):
                            mob2["killed_by"] = proj["owner"]
                        chained += 1
            elif elem == "nature":
                heal_amt = dmg * float(edata.get("lifesteal", 0.5))
                with _players_lock:
                    owner = players.get(proj["owner"])
                    if owner:
                        owner["health"] = min(
                            owner.get("health", 0.0) + heal_amt,
                            get_effective_health_max(owner),
                        )

    if dead_uids:
        with _proj_lock:
            _projectiles[:] = [p for p in _projectiles if p["uid"] not in dead_uids]


def get_snapshot() -> list[dict]:
    """Return a minimal, thread-safe snapshot for the state packet."""
    with _proj_lock:
        return [
            {"uid": p["uid"], "pos": list(p["pos"]), "element": p["element"]}
            for p in _projectiles
        ]

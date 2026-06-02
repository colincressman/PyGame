# server/network/projectiles.py
"""Server-side projectile management for wand spells.

Projectiles are spawned by fire_projectile(), ticked by tick_projectiles(dt),
and exposed as a lightweight snapshot via get_snapshot() for inclusion in the
game-state packet sent to every client each frame.

Element effects applied on mob hit:
  arcane   — pure damage (no secondary effect)
  ice      — slow target for 2 s
  fire     — burn DoT for 5 s at 8 dps
  lightning — hit primary target, then chain to 2 nearby mobs (60 % damage)
  nature   — lifesteal: heal owner for 50 % of damage dealt
  shadow   — 35 % crit chance (× 2.5 damage)
"""

import math
import time
import random
import threading
import uuid

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_PROJ_SPEED      = 10.0   # tiles / second
_PROJ_MAX_RANGE  = 14.0   # tiles — projectile vanishes beyond this
_PROJ_HIT_RADIUS = 0.75   # tiles — distance to count as a mob hit
_PROJ_HIT_R_SQ   = _PROJ_HIT_RADIUS ** 2

_WAND_COOLDOWN   = 0.55   # seconds between casts per player

# Per-element tuning
_ELEMENT_DATA: dict[str, dict] = {
    "arcane":    {"damage_mult": 1.0},
    "ice":       {"damage_mult": 0.8,  "slow_duration":  2.0},
    "fire":      {"damage_mult": 0.9,  "burn_duration":  5.0, "burn_dps": 8.0},
    "lightning": {"damage_mult": 1.2,  "chain_radius":   3.5, "chain_count": 2,
                  "chain_damage_mult": 0.6},
    "nature":    {"damage_mult": 0.7,  "lifesteal": 0.50},
    "shadow":    {"damage_mult": 1.1,  "crit_chance": 0.35,   "crit_mult": 2.5},
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_projectiles: list[dict] = []
_proj_lock = threading.Lock()

# Per-player cast cooldown timestamps
_player_last_cast: dict[str, float] = {}
_cooldown_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can_fire(player_id: str) -> bool:
    """Return True when the player's wand cooldown has expired."""
    with _cooldown_lock:
        return time.time() >= _player_last_cast.get(player_id, 0.0)


def fire_projectile(player_id: str, ox: float, oy: float,
                    dx: float, dy: float,
                    element: str, damage: float) -> None:
    """Spawn a new projectile if the player is not on cooldown.

    Parameters
    ----------
    player_id : str
    ox, oy    : float  — origin in tile coords (player centre)
    dx, dy    : float  — direction vector (need not be normalised)
    element   : str    — one of the keys in _ELEMENT_DATA
    damage    : float  — base damage (from the wand's attack_power)
    """
    mag = math.sqrt(dx * dx + dy * dy)
    if mag < 0.001:
        return

    with _cooldown_lock:
        now = time.time()
        if now < _player_last_cast.get(player_id, 0.0):
            return
        _player_last_cast[player_id] = now + _WAND_COOLDOWN

    vx = dx / mag * _PROJ_SPEED
    vy = dy / mag * _PROJ_SPEED

    proj = {
        "uid":      str(uuid.uuid4())[:8],
        "owner":    player_id,
        "pos":      [ox, oy],
        "vel":      [vx, vy],
        "element":  element if element in _ELEMENT_DATA else "arcane",
        "damage":   float(damage),
        "traveled": 0.0,
    }
    with _proj_lock:
        _projectiles.append(proj)


def tick_projectiles(dt: float, players: dict, mobs: dict) -> None:
    """Advance all projectiles by *dt* seconds and resolve collisions.

    Must be called from the single game-loop thread.  The function acquires
    mobs_lock and players_lock internally only when a hit is confirmed.
    """
    from server.shared_lock import players_lock as _players_lock
    from server.mobs.mob_manager import mobs_lock as _mobs_lock

    dead_uids: set[str] = set()

    # --- movement pass (no locks needed — only game-loop thread writes pos) ---
    snapshot: list[dict] = []
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

    # --- collision pass ---
    for proj in snapshot:
        if proj["uid"] in dead_uids:
            continue
        px, py = proj["pos"]
        elem   = proj["element"]
        edata  = _ELEMENT_DATA.get(elem, {})

        with _mobs_lock:
            hit_mob_id: str | None = None
            hit_mob: dict | None = None

            for mid, mob in list(mobs.items()):
                if mob.get("hp", 0) <= 0:
                    continue
                mx, my = mob["pos"]
                if (mx - px) ** 2 + (my - py) ** 2 < _PROJ_HIT_R_SQ:
                    hit_mob_id = mid
                    hit_mob    = mob
                    break

            if hit_mob is not None:
                dead_uids.add(proj["uid"])

                dmg = proj["damage"] * edata.get("damage_mult", 1.0)

                # Shadow: crit chance
                if elem == "shadow" and random.random() < edata.get("crit_chance", 0.0):
                    dmg *= edata.get("crit_mult", 2.0)

                hit_mob["health"] = max(0.0, hit_mob.get("health", 100.0) - dmg)
                hit_mob["hit_flash"] = 0.2
                if hit_mob["health"] <= 0 and not hit_mob.get("killed_by"):
                    hit_mob["killed_by"] = proj["owner"]

                # Element on-hit effects
                if elem == "fire":
                    hit_mob["burn_timer"] = max(hit_mob.get("burn_timer", 0.0),
                                                edata["burn_duration"])
                    hit_mob["burn_dps"]   = edata["burn_dps"]
                elif elem == "ice":
                    hit_mob["slow_timer"] = max(hit_mob.get("slow_timer", 0.0),
                                                edata["slow_duration"])
                elif elem == "lightning":
                    # Chain to nearby mobs
                    chain_r_sq  = edata.get("chain_radius", 3.5) ** 2
                    chain_count = edata.get("chain_count", 2)
                    chain_dmg   = dmg * edata.get("chain_damage_mult", 0.6)
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
                    # Lifesteal — heal the caster
                    heal_amt = dmg * edata.get("lifesteal", 0.5)
                    with _players_lock:
                        owner = players.get(proj["owner"])
                        if owner:
                            owner["health"] = min(
                                owner.get("health", 0.0) + heal_amt,
                                owner.get("health_max", 100.0)
                            )

    # --- cleanup ---
    if dead_uids:
        with _proj_lock:
            _projectiles[:] = [p for p in _projectiles if p["uid"] not in dead_uids]


def get_snapshot() -> list[dict]:
    """Return a minimal, thread-safe snapshot for the state packet.

    Each entry: {"uid": str, "pos": [x, y], "element": str}
    """
    with _proj_lock:
        return [
            {"uid": p["uid"], "pos": list(p["pos"]), "element": p["element"]}
            for p in _projectiles
        ]

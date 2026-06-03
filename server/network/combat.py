# server/network/combat.py
import math
import random
import time
from server.game_state.gem_data import get_gem_effect
from server.game_state.status_effects import apply_status_effect
from server.shared_lock import players_lock
from server.item_data import get_equip_bonuses, get_hotbar_bonus, get_effective_health_max, drain_durability
from server.config import KNOCKBACK_DECAY as _KB_DECAY


def _has_wall_between(ax: float, ay: float, tx: float, ty: float) -> bool:
    """Return True if a closed solid placed object blocks the line (ax,ay)→(tx,ty).

    Uses DDA sampling at 0.25-tile resolution.  Called while a combat lock is
    held; reads placed_objects WITHOUT placed_objects_lock — GIL makes individual
    dict lookups safe and a slightly stale view is fine for melee LOS.
    """
    try:
        from server.game_state.placed_objects import (
            _tile_index as _ti, placed_objects as _po, SOLID_TYPES as _ST,
        )
    except ImportError:
        return False

    dx = tx - ax
    dy = ty - ay
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 0.01:
        return False

    # One probe every 0.25 tiles; skip exact endpoints (t=0 and t=1)
    steps = max(4, int(dist / 0.25) + 1)
    for i in range(1, steps):
        t = i / steps
        cell = (int(math.floor(ax + dx * t)), int(math.floor(ay + dy * t)))
        uid = _ti.get(cell)
        if uid is None:
            continue
        obj = _po.get(uid)
        if obj is None:
            continue
        otype = obj.get("type", "")
        if otype not in _ST:
            continue
        if otype == "door" and obj.get("state", "closed") == "open":
            continue
        return True
    return False

# Attack constants (positions are in tile coords; 1 tile = 32 px)
ATK_RANGE         = 2.0    # tiles  (64 px)
_ATK_RANGE_SQ     = ATK_RANGE * ATK_RANGE  # avoids sqrt for out-of-range rejections
_ATK_POS_TOLERANCE = 1.5   # tiles — allows minor client/server desync during swings
_ATK_POS_TOLERANCE_SQ = _ATK_POS_TOLERANCE * _ATK_POS_TOLERANCE
KNOCKBACK         = 0.5    # tiles — player-on-player
MOB_KNOCKBACK     = 1.5    # tiles — player-on-mob (more satisfying)
ATK_GAIN          = 0.001  # attack_power increase per successful hit
MAX_ATK_POWER     = 500.0  # hard cap — prevents unbounded growth
ATK_COOLDOWN      = 0.45   # server-side minimum seconds between accepted melee swings
_last_attack_times: dict[str, float] = {}

_DIR_VEC = {
    "down":  ( 0,  1),
    "up":    ( 0, -1),
    "left":  (-1,  0),
    "right": ( 1,  0),
}
_COS45 = math.cos(math.radians(45))   # 90° cone half-angle threshold


def handle_attack(attacker_id: str, direction: str, pos: list, players: dict, mobs: dict | None = None):
    """Apply damage + knockback to all targets in the attack cone.

    Parameters
    ----------
    attacker_id : str
        Player performing the attack.
    direction : str
        One of 'down', 'up', 'left', 'right'.
    pos : list
        Attacker position [x, y] in tile coords.
    players : dict
        Shared players dict (held under players_lock by caller).
    mobs : dict | None
        Shared mobs dict (optional; used in Phase 7).
    """
    if direction not in _DIR_VEC:
        return

    vx, vy = _DIR_VEC[direction]
    now = time.monotonic()

    with players_lock:
        attacker = players.get(attacker_id)
        if not attacker:
            return
        last_attack = _last_attack_times.get(attacker_id, 0.0)
        if now - last_attack < ATK_COOLDOWN:
            return
        _last_attack_times[attacker_id] = now
        attacker_pos = attacker.get("pos", [0.0, 0.0])
        if not isinstance(pos, list) or len(pos) != 2:
            pos = attacker_pos
        else:
            dx = float(pos[0]) - float(attacker_pos[0])
            dy = float(pos[1]) - float(attacker_pos[1])
            if dx * dx + dy * dy > _ATK_POS_TOLERANCE_SQ:
                return
            pos = attacker_pos
        atk_power = (float(attacker.get("attack_power", 10.0))
                     + get_equip_bonuses(attacker.get("inventory", []))["attack_power"]
                     + get_hotbar_bonus(attacker.get("inventory", []),
                                        attacker.get("hotbar_slot", 0))["attack_power"])
        # --- Gem trait: read from equipped weapon meta ---
        _weapon_idx = 27 + attacker.get("hotbar_slot", 0)
        _inv        = attacker.get("inventory", [])
        _weapon     = _inv[_weapon_idx] if _weapon_idx < len(_inv) else None
        _gem_trait  = (_weapon[2].get("gem_trait")
                       if (_weapon and len(_weapon) >= 3 and isinstance(_weapon[2], dict))
                       else None)
        _gem_effect = get_gem_effect(_gem_trait)
        # Shadow gem: 15% crit chance (double damage)
        if _gem_effect == "crit" and random.random() < 0.15:
            atk_power *= 2.0
        # Drain stamina on every swing (skip if already depleted)
        _ATK_SP_COST = 12.0
        if attacker.get("stamina", 100.0) > 0:
            attacker["stamina"] = max(0.0, attacker.get("stamina", 100.0) - _ATK_SP_COST)
        hit_any   = False

        for pid, pdata in players.items():
            if pid == attacker_id:
                continue
            tx = pdata["pos"][0] - pos[0]
            ty = pdata["pos"][1] - pos[1]
            dist_sq = tx * tx + ty * ty
            if dist_sq > _ATK_RANGE_SQ:
                continue
            dist = math.sqrt(dist_sq)
            # 90° cone check via dot product
            if dist > 0 and (tx / dist) * vx + (ty / dist) * vy < _COS45:
                continue
            # Wall line-of-sight check
            if _has_wall_between(pos[0], pos[1], pdata["pos"][0], pdata["pos"][1]):
                continue
            # Apply damage (reduced by target's defense); skip if target is in creative mode or rolling
            if pdata.get("creative", False):
                continue
            if pdata.get("invulnerable", False):
                continue
            defense = get_equip_bonuses(pdata.get("inventory", []))["defense"]
            damage_taken = max(1.0, atk_power - defense)
            # Block / Parry check
            if pdata.get("blocking", False):
                import time as _time
                _block_age = _time.time() - pdata.get("block_start", 0.0)
                if _block_age < 0.15:
                    continue  # perfect parry — negate all damage
                damage_taken = max(0.0, damage_taken * 0.4)
            if damage_taken <= 0.0:
                continue
            pdata["health"] = max(0.0, pdata["health"] - damage_taken)
            # Drain 1 durability from each equipped armor piece
            for eq_idx in range(36, 45):
                drain_durability(pdata.get("inventory", []), eq_idx)
            # Apply knockback
            if dist > 0:
                pdata["pos"][0] += (tx / dist) * KNOCKBACK
                pdata["pos"][1] += (ty / dist) * KNOCKBACK
            # Gem on-hit effects (player targets)
            if _gem_effect == "burn" and random.random() < 0.20:
                apply_status_effect(pdata, "burn", duration=3.0, potency=5.0)
            elif _gem_effect == "slow":
                apply_status_effect(pdata, "slow", duration=1.5)
            elif _gem_effect == "lifesteal":
                attacker["health"] = min(
                    attacker.get("health", 0.0) + damage_taken * 0.05,
                    get_effective_health_max(attacker))
            elif _gem_effect == "poison" and random.random() < 0.25:
                apply_status_effect(pdata, "poison", duration=4.0, potency=3.0)
            hit_any = True
            print(f"[COMBAT] {attacker_id} hit {pid} for {atk_power:.1f} dmg "
                  f"(hp now {pdata['health']:.1f})")

        if hit_any:
            attacker["attack_power"] = min(atk_power + ATK_GAIN, MAX_ATK_POWER)
            # Drain 1 durability from the equipped weapon (active hotbar slot)
            weapon_idx = 27 + attacker.get("hotbar_slot", 0)
            drain_durability(attacker.get("inventory", []), weapon_idx)

        # Mob targets — separate lock to avoid AB/BA deadlock with mob_manager
    if mobs is not None:
        from server.mobs.mob_manager import mobs_lock
        with mobs_lock:
            # Grab attacker's gem_trait for mob hits (outside players_lock, re-read safely)
            with players_lock:
                _atk_data = players.get(attacker_id, {})
                _widx = 27 + _atk_data.get("hotbar_slot", 0)
                _ainv = _atk_data.get("inventory", [])
                _awpn = _ainv[_widx] if _widx < len(_ainv) else None
                _mob_gem = (_awpn[2].get("gem_trait")
                            if (_awpn and len(_awpn) >= 3 and isinstance(_awpn[2], dict))
                            else None)
                _mob_gem_effect = get_gem_effect(_mob_gem)
                _mob_atk = (float(_atk_data.get("attack_power", 10.0))
                            + get_equip_bonuses(_atk_data.get("inventory", []))["attack_power"]
                            + get_hotbar_bonus(_atk_data.get("inventory", []),
                                               _atk_data.get("hotbar_slot", 0))["attack_power"])
                if _mob_gem_effect == "crit" and random.random() < 0.15:
                    _mob_atk *= 2.0
            _mob_hit_any = False
            for mid, mob in list(mobs.items()):
                tx = mob["pos"][0] - pos[0]
                ty = mob["pos"][1] - pos[1]
                dist_sq = tx * tx + ty * ty
                if dist_sq > _ATK_RANGE_SQ:
                    continue
                dist = math.sqrt(dist_sq)
                if dist > 0 and (tx / dist) * vx + (ty / dist) * vy < _COS45:
                    continue
                # Wall line-of-sight check
                if _has_wall_between(pos[0], pos[1], mob["pos"][0], mob["pos"][1]):
                    continue
                mob["health"] = max(0.0, mob.get("health", 100.0) - _mob_atk)
                mob["hit_flash"] = 0.2
                if mob["health"] <= 0 and not mob.get("killed_by"):
                    mob["killed_by"] = attacker_id   # consumed by mob_manager for EXP award
                _mob_hit_any = True
                if dist > 0:
                    mob["knockback_vel"] = [(tx / dist) * MOB_KNOCKBACK * _KB_DECAY,
                                            (ty / dist) * MOB_KNOCKBACK * _KB_DECAY]
                    # Interrupt windup/lunge so the mob staggers on hit
                    if mob.get("state") in ("windup", "lunge"):
                        mob["state"] = "return_to_origin"
                        if not mob.get("origin_pos"):
                            mob["origin_pos"] = list(mob["pos"])
                # Gem on-hit effects (mob targets)
                if _mob_gem_effect == "burn" and random.random() < 0.20:
                    apply_status_effect(mob, "burn", duration=3.0, potency=5.0)
                elif _mob_gem_effect == "slow":
                    apply_status_effect(mob, "slow", duration=1.5)
                elif _mob_gem_effect == "lifesteal":
                    with players_lock:
                        _lp = players.get(attacker_id)
                        if _lp:
                            _lp["health"] = min(
                                _lp.get("health", 0.0) + _mob_atk * 0.05,
                                get_effective_health_max(_lp))
                elif _mob_gem_effect == "poison" and random.random() < 0.25:
                    apply_status_effect(mob, "poison", duration=4.0, potency=3.0)
                print(f"[COMBAT] {attacker_id} hit mob {mid} for {_mob_atk:.1f} dmg "
                      f"(hp now {mob['health']:.1f})"
                      + (f" [{_mob_gem}]" if _mob_gem else ""))
            # Drain weapon durability once per swing that connects with a mob
            if _mob_hit_any:
                with players_lock:
                    _wp = players.get(attacker_id)
                    if _wp:
                        _wi = 27 + _wp.get("hotbar_slot", 0)
                        drain_durability(_wp.get("inventory", []), _wi)

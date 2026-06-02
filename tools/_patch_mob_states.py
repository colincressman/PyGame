"""Patch script: replace lunge/landing/return states in mob_manager.py"""
import sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with open('server/mobs/mob_manager.py', encoding='utf-8') as f:
    content = f.read()

# ── Patch 1: lunge / landing / return / new states (slam_charge, flee) ──────
OLD1 = '''            # --- Lunge: charge at LUNGE_SPEED toward lunge_target ---
            if state == "lunge":
                tp = mob.get("lunge_target", pos)
                ddx, ddy = tp[0] - pos[0], tp[1] - pos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                # Per-tick hit check \u2014 if player is in the slime\u2019s path, they get hit
                if not mob.get("lunge_hit", False):
                    tpid = mob.get("target_player")
                    if tpid and tpid in player_snapshot:
                        if _dist(pos, player_snapshot[tpid]) < LUNGE_HIT_RADIUS:
                            pending_melee.append((tpid, mob.get("damage", MELEE_DAMAGE), list(pos)))
                            mob["lunge_hit"] = True
                            # Type-specific on-hit effects
                            _mob_type = mob.get("type", "slime")
                            if _mob_type == "scorpion":
                                pending_poison[tpid] = (SCORPION_POISON_DURATION, SCORPION_POISON_DPS)
                            elif _mob_type == "spider":
                                pending_slow[tpid] = max(pending_slow.get(tpid, 0.0), SPIDER_WEB_SLOW)
                if d < 0.2:  # reached endpoint
                    mob["state"]        = "landing"
                    mob["landing_timer"] = LANDING_PAUSE
                    mob["last_attack"]  = now
                else:
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * LUNGE_SPEED * dt
                    pos[1] += ny * LUNGE_SPEED * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_centers):
                        pos[0], pos[1] = prev_x, prev_y
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Landing: brief pause at endpoint (punish window) ---
            if state == "landing":
                mob["landing_timer"] = mob.get("landing_timer", LANDING_PAUSE) - dt
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
                else:
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * LUNGE_SPEED * dt
                    pos[1] += ny * LUNGE_SPEED * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_centers):
                        pos[0], pos[1] = prev_x, prev_y
                continue'''

NEW1 = '''            # --- Lunge: charge toward lunge_target ---
            if state == "lunge":
                tp = mob.get("lunge_target", pos)
                ddx, ddy = tp[0] - pos[0], tp[1] - pos[1]
                d = math.sqrt(ddx * ddx + ddy * ddy)
                # Per-tick hit check \u2014 if player is in the mob\u2019s path, they get hit
                if not mob.get("lunge_hit", False):
                    tpid = mob.get("target_player")
                    if tpid and tpid in player_snapshot:
                        if _dist(pos, player_snapshot[tpid]) < LUNGE_HIT_RADIUS:
                            pending_melee.append((tpid, mob.get("damage", MELEE_DAMAGE), list(pos)))
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
                                if _hp_pct < 0.66 and not mob.get("phase2_spawned_this_lunge"):
                                    # Phase 2+: spawn 2 mini-slimes near hit point
                                    _spos = list(pos)
                                    pending_spawns.append(
                                        lambda _pp=_spos: _spawn_slime_near(_pp, _floor_positions))
                                    pending_spawns.append(
                                        lambda _pp=_spos: _spawn_slime_near(_pp, _floor_positions))
                                    mob["phase2_spawned_this_lunge"] = True
                                if _hp_pct < 0.33:
                                    # Phase 3: AOE splash to all nearby players
                                    for _apid, _appos in player_snapshot.items():
                                        if _apid != tpid and _dist(pos, _appos) < 3.0:
                                            pending_melee.append(
                                                (_apid,
                                                 mob.get("damage", SLIME_KING_DAMAGE) * 0.5,
                                                 list(pos)))
                if d < 0.2:  # reached endpoint
                    mob["state"]         = "landing"
                    mob["landing_timer"] = LANDING_PAUSE
                    mob["last_attack"]   = now
                else:
                    _lunge_spd = BAT_LUNGE_SPEED if mob.get("type") == "bat" else LUNGE_SPEED
                    nx, ny = ddx / d, ddy / d
                    pos[0] += nx * _lunge_spd * dt
                    pos[1] += ny * _lunge_spd * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_centers):
                        pos[0], pos[1] = prev_x, prev_y
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue

            # --- Landing: brief pause at endpoint (punish window) ---
            if state == "landing":
                # Bats fly straight through \u2014 no landing pause
                if mob.get("type") == "bat":
                    mob["state"] = "return_to_origin"
                    continue
                mob["landing_timer"] = mob.get("landing_timer", LANDING_PAUSE) - dt
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
                    pos[0] += nx * LUNGE_SPEED * dt
                    pos[1] += ny * LUNGE_SPEED * dt
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_centers):
                        pos[0], pos[1] = prev_x, prev_y
                continue

            # --- Yeti AOE slam charge (entered from aggro) ---
            if state == "slam_charge":
                mob["slam_timer"] = mob.get("slam_timer", YETI_SLAM_CHARGE) - dt
                if mob["slam_timer"] <= 0:
                    _slam_pos = list(pos)
                    for _apid, _appos in player_snapshot.items():
                        if _dist(_slam_pos, _appos) <= YETI_SLAM_RADIUS:
                            pending_melee.append((_apid, mob.get("damage", YETI_DAMAGE), _slam_pos))
                    mob["last_slam"] = now
                    mob["state"]     = "idle"
                    mob["idle_timer"] = random.uniform(1.5, 3.0)
                continue

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
                    if _is_water(pos) or _is_obj_blocked(pos[0], pos[1], _solid_centers):
                        pos[0], pos[1] = prev_x, prev_y
                        mob["state"] = "wander"
                    else:
                        mob["facing"] = ("right" if nx > abs(ny) else
                                         "left"  if -nx > abs(ny) else
                                         "down"  if ny > 0 else "up")
                continue'''

if OLD1 in content:
    content = content.replace(OLD1, NEW1, 1)
    print('Patch 1 OK')
else:
    print('Patch 1 FAIL')
    sys.exit(1)

# ── Patch 2: aggro state — add yeti slam + bat overshoot + per-mob aggro range ──
OLD2 = '''            # --- Aggro: actively chase the target player ---
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
                if da <= ATTACK_RANGE and now - mob.get("last_attack", 0.0) >= ATTACK_COOLDOWN:
                    # Inline windup using the tracked target
                    dx_, dy_ = tppos[0] - pos[0], tppos[1] - pos[1]
                    d_   = math.sqrt(dx_ * dx_ + dy_ * dy_) or 1.0
                    nx_, ny_ = dx_ / d_, dy_ / d_
                    mob["state"]         = "windup"
                    mob["windup_timer"]  = mob.get("windup_time", WINDUP_TIME)
                    mob["origin_pos"]    = list(pos)
                    _overshoot = LUNGE_OVERSHOOT * (1.0 + 0.3 * (mob.get("level", 1) - 1))
                    mob["lunge_target"]  = [
                        pos[0] + nx_ * (d_ + _overshoot),
                        pos[1] + ny_ * (d_ + _overshoot),
                    ]
                    mob["facing"] = ("right" if nx_ > abs(ny_) else
                                     "left"  if -nx_ > abs(ny_) else
                                     "down"  if ny_ > 0 else "up")
                    continue'''

NEW2 = '''            # --- Aggro: actively chase the target player ---
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
                elif da <= ATTACK_RANGE and now - mob.get("last_attack", 0.0) >= ATTACK_COOLDOWN:
                    # Inline windup using the tracked target
                    dx_, dy_ = tppos[0] - pos[0], tppos[1] - pos[1]
                    d_   = math.sqrt(dx_ * dx_ + dy_ * dy_) or 1.0
                    nx_, ny_ = dx_ / d_, dy_ / d_
                    mob["state"]         = "windup"
                    mob["windup_timer"]  = mob.get("windup_time", WINDUP_TIME)
                    mob["origin_pos"]    = list(pos)
                    # Bats use a large overshoot for fly-through feel
                    if _mob_type_ag == "bat":
                        _overshoot = BAT_LUNGE_OVERSHOOT
                    else:
                        _overshoot = LUNGE_OVERSHOOT * (1.0 + 0.3 * (mob.get("level", 1) - 1))
                    mob["lunge_target"]  = [
                        pos[0] + nx_ * (d_ + _overshoot),
                        pos[1] + ny_ * (d_ + _overshoot),
                    ]
                    mob["facing"] = ("right" if nx_ > abs(ny_) else
                                     "left"  if -nx_ > abs(ny_) else
                                     "down"  if ny_ > 0 else "up")
                    continue'''

if OLD2 in content:
    content = content.replace(OLD2, NEW2, 1)
    print('Patch 2 OK')
else:
    print('Patch 2 FAIL')
    sys.exit(1)

# ── Patch 3: wander state — add per-mob aggro range + animal flee ─────────────
OLD3 = '''            # --- Wander: amble slowly toward a chosen point near origin ---
            if state == "wander":
                if closest_pid and closest_dist_sq <= AGGRO_RANGE_SQ:
                    mob["state"]         = "aggro"
                    mob["target_player"] = closest_pid
                    continue'''

NEW3 = '''            # --- Wander: amble slowly toward a chosen point near origin ---
            if state == "wander":
                _is_passive = mob.get("type") in ("rabbit", "deer")
                if _is_passive:
                    _fl_sq = mob.get("flee_range_sq", RABBIT_FLEE_RANGE ** 2)
                    if closest_pid and closest_dist_sq <= _fl_sq:
                        mob["state"] = "flee"
                        continue
                else:
                    _aggro_sq = mob.get("aggro_range_sq", AGGRO_RANGE_SQ)
                    if closest_pid and closest_dist_sq <= _aggro_sq:
                        mob["state"]         = "aggro"
                        mob["target_player"] = closest_pid
                        continue'''

if OLD3 in content:
    content = content.replace(OLD3, NEW3, 1)
    print('Patch 3 OK')
else:
    print('Patch 3 FAIL')
    sys.exit(1)

# ── Patch 4: idle section — add per-mob aggro range + animal flee ─────────────
OLD4 = '''            # --- Idle: rest, then pick next wander target ---
            if closest_pid and closest_dist_sq <= AGGRO_RANGE_SQ:
                mob["state"]         = "aggro"
                mob["target_player"] = closest_pid
                continue'''

NEW4 = '''            # --- Idle: rest, then pick next wander target ---
            _is_passive_idle = mob.get("type") in ("rabbit", "deer")
            if _is_passive_idle:
                _fl_sq_idle = mob.get("flee_range_sq", RABBIT_FLEE_RANGE ** 2)
                if closest_pid and closest_dist_sq <= _fl_sq_idle:
                    mob["state"] = "flee"
                    continue
            else:
                _aggro_sq_idle = mob.get("aggro_range_sq", AGGRO_RANGE_SQ)
                if closest_pid and closest_dist_sq <= _aggro_sq_idle:
                    mob["state"]         = "aggro"
                    mob["target_player"] = closest_pid
                    continue'''

if OLD4 in content:
    content = content.replace(OLD4, NEW4, 1)
    print('Patch 4 OK')
else:
    print('Patch 4 FAIL')
    sys.exit(1)

# ── Patch 5: after mob-mob separation section, add pending_spawns execution ──
OLD5 = '''        # --- Mob-mob separation — prevent stacking (idle/wander only) ---'''

NEW5 = '''        # Execute deferred spawns (e.g., Slime King phase 2 mini-slimes)
        for _spawn_fn in pending_spawns:
            _spawn_fn()

        # --- Mob-mob separation — prevent stacking (idle/wander only) ---'''

if OLD5 in content:
    content = content.replace(OLD5, NEW5, 1)
    print('Patch 5 OK')
else:
    print('Patch 5 FAIL')
    sys.exit(1)

# ── Patch 6: dead mob section — guard None drop + Slime King death ────────────
OLD6 = '''        if killed_by:
            pending_exp.append((killed_by, exp_reward))
            _spawn_world_item(mob_drop_id, drop_pos, qty=1)
            _spawn_world_item(COIN_ITEM_ID, drop_pos, qty=random.randint(mob_level, mob_level * 3))
            print(f"[MOB] {mob_type.title()} {mob_id} (Lv{mob_level}) died — dropped items at {drop_pos}")'''

NEW6 = '''        if mob_type == "slime_king":
            global _slime_king_active
            _slime_king_active = False
            _pending_events.append({"type": "boss_defeated", "name": "Slime King"})
        if killed_by:
            pending_exp.append((killed_by, exp_reward))
            if mob_drop_id is not None:
                _spawn_world_item(mob_drop_id, drop_pos, qty=1)
            _spawn_world_item(COIN_ITEM_ID, drop_pos, qty=random.randint(mob_level, mob_level * 3))
            print(f"[MOB] {mob_type.title()} {mob_id} (Lv{mob_level}) died \u2014 dropped items at {drop_pos}")'''

if OLD6 in content:
    content = content.replace(OLD6, NEW6, 1)
    print('Patch 6 OK')
else:
    print('Patch 6 FAIL')
    sys.exit(1)

with open('server/mobs/mob_manager.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('All patches written successfully.')

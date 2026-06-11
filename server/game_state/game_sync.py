from server.network.net_utils import send_json
from server.shared_lock import players_lock
from server.item_data import get_effective_health_max, get_equip_bonuses, get_hotbar_bonus
from server.game_state.world_items import get_nearby_items, spawn_world_item
from server.game_state.placed_objects import get_nearby as _get_nearby_placed
from server.mobs.mob_manager import get_nearby_mobs
from server.world.resource_nodes import (
    get_recent_updates as _get_node_updates,
    get_planted_snapshot as _get_planted_snapshot,
    get_recent_planted_updates as _get_planted_updates,
    get_depleted_snapshot as _get_depleted_snapshot,
)
from server.world.town_gen import (
    get_built_towns as _get_built_towns,
    get_npcs_near as _get_npcs_near,
    ensure_towns_near as _ensure_towns_near,
)
from server.config import (
    CHUNK_SIZE as _CHUNK_SIZE,
    RESPAWN_DELAY as _RESPAWN_DELAY,
    RESPAWN_HP_FRACTION as _RESPAWN_HP_FRACTION,
    RESPAWN_HP_MIN as _RESPAWN_HP_MIN,
    WORLD_DAY_SECONDS as _WORLD_DAY_SECONDS,
    WORLD_START_HOUR as _WORLD_START_HOUR,
    DAY_START_HOUR as _DAY_START_HOUR,
    DAY_END_HOUR as _DAY_END_HOUR,
    INVENTORY_SIZE as _INVENTORY_SIZE,
    KNOCKBACK_DECAY as _KNOCKBACK_DECAY,
    DEATH_DROP_SLOT_CHANCE as _DEATH_DROP_SLOT_CHANCE,
    DEATH_DROP_STACK_FRACTION as _DEATH_DROP_STACK_FRACTION,
)
from server.world.dungeon_gen import (
    get_built_dungeons as _get_built_dungeons,
    ensure_dungeons_near  as _ensure_dungeons_near,
    get_dungeons_near     as _get_dungeons_near,
    check_boss_trigger    as _check_boss_trigger,
)
from server.mobs.mob_manager import spawn_boss_at as _spawn_boss_at, mobs_lock as _mobs_lock
from server.factions import apply_death_penalty as _apply_faction_death_penalty
from server.factions import get_claim_overlays as _get_claim_overlays
from server.factions import get_chunk_owner_for_tile as _get_chunk_owner_for_tile
from server.factions import get_faction_info as _get_faction_info
from server.factions import get_player_faction as _get_player_faction
from server.factions import get_player_faction_tag as _get_player_faction_tag
from server.factions import get_player_power as _get_player_power
from server.game_state.replication_config import SERVER_REPLICATION_CFG

# Track last chunk per player so we only trigger town builds on chunk transitions
_player_last_build_chunk: dict = {}
import threading
import time
import math
import os
import random

_debug_last_log: dict[str, float] = {}
_VERBOSE_DEBUG = os.environ.get("PYGAME_M_DEBUG_LOGS", "").lower() in {"1", "true", "yes", "on"}


def _debug_log(key: str, message: str, interval: float = 2.0) -> None:
    if not _VERBOSE_DEBUG:
        return
    now = time.time()
    last = _debug_last_log.get(key, 0.0)
    if now - last < interval:
        return
    _debug_last_log[key] = now
    print(message)

# ---------------------------------------------------------------------------
# World time  (0.0 = midnight, 12.0 = noon, 24.0 = midnight)
# One full day takes _WORLD_DAY_SECONDS real seconds (from server.config).
# ---------------------------------------------------------------------------
_world_time_epoch: float = time.time() - _WORLD_START_HOUR / 24.0 * _WORLD_DAY_SECONDS


def get_world_time() -> float:
    """Return current game time (0.0–24.0); 0/24 = midnight, 12 = noon."""
    elapsed = (time.time() - _world_time_epoch) % _WORLD_DAY_SECONDS
    return round(elapsed / _WORLD_DAY_SECONDS * 24.0, 3)


def set_world_time(hour: float) -> None:
    """Snap world time to *hour* (0.0–24.0) immediately."""
    global _world_time_epoch
    hour = hour % 24.0
    _world_time_epoch = time.time() - (hour / 24.0 * _WORLD_DAY_SECONDS)
    print(f"[TIME] World time set to {hour:.2f} ({int(hour):02d}:{int((hour % 1) * 60):02d})")


# ---------------------------------------------------------------------------
# Sleep / bed system
# ---------------------------------------------------------------------------
_sleeping_players: set = set()
_sleep_lock = threading.Lock()


def set_player_sleeping(pid: str, sleeping: bool) -> None:
    """Mark or unmark a player as sleeping. Triggers a time-skip when enough
    players are asleep. Silently ignored if it's already daytime."""
    global _sleeping_players
    with _sleep_lock:
        if sleeping:
            wt = get_world_time()
            if _DAY_START_HOUR <= wt <= _DAY_END_HOUR:
                return  # daytime — beds just heal/set spawn, no sleep
            _sleeping_players.add(pid)
        else:
            _sleeping_players.discard(pid)
            return  # waking up never triggers a skip
    _check_sleep_skip()


def _check_sleep_skip() -> None:
    """Skip to morning if the sleeping-player threshold is met."""
    if _players is None:
        return
    with players_lock:
        total = len(_players)
        online_ids = set(_players.keys())
    if total == 0:
        return
    with _sleep_lock:
        n_sleeping = len(_sleeping_players & online_ids)
    # Solo / duo: 1 sleeper is enough; 3+ players: strict majority (>50%)
    needed = 1 if total <= 2 else total // 2 + 1
    if n_sleeping >= needed:
        _skip_to_morning()


def _skip_to_morning() -> None:
    """Snap world_time to 6.0 (dawn) and wake all sleeping players."""
    global _world_time_epoch, _sleeping_players
    elapsed_for_dawn = _DAY_START_HOUR / 24.0 * _WORLD_DAY_SECONDS
    _world_time_epoch = time.time() - elapsed_for_dawn
    with _sleep_lock:
        _sleeping_players.clear()
    print("[TIME] Night skipped — world time snapped to 06:00 (dawn)")


_players = None
_player_positions = None
_send_to_player = None

# Dirty flag — set when inventory is mutated (swap/craft/sell); cleared after sending
_inventory_lock: threading.Lock = threading.Lock()
_inventory_dirty: set = set()
_inventory_sent:  set = set()  # players who have received at least one full inventory
_node_snapshot_sent: set = set()  # players who have received the initial depleted-nodes snapshot
_planted_snapshot_sent: set = set()  # players who have received the initial planted-nodes snapshot
_state_send_cache: dict[str, dict] = {}

_DYNAMIC_INTERVAL = float(SERVER_REPLICATION_CFG.get("dynamic_interval", 0.08))
_WORLD_INTERVAL = float(SERVER_REPLICATION_CFG.get("world_interval", 0.25))
_TIME_INTERVAL = float(SERVER_REPLICATION_CFG.get("time_interval", 0.25))
_MOB_SYNC_INTERVAL = float(SERVER_REPLICATION_CFG.get("mob_sync_interval", 0.04))


def mark_inventory_dirty(player_id: str) -> None:
    """Called by tcp_routes whenever a player's inventory is mutated."""
    with _inventory_lock:
        _inventory_dirty.add(player_id)


def invalidate_node_snapshot(player_id: str) -> None:
    """Clear the node-snapshot-sent flag so the next connection gets a fresh snapshot."""
    with _inventory_lock:
        _node_snapshot_sent.discard(player_id)
        _planted_snapshot_sent.discard(player_id)
        _inventory_sent.discard(player_id)
        _inventory_dirty.discard(player_id)
    _state_send_cache.pop(player_id, None)


def invalidate_player_cache(player_id: str) -> None:
    """Force the next game-state packet for this player to include all buckets."""
    _state_send_cache.pop(player_id, None)


def _mob_snapshot(mob_id: str, mob: dict) -> dict:
    return {
        "id": mob_id,
        "type": mob["type"],
        "pos": list(mob["pos"]),
        "vel": list(mob.get("vel", [0.0, 0.0])),
        "ts": time.time(),
        "health": mob["health"],
        "health_max": mob["health_max"],
        "level": mob.get("level", 1),
        "hit_flash": mob.get("hit_flash", 0.0),
        "state": mob.get("state", "wander"),
        "facing": mob.get("facing", "down"),
    }


def _mob_signature(snapshot: dict) -> tuple:
    px, py = snapshot["pos"]
    vx, vy = snapshot.get("vel", [0.0, 0.0])
    return (
        snapshot["type"],
        round(px, 3),
        round(py, 3),
        round(vx, 3),
        round(vy, 3),
        round(snapshot["health"], 2),
        round(snapshot["health_max"], 2),
        int(snapshot.get("level", 1)),
        round(snapshot.get("hit_flash", 0.0), 2),
        snapshot.get("state", "wander"),
        snapshot.get("facing", "down"),
    )


def _send_mob_sync(player_id: str, sock, px: float, py: float, now: float, cache: dict) -> None:
    if now - cache.get("mob_sync_at", 0.0) < _MOB_SYNC_INTERVAL:
        return
    render_dist_sq = 50 * 50
    visible = {
        mid: _mob_snapshot(mid, mob)
        for mid, mob in get_nearby_mobs(px, py, render_dist_sq).items()
    }

    known_ids: set[str] = cache.setdefault("mob_known_ids", set())
    last_sent: dict[str, tuple] = cache.setdefault("mob_last_sent", {})
    reset = bool(cache.get("mob_reset", True))
    visible_ids = set(visible.keys())

    spawns = [visible[mid] for mid in sorted(visible_ids - known_ids)]
    despawns = sorted(known_ids - visible_ids)
    updates = []
    for mid in sorted(visible_ids & known_ids):
        snap = visible[mid]
        sig = _mob_signature(snap)
        if last_sent.get(mid) != sig:
            updates.append(snap)

    if not reset and not spawns and not updates and not despawns:
        cache["mob_sync_at"] = now
        return

    payload = {
        "type": "mob_sync",
        "reset": reset,
        "spawns": spawns,
        "updates": updates,
        "despawns": despawns,
    }
    send_json(sock, payload)

    if reset:
        known_ids.clear()
        last_sent.clear()
    for snap in spawns:
        mid = snap["id"]
        known_ids.add(mid)
        last_sent[mid] = _mob_signature(snap)
    for snap in updates:
        last_sent[snap["id"]] = _mob_signature(snap)
    for mid in despawns:
        known_ids.discard(mid)
        last_sent.pop(mid, None)
    cache["mob_sync_at"] = now
    cache["mob_reset"] = False


def send_mob_sync(player_id: str, sock) -> None:
    now = time.time()
    with players_lock:
        if player_id not in _players:
            return
        me = _players[player_id]
        pos = me.get("pos", [0.0, 0.0])
        px = float(pos[0])
        py = float(pos[1])
    cache = _state_send_cache.setdefault(
        player_id,
        {
            "dynamic_at": 0.0,
            "world_at": 0.0,
            "time_at": 0.0,
            "mob_sync_at": 0.0,
            "last_weather": None,
            "last_world_time": None,
            "mob_known_ids": set(),
            "mob_last_sent": {},
            "mob_reset": True,
        },
    )
    _send_mob_sync(player_id, sock, px, py, now, cache)


def set_game_state_refs(refs):
    global _players, _player_positions, _send_to_player
    _players = refs["players"]
    _player_positions = refs["player_positions"]
    _send_to_player = refs.get("send_to_player")


def tick_player_deaths(players: dict) -> None:
    """Called once per world tick. Handles death detection and delayed respawn."""
    now = time.time()
    respawned: list[tuple[str, list[float]]] = []
    with players_lock:
        for pid, p in players.items():
            if p.get("health", 100) <= 0 and "dead_since" not in p:
                _drop_items_on_death(pid, p)
                p["dead_since"] = now
                _apply_faction_death_penalty(pid, players, now=now)
            if "dead_since" in p and now - p["dead_since"] >= _RESPAWN_DELAY:
                raw_spawn = p.get("bed_spawn") or p.get("home_pos") or [0.0, 0.0]
                spawn = list(raw_spawn)
                p["pos"]        = spawn
                p["old_pos"]    = list(spawn)
                seq = int(p.get("seq", 0)) + 1
                p["seq"]        = seq
                p["health"]     = max(_RESPAWN_HP_MIN, get_effective_health_max(p) * _RESPAWN_HP_FRACTION)
                p.pop("dead_since", None)
                _player_positions[pid] = {
                    "pos": list(spawn),
                    "vel": [0.0, 0.0],
                    "timestamp": now,
                    "seq": seq,
                }
                respawned.append((pid, list(spawn)))
                print(f"[RESPAWN] player respawned at {spawn}")
    if not respawned:
        return
    from server.game_state.sync import invalidate_player
    for pid, spawn in respawned:
        invalidate_player(pid)
        invalidate_player_cache(pid)
        if _send_to_player is not None:
            _send_to_player(pid, {"type": "teleport", "pos": list(spawn)})


def _drop_items_on_death(player_id: str, player: dict) -> None:
    """Drop some stackable backpack items into the world and remove them from inventory."""
    from server.item_data import get_item

    pos = list(player.get("pos", [0.0, 0.0]))
    inventory = player.get("inventory", [])
    dropped_any = False
    for slot_idx in range(min(27, len(inventory))):
        slot = inventory[slot_idx]
        if slot is None or len(slot) < 2:
            continue
        item_id = int(slot[0])
        qty = int(slot[1])
        if qty <= 1:
            continue
        item_def = get_item(item_id)
        if not item_def.get("stackable", False):
            continue
        if random.random() >= _DEATH_DROP_SLOT_CHANCE:
            continue
        drop_qty = max(1, int(math.floor(qty * _DEATH_DROP_STACK_FRACTION)))
        if drop_qty >= qty:
            drop_qty = qty - 1
        if drop_qty <= 0:
            continue
        offset_x = random.uniform(-0.4, 0.4)
        offset_y = random.uniform(-0.4, 0.4)
        spawn_world_item(item_id, [pos[0] + offset_x, pos[1] + offset_y], qty=drop_qty)
        inventory[slot_idx][1] = qty - drop_qty
        dropped_any = True
    if dropped_any:
        player["inventory"] = inventory
        mark_inventory_dirty(player_id)


def send_game_state(player_id, sock):
    now = time.time()   # cache once — used for respawn_in and any other time references
    with players_lock:
        if player_id not in _players:
            return
        me = dict(_players[player_id])
        knockback = _players[player_id].pop("knockback", None)  # consume once
        dead_since = _players[player_id].get("dead_since")
        raw_inv = me.get("inventory", [])
        inventory = list(raw_inv) + [None] * max(0, _INVENTORY_SIZE - len(raw_inv))
        # Equipment slot indices used for visual rendering by other clients
        _EQUIP_SLOTS = (36, 37, 40, 41, 42, 44, 45, 46, 47)

        def _equip_ids(pdata):
            raw = pdata.get("inventory", [])
            inv = list(raw) + [None] * max(0, _INVENTORY_SIZE - len(raw))
            result = {}
            for idx in _EQUIP_SLOTS:
                slot = inv[idx] if idx < len(inv) else None
                if slot is not None:
                    item_id = slot[0] if isinstance(slot, (list, tuple)) else int(slot)
                    result[str(idx)] = item_id
            return result

        def _held_item_id(pdata):
            raw = pdata.get("inventory", [])
            inv = list(raw) + [None] * max(0, _INVENTORY_SIZE - len(raw))
            hotbar_slot = pdata.get("hotbar_slot", 0)
            if not isinstance(hotbar_slot, int) or not 0 <= hotbar_slot < 9:
                hotbar_slot = 0
            held_idx = 27 + hotbar_slot
            slot = inv[held_idx] if held_idx < len(inv) else None
            if slot is None:
                return None
            return slot[0] if isinstance(slot, (list, tuple)) else int(slot)

        others = {}
        for pid, pdata in _players.items():
            if pid == player_id:
                continue
            pos_state = _player_positions.get(pid, {})
            others[pid] = {
                "pos":        list(pos_state.get("pos", pdata.get("pos", [0, 0]))),
                "vel":        list(pos_state.get("vel", [0.0, 0.0])),
                "timestamp":  pos_state.get("timestamp"),
                "seq":        pos_state.get("seq", int(pdata.get("seq", 0))),
                "health":     pdata.get("health", 100),
                "faction":    _get_player_faction(pid, _players),
                "faction_tag": _get_player_faction_tag(pid, _players),
                "equip":      _equip_ids(pdata),
                "held_item":  _held_item_id(pdata),
                "appearance": pdata.get("appearance", {}),
            }

    equip  = get_equip_bonuses(inventory)
    hotbar = get_hotbar_bonus(inventory, me.get("hotbar_slot", 0))
    faction_power, faction_effective_power = _get_player_power(player_id, _players)
    territory_owner = _get_chunk_owner_for_tile(int(me.get("pos", [0, 0])[0]), int(me.get("pos", [0, 0])[1]))
    territory_info = _get_faction_info(territory_owner, _players) if territory_owner else None
    territory_tag = territory_info.get("tag") if territory_info else None

    self_data = {
        "pos":            list(me.get("pos", [0.0, 0.0])),
        "health":         me.get("health",       100),
        "health_max":     me.get("health_max",   100) + int(equip["health_max"]),
        "stamina_max":    round(me.get("stamina_max",  100.0) + equip["stamina_max"],  2),
        "attack_power":   round(me.get("attack_power", 10.0)  + equip["attack_power"] + hotbar["attack_power"], 2),
        "speed_bonus":    round(me.get("speed_bonus",  0.0)   + equip["speed_bonus"],  3),
        "level":          me.get("level",        1),
        "exp":            me.get("exp",          0),
        "exp_next":       me.get("exp_next",     100),
        "stat_points":    me.get("stat_points",  0),
        "coins":          me.get("coins",          0),
        "hp_regen":       round(me.get("hp_regen",       0.0) + equip["hp_regen"],       3),
        "sp_regen_bonus": round(me.get("sp_regen_bonus", 0.0) + equip["sp_regen_bonus"], 3),
        "slow_timer":     me.get("slow_timer",     0.0),
        "defense":        int(equip["defense"]),
        "creative":       bool(me.get("creative",    False)),
        "dead":           dead_since is not None,
        "respawn_in":     max(0.0, round(_RESPAWN_DELAY - (now - dead_since), 2))
                          if dead_since is not None else 0.0,
        "sleeping":       player_id in _sleeping_players,
        "poison_timer":   round(me.get("poison_timer", 0.0), 2),
        "burn_timer":     round(me.get("burn_timer",   0.0), 2),
        "appearance":     me.get("appearance", {}),
        "setup_required": not bool(me.get("first_join_complete", True)),
        "faction":        _get_player_faction(player_id, _players),
        "faction_tag":    _get_player_faction_tag(player_id, _players),
        "faction_power":  faction_power,
        "faction_effective_power": faction_effective_power,
        "territory_owner": territory_owner,
        "territory_tag": territory_tag,
    }
    if knockback:
        # Encode as initial velocity for a client-side exponential decay.
        # With decay rate k=KNOCKBACK_DECAY, total displacement = v0/k.
        self_data["knockback_vel"] = [knockback[0] * _KNOCKBACK_DECAY, knockback[1] * _KNOCKBACK_DECAY]

    # Include inventory only when dirty or on first send (dirty flag set by tcp_routes)
    with _inventory_lock:
        is_dirty = player_id in _inventory_dirty or player_id not in _inventory_sent
        if is_dirty:
            _inventory_dirty.discard(player_id)
            _inventory_sent.add(player_id)
    if is_dirty:
        self_data["inventory"] = inventory

    my_pos = me.get("pos", [0, 0])
    px, py = my_pos[0], my_pos[1]

    # Lazily build town structures when player enters a new chunk
    _cur_chunk = (int(px) // _CHUNK_SIZE, int(py) // _CHUNK_SIZE)
    if _player_last_build_chunk.get(player_id) != _cur_chunk:
        _player_last_build_chunk[player_id] = _cur_chunk
        _ensure_towns_near(px, py)
        _ensure_dungeons_near(px, py)

    # Boss trigger — spawn Slime King when a player enters an unoccupied Slime Lair
    _triggers = _check_boss_trigger(px, py, now)
    if _triggers:
        with _mobs_lock:
            for _dpos in _triggers:
                _spawn_boss_at(_dpos)
    _elapsed    = (time.time() - _world_time_epoch) % _WORLD_DAY_SECONDS
    _world_time = round(_elapsed / _WORLD_DAY_SECONDS * 24.0, 2)

    from server.game_state.weather import get_weather as _get_weather
    from server.network.projectiles import get_snapshot as _proj_snapshot
    RENDER_DIST_SQ = 50 * 50
    weather = _get_weather()
    cache = _state_send_cache.setdefault(
        player_id,
        {
            "dynamic_at": 0.0,
            "world_at": 0.0,
            "time_at": 0.0,
            "mob_sync_at": 0.0,
            "last_weather": None,
            "last_world_time": None,
            "mob_known_ids": set(),
            "mob_last_sent": {},
            "mob_reset": True,
        },
    )
    first_send = cache["world_at"] == 0.0
    include_dynamic = first_send or (now - cache["dynamic_at"] >= _DYNAMIC_INTERVAL)
    include_world = first_send or (now - cache["world_at"] >= _WORLD_INTERVAL)
    include_time = (
        first_send
        or weather != cache["last_weather"]
        or cache["last_world_time"] is None
        or abs(_world_time - cache["last_world_time"]) >= 0.05
        or (now - cache["time_at"] >= _TIME_INTERVAL)
    )
    payload = {
        "type": "game_state",
        "self": self_data,
    }
    if include_world:
        payload["players"] = others
        payload["placed_objects"] = _get_nearby_placed(px, py, viewer_id=player_id)
        payload["npcs"] = _get_npcs_near(px, py)
        payload["dungeons"] = _get_dungeons_near(px, py)
        payload["map_dungeons"] = _get_built_dungeons()
        payload["towns"] = _get_built_towns()
        payload["faction_claims"] = _get_claim_overlays(_players)
        cache["world_at"] = now
    if include_dynamic:
        payload["world_items"] = get_nearby_items(px, py, RENDER_DIST_SQ)
        payload["projectiles"] = _proj_snapshot()
        cache["dynamic_at"] = now
    if include_time:
        payload["world_time"] = _world_time
        payload["weather"] = weather
        cache["time_at"] = now
        cache["last_weather"] = weather
        cache["last_world_time"] = _world_time
    node_updates = _get_node_updates()
    if node_updates:
        payload["node_updates"] = node_updates
    # On first send to this player include the full depleted-node snapshot so
    # permanently-depleted nodes (loaded from disk on restart) are visible to the client.
    with _inventory_lock:
        needs_node_snapshot = player_id not in _node_snapshot_sent
        if needs_node_snapshot:
            _node_snapshot_sent.add(player_id)
    if needs_node_snapshot:
        payload["depleted_snapshot"] = _get_depleted_snapshot()
    with _inventory_lock:
        needs_planted_snapshot = player_id not in _planted_snapshot_sent
        if needs_planted_snapshot:
            _planted_snapshot_sent.add(player_id)
    # Send the full planted snapshot on first sync and on regular world-sync
    # ticks so growth that happens while a player is far away or outside the
    # delta-retention window still appears when they return without needing a
    # server restart/reconnect.
    if needs_planted_snapshot or include_world:
        payload["planted_snapshot"] = _get_planted_snapshot()
    planted_updates = _get_planted_updates()
    if planted_updates:
        payload["planted_updates"] = planted_updates
    _debug_log(
        f"send_game_state:{player_id}",
        (
            f"[GAME SYNC DEBUG] to={player_id} "
            f"self_pos=({px:.1f},{py:.1f}) "
            f"players={'yes' if 'players' in payload else 'no'} "
            f"placed={len(payload.get('placed_objects', []))} "
            f"items={len(payload.get('world_items', []))} mobs=mob_sync "
            f"npcs={len(payload.get('npcs', []))} dungeons={len(payload.get('dungeons', []))} "
            f"time={'yes' if 'world_time' in payload else 'no'} "
            f"weather={payload.get('weather', '-')} "
            f"inv={'yes' if 'inventory' in self_data else 'no'}"
        ),
    )
    if "players" in payload and others:
        _sample_pid, _sample = next(iter(others.items()))
        _debug_log(
            f"send_game_state_sample:{player_id}",
            (
                f"[GAME SYNC DEBUG] to={player_id} sample_remote={_sample_pid} "
                f"body={_sample.get('appearance', {}).get('body', 'missing')} "
                f"equip_slots={sorted(_sample.get('equip', {}).keys())}"
            ),
        )
    try:
        send_json(sock, payload)
    except OSError as e:
        print(f"[GAME SYNC] send failed for {player_id}: {e}")

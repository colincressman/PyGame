from server.network.net_utils import send_json
from server.shared_lock import players_lock
from server.item_data import get_equip_bonuses, get_hotbar_bonus
from server.game_state.world_items import world_items, world_items_lock
from server.game_state.placed_objects import get_nearby as _get_nearby_placed
from server.mobs.mob_manager import mobs, mobs_lock
from server.world.resource_nodes import get_recent_updates as _get_node_updates, get_planted_snapshot as _get_planted_snapshot, get_depleted_snapshot as _get_depleted_snapshot
from server.world.town_gen import get_npcs_near as _get_npcs_near, ensure_towns_near as _ensure_towns_near
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
)
from server.world.dungeon_gen import (
    ensure_dungeons_near  as _ensure_dungeons_near,
    get_dungeons_near     as _get_dungeons_near,
    check_boss_trigger    as _check_boss_trigger,
)
from server.mobs.mob_manager import spawn_boss_at as _spawn_boss_at, mobs_lock as _mobs_lock

# Track last chunk per player so we only trigger town builds on chunk transitions
_player_last_build_chunk: dict = {}
import threading
import time
import math

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

# Dirty flag — set when inventory is mutated (swap/craft/sell); cleared after sending
_inventory_lock: threading.Lock = threading.Lock()
_inventory_dirty: set = set()
_inventory_sent:  set = set()  # players who have received at least one full inventory
_node_snapshot_sent: set = set()  # players who have received the initial depleted-nodes snapshot


def mark_inventory_dirty(player_id: str) -> None:
    """Called by tcp_routes whenever a player's inventory is mutated."""
    with _inventory_lock:
        _inventory_dirty.add(player_id)


def invalidate_node_snapshot(player_id: str) -> None:
    """Clear the node-snapshot-sent flag so the next connection gets a fresh snapshot."""
    with _inventory_lock:
        _node_snapshot_sent.discard(player_id)
        _inventory_sent.discard(player_id)
        _inventory_dirty.discard(player_id)


def set_game_state_refs(refs):
    global _players, _player_positions
    _players = refs["players"]
    _player_positions = refs["player_positions"]


def tick_player_deaths(players: dict) -> None:
    """Called once per world tick. Handles death detection and delayed respawn."""
    now = time.time()
    with players_lock:
        for p in players.values():
            if p.get("health", 100) <= 0 and "dead_since" not in p:
                p["dead_since"] = now
            if "dead_since" in p and now - p["dead_since"] >= _RESPAWN_DELAY:
                spawn = list(p.get("bed_spawn", [0.0, 0.0]))
                p["pos"]        = spawn
                p["health"]     = max(_RESPAWN_HP_MIN, p.get("health_max", 100) * _RESPAWN_HP_FRACTION)
                p.pop("dead_since", None)
                print(f"[RESPAWN] player respawned at {spawn}")


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
                    result[idx] = item_id
            return result

        others = {
            pid: {
                "pos":        list(pdata.get("pos", [0, 0])),
                "health":     pdata.get("health", 100),
                "equip":      _equip_ids(pdata),
                "appearance": pdata.get("appearance", {}),
            }
            for pid, pdata in _players.items()
            if pid != player_id
        }

    equip  = get_equip_bonuses(inventory)
    hotbar = get_hotbar_bonus(inventory, me.get("hotbar_slot", 0))

    self_data = {
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

    # Include world items within render range (~50 tiles)
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
    RENDER_DIST_SQ = 50 * 50
    with world_items_lock:
        nearby_items = [
            {"uid": uid, "item_id": item["item_id"], "pos": item["pos"], "qty": item["qty"]}
            for uid, item in world_items.items()
            if (item["pos"][0] - px) ** 2 + (item["pos"][1] - py) ** 2 <= RENDER_DIST_SQ
        ]

    # Include mobs within render range
    with mobs_lock:
        nearby_mobs = [
            {"id": mid, "type": mob["type"], "pos": list(mob["pos"]),
             "health": mob["health"], "health_max": mob["health_max"],
             "level": mob.get("level", 1),
             "hit_flash": mob.get("hit_flash", 0.0),
             "state": mob.get("state", "wander"),
             "facing": mob.get("facing", "down")}
            for mid, mob in mobs.items()
            if (mob["pos"][0] - px) ** 2 + (mob["pos"][1] - py) ** 2 <= RENDER_DIST_SQ
        ]

    _elapsed    = (time.time() - _world_time_epoch) % _WORLD_DAY_SECONDS
    _world_time = round(_elapsed / _WORLD_DAY_SECONDS * 24.0, 2)

    from server.game_state.weather import get_weather as _get_weather
    from server.network.projectiles import get_snapshot as _proj_snapshot
    payload = {
        "type": "game_state",
        "self": self_data,
        "players": others,
        "world_items": nearby_items,
        "mobs": nearby_mobs,
        "placed_objects": _get_nearby_placed(px, py),
        "npcs": _get_npcs_near(px, py),
        "dungeons": _get_dungeons_near(px, py),
        "world_time": _world_time,
        "weather": _get_weather(),
        "projectiles": _proj_snapshot(),
    }
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
    payload["planted_nodes"] = _get_planted_snapshot()
    try:
        send_json(sock, payload)
    except OSError as e:
        print(f"[GAME SYNC] send failed for {player_id}: {e}")

import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, Future

from .config import PORT_WORLD, PORT_STATE, TICK_RATE, MAX_PLAYERS
from server.world import visible
from .shared_lock import clients_lock, players_lock

# === Global State ===
clients = {
    "world": {},
    "game_state": {},
    "udp": {}
}

players = {}
player_positions = {}
pending_udp_assignments = set()
client_id_counter = [1]  # List used for mutability

delta_cache = {}
last_chunk_hashes = {}

# Thread pool — sized to MAX_PLAYERS so every player can have a send in flight
# simultaneously without queueing behind an 8-worker cap.
executor = ThreadPoolExecutor(max_workers=MAX_PLAYERS)

# Per-player in-flight futures — skip submitting a new send if the previous
# one hasn't completed yet (prevents duplicate sends under lag).
_world_futures:  dict[str, Future] = {}
_state_futures:  dict[str, Future] = {}
_future_started_at: dict[tuple[str, str], float] = {}

# === Main Game Loop ===
def game_loop():
    import time as _time
    last_tick = _time.time()
    next_tick = last_tick
    tick_counter = 0
    while True:
        now  = _time.time()
        dt   = now - last_tick
        last_tick = now

        try:
            pickup_tick()
        except Exception as e:
            print(f"[PICKUP TICK ERROR] {e}")
            traceback.print_exc()

        try:
            spawner_tick(dt)
        except Exception as e:
            print(f"[SPAWNER TICK ERROR] {e}")
            traceback.print_exc()

        try:
            update_mobs(dt)
            for _evt in _drain_mob_events():
                if _evt.get("type") == "boss_spawned":
                    from server.network.tcp_state_handlers_v2 import broadcast_chat
                    broadcast_chat({"type": "chat", "sender": "SYSTEM",
                                    "text": f"\u26a0 THE {_evt['name'].upper()} HAS AWAKENED!"})
                elif _evt.get("type") == "boss_defeated":
                    from server.network.tcp_state_handlers_v2 import broadcast_chat
                    broadcast_chat({"type": "chat", "sender": "SYSTEM",
                                    "text": f"\u2605 The {_evt['name']} has been defeated!"})
                    _dpos = _evt.get("dungeon_pos")
                    if _dpos:
                        import time as _t
                        from server.world.dungeon_gen import set_boss_cooldown, BOSS_RESPAWN_DELAY
                        set_boss_cooldown(_dpos, _t.time() + BOSS_RESPAWN_DELAY)
        except Exception as e:
            print(f"[MOB TICK ERROR] {e}")
            traceback.print_exc()

        try:
            tick_status_effects(players, dt)
        except Exception as e:
            print(f"[STATUS EFFECTS ERROR] {e}")
            traceback.print_exc()

        try:
            from server.network.projectiles import tick_projectiles as _tick_proj
            from server.mobs.mob_manager import mobs as _mobs
            _tick_proj(dt, players, _mobs)
        except Exception as e:
            print(f"[PROJECTILE TICK ERROR] {e}")
            traceback.print_exc()

        update_world(players, player_positions)

        with clients_lock:
            valid_world_clients = list(clients["world"].items())
            valid_state_clients = list(clients["game_state"].items())

        with players_lock:
            active_players = set(players.keys())
            player_pos_copy = dict(player_positions)

        for player_id, sock in valid_world_clients:
            if player_id not in active_players or player_id not in player_pos_copy:
                continue
            # Skip if previous world-send for this player is still in flight
            prev = _world_futures.get(player_id)
            if prev is not None and not prev.done():
                started = _future_started_at.get(("world", player_id), now)
                if now - started > 1.0:
                    print(f"[WORLD SYNC DEBUG] stalled send player={player_id} age={now - started:.2f}s")
                continue
            if prev is not None and prev.done():
                err = prev.exception()
                if err is not None:
                    print(f"[WORLD SYNC ERROR] player={player_id} err={err}")
            try:
                _world_futures[player_id] = executor.submit(
                    send_if_changed, player_id, sock, force_full=False
                )
                _future_started_at[("world", player_id)] = now
            except Exception as e:
                print(f"[GAME LOOP ERROR] {e}")
                traceback.print_exc()

        if tick_counter % 6 == 0:   # 20 Hz game state; UDP still handles high-rate positions
            for player_id, sock in valid_state_clients:
                if player_id not in active_players:
                    continue
                # Skip if previous state-send for this player is still in flight
                prev = _state_futures.get(player_id)
                if prev is not None and not prev.done():
                    started = _future_started_at.get(("state", player_id), now)
                    if now - started > 1.0:
                        print(f"[STATE SYNC DEBUG] stalled send player={player_id} age={now - started:.2f}s")
                    continue
                if prev is not None and prev.done():
                    err = prev.exception()
                    if err is not None:
                        print(f"[STATE SYNC ERROR] player={player_id} err={err}")
                try:
                    _state_futures[player_id] = executor.submit(send_game_state, player_id, sock)
                    _future_started_at[("state", player_id)] = now
                except Exception as e:
                    print(f"[GAME LOOP STATE ERROR] {e}")
                    traceback.print_exc()

        tick_counter += 1
        next_tick += 1 / TICK_RATE
        sleep_for = next_tick - _time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_tick = _time.time()

# === Entry Point ===
if __name__ == "__main__":
    # On Windows, time.sleep() defaults to ~15.6ms resolution.
    # timeBeginPeriod(1) raises it to ~1ms so the 120 Hz game loop actually fires at 120 Hz.
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        print("[SERVER] Windows timer resolution set to 1ms")
    except Exception:
        pass

    print("[SERVER STARTING] Waiting for client connections...")
    from server.network.tcp_routes import handle_world, handle_state, set_tcp_state_refs
    from server.network.udp_routes import udp_loop, udp_broadcast_loop, set_udp_state_refs
    from server.network.listener import start_listener
    from server.network.tcp_state_handlers_v2 import set_chat_refs, broadcast_chat, kick_player, send_to_player
    from server.network.commands import set_server_refs as _set_cmd_refs
    from server.game_state.sync import send_if_changed
    from server.game_state.game_sync import send_game_state, set_game_state_refs
    from server.game_state.world_items import pickup_tick, set_world_items_refs, spawn_world_item
    from server.game_state.item_spawner import spawner_tick, set_spawner_refs
    from server.world.autosave import autosave_world, set_world_data_ref
    from server.world.update import update_world, world_data
    from server.cleanup import set_cleanup_refs
    from server.mobs import update_mobs, mobs, mobs_lock, set_mob_refs
    from server.mobs.mob_manager import drain_events as _drain_mob_events
    from server.game_state.status_effects import tick_status_effects

    visible.set_world_data_reference(world_data, player_positions)
    set_world_data_ref(world_data)

    # Inject shared game_state into handlers
    set_tcp_state_refs({
        "clients": clients,
        "players": players,
        "player_positions": player_positions,
    })

    set_chat_refs({"clients": clients})

    def _save_all_players():
        from server.player_save import save_player
        with players_lock:
            snapshot = list(players.items())
        for pid, pdata in snapshot:
            save_player(pid, dict(pdata))
        print("[SERVER] All players saved.")

    _set_cmd_refs({
        "kick_player":      kick_player,
        "broadcast_chat":   broadcast_chat,
        "save_all_players": _save_all_players,
        "send_to_player":   send_to_player,
        "player_positions": player_positions,
    })

    set_cleanup_refs({
        "clients": clients,
        "players": players,
        "player_positions": player_positions,
        "pending_udp_assignments": pending_udp_assignments,
        "last_world_hashes": last_chunk_hashes
    })

    set_game_state_refs({
        "players": players,
        "player_positions": player_positions,
    })

    set_world_items_refs({
        "players": players,
    })

    set_mob_refs({
        "players":          players,
        "spawn_world_item": spawn_world_item,
        "world_data":       world_data,
    })

    set_spawner_refs({
        "players":    players,
        "world_data": world_data,
    })

    set_udp_state_refs({
        "clients": clients,
        "players": players,
        "player_positions": player_positions,
        "pending_udp_assignments": pending_udp_assignments,
        "client_id_counter": client_id_counter,
        "world_data": world_data,
    })

    # Pre-build town structures around world spawn so they exist before anyone logs in
    from server.world.town_gen import ensure_towns_near as _ensure_towns_near
    _ensure_towns_near(0.0, 0.0, dist=350.0)

    threading.Thread(target=start_listener, args=(PORT_WORLD, handle_world), daemon=True).start()
    threading.Thread(target=start_listener, args=(PORT_STATE, handle_state), daemon=True).start()
    threading.Thread(target=udp_loop, daemon=True).start()
    threading.Thread(target=udp_broadcast_loop, daemon=True).start()
    threading.Thread(target=game_loop, daemon=True).start()
    threading.Thread(target=autosave_world, daemon=True).start()

    while True:
        time.sleep(1)

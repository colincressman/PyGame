import time
import threading
from concurrent.futures import ThreadPoolExecutor

from .config import PORT_WORLD, PORT_STATE
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

# Thread pool
executor = ThreadPoolExecutor(max_workers=8)

# === Main Game Loop ===
def game_loop():
    while True:
        update_world(players, player_positions)

        with clients_lock:
            valid_world_clients = list(clients["world"].items())

        with players_lock:
            active_players = set(players.keys())
            player_pos_copy = dict(player_positions)

        for player_id, sock in valid_world_clients:
            if player_id not in active_players or player_id not in player_pos_copy:
                continue

            try:
                executor.submit(send_if_changed, player_id, sock)
            except Exception as e:
                print(f"[GAME LOOP ERROR] {e}")

        time.sleep(1 / 60.0)


# === Entry Point ===
if __name__ == "__main__":
    print("[SERVER STARTING] Waiting for client connections...")
    from server.network.tcp_routes import handle_world, handle_state, set_tcp_state_refs
    from server.network.udp_routes import udp_loop, udp_broadcast_loop, set_udp_state_refs
    from server.network.listener import start_listener
    from server.game_state.sync import send_if_changed
    from server.world.autosave import autosave_world
    from server.world.update import update_world, world_data

    visible.set_world_data_reference(world_data, player_positions)

    # Inject shared game_state into handlers
    set_tcp_state_refs({
        "clients": clients,
        "players": players,
        "player_positions": player_positions,
        "mock_state_data": {"players": {}, "mobs": {}, "objects": {}, "items": {}}
    })

    set_udp_state_refs({
        "clients": clients,
        "players": players,
        "player_positions": player_positions,
        "pending_udp_assignments": pending_udp_assignments,
        "client_id_counter": client_id_counter
    })

    threading.Thread(target=start_listener, args=(PORT_WORLD, handle_world), daemon=True).start()
    threading.Thread(target=start_listener, args=(PORT_STATE, handle_state), daemon=True).start()
    threading.Thread(target=udp_loop, daemon=True).start()
    threading.Thread(target=udp_broadcast_loop, daemon=True).start()
    threading.Thread(target=game_loop, daemon=True).start()
    threading.Thread(target=autosave_world, daemon=True).start()

    while True:
        time.sleep(1)
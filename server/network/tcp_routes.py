# server/network/tcp_routes.py

import time
from server.shared_lock import clients_lock
from server.network.net_utils import send_json, recv_json
from server.cleanup import cleanup_player
from server.game_state.mock_data import mock_state_data

# Shared game_state references to be injected
clients = None

def set_tcp_state_refs(refs):
    global clients
    clients = refs["clients"]

def handle_world(sock, addr):
    try:
        handshake = recv_json(sock)
        if not handshake or handshake.get("socket_type") != "world":
            sock.close()
            return
        player_id = handshake.get("player_id", f"Unknown_{addr}")
        clients["world"][player_id] = sock
        print(f"[WORLD CONNECT] {player_id} at {addr}")
        send_json(sock, {"status": "connected", "type": "world"})

        while True:
            with clients_lock:
                if player_id not in clients["world"] or sock.fileno() == -1:
                    break
            time.sleep(1 / 20.0)

    except Exception as e:
        print(f"[WORLD ERROR] {e}")
    finally:
        print(f"[WORLD DISCONNECT] {player_id}")
        cleanup_player(player_id, clients)
        sock.close()


def handle_state(sock, addr):
    try:
        handshake = recv_json(sock)
        if not handshake or handshake.get("socket_type") != "game_state":
            sock.close()
            return
        player_id = handshake.get("player_id", f"Unknown_{addr}")
        clients["game_state"][player_id] = sock
        print(f"[STATE CONNECT] {player_id} at {addr}")
        send_json(sock, {"status": "connected", "type": "game_state"})

        while True:
            with clients_lock:
                if player_id not in clients["game_state"] or sock.fileno() == -1:
                    break
            send_json(sock, {"type": "game_state", "data": mock_state_data})
            time.sleep(1 / 60.0)

    except Exception as e:
        print(f"[STATE ERROR] {e}")
    finally:
        print(f"[STATE DISCONNECT] {player_id}")
        cleanup_player(player_id, clients)
        sock.close()

# server/network/udp_routes.py

import json
import socket
import struct
import time
from server.shared_lock import clients_lock, players_lock
from server.config import HOST, PORT_UDP, BUFFER_SIZE

# Shared game_state references to be injected
clients = None
players = None
player_positions = None
pending_udp_assignments = None
client_id_counter = None

def set_udp_state_refs(refs):
    global clients, players, player_positions, pending_udp_assignments, client_id_counter
    clients = refs["clients"]
    players = refs["players"]
    player_positions = refs["player_positions"]
    pending_udp_assignments = refs["pending_udp_assignments"]
    client_id_counter = refs["client_id_counter"]


def udp_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT_UDP))
    print(f"[UDP LISTENING] on {PORT_UDP}")

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            size = struct.unpack("!I", data[:4])[0]
            payload = json.loads(data[4:4+size].decode("utf-8"))

            player_id = payload.get("player_id")
            pos = payload.get("pos")

            if not player_id:
                new_id = f"Player{client_id_counter[0]}"
                client_id_counter[0] += 1
                player_id = new_id
                players[player_id] = {"pos": [0, 0], "health": 100, "level": 1, "last_seen": time.time()}
                player_positions[player_id] = [0, 0]
                clients["udp"][player_id] = addr
                pending_udp_assignments.add(player_id)

                response = json.dumps({"type": "assign_id", "player_id": player_id}).encode("utf-8")
                sock.sendto(struct.pack("!I", len(response)) + response, addr)
                print(f"[UDP ASSIGN] {player_id} assigned to {addr}")

            elif pos:
                player_positions[player_id] = pos
                players[player_id]["pos"] = pos
                players[player_id]["last_seen"] = time.time()
                clients["udp"][player_id] = addr

        except Exception as e:
            print(f"[UDP ERROR] {e}")

def udp_broadcast_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        # === Assign IDs to new clients ===
        with clients_lock:
            udp_clients_snapshot = dict(clients["udp"])

        with players_lock:
            pending_ids = list(pending_udp_assignments)

        for player_id in pending_ids:
            addr = udp_clients_snapshot.get(player_id)
            if not addr:
                continue

            try:
                response = json.dumps({
                    "type": "assign_id",
                    "player_id": player_id
                }).encode("utf-8")
                sock.sendto(struct.pack("!I", len(response)) + response, addr)

                with players_lock:
                    pending_udp_assignments.discard(player_id)

            except Exception as e:
                print(f"[UDP ASSIGN SEND ERROR] {e}")

        # === Send position updates ===
        with players_lock:
            if not player_positions:
                time.sleep(1 / 120.0)
                continue
            pos_snapshot = dict(player_positions)
            active_ids = set(player_positions.keys())

        with clients_lock:
            udp_clients = {
                pid: addr for pid, addr in clients["udp"].items()
                if pid in active_ids and pid not in pending_udp_assignments
            }

        payload = {
            "type": "positions",
            "players": pos_snapshot,
            "timestamp": time.time()  # Add server timestamp for better sync
        }
        encoded = json.dumps(payload).encode("utf-8")
        message = struct.pack("!I", len(encoded)) + encoded

        for player_id, addr in udp_clients.items():
            try:
                sock.sendto(message, addr)
            except Exception as e:
                print(f"[UDP POS SEND ERROR] {e}")

        time.sleep(1 / 120.0)

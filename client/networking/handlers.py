import time, struct
import socket, json
import threading, orjson
from .sockets import connect_with_retry
from .protocols import identify_socket, recv_json

def handle_world(HOST, PORT_WORLD, chunk_queue, client_running, player_id):
    sock = connect_with_retry(HOST, PORT_WORLD)
    if not sock:
        return
    identify_socket(sock, "world", player_id)
    sock.settimeout(0.1)  # avoid blocking forever
    print("[WORLD] Connected and handshake sent.")

    while client_running:
        try:
            data = recv_json(sock)
            if data and data.get("type") == "world_chunks":
                chunks = data.get("data", {})
                for chunk_key_str, tiles in chunks.items():
                    cx, cy = map(int, chunk_key_str.strip("()").split(","))
                    converted_tiles = {
                        tuple(map(int, key.split(","))): val
                        for key, val in tiles.items()
                    }
                    chunk_queue.put(((cx, cy), converted_tiles))

        except socket.timeout:
            continue  # allow frequent checks
        except Exception as e:
            print(f"[WORLD RECV ERROR] {e}")
            break

        time.sleep(1 / 60)

def handle_state(HOST, PORT_STATE, player_id):
    sock = connect_with_retry(HOST, PORT_STATE)
    if not sock:
        return
    identify_socket(sock, "game_state", player_id)
    print("[STATE] Connected and handshake sent.")

    while True:
        data = recv_json(sock)
        if data:
            pass
        time.sleep(1 / 45)

def send_and_receive_udp():
    from config import HOST, PORT_UDP, BUFFER_SIZE
    from state.player import player_id_dict, player_data 
    from config import client_running

    player_id = player_id_dict["player_id"]

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('0.0.0.0', 0))

    initial_payload = json.dumps({}).encode("utf-8")
    size = struct.pack("!I", len(initial_payload))
    udp_sock.sendto(size + initial_payload, (HOST, PORT_UDP))

    try:
        data, _ = udp_sock.recvfrom(BUFFER_SIZE)
        size = struct.unpack("!I", data[:4])[0]
        payload = json.loads(data[4:4+size].decode("utf-8"))
        player_id = payload["player_id"]
        player_data["pos"] = [680, 272]
        print(f"[UDP ASSIGNED ID] {player_id}")
    except Exception as e:
        print(f"[UDP INIT ERROR] {e}")
        return

    threading.Thread(target=udp_receive_loop, args=(udp_sock,), daemon=True).start()

    while client_running:
        pos_payload = orjson.dumps({
            "player_id": player_id,
            "pos": player_data["pos"]
        })
        udp_sock.sendto(struct.pack("!I", len(pos_payload)) + pos_payload, (HOST, PORT_UDP))
        time.sleep(1 / 120)

def udp_receive_loop(sock):
    from config import BUFFER_SIZE
    from state.player import player_id_dict
    from config import players_data, client_running
    from shared_lock import data_lock

    sock.setblocking(False)

    while client_running:
        try:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            size = struct.unpack("!I", data[:4])[0]
            payload = json.loads(data[4:4+size].decode("utf-8"))

            if payload.get("type") == "positions":
                with data_lock:
                    raw_positions = payload.get("players", {})
                    players_data.clear()

                    for pid, pos in raw_positions.items():
                        players_data[pid] = {
                            "pos": pos
                        }
            if payload.get("type") == "assign_id":
                player_id_dict["player_id"] = payload.get("player_id")
                player_id = player_id_dict["player_id"]
                print(f"[CLIENT] Assigned player_id: {player_id}")
        except BlockingIOError:
            pass
        except Exception as e:
            print(f"[UDP RECV ERROR] {e}")

        time.sleep(1 / 120)
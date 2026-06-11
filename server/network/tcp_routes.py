# server/network/tcp_routes.py
import struct
import time
import socket
import select
import orjson
from server.shared_lock import clients_lock, players_lock, world_items_lock
from server.player_save import _SAFE_ID
from server.game_state.world_items import world_items as _world_items
from server.network.net_utils import send_json, recv_json, discard_socket
from server.network.tcp_state_handlers_v2 import dispatch_message as _dispatch_state_message_v2
from server.cleanup import cleanup_player
from server.item_data import get_item, roll_item_stats
from server.session_auth import verify_token

# Shared game_state references to be injected
clients = None
players = None
player_positions = None


def _is_safe_player_id(player_id) -> bool:
    return isinstance(player_id, str) and bool(_SAFE_ID.match(player_id))


def set_tcp_state_refs(refs):
    global clients, players, player_positions
    clients = refs["clients"]
    players = refs["players"]
    player_positions = refs["player_positions"]


def _valid_handshake(handshake: dict | None, socket_type: str, addr) -> str | None:
    if not handshake or handshake.get("socket_type") != socket_type:
        return None
    player_id = handshake.get("player_id", f"Unknown_{addr}")
    if not _is_safe_player_id(player_id):
        print(f"[{socket_type.upper()} REJECT] unsafe player_id from {addr}: {player_id!r}")
        return None
    if not verify_token(player_id, handshake.get("session_token")):
        print(f"[{socket_type.upper()} REJECT] invalid session token for {player_id} from {addr}")
        return None
    return player_id


# ---------------------------------------------------------------------------
# Inventory helper — add item_id × qty to a player's bag (slots 0-35)
# ---------------------------------------------------------------------------

def _give_item(player: dict, item_id: int, qty: int) -> bool:
    """Add item_id × qty to the first available bag slot(s).  Returns True if fully added."""
    item_def  = get_item(item_id)
    if not item_def:
        return False
    stackable = item_def.get("stackable", False)
    max_stack = item_def.get("max_stack", 1)
    inv       = player["inventory"]
    remaining = qty

    if stackable:
        # Top up existing stacks first
        for i in range(36):
            slot = inv[i]
            if slot is not None and slot[0] == item_id:
                space = max_stack - slot[1]
                if space > 0:
                    add = min(space, remaining)
                    slot[1] += add
                    remaining -= add
            if remaining == 0:
                return True

    # Place in empty slots (roll stats for non-stackable gear)
    for i in range(36):
        if remaining <= 0:
            break
        if inv[i] is None:
            add  = min(max_stack, remaining)
            meta = roll_item_stats(item_id) if (add == 1 and not stackable) else None
            inv[i]    = [item_id, add, meta] if meta is not None else [item_id, add]
            remaining -= add

    return remaining == 0

def handle_world(sock, addr):
    player_id = None
    try:
        handshake = recv_json(sock)
        player_id = _valid_handshake(handshake, "world", addr)
        if player_id is None:
            sock.close()
            return
        clients["world"][player_id] = sock
        print(f"[WORLD CONNECT] {player_id} at {addr}")
        send_json(sock, {"status": "connected", "type": "world"})

        sock.settimeout(5.0)
        while True:
            try:
                data = sock.recv(4)
                if not data:
                    break  # client closed connection
            except socket.timeout:
                with clients_lock:
                    if player_id not in clients["world"] or sock.fileno() == -1:
                        break
            except Exception:
                break

    except Exception as e:
        print(f"[WORLD ERROR] {e}")
    finally:
        print(f"[WORLD DISCONNECT] {player_id}")
        if player_id is not None:
            cleanup_player(player_id)
        discard_socket(sock)
        sock.close()


def handle_state(sock, addr):
    player_id = None
    try:
        handshake = recv_json(sock)
        player_id = _valid_handshake(handshake, "game_state", addr)
        if player_id is None:
            sock.close()
            return
        clients["game_state"][player_id] = sock
        print(f"[STATE CONNECT] {player_id} at {addr}")
        send_json(sock, {"status": "connected", "type": "game_state"})

        sock.settimeout(None)
        while True:
            # ── Receive one framed message ──────────────────────────────────
            msg_bytes = None
            try:
                ready, _, _ = select.select([sock], [], [], 0.5)
                if not ready:
                    with clients_lock:
                        if player_id not in clients["game_state"] or sock.fileno() == -1:
                            break
                    continue
                size_bytes = sock.recv(4)
                if not size_bytes:
                    break   # client disconnected cleanly
                if len(size_bytes) < 4:
                    break
                size = struct.unpack("!I", size_bytes)[0]
                if size > 10 * 1024 * 1024:
                    break
                _chunks = []
                _received = 0
                while _received < size:
                    chunk = sock.recv(size - _received)
                    if not chunk:
                        break
                    _chunks.append(chunk)
                    _received += len(chunk)
                msg_bytes = b"".join(_chunks)
                if len(msg_bytes) < size:
                    break
            except socket.timeout:
                with clients_lock:
                    if player_id not in clients["game_state"] or sock.fileno() == -1:
                        break
                continue
            except Exception:
                break   # real socket error — disconnect

            # ── Dispatch (handler errors must NOT kill the connection) ───────
            if msg_bytes:
                try:
                    data = orjson.loads(msg_bytes)
                    _dispatch_state_message_v2(data, player_id, players, _give_item, _world_items)
                except Exception as _e:
                    print(f"[STATE HANDLER ERROR] {player_id}: {_e}")

    except Exception as e:
        print(f"[STATE ERROR] {e}")
    finally:
        print(f"[STATE DISCONNECT] {player_id}")
        if player_id is not None:
            cleanup_player(player_id)
        discard_socket(sock)
        sock.close()

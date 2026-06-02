import struct
import socket

try:
    import orjson as _json_lib
    _dumps = lambda obj: _json_lib.dumps(obj)          # returns bytes
    _loads = _json_lib.loads                            # accepts bytes
except ImportError:
    import json as _json_lib                            # fallback for dev environments
    _dumps = lambda obj: _json_lib.dumps(obj).encode("utf-8")
    _loads = lambda b: _json_lib.loads(b.decode("utf-8"))

MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB — mirrors server/network/net_utils.py


def identify_socket(sock, socket_type, player_id=None, session_token=None):
    msg = {"socket_type": socket_type}
    if player_id is not None:
        msg["player_id"] = player_id
    if session_token is not None:
        msg["session_token"] = session_token
    send_json(sock, msg)


def send_json(sock, data):
    encoded = _dumps(data)
    sock.sendall(struct.pack("!I", len(encoded)) + encoded)


def recv_json(sock):
    try:
        size_data = sock.recv(4)
        if not size_data:
            raise ConnectionError("Remote end closed connection")
        size = struct.unpack("!I", size_data)[0]
        if size > MAX_MESSAGE_SIZE:
            raise ConnectionError(
                f"Incoming message size {size} exceeds MAX_MESSAGE_SIZE ({MAX_MESSAGE_SIZE})"
            )
        msg_data = b''
        while len(msg_data) < size:
            chunk = sock.recv(size - len(msg_data))
            if not chunk:
                raise ConnectionError("Remote end closed connection mid-packet")
            msg_data += chunk
        return _loads(msg_data)
    except (socket.timeout, ConnectionError):
        raise
    except Exception:
        return None

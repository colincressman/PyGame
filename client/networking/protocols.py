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


def _recv_exact(sock, size: int) -> bytes:
    """Read exactly *size* bytes, preserving partial progress across timeouts.

    If no bytes are available before the socket timeout fires, re-raise
    socket.timeout so callers can stay responsive. Once any part of a frame has
    arrived, keep reading until the frame is complete or the connection closes.
    """
    chunks: list[bytes] = []
    received = 0
    saw_any = False
    while received < size:
        try:
            chunk = sock.recv(size - received)
            if not chunk:
                raise ConnectionError("Remote end closed connection mid-packet")
            chunks.append(chunk)
            received += len(chunk)
            saw_any = True
        except socket.timeout:
            if not saw_any:
                raise
            continue
    return b"".join(chunks)


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
        size_data = _recv_exact(sock, 4)
        size = struct.unpack("!I", size_data)[0]
        if size > MAX_MESSAGE_SIZE:
            raise ConnectionError(
                f"Incoming message size {size} exceeds MAX_MESSAGE_SIZE ({MAX_MESSAGE_SIZE})"
            )
        msg_data = _recv_exact(sock, size)
        return _loads(msg_data)
    except (socket.timeout, ConnectionError):
        raise
    except Exception:
        return None

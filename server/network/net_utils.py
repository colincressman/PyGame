import struct
import orjson

MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap


def send_json(sock, data):
    """Send a JSON-serializable object with a 4-byte length prefix.

    Raises the underlying socket exception so callers can detect a failed
    send and clean up the connection rather than silently dropping data.
    """
    encoded = orjson.dumps(data)          # returns bytes directly
    sock.sendall(struct.pack("!I", len(encoded)) + encoded)


def recv_json(sock):
    """Receive a 4-byte-prefixed JSON message."""
    try:
        size_data = sock.recv(4)
        if not size_data:
            return None
        size = struct.unpack("!I", size_data)[0]
        if size > MAX_MESSAGE_SIZE:
            print(f"[RECV ERROR] Message size {size} exceeds limit of {MAX_MESSAGE_SIZE}")
            return None
        msg_data = b''
        while len(msg_data) < size:
            chunk = sock.recv(size - len(msg_data))
            if not chunk:
                return None
            msg_data += chunk
        return orjson.loads(msg_data)         # accepts bytes directly
    except Exception as e:
        print(f"[RECV ERROR] {e}")
        return None

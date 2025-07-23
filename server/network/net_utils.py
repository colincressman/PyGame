import json
import struct


def send_json(sock, data):
    """Send a JSON-serializable object with a 4-byte length prefix."""
    try:
        encoded = json.dumps(data).encode("utf-8")
        length = struct.pack("!I", len(encoded))
        sock.sendall(length + encoded)
    except Exception as e:
        print(f"[SEND ERROR] {e}")


def recv_json(sock):
    """Receive a 4-byte-prefixed JSON message."""
    try:
        size_data = sock.recv(4)
        if not size_data:
            return None
        size = struct.unpack("!I", size_data)[0]
        msg_data = b''
        while len(msg_data) < size:
            chunk = sock.recv(size - len(msg_data))
            if not chunk:
                return None
            msg_data += chunk
        return json.loads(msg_data.decode("utf-8"))
    except Exception as e:
        print(f"[RECV ERROR] {e}")
        return None

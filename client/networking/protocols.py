import json, struct

def identify_socket(sock, socket_type, player_id=None):
    msg = {"socket_type": socket_type}
    if player_id is not None:
        msg["player_id"] = player_id
    send_json(sock, msg)

# Helper to send JSON with length header
def send_json(sock, data):
    encoded = json.dumps(data).encode("utf-8")
    length = struct.pack("!I", len(encoded))
    sock.sendall(length + encoded)

# Helper to receive length-prefixed JSON
def recv_json(sock):
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
        return None
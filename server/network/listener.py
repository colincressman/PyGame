import socket
import threading
from server.config import HOST


def start_listener(port, handler):
    """
    Starts a TCP listener on the given port and assigns the handler function to new connections.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, port))
    s.listen()
    print(f"[TCP LISTENING] on {port}")

    def accept_loop():
        while True:
            client, addr = s.accept()
            threading.Thread(target=handler, args=(client, addr), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()

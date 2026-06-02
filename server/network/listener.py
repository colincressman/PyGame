import socket
import threading
from server.config import HOST

# Registry of all open listener sockets, keyed by port, so stop() can close them.
_listener_sockets: dict[int, socket.socket] = {}


def start_listener(port, handler):
    """
    Starts a TCP listener on the given port and dispatches new connections to handler.
    The server socket is stored in _listener_sockets so stop_listener() can close it.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, port))
    s.listen()
    _listener_sockets[port] = s
    print(f"[TCP LISTENING] on {port}")

    def accept_loop():
        while True:
            try:
                client, addr = s.accept()
            except OSError:
                # Socket was closed by stop_listener(); exit the loop cleanly.
                break
            threading.Thread(target=handler, args=(client, addr), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()


def stop_listener(port: int) -> None:
    """Close the listening socket for *port*, causing accept_loop to exit."""
    s = _listener_sockets.pop(port, None)
    if s:
        try:
            s.close()
        except OSError:
            pass

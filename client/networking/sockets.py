# client/networking/sockets.py

import socket
import time

def connect_with_retry(host, port, retries=5, delay=2, timeout=5):
    for attempt in range(1, retries + 1):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            print(f"[CLIENT] Connected to {host}:{port} on attempt {attempt}")
            return sock
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            print(f"[CLIENT] Attempt {attempt}/{retries} failed: {e}")
            time.sleep(delay)
    print(f"[CLIENT] Failed to connect to {host}:{port} after {retries} attempts.")
    return None

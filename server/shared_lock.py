# shared_lock.py
import threading

# === Fine-grained locks ===

# For accessing/updating world_data (tile info)
world_data_lock = threading.Lock()

# For accessing/updating players and player_positions
players_lock = threading.Lock()

# For accessing/updating clients dictionary
clients_lock = threading.Lock()

# For chunk hash/delta tracking (sync, cache)
hashes_lock = threading.Lock()

# For general-purpose use (legacy support — avoid if possible)
global_lock = threading.Lock()

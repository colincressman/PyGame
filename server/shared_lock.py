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

# Mob state — defined here so the locking hierarchy is visible in one place
mobs_lock = threading.Lock()

# World items (dropped loot, spawned pickups) — same rationale
world_items_lock = threading.Lock()

# Placed world objects (campfire, crafting_table, furnace)
placed_objects_lock = threading.Lock()

# For general-purpose use (legacy support — avoid if possible)
global_lock = threading.Lock()

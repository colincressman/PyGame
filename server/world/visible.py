from server.config import CHUNK_RADIUS, CHUNK_SIZE
from server.shared_lock import world_data_lock, players_lock
from collections import defaultdict

# This will be injected or set externally
world_data = {}
player_positions = {}

def set_world_data_reference(world, positions):
    global world_data, player_positions
    world_data = world
    player_positions = positions

def get_visible_chunks_for_player(player_id):
    # Get player position with minimal locking
    with players_lock:
        pos = player_positions.get(player_id)
    if not pos:
        return {}

    px, py = map(int, pos)
    base_cx, base_cy = px // CHUNK_SIZE, py // CHUNK_SIZE
    visible_chunks = {}

    chunk_to_keys = defaultdict(list)
    for dx in range(-CHUNK_RADIUS, CHUNK_RADIUS + 1):
        cx = base_cx + dx
        for dy in range(-CHUNK_RADIUS, CHUNK_RADIUS + 1):
            cy = base_cy + dy
            chunk_key = (cx, cy)
            for i in range(CHUNK_SIZE):
                for j in range(CHUNK_SIZE):
                    tile_key = (cx * CHUNK_SIZE + i, cy * CHUNK_SIZE + j)
                    chunk_to_keys[chunk_key].append(tile_key)

    # Lock world_data only for a brief dictionary lookup
    with world_data_lock:
        for chunk_key, tile_keys in chunk_to_keys.items():
            chunk_tiles = {
                k: world_data[k] for k in tile_keys if k in world_data
            }
            if chunk_tiles:
                visible_chunks[chunk_key] = chunk_tiles

    return visible_chunks
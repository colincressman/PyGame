from server.config import CHUNK_RADIUS, CHUNK_SIZE
from server.shared_lock import world_data_lock, players_lock
from collections import defaultdict

# This will be injected or set externally
world_data = {}
player_positions = {}

# ---------------------------------------------------------------------------
# Pre-computed static layouts (depend only on compile-time constants)
# ---------------------------------------------------------------------------
# All (dx, dy) chunk offsets within the render radius — constant per world config.
_CHUNK_OFFSETS: list[tuple[int, int]] = [
    (dx, dy)
    for dx in range(-CHUNK_RADIUS, CHUNK_RADIUS + 1)
    for dy in range(-CHUNK_RADIUS, CHUNK_RADIUS + 1)
]

# All (ti, tj) tile offsets within a single chunk — same for every chunk.
_TILE_OFFSETS: list[tuple[int, int]] = [
    (i, j) for i in range(CHUNK_SIZE) for j in range(CHUNK_SIZE)
]

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

    px, py = map(int, pos['pos'])
    base_cx, base_cy = px // CHUNK_SIZE, py // CHUNK_SIZE
    visible_chunks = {}

    # Build chunk→tile_key mapping using pre-cached offsets (no per-call loop)
    chunk_to_keys: dict[tuple, list] = {}
    for dx, dy in _CHUNK_OFFSETS:
        cx = base_cx + dx
        cy = base_cy + dy
        origin_x = cx * CHUNK_SIZE
        origin_y = cy * CHUNK_SIZE
        chunk_to_keys[(cx, cy)] = [
            (origin_x + ti, origin_y + tj) for ti, tj in _TILE_OFFSETS
        ]

    # Lock world_data only for a brief dictionary lookup
    with world_data_lock:
        for chunk_key, tile_keys in chunk_to_keys.items():
            chunk_tiles = {
                k: world_data[k] for k in tile_keys if k in world_data
            }
            if chunk_tiles:
                visible_chunks[chunk_key] = chunk_tiles

    return visible_chunks
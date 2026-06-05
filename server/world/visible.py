from server.config import CHUNK_RADIUS, CHUNK_SIZE
from server.shared_lock import world_data_lock, players_lock

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

def get_visible_chunk_keys_for_player(player_id):
    # Get player position with minimal locking
    with players_lock:
        pos = player_positions.get(player_id)
    if not pos:
        return []

    px, py = map(int, pos['pos'])
    base_cx, base_cy = px // CHUNK_SIZE, py // CHUNK_SIZE
    return [
        (base_cx + dx, base_cy + dy)
        for dx, dy in _CHUNK_OFFSETS
    ]


def get_visible_chunks(chunk_keys):
    visible_chunks = {}
    with world_data_lock:
        for chunk_key in chunk_keys:
            origin_x = chunk_key[0] * CHUNK_SIZE
            origin_y = chunk_key[1] * CHUNK_SIZE
            tile_keys = [
                (origin_x + ti, origin_y + tj)
                for ti, tj in _TILE_OFFSETS
            ]
            chunk_tiles = {
                k: world_data[k] for k in tile_keys if k in world_data
            }
            if chunk_tiles:
                visible_chunks[chunk_key] = chunk_tiles

    return visible_chunks


def get_visible_chunks_for_player(player_id):
    return get_visible_chunks(get_visible_chunk_keys_for_player(player_id))

from server.world.chunk_utils import split_tiles_by_chunk
from server.world.io import save_multiple_chunks
from server.world.dyn_chunk_gen import queue_chunks_near_players, process_chunk_queue
from server.shared_lock import players_lock, world_data_lock
import time

# Shared game_state to be injected
world_data = {}

CHUNK_RADIUS = 5
CHUNK_SIZE = 16

def update_world(players, player_positions):
    global world_data

    if not player_positions:
        return

    # 1. Safely copy player positions
    with players_lock:
        player_positions_copy = dict(player_positions)

    # 2. Choose one player's position as the "central" player for sorting
    # In single-player, this works perfectly.
    # In multiplayer, you may want to sort queue per-player or based on the local player.
    first_pos = next(iter(player_positions_copy.values()))
    player_pos = (float(first_pos[0]), float(first_pos[1]))

    # 3. Queue chunks to be generated
    queue_chunks_near_players(player_positions_copy, CHUNK_RADIUS)

    # 4. Generate new chunk data prioritized by player's actual location
    new_data = process_chunk_queue(world_data, player_pos)

    # 5. Apply updates
    if new_data:
        with world_data_lock:
            world_data.update(new_data)

        chunks = split_tiles_by_chunk(new_data)
        save_multiple_chunks(chunks)

    time.sleep(0.01)

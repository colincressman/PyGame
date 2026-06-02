from server.world.chunk_utils import split_tiles_by_chunk
from server.world.io import save_multiple_chunks
from server.world.dyn_chunk_gen import queue_chunks_near_players, process_chunk_queue
from server.world.resource_nodes import tick_respawns as _tick_node_respawns, register_planted_node as _register_planted_node
from server.game_state.placed_objects import tick_growing_plants as _tick_growing_plants
from server.game_state.game_sync import tick_player_deaths as _tick_deaths
from server.shared_lock import players_lock, world_data_lock
from server.config import CHUNK_RADIUS, CHUNK_SIZE

# Shared game_state to be injected
world_data = {}

def update_world(players, player_positions):
    global world_data

    if not player_positions:
        return

    # 1. Safely copy player positions
    with players_lock:
        player_positions_copy = dict(player_positions)

    queue_chunks_near_players(player_positions_copy, CHUNK_RADIUS)

    # 2. Generate new chunk data — heap is now sorted by min-distance to any player,
    #    so all players get fair chunk loading priority.
    new_data = process_chunk_queue(world_data)

    # 3. Apply updates
    if new_data:
        with world_data_lock:
            world_data.update(new_data)

        chunks = split_tiles_by_chunk(new_data)
        save_multiple_chunks(chunks)

    # 4. Tick resource node respawns (broadcasts via resource_nodes._bcast_log)
    _tick_node_respawns()

    # 4b. Tick growing plants; register any that have matured as planted nodes
    import time as _time
    matured = _tick_growing_plants(_time.time())
    for plant in matured:
        _register_planted_node(plant["node_type"], plant["wx"], plant["wy"])

    # 5. Tick player death / respawn timers
    _tick_deaths(players)

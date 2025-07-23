import hashlib
import json
from server.world.visible import get_visible_chunks_for_player
from server.network.net_utils import send_json

last_sent_hashes = {}

def send_if_changed(player_id, sock):
    visible_chunks = get_visible_chunks_for_player(player_id)
    if not visible_chunks:
        return
    
    prev_hashes = last_sent_hashes.get(player_id, {})
    delta = {}
    computed_hashes = {}

    for chunk_key, chunk_tiles in visible_chunks.items():
        # Convert tile keys to string for hashing
        stringified_tiles = {f"{x},{y}": v for (x, y), v in chunk_tiles.items()}
        chunk_data_str = json.dumps(stringified_tiles, sort_keys=True)
        chunk_hash = hashlib.md5(chunk_data_str.encode("utf-8")).hexdigest()
        computed_hashes[chunk_key] = chunk_hash

        if prev_hashes.get(chunk_key) != chunk_hash:
            delta[str(chunk_key)] = stringified_tiles  # Chunk key also stringified for network

    if delta:
        send_json(sock, {"type": "world_chunks", "data": delta})
        # Update the hashes with current values
        last_sent_hashes[player_id] = computed_hashes

from server.world.visible import get_visible_chunks_for_player
from server.network.net_utils import send_json
from server.shared_lock import hashes_lock
from server.world.dyn_chunk_gen import chunk_nodes_cache, chunk_nodes_lock
from server.world.resource_nodes import NODE_TYPES as _NODE_TYPES

# Track which chunk keys have already been sent to each player.
# World tiles are static (biome/elevation never change after generation),
# so a chunk only needs to be sent once per player session.
# Use hashes_lock to guard this dict (reuses existing lock).
_sent_chunks: dict[str, set] = {}


def invalidate_player(player_id: str) -> None:
    """Clear a player's sent-chunk set so all visible chunks are re-sent on next tick.
    Call this when a player (re)connects or force_full is needed."""
    with hashes_lock:
        _sent_chunks.pop(player_id, None)


def forget_player_chunks(player_id: str, chunk_keys: list) -> None:
    """Remove specific chunks from a player's sent-chunk set so they are re-sent next tick.
    Called when the client evicts distant chunk data and needs a fresh delivery on return."""
    with hashes_lock:
        sent = _sent_chunks.get(player_id)
        if sent:
            for ck in chunk_keys:
                sent.discard(tuple(ck))


def send_if_changed(player_id, sock, force_full=False):
    visible_chunks = get_visible_chunks_for_player(player_id)
    if not visible_chunks:
        return

    with hashes_lock:
        if force_full:
            _sent_chunks.pop(player_id, None)
        already_sent = _sent_chunks.get(player_id)
        if already_sent is None:
            already_sent = set()
            _sent_chunks[player_id] = already_sent

    # Only build payloads for chunks this player hasn't received yet
    delta = {}
    for chunk_key, chunk_tiles in visible_chunks.items():
        if chunk_key not in already_sent:
            delta[str(chunk_key)] = {f"{x},{y}": v for (x, y), v in chunk_tiles.items()}

    if delta:
        # Attach node definitions for all newly-sent chunks
        # Inject "max_hp" so the client doesn't need a local copy of NODE_TYPES hp values.
        node_data = {}
        with chunk_nodes_lock:
            for chunk_key_str in delta:
                cx, cy = map(int, chunk_key_str.strip("()").split(","))
                nodes = chunk_nodes_cache.get((cx, cy))
                if nodes:
                    node_data[chunk_key_str] = [
                        {**n, "max_hp": _NODE_TYPES[n["type"]]["hp"]}
                        if n["type"] in _NODE_TYPES else n
                        for n in nodes
                        if n is not None
                    ]

        payload = {"type": "world_chunks", "data": delta}
        if node_data:
            payload["node_data"] = node_data

        try:
            send_json(sock, payload)
        except OSError as e:
            print(f"[SYNC] send failed for {player_id}: {e}")
            return

        # Mark all successfully sent chunks
        with hashes_lock:
            already_sent.update(visible_chunks.keys())

from .shared_lock import clients_lock, players_lock, hashes_lock
from server.game_state.sync import invalidate_player as _sync_invalidate
from server.game_state.game_sync import invalidate_node_snapshot as _game_sync_invalidate
from server.player_save import save_player

# Persists last known position across disconnect/reconnect within the same server session
last_positions = {}  # {player_id: [x, y]}

# These should be imported or injected from the main server game_state
clients = None
players = None
player_positions = None
pending_udp_assignments = None
last_world_hashes = None


def set_cleanup_refs(refs):
    global clients, players, player_positions, pending_udp_assignments, last_world_hashes
    clients = refs["clients"]
    players = refs["players"]
    player_positions = refs["player_positions"]
    pending_udp_assignments = refs["pending_udp_assignments"]
    last_world_hashes = refs.get("last_world_hashes")


def cleanup_player(player_id):
    """Remove a player from all relevant server data structures."""

    # Remove from clients
    with clients_lock:
        world_sock = clients["world"].pop(player_id, None)
        state_sock = clients["game_state"].pop(player_id, None)
        clients["udp"].pop(player_id, None)

    # Close sockets safely outside the lock
    try:
        if world_sock:
            world_sock.close()
    except:
        pass
    try:
        if state_sock:
            state_sock.close()
    except:
        pass

    # Remove from player-related structures; capture snapshot for disk save outside lock
    with players_lock:
        player_snapshot = dict(players[player_id]) if player_id in players else None
        # Save last position for in-session rejoin (in-memory fallback)
        if player_snapshot and "pos" in player_snapshot:
            last_positions[player_id] = list(player_snapshot["pos"])
        players.pop(player_id, None)
        player_positions.pop(player_id, None)
        if pending_udp_assignments:
            pending_udp_assignments.discard(player_id)
        if last_world_hashes:
            last_world_hashes.pop(player_id, None)

    # Clear sent-chunk cache so the next connection for this ID gets a full resend
    _sync_invalidate(player_id)
    _game_sync_invalidate(player_id)

    # Persist player state to disk outside all locks (avoids blocking other threads)
    if player_snapshot:
        save_player(player_id, player_snapshot)

    print(f"[CLEANUP] Removed player: {player_id}")

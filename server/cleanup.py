from .shared_lock import clients_lock, players_lock

# These should be imported or injected from the main server game_state
clients = None
players = None
player_positions = None
pending_udp_assignments = None
last_world_hashes = None


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

    # Remove from player-related structures
    with players_lock:
        players.pop(player_id, None)
        player_positions.pop(player_id, None)
        if pending_udp_assignments:
            pending_udp_assignments.discard(player_id)
        if last_world_hashes:
            last_world_hashes.pop(player_id, None)

    print(f"[CLEANUP] Removed player: {player_id}")

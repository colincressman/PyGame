# server/game_state/players.py

from server.shared_lock import players_lock

# Player game_state
players = {}  # player_id -> player_data (dict of pos, health, level, etc)
player_positions = {}  # player_id -> [x, y]
pending_udp_assignments = set()


def update_player_position(player_id, pos):
    with players_lock:
        player_positions[player_id] = pos
        if player_id in players:
            players[player_id]["pos"] = pos


def get_player_position(player_id):
    with players_lock:
        return player_positions.get(player_id)


def remove_player(player_id):
    with players_lock:
        players.pop(player_id, None)
        player_positions.pop(player_id, None)
        pending_udp_assignments.discard(player_id)


def assign_new_player(player_id, initial_data, addr=None):
    with players_lock:
        players[player_id] = initial_data
        player_positions[player_id] = initial_data["pos"]
        pending_udp_assignments.add(player_id)
        # Optionally handle `addr` elsewhere


def get_all_positions():
    with players_lock:
        return dict(player_positions)


def get_all_players():
    with players_lock:
        return dict(players)


def is_pending_assignment(player_id):
    with players_lock:
        return player_id in pending_udp_assignments


def mark_assignment_complete(player_id):
    with players_lock:
        pending_udp_assignments.discard(player_id)

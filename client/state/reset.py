from config import *
from state.player import *
from networking.interpolation import player_interpolator

def reset_client_state():
    global player_data, players_data, world_data, full_world_data
    global chunk_cache, map_surface_cache, last_player_chunk, is_fullscreen
    global ping, last_ping_sent, awaiting_ping, client_running, player_id
    global WINDOW_WIDTH, WINDOW_HEIGHT, screen

    player_data = {"pos": [680, 272], "health": 100, "level": 1}
    players_data.clear()
    world_data.clear()
    full_world_data.clear()
    chunk_cache.clear()

    map_surface_cache = None
    last_player_chunk = None
    is_fullscreen = False
    screen = None
    WINDOW_WIDTH, WINDOW_HEIGHT = 1280, 720

    ping = 0
    last_ping_sent = 0
    awaiting_ping = False
    client_running = True
    player_id = None
    
    # Clear interpolation data
    player_interpolator.position_history.clear()
    player_interpolator.velocities.clear()
    player_interpolator.last_update_time.clear()

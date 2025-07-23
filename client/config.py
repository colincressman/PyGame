# client/config.py
import os
from queue import Queue
import queue

# Server connection details
HOST = '127.0.0.1'
PORT_WORLD = 6000
PORT_STATE = 6001
PORT_UDP = 6002
BUFFER_SIZE = 4096
TILE_SIZE = 32
CHUNK_SIZE = 16
LOG_FILE = "client_log.txt"

# Display settings
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
TILE_SIZE = 32
FONT_NAME = "Arial"
FONT_SIZE = 16

# World handling
CHUNK_SIZE = 16
CHUNK_RADIUS_X = 3
CHUNK_RADIUS_Y = 3
FULL_WORLD_UPDATE_INTERVAL = 5  # seconds

# Timing
TARGET_FPS = 60
PLAYER_SPEED = 6
SPRINT_SPEED = 9

# Player defaults
DEFAULT_PLAYER_ID = 'Player1'

# Debugging
DEBUG_MODE = True

BIOME_ID_TO_NAME = {
    0: "ocean", 1: "beach", 2: "swamp", 3: "river", 4: "plains",
    5: "forest", 6: "desert", 7: "alt_desert", 8: "tropical",
    9: "tundra", 10: "mountain"
}

CLIFF_ID_TO_NAME = {
    100: "cliff_north", 101: "cliff_south", 102: "cliff_east", 103: "cliff_west",
    104: "cliff_northeast", 105: "cliff_northwest", 106: "cliff_southeast", 107: "cliff_southwest",
    108: "cliff_tall_south", 109: "cliff_tall_southwest", 110: "cliff_tall_southeast"
}

# Ensure paths are correct regardless of where the script is run from
base_dir = os.path.dirname(os.path.abspath(__file__))
tiles_folder = os.path.join(base_dir, "tiles")
tile_paths = {
    name: os.path.join(tiles_folder, f"{name}.png")
    for name in [
        "ocean", "beach", "swamp", "river", "plains", "forest",
        "desert", "alt_desert", "tropical", "tundra", "mountain",
        "cliff_north", "cliff_south", "cliff_east", "cliff_west",
        "cliff_northeast", "cliff_northwest", "cliff_southeast", "cliff_southwest",
        "cliff_tall_south", "cliff_tall_southwest", "cliff_tall_southeast"
    ]
}

# Game State
players_data = {}
world_data = {}
full_world_data = {}
running = True
show_map = False
map_needs_redraw = True

# Rendering and Camera
chunk_cache = {}
map_surface_cache = None
last_player_chunk = None
is_fullscreen = False
screen = None

# Networking
client_running = True
ping = 0
last_ping_sent = 0
awaiting_ping = False

scheduled_chunk_renders = set()
chunk_queue = Queue()
render_queue = queue.PriorityQueue()
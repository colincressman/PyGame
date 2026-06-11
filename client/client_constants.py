import os
import pygame


# Server connection defaults
HOST = "127.0.0.1"
PORT_WORLD = 6000
PORT_STATE = 6001
PORT_UDP = 6002
BUFFER_SIZE = 4096
LOG_FILE = "client_log.txt"

# World / rendering constants
TILE_SIZE = 32
CHUNK_SIZE = 16
MINIMAP_SIZE = 128
MINIMAP_TILE_PX = 2
MINIMAP_PADDING = 8
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 720
FONT_NAME = "Arial"
FONT_SIZE = 16
CHUNK_RADIUS_X = 3
CHUNK_RADIUS_Y = 3
FULL_WORLD_UPDATE_INTERVAL = 5
TARGET_FPS = 60
WORLD_MAX_TILES = 2000

# Combat / movement constants
KNOCKBACK_DECAY = 12.0
PARRY_WINDOW = 0.15
PLAYER_SPEED = 6
SPRINT_SPEED = 9
STEALTH_SPEED = 3

# Player / inventory defaults
INVENTORY_SIZE = 48
DEFAULT_PLAYER_ID = "Player1"
PLAYER_START_X = 680
PLAYER_START_Y = 272
DEBUG_MODE = True

# Chat constants
CHAT_MAX_MESSAGES = 50
CHAT_DISPLAY = 10

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TILES_FOLDER = os.path.join(BASE_DIR, "tiles")
TILE_PATHS = {
    name: os.path.join(TILES_FOLDER, f"{name}.png")
    for name in [
        "ocean", "beach", "swamp", "river", "plains", "forest",
        "desert", "alt_desert", "tropical", "tundra", "mountain",
        "cliff_north", "cliff_south", "cliff_east", "cliff_west",
        "cliff_northeast", "cliff_northwest", "cliff_southeast", "cliff_southwest",
        "cliff_tall_south", "cliff_tall_southwest", "cliff_tall_southeast",
    ]
}

DEFAULT_KEYBINDS = {
    "move_up": pygame.K_w,
    "move_down": pygame.K_s,
    "move_left": pygame.K_a,
    "move_right": pygame.K_d,
    "sprint": pygame.K_LSHIFT,
    "crouch": pygame.K_LCTRL,
    "roll": pygame.K_SPACE,
    "inventory": pygame.K_e,
    "interact": pygame.K_f,
    "door": pygame.K_r,
    "map": pygame.K_m,
    "stats": pygame.K_p,
    "attack": -1,
    "block": -2,
}

DEFAULT_PLAYER_APPEARANCE = {
    "body": "male",
    "hair_style": "plain",
    "hair_color": "dark_brown",
    "skin_tint": None,
    "back_ext": None,
    "back_ext_color": "white",
    "aura": None,
}

SETTINGS_DIR = os.path.join(BASE_DIR, "config")
KEYBINDS_FILE = os.path.join(SETTINGS_DIR, "keybinds.json")
VISITED_FILE = os.path.join(SETTINGS_DIR, "visited_chunks.json")
MAP_MEMORY_FILE = os.path.join(SETTINGS_DIR, "map_memory.json")

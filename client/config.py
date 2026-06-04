# client/config.py
import os
import json
from queue import Queue
import queue
import pygame
from world_types import BIOME_ID_TO_NAME, CLIFF_ID_TO_NAME

# Server connection details
HOST = '127.0.0.1'
PORT_WORLD = 6000
PORT_STATE = 6001
PORT_UDP = 6002
BUFFER_SIZE = 4096
TILE_SIZE = 32
CHUNK_SIZE = 16
LOG_FILE = "client_log.txt"

# ---------------------------------------------------------------------------
# Combat / physics (must match server/config.py)
# ---------------------------------------------------------------------------
KNOCKBACK_DECAY = 12.0  # exponential decay rate for knockback velocity
PARRY_WINDOW    = 0.15  # seconds after block-start for a perfect parry

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
INVENTORY_SIZE = 48  # total slot count including all equipment slots

# ---------------------------------------------------------------------------
# Minimap rendering
# ---------------------------------------------------------------------------
MINIMAP_SIZE    = 128   # pixels square
MINIMAP_TILE_PX = 2     # pixels per world tile
MINIMAP_PADDING = 8     # offset from top-right corner of the screen

# Display settings
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FONT_NAME = "Arial"
FONT_SIZE = 16

# World handling
CHUNK_RADIUS_X = 3
CHUNK_RADIUS_Y = 3
FULL_WORLD_UPDATE_INTERVAL = 5  # seconds

# Timing
TARGET_FPS = 60
PLAYER_SPEED = 6
SPRINT_SPEED = 9
STEALTH_SPEED = 3

# World limits — must match WORLD_RADIUS in server/config.py
WORLD_MAX_TILES = 2000

# Player defaults
DEFAULT_PLAYER_ID = 'Player1'
PLAYER_START_X = 680
PLAYER_START_Y = 272

# Debugging
DEBUG_MODE = True

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
client_running = True

# Ping tracking
ping = 0
last_ping_sent = 0.0
awaiting_ping = False

# Rendering and Camera
chunk_cache = {}
map_surface_cache = None
last_player_chunk = None
world_data_loaded_chunks: set = set()  # tracks which (cx,cy) chunks have tile data in world_data
is_fullscreen = False
screen = None

# Networking
last_player_id = None  # persists across sessions for rejoin
session_token = None  # assigned by server; required on UDP/TCP packets
session_id = 0  # incremented each time a game session ends; threads compare against their captured value

# Player stats (server-authoritative, updated by game state channel)
player_health = 100
player_health_max = 100
hit_flash_timer = 0.0  # seconds remaining for red hit-flash overlay
player_stamina = 100.0
player_stamina_max = 100.0
player_attack_power = 10.0
player_speed_bonus = 0.0   # tiles/sec bonus on top of base PLAYER_SPEED
player_level = 1
player_exp = 0
player_exp_next = 100
player_stat_points = 0
player_coins = 0
player_hp_regen = 0.0
player_sp_regen_bonus = 0.0
player_slow_timer = 0.0
player_dead = False          # True while waiting to respawn
player_respawn_in = 0.0     # seconds until respawn (countdown)
player_defense = 0          # total defense from equipped armor

# Dodge roll (client-predicted; rolling flag sent to server for i-frame)
rolling: bool = False        # True for the 0.25 s roll window
roll_cooldown: float = 0.0   # seconds until next roll is allowed

# World time (server-authoritative)  0.0 = midnight, 12.0 = noon, 24.0 = midnight
world_time = 12.0
sleeping   = False   # True while the server has this player marked as sleeping

# Weather (server-authoritative): "clear" | "cloudy" | "rain" | "snow" | "fog"
weather: str = "clear"

# Minimap HUD info — updated every frame in client.py
current_biome_name: str   = ""
current_elevation: float  = 0.0

# Active status effects (server-authoritative)
poison_timer: float = 0.0

# Camera-to-world pixel offset — updated each render frame for light_sources.py
camera_offset_x: float = 0.0
camera_offset_y: float = 0.0

# Inventory (server-authoritative; each slot is [item_id, qty] or None)
player_inventory = [None] * INVENTORY_SIZE  # 0-35 bags, 36=head, 37=chest, 38=ring1, 39=ring2, 40=pants, 41=shoes, 42=arms, 43=necklace, 44=back, 45=shield, 46=shoulders
hotbar_slot = 0        # currently selected hotbar index (0-8)
show_inventory = False
show_menu = False          # True while the pause menu is displayed
menu_click_pos = None      # set by handle_events on left-click while menu is open
show_stats = False         # True while the character stats screen is open
stat_click_pos = None      # set by handle_events on left-click while stats screen is open
show_crafting     = False  # retained for compatibility — craft is now an inventory tab
crafting_category = "all"
crafting_scroll   = 0
selected_recipe   = None

# Inventory panel tab
inventory_tab: str = "bag"          # "bag" | "craft"

# Station popup (opened via F near furnace / campfire / crafting_table)
show_station_popup: str | None = None  # "furnace" | "campfire" | "crafting_table" | None
station_popup_uid:  str | None = None  # uid of the placed object whose popup is open
station_popup_scroll: int = 0
station_popup_recipe: int | None = None
station_popup_tab: str = "weapon"   # active tab for crafting_table popup

# Chest interaction
open_chest_uid: str | None = None   # uid of the chest currently open, or None
chest_drag_slot: int | None = None  # chest-side slot being dragged from, or None
chest_ui_hold_until: float = 0.0    # briefly preserve optimistic chest state across stale server snapshots

# Part Combiner state
combiner_slots: list = [None, None, None, None]  # inv slot indices for [Mold, Primary, Handle, Binding]
combiner_selected_slot: int = -1  # which combiner slot is active (-1 = none)

# Embedder state
embedder_slots: list = [None, None]   # [item_inv_idx, gem_inv_idx]
embedder_selected_slot: int = -1      # 0=item, 1=gem, -1=none

# Repair state (crafting_table → Repair tab)
repair_selected_slot: int | None = None  # inv slot index of item to repair

# Drag-and-drop state (cleared when inventory closes or session resets)
drag_slot = None       # source slot index while dragging, or None
drag_item = None       # [item_id, qty] copy while dragging, or None

# Outbound messages for the game-state TCP thread to forward to the server
state_outbox: queue.Queue = queue.Queue()

# Player animation / combat state
player_facing    = "down"   # last movement direction ("down"/"up"/"left"/"right")
is_moving        = False    # True when the player moved this tick
is_running       = False    # True when moving + Shift held (sprint)
is_attacking     = False    # True while attack animation is playing
is_stealthy      = False    # True while player is sneaking (Ctrl held)
last_attack_time = 0.0     # time.time() of last attack

# Outbound UDP messages (attack events, etc.) drained by the UDP send thread
udp_outbox: queue.Queue = queue.Queue()

# World items visible near the player (server-authoritative)
# {uid: {"item_id": int, "pos": [x, y], "qty": int}}
world_items = {}

# Mobs visible near the player (server-authoritative)
# list of {id, type, pos, health, health_max}
mobs: list = []

# NPCs near the player (server-authoritative)
# list of {id, type, name, greeting, pos: [wx, wy]}
npcs: list = []

# Resource nodes visible near the player (server-authoritative)
# {node_id: {"type": str, "wx": int, "wy": int, "max_hp": int, "depleted": bool, "hits": int}}
world_nodes: dict = {}

# Placed world objects near the player (server-authoritative)
# {uid: {"type": str, "pos": [tx, ty], "placed_by": str[, "state": str]}}
placed_objects: dict = {}

# Station types within interaction range this frame — recomputed each tick
nearby_stations: set = set()

# Placement preview (updated each frame before handle_events)
mouse_tile: tuple = (0, 0)         # world tile currently under the mouse cursor
placement_blocked: bool = False    # True when mouse_tile is occupied
pickup_mode: bool = False          # True while Z pickup mode is active

scheduled_chunk_renders = set()
chunk_queue = Queue()
render_queue = queue.PriorityQueue()

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
chat_open: bool = False          # True while chat input box is visible
chat_input: str = ""             # text currently being typed
# Each entry: {"sender": str, "text": str, "ts": float}
chat_messages: list = []
CHAT_MAX_MESSAGES: int = 50     # history kept in memory
CHAT_DISPLAY: int = 10          # lines shown on screen at once
visited_chunks: set = set()     # (chunk_x, chunk_y) tuples seen by player; used by minimap
player_creative: bool = False   # True when the server has creative mode active
creative_scroll: int = 0        # row offset for creative inventory scroll
connection_error: str = ""      # set when server rejects login (e.g. banned)

# ---------------------------------------------------------------------------
# Controls / keybinds (remappable via the controls screen)
# ---------------------------------------------------------------------------
keybinds: dict = {
    "move_up":    pygame.K_w,
    "move_down":  pygame.K_s,
    "move_left":  pygame.K_a,
    "move_right": pygame.K_d,
    "sprint":     pygame.K_LSHIFT,
    "crouch":     pygame.K_LCTRL,
    "roll":       pygame.K_SPACE,
    "inventory":  pygame.K_e,
    "interact":   pygame.K_f,
    "door":       pygame.K_r,
    "map":        pygame.K_m,
    "stats":      pygame.K_p,
    # -1 = LMB, -2 = RMB (mouse button sentinels); 0 = unbound; >0 = pygame key
    "attack":     -1,
    "block":      -2,
}
show_controls: bool       = False        # True while controls rebind screen is open
controls_click_pos        = None         # set by handle_events on LMB while controls open
controls_listen: str | None = None       # action name being rebound, or None

# Block / Parry
is_blocking: bool        = False         # True while RMB is held in the game world
block_start_time: float  = 0.0          # client-side timestamp for HUD parry-flash window

# Active status effects (client-predicted / server-authoritative)
burn_timer: float = 0.0

# Dungeons near the player (server-authoritative)
dungeons: list = []

# ---------------------------------------------------------------------------
# NPC shop state
# ---------------------------------------------------------------------------
# Set when a player interacts with an NPC (F key within range).
# Cleared when the shop panel is closed.
show_shop: bool              = False
shop_npc_type: str | None    = None  # "merchant" | "blacksmith" | "healer" | "innkeeper"
shop_npc_id: str | None      = None  # unique NPC id string
shop_items: list             = []    # list of {"id", "name", "price", "qty"} from server
shop_scroll: int             = 0     # vertical scroll offset for shop list
shop_tab: str                = "buy" # "buy" | "sell"

# ---------------------------------------------------------------------------
# Character appearance / customisation
# ---------------------------------------------------------------------------
player_appearance: dict = {
    "body":           "male",        # "male" | "female" | "muscular" | "teen"
    "hair_style":     "plain",       # subfolder name under hair/
    "hair_color":     "dark_brown",  # colour variant name (hair/ sheets are colour-subdir)
    "skin_tint":      None,          # (R,G,B,A) tint or None for default
    "back_ext":       None,          # wing/cape type: "feathered"|"bat"|"pixie"|"lunar"|"monarch"|"dragonfly"|None
    "back_ext_color": "white",       # colour name for the wing/cape
    "aura":           None,          # "fire"|"ice"|"golden"|"shadow"|"rainbow"|None
}
show_char_creator: bool = False      # True while the character editor screen is open

# ---------------------------------------------------------------------------
# Active projectiles (server-authoritative, rendered client-side)
# ---------------------------------------------------------------------------
projectiles: list = []   # list of {"uid", "pos": [x,y], "element"}

# ---------------------------------------------------------------------------
# Keybind persistence helpers
# ---------------------------------------------------------------------------
_SETTINGS_DIR  = os.path.join(os.path.dirname(__file__), "config")
_KEYBINDS_FILE = os.path.join(_SETTINGS_DIR, "keybinds.json")


def load_keybinds() -> None:
    """Overwrite keybinds dict with values from config/keybinds.json (if it exists)."""
    global keybinds
    try:
        with open(_KEYBINDS_FILE, "r") as _f:
            _data = json.load(_f)
        for _k, _v in _data.items():
            if _k in keybinds and isinstance(_v, int):
                keybinds[_k] = _v
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass  # first run or corrupt file — use compiled defaults


def save_keybinds() -> None:
    """Write current keybinds dict to config/keybinds.json."""
    try:
        os.makedirs(_SETTINGS_DIR, exist_ok=True)
        with open(_KEYBINDS_FILE, "w") as _f:
            json.dump(keybinds, _f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Visited-chunks persistence (fog-of-war map memory)
# ---------------------------------------------------------------------------
_VISITED_FILE = os.path.join(_SETTINGS_DIR, "visited_chunks.json")


def load_visited_chunks() -> None:
    """Merge previously visited chunks into the in-memory set."""
    try:
        with open(_VISITED_FILE, "r") as _f:
            _data = json.load(_f)
        visited_chunks.update(tuple(_c) for _c in _data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def save_visited_chunks() -> None:
    """Write current visited_chunks set to disk."""
    try:
        os.makedirs(_SETTINGS_DIR, exist_ok=True)
        with open(_VISITED_FILE, "w") as _f:
            json.dump([list(_c) for _c in visited_chunks], _f)
    except OSError:
        pass


# Load persisted keybinds immediately so callers always see the saved values.
load_keybinds()
# Load persisted map exploration history.
load_visited_chunks()

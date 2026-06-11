# client/config.py
import os
import json
import time
import threading
from queue import Queue
import queue
import pygame
try:
    import orjson as _fast_json
except ImportError:
    _fast_json = None
from world_types import BIOME_ID_TO_NAME, CLIFF_ID_TO_NAME
from client_constants import (
    BUFFER_SIZE,
    CHAT_DISPLAY as DEFAULT_CHAT_DISPLAY,
    CHAT_MAX_MESSAGES as DEFAULT_CHAT_MAX_MESSAGES,
    CHUNK_RADIUS_X,
    CHUNK_RADIUS_Y,
    CHUNK_SIZE,
    DEBUG_MODE as DEFAULT_DEBUG_MODE,
    DEFAULT_KEYBINDS,
    DEFAULT_PLAYER_APPEARANCE,
    DEFAULT_PLAYER_ID as DEFAULT_PLAYER_ID_DEFAULT,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    FONT_NAME,
    FONT_SIZE,
    FULL_WORLD_UPDATE_INTERVAL,
    HOST as DEFAULT_HOST,
    INVENTORY_SIZE,
    KEYBINDS_FILE,
    KNOCKBACK_DECAY,
    LOG_FILE,
    MAP_MEMORY_FILE,
    MINIMAP_PADDING,
    MINIMAP_SIZE,
    MINIMAP_TILE_PX,
    PARRY_WINDOW,
    PLAYER_SPEED,
    PLAYER_START_X,
    PLAYER_START_Y,
    PORT_STATE,
    PORT_UDP,
    PORT_WORLD,
    SETTINGS_DIR,
    SPRINT_SPEED,
    STEALTH_SPEED,
    TARGET_FPS,
    TILE_PATHS,
    TILE_SIZE,
    VISITED_FILE,
    WORLD_MAX_TILES,
)

# Mutable launch/session settings seeded from constants.
HOST = DEFAULT_HOST
WINDOW_WIDTH = DEFAULT_WINDOW_WIDTH
WINDOW_HEIGHT = DEFAULT_WINDOW_HEIGHT
DEFAULT_PLAYER_ID = DEFAULT_PLAYER_ID_DEFAULT
DEBUG_MODE = DEFAULT_DEBUG_MODE
tile_paths = dict(TILE_PATHS)
debug_overlay_mode = 1 if DEBUG_MODE else 0
debug_chunk_apply_ms: float = 0.0
debug_chunk_apply_count: int = 0
debug_world_recv_ms: float = 0.0
debug_world_recv_chunks: int = 0
debug_world_recv_nodes: int = 0

# Game State
players_data = {}
world_data = {}
full_world_data = {}
client_running = True
map_memory_dirty: bool = False
map_memory_last_save: float = 0.0
_map_memory_lock = threading.Lock()

# Ping tracking
ping = 0
last_ping_sent = 0.0
awaiting_ping = False

# Rendering and Camera
chunk_cache = {}
map_surface_cache = None
last_player_chunk = None
last_cache_cleanup_chunk = None
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

# Territory / faction-claim HUD state
current_territory_owner: str | None = None
current_territory_tag: str | None = None
territory_state_ready: bool = False
territory_banner_text: str = ""
territory_banner_started_at: float = 0.0
territory_banner_until: float = 0.0

# Shared map / POI state
known_dungeons: dict = {}
known_towns: dict = {}
faction_claims: list = []
waypoints: list = []

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
pending_private_chest: bool = False

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
mob_entities: dict = {}

# NPCs near the player (server-authoritative)
# list of {id, type, name, greeting, pos: [wx, wy]}
npcs: list = []

# Resource nodes visible near the player (server-authoritative)
# {node_id: {"type": str, "wx": int, "wy": int, "max_hp": int, "depleted": bool, "hits": int}}
world_nodes: dict = {}
node_by_tile: dict = {}

# Placed world objects near the player (server-authoritative)
# {uid: {"type": str, "pos": [tx, ty], "placed_by": str[, "state": str]}}
placed_objects: dict = {}
object_by_tile: dict = {}
floor_by_tile: dict = {}
stations_by_chunk: dict = {}

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
CHAT_MAX_MESSAGES: int = DEFAULT_CHAT_MAX_MESSAGES     # history kept in memory
CHAT_DISPLAY: int = DEFAULT_CHAT_DISPLAY          # lines shown on screen at once
visited_chunks: set = set()     # (chunk_x, chunk_y) tuples seen by player; used by minimap
player_creative: bool = False   # True when the server has creative mode active
creative_scroll: int = 0        # row offset for creative inventory scroll
connection_error: str = ""      # set when server rejects login (e.g. banned)

# ---------------------------------------------------------------------------
# Controls / keybinds (remappable via the controls screen)
# ---------------------------------------------------------------------------
keybinds: dict = dict(DEFAULT_KEYBINDS)
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
player_appearance: dict = dict(DEFAULT_PLAYER_APPEARANCE)
show_char_creator: bool = False      # True while the character editor screen is open
first_join_setup_required: bool = False

# ---------------------------------------------------------------------------
# Active projectiles (server-authoritative, rendered client-side)
# ---------------------------------------------------------------------------
projectiles: list = []   # list of {"uid", "pos": [x,y], "element"}

# ---------------------------------------------------------------------------
# Keybind persistence helpers
# ---------------------------------------------------------------------------
_SETTINGS_DIR = SETTINGS_DIR
_KEYBINDS_FILE = KEYBINDS_FILE
_MAP_MEMORY_FILE = MAP_MEMORY_FILE
_MAP_MEMORY_SAVE_INTERVAL = 60.0


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
_VISITED_FILE = VISITED_FILE


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


def _serialize_map_tile(tile):
    if isinstance(tile, dict):
        out = {}
        for key in ("biome", "elevation", "cliff"):
            if key in tile:
                out[key] = tile[key]
        return out
    return tile


def _deserialize_map_tile(tile):
    if isinstance(tile, dict):
        return dict(tile)
    return tile


def mark_map_memory_dirty() -> None:
    global map_memory_dirty
    with _map_memory_lock:
        map_memory_dirty = True


def remember_world_tiles(tiles: dict) -> None:
    global map_memory_dirty
    changed = False
    with _map_memory_lock:
        for key, value in tiles.items():
            stored = _serialize_map_tile(value)
            if full_world_data.get(key) != stored:
                full_world_data[key] = stored
                changed = True
        if changed:
            map_memory_dirty = True


def save_map_memory(force: bool = False) -> None:
    global map_memory_dirty, map_memory_last_save
    now = time.time()
    with _map_memory_lock:
        if not force and (not map_memory_dirty or now - map_memory_last_save < _MAP_MEMORY_SAVE_INTERVAL):
            return
        tiles_snapshot = [
            [tx, ty, _serialize_map_tile(tile)]
            for (tx, ty), tile in full_world_data.items()
        ]
        dungeons_snapshot = list(known_dungeons.values())
        towns_snapshot = list(known_towns.values())
        waypoints_snapshot = list(waypoints)
    try:
        os.makedirs(_SETTINGS_DIR, exist_ok=True)
        payload = {
            "tiles": tiles_snapshot,
            "dungeons": dungeons_snapshot,
            "towns": towns_snapshot,
            "waypoints": waypoints_snapshot,
        }
        if _fast_json is not None:
            with open(_MAP_MEMORY_FILE, "wb") as _f:
                _f.write(_fast_json.dumps(payload))
        else:
            with open(_MAP_MEMORY_FILE, "w", encoding="utf-8") as _f:
                json.dump(payload, _f)
        with _map_memory_lock:
            map_memory_dirty = False
            map_memory_last_save = now
    except OSError:
        pass


def load_map_memory() -> None:
    global map_memory_dirty, map_memory_last_save, waypoints
    try:
        with open(_MAP_MEMORY_FILE, "r", encoding="utf-8") as _f:
            payload = json.load(_f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return

    with _map_memory_lock:
        tiles = payload.get("tiles", [])
        if isinstance(tiles, list):
            for entry in tiles:
                if not isinstance(entry, list) or len(entry) != 3:
                    continue
                tx, ty, tile = entry
                full_world_data[(int(tx), int(ty))] = _deserialize_map_tile(tile)

        for dng in payload.get("dungeons", []):
            if isinstance(dng, dict) and "id" in dng:
                known_dungeons[str(dng["id"])] = dict(dng)
        for town in payload.get("towns", []):
            if isinstance(town, dict) and "id" in town:
                known_towns[str(town["id"])] = dict(town)
        loaded_waypoints = payload.get("waypoints", [])
        if isinstance(loaded_waypoints, list):
            waypoints = [dict(wp) for wp in loaded_waypoints if isinstance(wp, dict)]

        map_memory_dirty = False
        map_memory_last_save = time.time()


def merge_known_dungeons(dungeons: list) -> None:
    global map_memory_dirty
    changed = False
    with _map_memory_lock:
        for dng in dungeons or []:
            if not isinstance(dng, dict):
                continue
            dng_id = dng.get("id")
            if not dng_id:
                continue
            entry = dict(dng)
            if known_dungeons.get(dng_id) != entry:
                known_dungeons[dng_id] = entry
                changed = True
        if changed:
            map_memory_dirty = True


def merge_known_towns(towns: list) -> None:
    global map_memory_dirty
    changed = False
    with _map_memory_lock:
        for town in towns or []:
            if not isinstance(town, dict):
                continue
            town_id = town.get("id")
            if not town_id:
                continue
            entry = dict(town)
            if known_towns.get(town_id) != entry:
                known_towns[town_id] = entry
                changed = True
        if changed:
            map_memory_dirty = True


def add_waypoint(tile_x: int, tile_y: int) -> dict:
    global map_memory_dirty
    with _map_memory_lock:
        next_idx = 1
        for wp in waypoints:
            try:
                next_idx = max(next_idx, int(str(wp.get("id", "wp-0")).split("-")[-1]) + 1)
            except ValueError:
                continue
        waypoint = {
            "id": f"wp-{next_idx}",
            "name": f"Waypoint {next_idx}",
            "pos": [int(tile_x), int(tile_y)],
        }
        waypoints.append(waypoint)
        map_memory_dirty = True
        return waypoint


def remove_nearest_waypoint(tile_x: int, tile_y: int, max_dist: float = 10.0) -> dict | None:
    global map_memory_dirty
    with _map_memory_lock:
        best_idx = None
        best_dsq = max_dist * max_dist
        for idx, wp in enumerate(waypoints):
            pos = wp.get("pos")
            if not isinstance(pos, list) or len(pos) != 2:
                continue
            dx = float(pos[0]) - float(tile_x)
            dy = float(pos[1]) - float(tile_y)
            dsq = dx * dx + dy * dy
            if dsq <= best_dsq:
                best_dsq = dsq
                best_idx = idx
        if best_idx is None:
            return None
        removed = waypoints.pop(best_idx)
        map_memory_dirty = True
        return removed


def run_map_memory_saver() -> None:
    """Background autosave loop for exploration memory so disk I/O never blocks rendering."""
    my_session = session_id
    while session_id == my_session and client_running:
        try:
            save_map_memory()
        except Exception:
            pass
        time.sleep(1.0)


def _tile_int_pair(pos_x, pos_y):
    return int(pos_x), int(pos_y)


def _chunk_key_from_tile(tile_x: int, tile_y: int) -> tuple[int, int]:
    return tile_x // CHUNK_SIZE, tile_y // CHUNK_SIZE


def rebuild_world_node_index() -> None:
    global node_by_tile
    new_index: dict = {}
    for node_id, node in world_nodes.items():
        tile = _tile_int_pair(node.get("wx", 0), node.get("wy", 0))
        new_index.setdefault(tile, set()).add(node_id)
    node_by_tile = new_index


def set_world_nodes(new_nodes: dict) -> None:
    global world_nodes
    world_nodes = new_nodes
    rebuild_world_node_index()


def upsert_world_node(node_id: str, node: dict) -> None:
    old_node = world_nodes.get(node_id)
    if old_node is not None:
        old_tile = _tile_int_pair(old_node.get("wx", 0), old_node.get("wy", 0))
        old_ids = node_by_tile.get(old_tile)
        if old_ids is not None:
            old_ids.discard(node_id)
            if not old_ids:
                node_by_tile.pop(old_tile, None)
    world_nodes[node_id] = node
    tile = _tile_int_pair(node.get("wx", 0), node.get("wy", 0))
    node_by_tile.setdefault(tile, set()).add(node_id)


def add_world_nodes_bulk(new_nodes: dict[str, dict]) -> int:
    """Add only genuinely-new world nodes without rebuilding global indexes."""
    added = 0
    for node_id, node in new_nodes.items():
        if node_id in world_nodes:
            continue
        world_nodes[node_id] = node
        tile = _tile_int_pair(node.get("wx", 0), node.get("wy", 0))
        node_by_tile.setdefault(tile, set()).add(node_id)
        added += 1
    return added


def remove_world_node(node_id: str):
    node = world_nodes.pop(node_id, None)
    if node is None:
        return None
    tile = _tile_int_pair(node.get("wx", 0), node.get("wy", 0))
    node_ids = node_by_tile.get(tile)
    if node_ids is not None:
        node_ids.discard(node_id)
        if not node_ids:
            node_by_tile.pop(tile, None)
    return node


def rebuild_placed_object_indexes() -> None:
    global object_by_tile, floor_by_tile, stations_by_chunk
    new_object_index: dict = {}
    new_floor_index: dict = {}
    new_station_index: dict = {}
    for uid, obj in placed_objects.items():
        pos = obj.get("pos", [0, 0])
        tile = _tile_int_pair(pos[0], pos[1])
        if obj.get("type") == "stone_brick_floor":
            new_floor_index[tile] = uid
        else:
            new_object_index[tile] = uid
            chunk_key = _chunk_key_from_tile(tile[0], tile[1])
            new_station_index.setdefault(chunk_key, set()).add(uid)
    object_by_tile = new_object_index
    floor_by_tile = new_floor_index
    stations_by_chunk = new_station_index


def set_placed_objects(new_objects: dict) -> None:
    global placed_objects
    placed_objects = new_objects
    rebuild_placed_object_indexes()


def upsert_placed_object(uid: str, obj: dict) -> None:
    if uid in placed_objects:
        remove_placed_object(uid)
    placed_objects[uid] = obj
    pos = obj.get("pos", [0, 0])
    tile = _tile_int_pair(pos[0], pos[1])
    if obj.get("type") == "stone_brick_floor":
        floor_by_tile[tile] = uid
    else:
        object_by_tile[tile] = uid
        chunk_key = _chunk_key_from_tile(tile[0], tile[1])
        stations_by_chunk.setdefault(chunk_key, set()).add(uid)


def remove_placed_object(uid: str):
    obj = placed_objects.pop(uid, None)
    if obj is None:
        return None
    pos = obj.get("pos", [0, 0])
    tile = _tile_int_pair(pos[0], pos[1])
    if obj.get("type") == "stone_brick_floor":
        if floor_by_tile.get(tile) == uid:
            floor_by_tile.pop(tile, None)
    else:
        if object_by_tile.get(tile) == uid:
            object_by_tile.pop(tile, None)
        chunk_key = _chunk_key_from_tile(tile[0], tile[1])
        chunk_uids = stations_by_chunk.get(chunk_key)
        if chunk_uids is not None:
            chunk_uids.discard(uid)
            if not chunk_uids:
                stations_by_chunk.pop(chunk_key, None)
    return obj


def get_node_at_tile(tile: tuple[int, int]):
    node_ids = node_by_tile.get(tile)
    if not node_ids:
        return None, None
    node_id = next(iter(node_ids))
    return node_id, world_nodes.get(node_id)


def get_placed_object_at_tile(tile: tuple[int, int], include_floor: bool = True):
    uid = object_by_tile.get(tile)
    if uid is not None:
        return uid, placed_objects.get(uid)
    if include_floor:
        uid = floor_by_tile.get(tile)
        if uid is not None:
            return uid, placed_objects.get(uid)
    return None, None


def iter_world_nodes_near(pos_x: float, pos_y: float, radius_tiles: float):
    radius = max(1, int(radius_tiles) + 1)
    base_x = int(pos_x)
    base_y = int(pos_y)
    for tx in range(base_x - radius, base_x + radius + 1):
        for ty in range(base_y - radius, base_y + radius + 1):
            node_ids = node_by_tile.get((tx, ty))
            if not node_ids:
                continue
            for node_id in tuple(node_ids):
                node = world_nodes.get(node_id)
                if node is not None:
                    yield node_id, node


def iter_placed_objects_near(pos_x: float, pos_y: float, radius_tiles: float, include_floor: bool = False):
    radius = max(1, int(radius_tiles) + 1)
    base_x = int(pos_x)
    base_y = int(pos_y)
    seen: set[str] = set()
    for tx in range(base_x - radius, base_x + radius + 1):
        for ty in range(base_y - radius, base_y + radius + 1):
            uid = object_by_tile.get((tx, ty))
            if uid is not None and uid not in seen:
                obj = placed_objects.get(uid)
                if obj is not None:
                    seen.add(uid)
                    yield uid, obj
            if include_floor:
                floor_uid = floor_by_tile.get((tx, ty))
                if floor_uid is not None and floor_uid not in seen:
                    obj = placed_objects.get(floor_uid)
                    if obj is not None:
                        seen.add(floor_uid)
                        yield floor_uid, obj


# Load persisted keybinds immediately so callers always see the saved values.
load_keybinds()
# Load persisted map exploration history.
load_visited_chunks()
# Load persisted map memory / POIs.
load_map_memory()

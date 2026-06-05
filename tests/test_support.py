import json
import os
import queue
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = ROOT / "client"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
if not pygame.display.get_init():
    pygame.display.init()
if pygame.display.get_surface() is None:
    pygame.display.set_mode((1, 1))


def load_items_data() -> dict[int, dict]:
    items_path = ROOT / "server" / "items.json"
    with items_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {int(key): value for key, value in data.items()}


_ITEMS = load_items_data()


def find_item(predicate) -> tuple[int, dict]:
    for item_id, item_def in _ITEMS.items():
        if predicate(item_id, item_def):
            return item_id, item_def
    raise LookupError("No matching item found for test setup")


def make_surface(width: int = 1280, height: int = 720) -> pygame.Surface:
    return pygame.Surface((width, height))


def surface_has_color(surface: pygame.Surface, color: tuple[int, int, int]) -> bool:
    pixels = pygame.surfarray.array3d(surface)
    return bool(((pixels == color).all(axis=2)).any())


def reset_client_config():
    import config

    config.player_inventory = [None] * 45
    config.hotbar_slot = 0
    config.show_inventory = False
    config.show_menu = False
    config.menu_click_pos = None
    config.show_stats = False
    config.stat_click_pos = None
    config.show_station_popup = None
    config.station_popup_uid = None
    config.station_popup_scroll = 0
    config.station_popup_recipe = None
    config.station_popup_tab = "weapon"
    config.open_chest_uid = None
    config.chest_drag_slot = None
    config.drag_slot = None
    config.drag_item = None
    config.state_outbox = queue.Queue()
    config.udp_outbox = queue.Queue()
    config.combiner_slots = [None, None, None, None]
    config.combiner_selected_slot = -1
    config.embedder_slots = [None, None]
    config.embedder_selected_slot = -1
    config.repair_selected_slot = None
    config.player_stat_points = 0
    config.player_defense = 0
    config.player_health_max = 100
    config.player_stamina_max = 100
    config.player_speed_bonus = 0.0
    config.player_attack_power = 10.0
    config.player_hp_regen = 0.0
    config.player_sp_regen_bonus = 0.0
    config.nearby_stations = {"campfire", "crafting_table", "furnace", "part_maker", "embedder"}
    config.set_placed_objects({})
    config.set_world_nodes({})
    config.world_items = {}
    config.mouse_tile = (0, 0)
    config.placement_blocked = False
    config.pickup_mode = False
    return config

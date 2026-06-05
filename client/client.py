import os
import sys
import pygame
import threading
import time
import math
import queue
import traceback

import config
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, HOST, PORT_WORLD, PORT_STATE,
    chunk_queue, world_data, full_world_data, TILE_SIZE, CHUNK_SIZE,
    tile_paths, render_queue, scheduled_chunk_renders, chunk_cache,
    players_data,
)
from input.controls import handle_events, handle_movement
from networking.handlers import send_and_receive_udp, handle_world, handle_state
from rendering.display import (
    generate_minimap_surface, render_chunk, draw_info_overlay, get_biome_name,
    resolve_biome_name, run_minimap_renderer, run_chunk_renderer, draw_world_items,
    draw_placed_object, draw_placed_objects, draw_placement_ghost, get_node_drawables,
    draw_day_night_overlay, draw_sleep_overlay, draw_projectiles,
)
from rendering.item_art import draw_item
from rendering.hud import draw_hud, draw_level_bar, draw_death_overlay, draw_toasts
from rendering.inventory import draw_hotbar, draw_inventory_grid
from rendering.chest import draw_chest_ui
from rendering.player import draw_player, update as update_animation, draw_remote_player, get_sprite_feet_offset
from rendering.mobs import get_mob_drawables
from rendering.npcs import get_npc_drawables
from rendering.particles import update as update_particles, draw as draw_particles
from rendering.cache import clear_distant_cache
from rendering.chat import draw_chat
from rendering.minimap import draw_minimap
from rendering.weather import draw_weather
from rendering.status_effects import draw_status_effects
from state.world import get_radial_sorted_chunks
from state.reset import reset_client_state
from state.player import player_id_dict, player_data
from shared_lock import data_lock
from utils import log_error

# â”€â”€â”€ Launcher / menu constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_C_BG     = ( 26,  26,  46)
_C_PANEL  = ( 22,  33,  62)
_C_ACCENT = ( 15,  52,  96)
_C_PLAY   = (233,  69,  96)
_C_FG     = (234, 234, 234)
_C_ENTRY  = ( 13,  33,  55)
_C_TAB    = ( 26,  74, 138)

# Persists between sessions so the user's last choices are remembered
_launcher: dict = {
    "player_name": config.DEFAULT_PLAYER_ID,
    "host":        config.HOST,
    "fps_cap":     60,
    "debug":       config.DEBUG_MODE,
    "width":       config.WINDOW_WIDTH,
    "height":      config.WINDOW_HEIGHT,
}


def _apply_launcher_settings() -> None:
    config.DEFAULT_PLAYER_ID = _launcher["player_name"]
    config.HOST              = _launcher["host"]
    config.WINDOW_WIDTH      = _launcher["width"]
    config.WINDOW_HEIGHT     = _launcher["height"]
    config.DEBUG_MODE        = _launcher["debug"]


class _TextInput:
    """Single-line text input box for the pygame start menu."""

    def __init__(self, text: str = "", max_len: int = 48) -> None:
        self.text    = text
        self.max_len = max_len

    def handle_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif event.unicode and ord(event.unicode) >= 32 and len(self.text) < self.max_len:
            self.text += event.unicode

    def draw(self, screen: pygame.Surface, rect: pygame.Rect,
             font: pygame.font.Font, focused: bool) -> None:
        border = _C_TAB if focused else _C_ACCENT
        pygame.draw.rect(screen, _C_ENTRY, rect, border_radius=4)
        pygame.draw.rect(screen, border,   rect, 2, border_radius=4)
        surf   = font.render(self.text, True, _C_FG)
        ty     = rect.y + (rect.height - surf.get_height()) // 2
        clip_w = rect.width - 14
        screen.blit(surf, (rect.x + 8, ty),
                    area=pygame.Rect(0, 0, clip_w, surf.get_height()))
        if focused and int(time.time() * 2) % 2 == 0:
            cx = rect.x + 8 + min(surf.get_width(), clip_w)
            pygame.draw.line(screen, _C_FG, (cx, rect.y + 6), (cx, rect.bottom - 6))


def _menu_btn(screen: pygame.Surface, rect: pygame.Rect, label: str,
              font: pygame.font.Font, hovered: bool,
              base: tuple = _C_ACCENT) -> None:
    col = tuple(min(255, c + 40) for c in base) if hovered else base
    pygame.draw.rect(screen, col, rect, border_radius=6)
    ts = font.render(label, True, _C_FG)
    screen.blit(ts, ts.get_rect(center=rect.center))


def _commit_play(name_box: _TextInput, host_box: _TextInput) -> None:
    _launcher["player_name"] = name_box.text.strip() or "Player1"
    _launcher["host"]        = host_box.text.strip() or "127.0.0.1"
    _apply_launcher_settings()


def start_menu(screen: pygame.Surface) -> pygame.Surface:
    """Pure-pygame launcher.  Returns a game-sized surface when Play is pressed."""
    MENU_W, MENU_H = 820, 520
    screen = pygame.display.set_mode((MENU_W, MENU_H), pygame.RESIZABLE)
    pygame.display.set_caption("RPG Game")
    f_title = pygame.font.SysFont("Arial", 28, bold=True)
    f_sub   = pygame.font.SysFont("Arial", 10)
    f_label = pygame.font.SysFont("Arial", 13)
    f_btn   = pygame.font.SysFont("Arial", 13, bold=True)
    f_input = pygame.font.SysFont("Arial", 12)

    tab      = "play"
    name_box = _TextInput(_launcher["player_name"])
    host_box = _TextInput(_launcher["host"])
    focused  = "name"
    fps_opts   = [30, 60, 120, 144, 0]
    fps_labels = ["30", "60", "120", "144", "Unlimited"]
    fps_idx    = next((i for i, v in enumerate(fps_opts) if v == _launcher["fps_cap"]), 1)
    res_opts   = [(1280, 720), (1600, 900), (1920, 1080)]
    res_labels = ["1280×720", "1600×900", "1920×1080"]
    cur_res    = (_launcher["width"], _launcher["height"])
    res_idx    = next((i for i, r in enumerate(res_opts) if r == cur_res), 0)
    debug_on   = _launcher["debug"]
    clock      = pygame.time.Clock()

    while True:
        W, H   = screen.get_size()
        mx, my = pygame.mouse.get_pos()
        HEADER = 88;  TAB_H = 38;  CY = HEADER + TAB_H + 28
        PW = min(460, W - 80);  PX = (W - PW) // 2

        name_rect = pygame.Rect(PX,              CY + 26,  PW,  34)
        host_rect = pygame.Rect(PX,              CY + 96,  PW,  34)
        join_rect = pygame.Rect(PX + PW//2 - 80, CY + 158, 160, 42)
        exit_rect = pygame.Rect(PX + PW//2 - 36, CY + 212,  72, 28)
        OBW      = 44
        fps_prev = pygame.Rect(PX,                  CY + 38,  OBW, 30)
        fps_disp = pygame.Rect(PX + OBW + 4,        CY + 38,   90, 30)
        fps_next = pygame.Rect(PX + OBW + 4 + 94,   CY + 38,  OBW, 30)
        res_prev = pygame.Rect(PX,                  CY + 108, OBW, 30)
        res_disp = pygame.Rect(PX + OBW + 4,        CY + 108, 110, 30)
        res_next = pygame.Rect(PX + OBW + 4 + 114,  CY + 108, OBW, 30)
        dbg_box  = pygame.Rect(PX,                  CY + 162,  20, 20)
        tp = pygame.Rect(0,    HEADER, W // 2, TAB_H)
        to = pygame.Rect(W//2, HEADER, W // 2, TAB_H)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                elif tab == "play":
                    if event.key == pygame.K_TAB:
                        focused = "host" if focused == "name" else "name"
                    elif event.key == pygame.K_RETURN:
                        _commit_play(name_box, host_box)
                        return pygame.display.set_mode(
                            (_launcher["width"], _launcher["height"]), pygame.RESIZABLE)
                    elif focused == "name":
                        name_box.handle_key(event)
                    elif focused == "host":
                        host_box.handle_key(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if tp.collidepoint(mx, my):   tab = "play"
                elif to.collidepoint(mx, my): tab = "options"
                if tab == "play":
                    if   name_rect.collidepoint(mx, my): focused = "name"
                    elif host_rect.collidepoint(mx, my): focused = "host"
                    else: focused = None
                    if join_rect.collidepoint(mx, my):
                        _commit_play(name_box, host_box)
                        return pygame.display.set_mode(
                            (_launcher["width"], _launcher["height"]), pygame.RESIZABLE)
                    if exit_rect.collidepoint(mx, my):
                        pygame.quit(); sys.exit()
                elif tab == "options":
                    if fps_prev.collidepoint(mx, my):
                        fps_idx = (fps_idx - 1) % len(fps_opts)
                        _launcher["fps_cap"] = fps_opts[fps_idx]
                    elif fps_next.collidepoint(mx, my):
                        fps_idx = (fps_idx + 1) % len(fps_opts)
                        _launcher["fps_cap"] = fps_opts[fps_idx]
                    elif res_prev.collidepoint(mx, my):
                        res_idx = (res_idx - 1) % len(res_opts)
                        _launcher["width"], _launcher["height"] = res_opts[res_idx]
                    elif res_next.collidepoint(mx, my):
                        res_idx = (res_idx + 1) % len(res_opts)
                        _launcher["width"], _launcher["height"] = res_opts[res_idx]
                    elif dbg_box.collidepoint(mx, my):
                        debug_on = not debug_on
                        _launcher["debug"] = debug_on
                    _apply_launcher_settings()

        screen.fill(_C_BG)
        pygame.draw.rect(screen, _C_ACCENT, (0, 0, W, HEADER))
        ts = f_title.render("RPG Game", True, _C_FG)
        ss = f_sub.render("multiplayer survival RPG", True, (170, 196, 232))
        screen.blit(ts, ts.get_rect(centerx=W // 2, top=16))
        screen.blit(ss, ss.get_rect(centerx=W // 2, top=52))

        for tid, tr, tlbl in [("play", tp, "  Play  "), ("options", to, "  Options  ")]:
            pygame.draw.rect(screen, _C_TAB if tid == tab else _C_PANEL, tr)
            t2 = f_btn.render(tlbl, True, _C_FG)
            screen.blit(t2, t2.get_rect(center=tr.center))

        if tab == "play":
            screen.blit(f_label.render("Player Name", True, _C_FG), (PX, CY))
            name_box.draw(screen, name_rect, f_input, focused == "name")
            screen.blit(f_label.render("Server IP", True, _C_FG), (PX, CY + 70))
            host_box.draw(screen, host_rect, f_input, focused == "host")
            _menu_btn(screen, join_rect, "JOIN GAME", f_btn,
                      join_rect.collidepoint(mx, my), _C_PLAY)
            _menu_btn(screen, exit_rect, "Exit", f_label,
                      exit_rect.collidepoint(mx, my), (55, 55, 55))
        else:
            screen.blit(f_label.render("Target FPS", True, _C_FG), (PX, CY + 10))
            _menu_btn(screen, fps_prev, "<", f_btn, fps_prev.collidepoint(mx, my))
            _menu_btn(screen, fps_next, ">", f_btn, fps_next.collidepoint(mx, my))
            pygame.draw.rect(screen, _C_ENTRY, fps_disp, border_radius=4)
            _fvs = f_input.render(fps_labels[fps_idx], True, _C_FG)
            screen.blit(_fvs, _fvs.get_rect(center=fps_disp.center))
            screen.blit(f_label.render("Resolution", True, _C_FG), (PX, CY + 80))
            _menu_btn(screen, res_prev, "<", f_btn, res_prev.collidepoint(mx, my))
            _menu_btn(screen, res_next, ">", f_btn, res_next.collidepoint(mx, my))
            pygame.draw.rect(screen, _C_ENTRY, res_disp, border_radius=4)
            _rvs = f_input.render(res_labels[res_idx], True, _C_FG)
            screen.blit(_rvs, _rvs.get_rect(center=res_disp.center))
            screen.blit(f_label.render("Debug overlay", True, _C_FG), (PX + 28, CY + 160))
            pygame.draw.rect(screen, _C_ENTRY, dbg_box, border_radius=3)
            pygame.draw.rect(screen, _C_ACCENT, dbg_box, 1, border_radius=3)
            if debug_on:
                pygame.draw.lines(screen, (80, 220, 80), False,
                                  [(dbg_box.x + 3, dbg_box.centery),
                                   (dbg_box.x + 8, dbg_box.bottom - 4),
                                   (dbg_box.right - 2, dbg_box.top + 3)], 2)

        pygame.display.flip()
        clock.tick(60)


def start_game_client(screen: pygame.Surface) -> None:
    """Run a single game session.  Returns when the player quits or disconnects."""

    state = {
        "WINDOW_WIDTH": config.WINDOW_WIDTH,
        "WINDOW_HEIGHT": config.WINDOW_HEIGHT,
        "is_fullscreen": False,
        "screen": screen,
        "camera_x": 0,
        "camera_y": 0,
        "player_data": player_data,
        "running": True,
        "show_map": False,
        "map_needs_redraw": True,
        "map_surface_cache": None,
        "client_running": True
    }

    font = pygame.font.SysFont("Arial", 18)

    print("[CLIENT STARTED] Connecting to server...")
    threading.Thread(target=send_and_receive_udp, daemon=True).start()
    while player_id_dict["player_id"] is None:
        # Show ban/error if received during connecting
        if config.connection_error:
            state["screen"].fill((10, 10, 18))
            err_surf = font.render(config.connection_error, True, (230, 60, 60))
            state["screen"].blit(err_surf, (
                state["WINDOW_WIDTH"]  // 2 - err_surf.get_width()  // 2,
                state["WINDOW_HEIGHT"] // 2 - err_surf.get_height() // 2,
            ))
            pygame.display.flip()
            time.sleep(5)
            pygame.quit()
            return
        time.sleep(0.1)

    threading.Thread(
        target=handle_world,
        args=(HOST, PORT_WORLD, chunk_queue, player_id_dict["player_id"]),
        daemon=True
    ).start()

    threading.Thread(
        target=handle_state,
        args=(HOST, PORT_STATE, player_id_dict["player_id"]),
        daemon=True
    ).start()

    # Load tile images
    def load_tile_images(paths):
        images = {}
        for name, path in paths.items():
            try:
                images[name] = pygame.image.load(path).convert()
            except pygame.error as e:
                log_error(f"[ERROR] Failed to load {name}: {e}")
        return images

    tile_images = load_tile_images(tile_paths)
    minimap_queue = queue.Queue()

    threading.Thread(target=run_minimap_renderer, args=(minimap_queue, tile_images, state), daemon=True).start()

    for _ in range(3):
        threading.Thread(
            target=run_chunk_renderer,
            args=(render_queue, world_data, tile_images, {}, data_lock, chunk_cache, scheduled_chunk_renders, state),
            daemon=True
        ).start()

    chunk_radius_x = (state["WINDOW_WIDTH"] // TILE_SIZE // CHUNK_SIZE) + 3
    chunk_radius_y = (state["WINDOW_HEIGHT"] // TILE_SIZE // CHUNK_SIZE) + 3

    state["camera_x"] = state["player_data"]["pos"][0] * TILE_SIZE
    state["camera_y"] = state["player_data"]["pos"][1] * TILE_SIZE

    _load = {"done": False}

    def is_chunk_loaded(cx, cy):
        for dx in range(CHUNK_SIZE):
            for dy in range(CHUNK_SIZE):
                key = (cx * CHUNK_SIZE + dx, cy * CHUNK_SIZE + dy)
                if key not in world_data:
                    return False
        return True

    player_x0, player_y0 = state["player_data"]["pos"]
    center_cx0 = int(player_x0) // CHUNK_SIZE
    center_cy0 = int(player_y0) // CHUNK_SIZE
    total_chunks = (2 * chunk_radius_x + 1) * (2 * chunk_radius_y + 1)

    clock = pygame.time.Clock()
    _CRAFTING_STATIONS = frozenset({"campfire", "crafting_table", "furnace", "alloy_forge",
                                    "part_maker", "part_combiner", "embedder"})
    # Cache keys for expensive per-frame scans
    _last_placement_key = [None]
    _last_station_tile  = [None]
    # Cache the sorted chunk list — only recompute when the player moves to a new chunk
    _sorted_chunks_cache:    list  = []
    _sorted_chunks_last_key: tuple = (None, None)

    # Suppress Python GC during the game loop; collect manually every 120 frames
    import gc as _gc
    _gc.disable()
    _gc_frame_counter = 0


    # â”€â”€ teardown: called when the game session ends â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    fps_cap = _launcher.get("fps_cap", 60)

    def game_tick():
        nonlocal _gc_frame_counter, _sorted_chunks_last_key
        dt = clock.tick(fps_cap if fps_cap else 0) / 1000.0

        # Manual GC every 120 frames to avoid unpredictable mid-frame pauses
        _gc_frame_counter += 1
        if _gc_frame_counter >= 120:
            _gc_frame_counter = 0
            _gc.collect()

        # Compute mouse tile BEFORE handle_events
        _mx, _my = pygame.mouse.get_pos()
        _pre_off_x = state["WINDOW_WIDTH"]  // 2 - state["camera_x"]
        _pre_off_y = state["WINDOW_HEIGHT"] // 2 - state["camera_y"]
        config.mouse_tile = (
            int((_mx - _pre_off_x) // TILE_SIZE),
            int((_my - _pre_off_y) // TILE_SIZE),
        )
        _mt = config.mouse_tile
        _hs = config.player_inventory[27 + config.hotbar_slot]
        _placing_floor = _hs is not None and _hs[0] == 254
        _placement_key = (_mt, _placing_floor)
        if _placement_key != _last_placement_key[0]:
            _last_placement_key[0] = _placement_key
            _node_id, _node = config.get_node_at_tile(_mt)
            if _placing_floor:
                config.placement_blocked = (
                    _node is not None
                    or _mt in config.floor_by_tile
                )
            else:
                config.placement_blocked = (
                    _node is not None
                    or _mt in config.object_by_tile
                )

        handle_events(state)
        state["screen"].fill((0, 0, 0))

        _px, _py = state["player_data"]["pos"]
        _station_tile = (int(_px), int(_py))
        if _station_tile != _last_station_tile[0]:
            _last_station_tile[0] = _station_tile
            _STATION_DIST_SQ = 4.0
            nearby: set = set()
            chunk_x = int(_px) // CHUNK_SIZE
            chunk_y = int(_py) // CHUNK_SIZE
            for cx in range(chunk_x - 1, chunk_x + 2):
                for cy in range(chunk_y - 1, chunk_y + 2):
                    for uid in config.stations_by_chunk.get((cx, cy), ()):
                        obj = config.placed_objects.get(uid)
                        if obj is None:
                            continue
                        if obj["type"] not in _CRAFTING_STATIONS:
                            continue
                        if (obj["pos"][0] - _px) ** 2 + (obj["pos"][1] - _py) ** 2 <= _STATION_DIST_SQ:
                            nearby.add(obj["type"])
            config.nearby_stations = nearby

        keys = pygame.key.get_pressed()
        if not state["show_map"] and not config.show_inventory and not config.show_menu and not config.show_stats and not config.show_controls and config.show_station_popup is None and config.open_chest_uid is None:
            handle_movement(state, keys, dt)
        else:
            config.is_blocking = False  # clear block when any UI is open

        kbv = state["player_data"].get("knockback_vel")
        if kbv:
            state["player_data"]["pos"][0] += kbv[0] * dt
            state["player_data"]["pos"][1] += kbv[1] * dt
            decay = max(0.0, 1.0 - config.KNOCKBACK_DECAY * dt)
            kbv[0] *= decay
            kbv[1] *= decay
            if kbv[0] * kbv[0] + kbv[1] * kbv[1] < 0.01:
                state["player_data"].pop("knockback_vel", None)

        if config.hit_flash_timer > 0.0:
            config.hit_flash_timer = max(0.0, config.hit_flash_timer - dt)

        update_animation(dt)

        try:
            player_x, player_y = state["player_data"]["pos"]

            current_chunk = (
                int(state["player_data"]["pos"][0]) // CHUNK_SIZE,
                int(state["player_data"]["pos"][1]) // CHUNK_SIZE
            )

            if current_chunk != config.last_player_chunk:
                clear_distant_cache(current_chunk[0], current_chunk[1])
                config.last_player_chunk = current_chunk

            state["camera_x"] += (player_x * TILE_SIZE - state["camera_x"]) * min(1.0, dt * 15.0)
            state["camera_y"] += (player_y * TILE_SIZE - state["camera_y"]) * min(1.0, dt * 15.0)

            offset_x = state["WINDOW_WIDTH"] // 2 - state["camera_x"]
            offset_y = state["WINDOW_HEIGHT"] // 2 - state["camera_y"]

            # Expose camera offsets so light_sources.py can project world → screen.
            config.camera_offset_x = offset_x
            config.camera_offset_y = offset_y

            if world_data:
                if state["show_map"] and full_world_data:
                    # Always submit so player dot stays current
                    if minimap_queue.empty():
                        items_copy = list(full_world_data.items())
                        minimap_queue.put((items_copy, player_x, player_y,
                                           (state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]), CHUNK_SIZE))

                    if state["map_surface_cache"]:
                        state["screen"].blit(state["map_surface_cache"], (0, 0))
                        _hint = font.render("M  -  close map", True, (200, 200, 200))
                        state["screen"].blit(_hint, (8, state["WINDOW_HEIGHT"] - 26))
                else:
                    while not chunk_queue.empty():
                        chunk_key, tiles = chunk_queue.get()
                        world_data.update(tiles)
                        full_world_data.update(tiles)
                        config.world_data_loaded_chunks.add(chunk_key)
                        chunk_queue.task_done()

                    # Recompute sorted chunk list only when the player enters a new chunk
                    if current_chunk != _sorted_chunks_last_key:
                        _sorted_chunks_last_key = current_chunk
                        _sorted_chunks_cache[:] = get_radial_sorted_chunks(
                            current_chunk[0], current_chunk[1],
                            chunk_radius_x, chunk_radius_y, 1
                        )
                    for cx, cy in _sorted_chunks_cache:
                        chunk_key = (cx, cy)
                        world_x = cx * CHUNK_SIZE * TILE_SIZE
                        world_y = cy * CHUNK_SIZE * TILE_SIZE
                        screen_x = world_x + offset_x
                        screen_y = world_y + offset_y
                        buffer = TILE_SIZE * 4
                        chunk_rect = pygame.Rect(screen_x, screen_y, CHUNK_SIZE * TILE_SIZE, CHUNK_SIZE * TILE_SIZE)
                        if not state["screen"].get_rect().inflate(buffer, buffer).colliderect(chunk_rect):
                            continue

                        if chunk_key in chunk_cache:
                            state["screen"].blit(chunk_cache[chunk_key], (screen_x, screen_y))
                        elif chunk_key not in scheduled_chunk_renders:
                            dx = cx * CHUNK_SIZE + CHUNK_SIZE // 2 - player_x
                            dy = cy * CHUNK_SIZE + CHUNK_SIZE // 2 - player_y
                            dist = dx * dx + dy * dy
                            render_queue.put((dist, (cx, cy)))
                            scheduled_chunk_renders.add(chunk_key)

            if not state["show_map"]:
                cam_px = state["camera_x"] / TILE_SIZE
                cam_py = state["camera_y"] / TILE_SIZE

                draw_placement_ghost(state["screen"], offset_x, offset_y)

                _draw_list = list(get_node_drawables(
                    state["screen"], config.world_nodes, offset_x, offset_y
                ))

                _wi_size = TILE_SIZE // 2
                _wi_pad = (TILE_SIZE - _wi_size) // 2
                for _wi in config.world_items.values():
                    _wi_x = int(_wi["pos"][0] * TILE_SIZE + offset_x + _wi_pad)
                    _wi_y = int(_wi["pos"][1] * TILE_SIZE + offset_y + _wi_pad)
                    _wi_sort = _wi["pos"][1] + 0.5
                    _wi_id = _wi.get("item_id", 1)
                    _draw_list.append((_wi_sort, lambda _sx=_wi_x, _sy=_wi_y, _iid=_wi_id:
                        draw_item(state["screen"], _sx, _sy, _wi_size, _iid)))

                for _po in config.placed_objects.values():
                    _po_sort_y = float('-inf') if _po["type"] == "stone_brick_floor" else _po["pos"][1] + 1.0
                    _draw_list.append((_po_sort_y, lambda _o=_po: draw_placed_object(
                        state["screen"], _o, offset_x, offset_y
                    )))

                _mob_now = time.time()
                _mob_draw_state = [
                    {
                        "id": mob.mob_id,
                        "type": mob.mob_type,
                        "pos": mob.get_render_pos(_mob_now),
                        "_pre_smoothed": True,
                        "health": mob.health,
                        "health_max": mob.health_max,
                        "level": mob.level,
                        "hit_flash": mob.hit_flash,
                        "state": mob.state,
                        "facing": mob.facing,
                    }
                    for mob in config.mob_entities.values()
                ]
                for _world_y, _fn in get_mob_drawables(
                    state["screen"], _mob_draw_state,
                    [cam_px, cam_py],
                    state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"], dt
                ):
                    _draw_list.append((_world_y, _fn))

                for _world_y, _fn in get_npc_drawables(
                    state["screen"], config.npcs,
                    [cam_px, cam_py], offset_x, offset_y
                ):
                    _draw_list.append((_world_y, _fn))

                _draw_list.append((player_y + get_sprite_feet_offset(), lambda: draw_player(
                    state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                )))

                _now = time.time()
                for pid, rp in players_data.items():
                    if pid != player_id_dict["player_id"]:
                        rp.update_anim(dt)
                        _combat_active = (
                            config.is_attacking
                            or config.is_blocking
                            or rp.is_attacking
                        )
                        _interp_delay = rp.get_interp_delay(
                            state["player_data"]["pos"],
                            combat_active=_combat_active,
                        )
                        _rp_pos = rp.get_render_pos(_now, interp_delay=_interp_delay)
                        _draw_list.append((
                            _rp_pos[1] + get_sprite_feet_offset(),
                            lambda _rp=rp, _pos=_rp_pos, _pid=pid: draw_remote_player(
                                state["screen"], _pos,
                                _rp.facing, _rp.walk_frame,
                                cam_px, cam_py,
                                state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"],
                                is_attacking=_rp.is_attacking, atk_frame=_rp.atk_frame,
                                equip_ids=_rp.equip_ids,
                                held_item_id=_rp.held_item_id,
                                name=_pid,
                                appearance=_rp.appearance,
                            )
                        ))

                _draw_list.sort(key=lambda t: t[0])
                for _, _fn in _draw_list:
                    _fn()

                update_particles(dt)
                # Aura — emit every frame while active
                _aura = config.player_appearance.get("aura")
                if _aura:
                    from rendering.particles import emit_aura as _emit_aura
                    _emit_aura(player_x, player_y, _aura)
                draw_particles(state["screen"])
                draw_projectiles(state["screen"])

                fps = clock.get_fps()
                px_int, py_int = int(state["player_data"]["pos"][0]), int(state["player_data"]["pos"][1])

                current_tile = world_data.get((px_int, py_int), {})
                if isinstance(current_tile, dict):
                    biome_type = current_tile.get("biome", "unknown")
                    elevation = current_tile.get("elevation", 0.0)
                else:
                    biome_type = current_tile
                    elevation = 0.0

                biome_name = get_biome_name(resolve_biome_name(biome_type))
                config.current_biome_name = biome_name
                config.current_elevation  = elevation
                draw_info_overlay(state["screen"], font, fps, config.ping, biome_name, elevation, player_x, player_y)
            draw_day_night_overlay(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_sleep_overlay(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_weather(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"], dt)
            draw_status_effects(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_hud(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_level_bar(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_hotbar(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            if config.show_inventory and config.open_chest_uid is None:
                draw_inventory_grid(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            if config.open_chest_uid is not None:
                draw_chest_ui(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])

            if config.show_station_popup:
                if config.show_station_popup == "part_combiner":
                    from rendering.combiner import draw_combiner_popup
                    draw_combiner_popup(state["screen"],
                                        state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
                elif config.show_station_popup == "embedder":
                    from rendering.embedder import draw_embedder_popup
                    draw_embedder_popup(state["screen"],
                                        state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
                else:
                    from rendering.crafting import draw_station_popup
                    draw_station_popup(state["screen"], config.show_station_popup,
                                       state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])

            if config.show_shop:
                from rendering.npc_shop import draw_shop
                draw_shop(state["screen"])

            if config.show_char_creator:
                from rendering.char_creator import draw_char_creator
                draw_char_creator(state["screen"])

            if config.show_menu:
                from rendering.menu import draw_menu
                action = draw_menu(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"],
                                   config.menu_click_pos)
                config.menu_click_pos = None
                if action == "resume":
                    config.show_menu = False
                elif action == "stats":
                    config.show_menu = False
                    config.show_stats = True
                elif action == "controls":
                    config.show_menu = False
                    config.show_controls = True
                elif action == "quit":
                    state["running"] = False

            if config.show_controls:
                from rendering.controls_settings import draw_controls
                action = draw_controls(state["screen"], state["WINDOW_WIDTH"],
                                       state["WINDOW_HEIGHT"], config.controls_click_pos)
                config.controls_click_pos = None
                if action == "close":
                    config.show_controls = False
                    config.controls_listen = None
                elif action and action.startswith("listen:"):
                    config.controls_listen = action.split(":", 1)[1]

            draw_death_overlay(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_toasts(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            draw_chat(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
            config.player_pos = state["player_data"]["pos"]
            draw_minimap(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])

            if config.show_stats:
                from rendering.stat_screen import draw_stat_screen
                action = draw_stat_screen(state["screen"], state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"],
                                          config.stat_click_pos)
                config.stat_click_pos = None
                if action and action.startswith("spend:"):
                    stat = action.split(":", 1)[1]
                    config.state_outbox.put({"type": "spend_stat", "stat": stat})

        except Exception as e:
            log_error(f"[ERROR] Rendering failed: {e}\n{traceback.format_exc()}")
            state["running"] = False

        pygame.display.flip()

        # Schedule next tick â€” use a short delay so Tk can process its events
    # ── Loading loop ─────────────────────────────────────────────────────────────────────
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        while not chunk_queue.empty():
            chunk_key, tiles = chunk_queue.get()
            world_data.update(tiles)
            full_world_data.update(tiles)
            config.world_data_loaded_chunks.add(chunk_key)
            chunk_queue.task_done()
        state["screen"].fill((0, 0, 0))
        player_x, player_y = state["player_data"]["pos"]
        center_chunk_x = int(player_x) // CHUNK_SIZE
        center_chunk_y = int(player_y) // CHUNK_SIZE
        loaded_chunks = sum(
            1
            for cx in range(center_chunk_x - chunk_radius_x, center_chunk_x + chunk_radius_x + 1)
            for cy in range(center_chunk_y - chunk_radius_y, center_chunk_y + chunk_radius_y + 1)
            if is_chunk_loaded(cx, cy)
        )
        loading_text = font.render(
            f"Loading world... {int(min(loaded_chunks / total_chunks, 1.0) * 100)}%",
            True, (255, 255, 255))
        state["screen"].blit(loading_text,
                             loading_text.get_rect(center=(state["WINDOW_WIDTH"] // 2,
                                                           state["WINDOW_HEIGHT"] // 2)))
        pygame.display.flip()
        if loaded_chunks >= total_chunks:
            break
        clock.tick(20)

    # ── Fade-in ────────────────────────────────────────────────────────────────────────────
    for alpha in range(240, -1, -20):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        fade = pygame.Surface((state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]))
        fade.set_alpha(alpha)
        fade.fill((0, 0, 0))
        state["screen"].blit(fade, (0, 0))
        pygame.display.flip()
        pygame.time.delay(10)

    # ── Main game loop ──────────────────────────────────────────────────────────────────────
    while state["running"]:
        game_tick()

    # ── Session teardown ───────────────────────────────────────────────────────────────
    _gc.enable()
    state["client_running"] = False
    config.session_id += 1
    state["screen"].fill((0, 0, 0))
    msg = font.render("Disconnecting...", True, (255, 255, 255))
    state["screen"].blit(msg, msg.get_rect(
        center=(state["WINDOW_WIDTH"] // 2, state["WINDOW_HEIGHT"] // 2)))
    pygame.display.flip()
    time.sleep(0.4)
    reset_client_state()


if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode(
        (_launcher["width"], _launcher["height"]), pygame.RESIZABLE)
    while True:
        screen = start_menu(screen)
        start_game_client(screen)

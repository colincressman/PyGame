import pygame
import threading
import time
import math
import tkinter as tk

from config import *
from input.controls import *
from networking.sockets import *
from networking.handlers import *
from rendering.display import *
from rendering.cache import *
from state.world import get_radial_sorted_chunks
from state.reset import reset_client_state
from utils import log_error
from rendering.cache import clear_distant_cache
from state.player import *

def start_game_client():    
    global last_player_chunk, map_surface_cache
    pygame.init()

    state = {
        "WINDOW_WIDTH": WINDOW_WIDTH,
        "WINDOW_HEIGHT": WINDOW_HEIGHT,
        "is_fullscreen": False,
        "screen": pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE | pygame.DOUBLEBUF),
        "camera_x": 0,
        "camera_y": 0,
        "player_data": player_data,
        "running": True,
        "show_map": False,
        "map_needs_redraw": True,
        "client_running": True,
    }

    pygame.display.set_caption("RPG Game")
    font = pygame.font.SysFont("Arial", 18)

    print("[CLIENT STARTED] Connecting to server...")
    threading.Thread(target=send_and_receive_udp, daemon=True).start()
    while player_id_dict["player_id"] is None:
        time.sleep(0.1)

    threading.Thread(
        target=handle_world,
        args=(HOST, PORT_WORLD, chunk_queue, state["client_running"], player_id_dict["player_id"]),
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
    tile_cache = {}

    def chunk_renderer():
        while True:
            _, (cx, cy) = render_queue.get()
            chunk_surface, is_complete = render_chunk(cx, cy, world_data, tile_images, tile_cache)
            with data_lock:
                if is_complete:
                    chunk_cache[(cx, cy)] = chunk_surface
                    scheduled_chunk_renders.discard((cx, cy))
                else:
                    player_x, player_y = state["player_data"]["pos"]
                    dx = cx * CHUNK_SIZE + CHUNK_SIZE // 2 - player_x
                    dy = cy * CHUNK_SIZE + CHUNK_SIZE // 2 - player_y
                    dist = dx * dx + dy * dy
                    render_queue.put((dist, (cx, cy)))
            render_queue.task_done()

    for _ in range(3):  # Increase this number as needed
        threading.Thread(target=chunk_renderer, daemon=True).start()

    chunk_radius_x = (state["WINDOW_WIDTH"] // TILE_SIZE // CHUNK_SIZE) + 3
    chunk_radius_y = (state["WINDOW_HEIGHT"] // TILE_SIZE // CHUNK_SIZE) + 3

    state["camera_x"] = state["player_data"]["pos"][0] * TILE_SIZE
    state["camera_y"] = state["player_data"]["pos"][1] * TILE_SIZE

    loading = True
    while loading:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        while not chunk_queue.empty():
            chunk_key, tiles = chunk_queue.get()
            world_data.update(tiles)
            full_world_data.update(tiles)
            chunk_queue.task_done()

        state["screen"].fill((0, 0, 0))

        total_chunks_expected = (2 * chunk_radius_x + 1) * (2 * chunk_radius_y + 1)
        loaded_chunks = 0

        player_x, player_y = state["player_data"]["pos"]
        center_chunk_x = int(player_x) // CHUNK_SIZE
        center_chunk_y = int(player_y) // CHUNK_SIZE

        def is_chunk_loaded(cx, cy):
            for dx in range(CHUNK_SIZE):
                for dy in range(CHUNK_SIZE):
                    key = (cx * CHUNK_SIZE + dx, cy * CHUNK_SIZE + dy)
                    if key not in world_data:  
                        return False
            return True

        for cx in range(center_chunk_x - chunk_radius_x, center_chunk_x + chunk_radius_x + 1):
            for cy in range(center_chunk_y - chunk_radius_y, center_chunk_y + chunk_radius_y + 1):
                if is_chunk_loaded(cx, cy):
                    loaded_chunks += 1

        progress = min(loaded_chunks / total_chunks_expected, 1.0)
        percent = int(progress * 100)
        loading_text = font.render(f"Loading world... {percent}%", True, (255, 255, 255))
        rect = loading_text.get_rect(center=(state["WINDOW_WIDTH"] // 2, state["WINDOW_HEIGHT"] // 2))
        state["screen"].blit(loading_text, rect)

        pygame.display.flip()

        if loaded_chunks >= total_chunks_expected:
            loading = False

        time.sleep(0.1)

    fade_overlay = pygame.Surface((state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]))
    for alpha in range(255, 0, -15):
        fade_overlay.set_alpha(alpha)
        fade_overlay.fill((0, 0, 0))
        state["screen"].blit(fade_overlay, (0, 0))
        pygame.display.flip()
        time.sleep(0.01)

    clock = pygame.time.Clock()

    while state["running"]:
        dt = clock.tick(60) / 1000

        handle_events(state)
        state["screen"].fill((0, 0, 0))

        keys = pygame.key.get_pressed()
        if not state["show_map"]:
            handle_movement(state, keys, dt)

        try:
            player_x, player_y = state["player_data"]["pos"]

            current_chunk = (
                int(state["player_data"]["pos"][0]) // CHUNK_SIZE,
                int(state["player_data"]["pos"][1]) // CHUNK_SIZE
            )

            if current_chunk != last_player_chunk:
                clear_distant_cache(current_chunk[0], current_chunk[1])
                last_player_chunk = current_chunk

            state["camera_x"] += (player_x * TILE_SIZE - state["camera_x"]) * 0.25
            state["camera_y"] += (player_y * TILE_SIZE - state["camera_y"]) * 0.25

            offset_x = state["WINDOW_WIDTH"] // 2 - state["camera_x"]
            offset_y = state["WINDOW_HEIGHT"] // 2 - state["camera_y"]

            if world_data:
                if state["show_map"] and full_world_data:
                    if map_surface_cache is None or state["map_needs_redraw"]:
                        items_copy = list(full_world_data.items())
                        map_surface_cache = generate_minimap_surface(
                            tile_images, items_copy, player_x, player_y,
                            (state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]), CHUNK_SIZE
                        )
                        state["map_needs_redraw"] = False

                    if map_surface_cache:
                        map_x = (state["WINDOW_WIDTH"] - map_surface_cache.get_width()) // 2
                        map_y = (state["WINDOW_HEIGHT"] - map_surface_cache.get_height()) // 2
                        state["screen"].blit(map_surface_cache, (map_x, map_y))
                else:
                    while not chunk_queue.empty():
                        chunk_key, tiles = chunk_queue.get()
                        world_data.update(tiles)   
                        full_world_data.update(tiles)
                        chunk_queue.task_done()

                    sorted_chunks = get_radial_sorted_chunks(current_chunk[0], current_chunk[1], chunk_radius_x, chunk_radius_y, 1)
                    for cx, cy in sorted_chunks:
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

            pygame.draw.rect(state["screen"], (255, 0, 0), (state["WINDOW_WIDTH"] // 2, state["WINDOW_HEIGHT"] // 2, TILE_SIZE, TILE_SIZE))

            for pid, pdata in players_data.items():
                if pid != player_id_dict["player_id"]:
                    other_x, other_y = pdata["pos"]
                    draw_x = (other_x - player_x) * TILE_SIZE + state["WINDOW_WIDTH"] // 2
                    draw_y = (other_y - player_y) * TILE_SIZE + state["WINDOW_HEIGHT"] // 2
                    pygame.draw.rect(state["screen"], (0, 0, 255), (draw_x, draw_y, TILE_SIZE, TILE_SIZE))

            fps = clock.get_fps()
            px_int, py_int = int(state["player_data"]["pos"][0]), int(state["player_data"]["pos"][1])

            current_tile = world_data.get((px_int, py_int), {})
            if isinstance(current_tile, dict):
                biome_type = current_tile.get("biome", "unknown")
                elevation = current_tile.get("elevation", 0.0)
            else:
                biome_type = current_tile
                elevation = 0.0

            biome_name = get_biome_name(biome_type)
            draw_info_overlay(state["screen"], font, fps, ping, biome_name, elevation, player_x, player_y)

        except Exception as e:
            log_error(f"[ERROR] Rendering failed: {e}")
            state["running"] = False

        pygame.display.flip()

    state["client_running"] = False
    time.sleep(0.1)

    state["screen"].fill((0, 0, 0))
    disconnect_msg = font.render("Disconnecting...", True, (255, 255, 255))
    state["screen"].blit(disconnect_msg, (state["WINDOW_WIDTH"] // 2 - 100, state["WINDOW_HEIGHT"] // 2))
    pygame.display.flip()

    pygame.quit()
    print("[CLIENT] Disconnected from server.")

    reset_client_state()
    start_menu()

def start_menu():
    root = tk.Tk()
    root.title("RPG Game - Main Menu")
    root.geometry("800x600")

    title_label = tk.Label(root, text="RPG Game", font=("Arial", 36))
    title_label.pack(pady=20)

    join_button = tk.Button(
        root, text="Join Game", width=15, height=2, bg="#649AFF", fg="white",
        font=("Arial", 16), command=lambda: (root.destroy(), start_game_client())
    )
    join_button.pack(pady=10)

    exit_button = tk.Button(
        root, text="Exit", width=15, height=2, bg="#FF6464", fg="white",
        font=("Arial", 16), command=root.quit
    )
    exit_button.pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    start_menu()

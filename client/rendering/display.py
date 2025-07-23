# client/rendering/display.py

import pygame, time
from config import *
from shared_lock import data_lock

def get_font():
    return pygame.font.SysFont(FONT_NAME, FONT_SIZE)

def toggle_fullscreen(state):
    state["is_fullscreen"] = not state["is_fullscreen"]

    if state["is_fullscreen"]:
        pygame.display.quit()
        time.sleep(0.05)
        pygame.display.init()
        state["screen"] = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        info = pygame.display.Info()
        state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"] = info.current_w, info.current_h
    else:
        state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"] = 1280, 720
        state["screen"] = pygame.display.set_mode(
            (state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]),
            pygame.RESIZABLE
        )

    px, py = state["player_data"]["pos"]
    state["camera_x"] = px * TILE_SIZE
    state["camera_y"] = py * TILE_SIZE


def draw_info_overlay(screen, font, fps, ping, biome, elevation, player_x, player_y):
    info_lines = [
        f"FPS: {int(fps)}",
        f"Ping: {ping} ms",
        f"Biome: {biome}",
        f"Elevation: {elevation:.2f}",
        f"Coords: {int(player_x)}, {int(player_y)}"
    ]
    for i, line in enumerate(info_lines):
        text = font.render(line, True, (255, 255, 255))
        screen.blit(text, (10, 10 + i * 20))

def get_biome_name(tile_type):
    names = {
        "ocean": "Ocean",
        "river": "River",
        "beach": "Beach",
        "swamp": "Swamp",
        "plains": "Plains",
        "forest": "Forest",
        "desert": "Desert",
        "alt_desert": "Arid Desert",
        "tropical": "Tropical Forest",
        "tundra": "Tundra",
        "mountain": "Mountain",
    }
    return names.get(tile_type, "Unknown")

def generate_minimap_surface(tile_images, items_copy, player_x, player_y, window_size, chunk_size):
    quarter_size = chunk_size
    quarter_biome_counts = {}

    # Step 1: Tally biomes in quarter chunks
    for (tx, ty), tile_data in items_copy:
        qx, qy = tx // quarter_size, ty // quarter_size
        qkey = (qx, qy)

        biome = tile_data.get("biome") if isinstance(tile_data, dict) else tile_data
        if qkey not in quarter_biome_counts:
            quarter_biome_counts[qkey] = {}

        biome_dict = quarter_biome_counts[qkey]
        biome_dict[biome] = biome_dict.get(biome, 0) + 1

    # Step 2: Create raw map surface
    qx_vals = [q[0] for q in quarter_biome_counts]
    qy_vals = [q[1] for q in quarter_biome_counts]
    min_qx, max_qx = min(qx_vals), max(qx_vals)
    min_qy, max_qy = min(qy_vals), max(qy_vals)
    map_w, map_h = max_qx - min_qx + 1, max_qy - min_qy + 1

    raw_map = pygame.Surface((map_w, map_h))

    for (qx, qy), biome_counts in quarter_biome_counts.items():
        dominant_biome = max(biome_counts.items(), key=lambda x: x[1])[0]
        color = (255, 255, 255)
        if dominant_biome in tile_images:
            avg_color = pygame.transform.scale(tile_images[dominant_biome], (1, 1)).get_at((0, 0))
            color = (avg_color.r, avg_color.g, avg_color.b)

        raw_map.set_at((qx - min_qx, qy - min_qy), color)

    # Step 3: Player marker
    player_qx = int(player_x) // quarter_size - min_qx
    player_qy = int(player_y) // quarter_size - min_qy
    if 0 <= player_qx < map_w and 0 <= player_qy < map_h:
        raw_map.set_at((player_qx, player_qy), (255, 0, 0))

    # Step 4: Scale to screen
    win_w, win_h = window_size
    scale = min(win_w / map_w, win_h / map_h)
    new_w, new_h = max(1, int(map_w * scale)), max(1, int(map_h * scale))
    return pygame.transform.scale(raw_map, (new_w, new_h))

def resolve_biome_name(biome_id_or_name):
    if isinstance(biome_id_or_name, int):
        return CLIFF_ID_TO_NAME.get(biome_id_or_name, BIOME_ID_TO_NAME.get(biome_id_or_name, "unknown"))
    return biome_id_or_name

def render_chunk(cx, cy, world_data, tile_images, tile_cache):
    incomplete = False
    chunk_surface = pygame.Surface((CHUNK_SIZE * TILE_SIZE, CHUNK_SIZE * TILE_SIZE))
    chunk_surface.fill((0, 0, 0))

    MISSING_TILE_SURFACE = pygame.Surface((TILE_SIZE, TILE_SIZE))
    MISSING_TILE_SURFACE.fill((255, 0, 255))

    base_tx = cx * CHUNK_SIZE
    base_ty = cy * CHUNK_SIZE
    for tx_off in range(CHUNK_SIZE):
        for ty_off in range(CHUNK_SIZE):
            tx = base_tx + tx_off
            ty = base_ty + ty_off
            tile_info = world_data.get((tx, ty))

            if tile_info:
                raw_type = tile_info["biome"] if isinstance(tile_info, dict) else tile_info
                tile_type = resolve_biome_name(raw_type)
                cache_key = (tile_type, tx, ty)
                tile_surface = tile_cache.get(cache_key)

                if tile_surface is None:
                    base_surface = tile_images.get(tile_type)
                    tile_surface = base_surface if base_surface else MISSING_TILE_SURFACE
                    if not base_surface:
                        tile_surface.fill((255, 0, 255))  # Magenta for missing tiles
                    tile_cache[cache_key] = tile_surface

                chunk_surface.blit(tile_surface, (tx_off * TILE_SIZE, ty_off * TILE_SIZE))
            else:
                incomplete = True

    return chunk_surface, not incomplete

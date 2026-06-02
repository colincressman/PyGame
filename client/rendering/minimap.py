"""minimap.py — 128×128 corner minimap with biome colours, fog-of-war, and info panel."""
import pygame
import config

MM_SIZE    = config.MINIMAP_SIZE        # pixels square
MM_TILE_PX = config.MINIMAP_TILE_PX     # pixels per world tile (64×64 tile area visible)
MM_PADDING = config.MINIMAP_PADDING     # offset from top-right corner
MM_RADIUS  = MM_SIZE // (2 * MM_TILE_PX)   # 32 tiles each direction

_INFO_PAD  = 4   # padding inside the info panel
_INFO_GAP  = 2   # vertical gap between info rows

_BIOME_COLORS: dict[int, tuple] = {
    0:  (20,  40,  100),  # ocean
    1:  (220, 200, 120),  # beach
    2:  (60,  80,  40),   # swamp
    3:  (40,  80,  160),  # river
    4:  (160, 200, 80),   # plains
    5:  (30,  100, 30),   # forest
    6:  (200, 170, 80),   # desert
    7:  (180, 150, 60),   # alt_desert
    8:  (40,  160, 60),   # tropical
    9:  (200, 220, 240),  # tundra
    10: (140, 140, 140),  # mountain
}
_FOG_COLOR     = (20, 20, 20)
_UNKNOWN_COLOR = (45, 45, 45)
_CHUNK_SIZE    = config.CHUNK_SIZE  # tiles per chunk (from config; not duplicated here)

_WEATHER_ICONS = {
    "clear":  "[Sun]",
    "cloudy": "[Cloud]",
    "rain":   "[Rain]",
    "snow":   "[Snow]",
    "fog":    "[Fog]",
}

_mm_surf:        pygame.Surface | None = None
_mm_last_center: tuple | None = None
_mm_info_font:   pygame.font.Font | None = None


def _get_info_font() -> pygame.font.Font:
    global _mm_info_font
    if _mm_info_font is None:
        _mm_info_font = pygame.font.SysFont("Arial", 12)
    return _mm_info_font


def _rebuild(player_x: float, player_y: float) -> None:
    """Rebuild the 128×128 surface centred on the player's current tile."""
    global _mm_surf, _mm_last_center
    surf = pygame.Surface((MM_SIZE, MM_SIZE))
    surf.fill(_FOG_COLOR)
    world_data: dict = getattr(config, "world_data", {}) or {}

    cx0 = int(player_x)
    cy0 = int(player_y)
    visited: set = config.visited_chunks

    for py in range(MM_SIZE):
        for px in range(MM_SIZE):
            tx = cx0 - MM_RADIUS + px // MM_TILE_PX
            ty = cy0 - MM_RADIUS + py // MM_TILE_PX
            chunk_key = (tx // _CHUNK_SIZE, ty // _CHUNK_SIZE)
            if chunk_key not in visited:
                continue  # fog
            tile = world_data.get((tx, ty))
            if tile is None:
                color = _UNKNOWN_COLOR
            elif isinstance(tile, dict):
                color = _BIOME_COLORS.get(tile.get("biome", -1), _UNKNOWN_COLOR)
            else:
                color = _BIOME_COLORS.get(tile, _UNKNOWN_COLOR)
            surf.set_at((px, py), color)

    _mm_surf = surf
    _mm_last_center = (cx0, cy0)


def draw_minimap(screen: pygame.Surface,
                 window_width: int,
                 window_height: int) -> None:
    """Draw the minimap + info panel in the top-right corner of *screen*."""
    global _mm_surf, _mm_last_center

    # --- Get player position ---
    try:
        state_data = getattr(config, "state", None)
        if state_data and "player_data" in state_data:
            px, py = state_data["player_data"]["pos"]
        elif hasattr(config, "player_pos"):
            px, py = config.player_pos
        else:
            return
    except (KeyError, TypeError, AttributeError):
        return

    # --- Mark nearby chunks as visited ---
    chunk_x = int(px) // _CHUNK_SIZE
    chunk_y = int(py) // _CHUNK_SIZE
    visited: set = config.visited_chunks
    for dcx in range(-3, 4):
        for dcy in range(-3, 4):
            visited.add((chunk_x + dcx, chunk_y + dcy))

    # --- Rebuild surface when the player crosses a tile boundary ---
    center = (int(px), int(py))
    if _mm_surf is None or center != _mm_last_center:
        _rebuild(px, py)

    if _mm_surf is None:
        return

    # --- Info rows (built before drawing so we know panel height) ---
    info_font = _get_info_font()
    fh = info_font.get_height()
    row_h = fh + _INFO_GAP

    h_raw = int(config.world_time)
    m_raw = int((config.world_time - h_raw) * 60)
    time_str = f"{h_raw:02d}:{m_raw:02d}"
    weather_raw = getattr(config, "weather", "clear")
    weather_str = f"{_WEATHER_ICONS.get(weather_raw, '')} {weather_raw.capitalize()}"
    biome_str   = getattr(config, "current_biome_name", "") or "—"
    elev_str    = f"{getattr(config, 'current_elevation', 0.0):.2f}"
    coords_str  = f"{int(px)}, {int(py)}"

    info_rows = [
        ("Weather",   weather_str),
        ("Biome",     biome_str),
        ("Coords",    coords_str),
        ("Elev",      elev_str),
        ("Time",      time_str),
    ]
    info_h = len(info_rows) * row_h + _INFO_PAD * 2

    # --- Layout ---
    mm_x = window_width - MM_SIZE - MM_PADDING
    mm_y = MM_PADDING
    panel_w = MM_SIZE + 4   # 2px border on each side
    panel_h = MM_SIZE + info_h + 4

    # Unified dark backdrop
    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 170))
    screen.blit(bg, (mm_x - 2, mm_y - 2))
    pygame.draw.rect(screen, (90, 90, 90),
                     (mm_x - 2, mm_y - 2, panel_w, panel_h), 2)

    # --- Blit minimap tiles ---
    screen.blit(_mm_surf, (mm_x, mm_y))

    # --- Player dot (always centred) ---
    pcx = mm_x + MM_SIZE // 2
    pcy = mm_y + MM_SIZE // 2
    pygame.draw.rect(screen, (255, 255, 255), (pcx - 1, pcy - 1, 3, 3))

    # --- Mob dots ---
    try:
        mobs = getattr(config, "mobs", None) or []
        for mob in mobs:
            try:
                mx, my = mob["pos"]
            except (KeyError, TypeError, ValueError):
                continue
            dx = int((mx - px) * MM_TILE_PX)
            dy = int((my - py) * MM_TILE_PX)
            mdx = pcx + dx
            mdy = pcy + dy
            if mm_x <= mdx <= mm_x + MM_SIZE - 1 and mm_y <= mdy <= mm_y + MM_SIZE - 1:
                mob_type = mob.get("type", "slime")
                if mob_type == "slime_king":
                    color = (255, 200, 0)
                elif mob_type in ("rabbit", "deer"):
                    color = (180, 255, 130)
                else:
                    color = (210, 50, 50)
                pygame.draw.rect(screen, color, (mdx - 1, mdy - 1, 2, 2))
    except (AttributeError, TypeError):
        pass

    # --- Separator between map and info panel ---
    sep_y = mm_y + MM_SIZE + 2
    pygame.draw.line(screen, (70, 70, 70),
                     (mm_x - 2, sep_y), (mm_x + MM_SIZE + 2, sep_y))

    # --- Info rows ---
    ty = sep_y + _INFO_PAD
    for label, value in info_rows:
        label_surf = info_font.render(f"{label}:", True, (160, 160, 180))
        value_surf = info_font.render(value, True, (220, 220, 220))
        screen.blit(label_surf, (mm_x, ty))
        screen.blit(value_surf, (mm_x + MM_SIZE - value_surf.get_width(), ty))
        ty += row_h

    # --- Dungeon (Slime Lair) markers ---
    try:
        dungeons = getattr(config, "dungeons", None) or []
        for dng in dungeons:
            try:
                dx_w, dy_w = dng["pos"]
            except (KeyError, TypeError, ValueError):
                continue
            ddx = int((dx_w - px) * MM_TILE_PX)
            ddy = int((dy_w - py) * MM_TILE_PX)
            mx = pcx + ddx
            my = pcy + ddy
            if mm_x <= mx <= mm_x + MM_SIZE - 1 and mm_y <= my <= mm_y + MM_SIZE - 1:
                # Dark red outer square + brighter inner square (skull-like icon)
                pygame.draw.rect(screen, (140, 20, 20), (mx - 3, my - 3, 7, 7))
                pygame.draw.rect(screen, (220, 60, 60), (mx - 1, my - 1, 3, 3))
    except (AttributeError, TypeError):
        pass

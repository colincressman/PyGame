"""Shared map rendering for the corner minimap and fullscreen world map."""
from collections import Counter, deque
import math
import time
import pygame

import config

MM_SIZE = config.MINIMAP_SIZE
MM_TILE_PX = config.MINIMAP_TILE_PX
MM_PADDING = config.MINIMAP_PADDING
MM_RADIUS = MM_SIZE // (2 * MM_TILE_PX)

_CHUNK_SIZE = config.CHUNK_SIZE
_INFO_PAD = 4
_INFO_GAP = 2
_WORLD_MAP_PAD = 28

_BIOME_COLORS: dict[int, tuple[int, int, int]] = {
    0: (20, 40, 100),
    1: (220, 200, 120),
    2: (60, 80, 40),
    3: (40, 80, 160),
    4: (160, 200, 80),
    5: (30, 100, 30),
    6: (200, 170, 80),
    7: (180, 150, 60),
    8: (40, 160, 60),
    9: (200, 220, 240),
    10: (140, 140, 140),
}
_FOG_COLOR = (20, 20, 20)
_UNKNOWN_COLOR = (45, 45, 45)
_WORLD_BG = (10, 12, 18)
_WORLD_PANEL = (20, 24, 34)
_WORLD_BORDER = (88, 100, 122)
_PLAYER_COLOR = (255, 255, 255)
_DUNGEON_COLOR = (220, 60, 60)
_TOWN_COLOR = (235, 205, 90)
_WAYPOINT_COLOR = (110, 215, 255)
_STRUCTURE_COLOR = (170, 230, 255)
_CLAIM_NEON_PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 64, 180),   # neon pink
    (0, 235, 255),    # electric cyan
    (144, 255, 64),   # acid green
    (255, 170, 40),   # neon orange
    (190, 90, 255),   # hot violet
    (255, 72, 72),    # laser red
    (255, 235, 70),   # bright yellow
    (60, 255, 180),   # mint neon
)

_WEATHER_ICONS = {
    "clear": "[Sun]",
    "cloudy": "[Cloud]",
    "rain": "[Rain]",
    "snow": "[Snow]",
    "fog": "[Fog]",
}

_STRUCTURE_IGNORE_TYPES = {
    "torch",
    "lantern",
    "campfire",
}
_MINIMAP_BLOCK_TYPES = {
    "wood_wall",
    "stone_wall",
    "stone_brick_wall",
    "stone_brick_floor",
    "door",
}
_STRUCTURE_BASE_TYPES = {
    "wood_wall",
    "stone_wall",
    "stone_brick_wall",
    "stone_brick_floor",
    "door",
    "bed",
    "chest",
    "crafting_table",
    "furnace",
    "alloy_forge",
    "part_maker",
    "part_combiner",
    "embedder",
}
_STRUCTURE_COLORS: dict[str, tuple[int, int, int]] = {
    "wood_wall": (173, 122, 72),
    "stone_wall": (126, 126, 136),
    "stone_brick_wall": (164, 184, 214),
    "stone_brick_floor": (140, 160, 190),
    "door": (200, 160, 92),
    "bed": (205, 80, 80),
    "chest": (215, 168, 70),
    "crafting_table": (195, 138, 78),
    "furnace": (120, 120, 132),
    "alloy_forge": (150, 150, 168),
    "part_maker": (120, 205, 225),
    "part_combiner": (188, 126, 232),
    "embedder": (110, 230, 180),
}
_MIN_STRUCTURE_COMPONENT_SIZE = 8

_mm_surf: pygame.Surface | None = None
_mm_last_center: tuple[int, int] | None = None
_mm_info_font: pygame.font.Font | None = None
_map_font: pygame.font.Font | None = None
_world_map_layout: dict | None = None
_world_map_bg_cache: pygame.Surface | None = None
_world_map_bg_cache_key: tuple | None = None
_MM_VISIBLE_TILES = (MM_SIZE + MM_TILE_PX - 1) // MM_TILE_PX


def _get_info_font() -> pygame.font.Font:
    global _mm_info_font
    if _mm_info_font is None:
        _mm_info_font = pygame.font.SysFont("Arial", 12)
    return _mm_info_font


def _get_map_font() -> pygame.font.Font:
    global _map_font
    if _map_font is None:
        _map_font = pygame.font.SysFont("Arial", 14)
    return _map_font


def _get_player_pos() -> tuple[float, float] | None:
    try:
        state_data = getattr(config, "state", None)
        if state_data and "player_data" in state_data:
            px, py = state_data["player_data"]["pos"]
        elif hasattr(config, "player_pos"):
            px, py = config.player_pos
        else:
            return None
    except (KeyError, TypeError, AttributeError):
        return None
    return float(px), float(py)


def _tile_value(tx: int, ty: int):
    tile = config.world_data.get((tx, ty))
    if tile is None:
        tile = config.full_world_data.get((tx, ty))
    return tile


def _tile_color(tile) -> tuple[int, int, int]:
    if tile is None:
        return _UNKNOWN_COLOR
    if isinstance(tile, dict):
        biome = tile.get("biome", -1)
    else:
        biome = tile
    return _BIOME_COLORS.get(biome, _UNKNOWN_COLOR)


def _claim_color(tag: str | None, owner: str | None) -> tuple[int, int, int]:
    seed = f"{tag or ''}:{owner or ''}"
    idx = sum(ord(ch) for ch in seed) % len(_CLAIM_NEON_PALETTE)
    return _CLAIM_NEON_PALETTE[idx]


def _mark_visible_chunks_visited(px: float, py: float) -> None:
    chunk_x = int(px) // _CHUNK_SIZE
    chunk_y = int(py) // _CHUNK_SIZE
    visited: set = config.visited_chunks
    for dcx in range(-3, 4):
        for dcy in range(-3, 4):
            visited.add((chunk_x + dcx, chunk_y + dcy))


def _iter_player_structure_markers():
    structure_tiles: dict[tuple[int, int], dict] = {}
    for obj in config.placed_objects.values():
        obj_type = obj.get("type")
        if obj_type in _STRUCTURE_IGNORE_TYPES:
            continue
        if obj_type not in _STRUCTURE_BASE_TYPES:
            continue
        placed_by = obj.get("placed_by")
        if placed_by in {"town", "dungeon"}:
            continue
        pos = obj.get("pos")
        if not isinstance(pos, list) or len(pos) != 2:
            continue
        structure_tiles[(int(pos[0]), int(pos[1]))] = obj

    seen: set[tuple[int, int]] = set()
    for start in structure_tiles:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        component: list[tuple[int, int]] = []
        type_counts: Counter[str] = Counter()
        while queue:
            tile = queue.popleft()
            component.append(tile)
            obj = structure_tiles[tile]
            obj_type = obj.get("type")
            if isinstance(obj_type, str):
                type_counts[obj_type] += 1
            tx, ty = tile
            for neighbor in ((tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1)):
                if neighbor in seen or neighbor not in structure_tiles:
                    continue
                seen.add(neighbor)
                queue.append(neighbor)

        if len(component) < _MIN_STRUCTURE_COMPONENT_SIZE:
            continue
        dominant_type = type_counts.most_common(1)[0][0] if type_counts else "stone_brick_wall"
        color = _STRUCTURE_COLORS.get(dominant_type, _STRUCTURE_COLOR)
        avg_x = sum(tx for tx, _ in component) / len(component) + 0.5
        avg_y = sum(ty for _, ty in component) / len(component) + 0.5
        yield {
            "pos": [avg_x, avg_y],
            "color": color,
            "size": max(3, min(6, 2 + len(component) // 12)),
        }


def _iter_minimap_structure_tiles():
    for obj in config.placed_objects.values():
        obj_type = obj.get("type")
        if obj_type not in _MINIMAP_BLOCK_TYPES:
            continue
        placed_by = obj.get("placed_by")
        if placed_by in {"town", "dungeon"}:
            continue
        pos = obj.get("pos")
        if not isinstance(pos, list) or len(pos) != 2:
            continue
        color = _STRUCTURE_COLORS.get(obj_type, _STRUCTURE_COLOR)
        yield int(pos[0]), int(pos[1]), color


def _iter_towns():
    return list(getattr(config, "known_towns", {}).values())


def _iter_dungeons():
    return list(getattr(config, "known_dungeons", {}).values())


def _iter_waypoints():
    return list(getattr(config, "waypoints", []))


def _iter_claims():
    return list(getattr(config, "faction_claims", []))


def _claim_chunks_by_owner() -> dict[tuple[int, int], dict]:
    out: dict[tuple[int, int], dict] = {}
    for claim in _iter_claims():
        chunk = claim.get("chunk")
        if not isinstance(chunk, list) or len(chunk) != 2:
            continue
        out[(int(chunk[0]), int(chunk[1]))] = claim
    return out


def _claim_edges_for_chunk(chunk_map: dict[tuple[int, int], dict], cx: int, cy: int, owner: str | None) -> tuple[bool, bool, bool, bool]:
    left_claim = chunk_map.get((cx - 1, cy))
    right_claim = chunk_map.get((cx + 1, cy))
    up_claim = chunk_map.get((cx, cy - 1))
    down_claim = chunk_map.get((cx, cy + 1))
    return (
        left_claim is None or left_claim.get("owner") != owner,
        right_claim is None or right_claim.get("owner") != owner,
        up_claim is None or up_claim.get("owner") != owner,
        down_claim is None or down_claim.get("owner") != owner,
    )


def _draw_claim_outline(screen: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int],
                        edges: tuple[bool, bool, bool, bool], width: int = 1) -> None:
    left, right, top, bottom = edges
    if left:
        pygame.draw.line(screen, color, rect.topleft, rect.bottomleft, width)
    if right:
        pygame.draw.line(screen, color, rect.topright, rect.bottomright, width)
    if top:
        pygame.draw.line(screen, color, rect.topleft, rect.topright, width)
    if bottom:
        pygame.draw.line(screen, color, rect.bottomleft, rect.bottomright, width)


def _world_to_local_minimap(mm_x: int, mm_y: int, px: float, py: float, wx: float, wy: float) -> tuple[int, int]:
    center_x = mm_x + MM_SIZE // 2
    center_y = mm_y + MM_SIZE // 2
    sx = center_x + int((wx - px) * MM_TILE_PX)
    sy = center_y + int((wy - py) * MM_TILE_PX)
    return sx, sy


def _draw_minimap_claims(screen: pygame.Surface, mm_x: int, mm_y: int, px: float, py: float) -> None:
    chunk_map = _claim_chunks_by_owner()
    for (cx, cy), claim in chunk_map.items():
        chunk = claim.get("chunk")
        tx0 = cx * _CHUNK_SIZE
        ty0 = cy * _CHUNK_SIZE
        sx0, sy0 = _world_to_local_minimap(mm_x, mm_y, px, py, tx0, ty0)
        rect = pygame.Rect(sx0, sy0, _CHUNK_SIZE * MM_TILE_PX, _CHUNK_SIZE * MM_TILE_PX)
        if rect.right < mm_x or rect.bottom < mm_y or rect.left > mm_x + MM_SIZE or rect.top > mm_y + MM_SIZE:
            continue
        col = _claim_color(claim.get("tag"), claim.get("owner"))
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*col, 24))
        screen.blit(overlay, rect.topleft)
        edges = _claim_edges_for_chunk(chunk_map, cx, cy, claim.get("owner"))
        _draw_claim_outline(screen, rect, col, edges, 1)


def _draw_minimap_marker(screen: pygame.Surface, mm_x: int, mm_y: int, px: float, py: float,
                         wx: float, wy: float, color: tuple[int, int, int], size: int) -> None:
    sx, sy = _world_to_local_minimap(mm_x, mm_y, px, py, wx, wy)
    if mm_x <= sx <= mm_x + MM_SIZE - 1 and mm_y <= sy <= mm_y + MM_SIZE - 1:
        pygame.draw.rect(screen, color, (sx - size // 2, sy - size // 2, size, size))


def _draw_minimap_structure_tiles(screen: pygame.Surface, mm_x: int, mm_y: int, px: float, py: float) -> None:
    for tx, ty, color in _iter_minimap_structure_tiles():
        sx, sy = _world_to_local_minimap(mm_x, mm_y, px, py, tx, ty)
        rect = pygame.Rect(sx, sy, MM_TILE_PX, MM_TILE_PX)
        if rect.right < mm_x or rect.bottom < mm_y or rect.left > mm_x + MM_SIZE or rect.top > mm_y + MM_SIZE:
            continue
        pygame.draw.rect(screen, color, rect)


def _paint_minimap_tile(surface: pygame.Surface, tile_x: int, tile_y: int, center_x: int, center_y: int,
                        visited: set[tuple[int, int]]) -> None:
    world_x = center_x - MM_RADIUS + tile_x
    world_y = center_y - MM_RADIUS + tile_y
    chunk_key = (world_x // _CHUNK_SIZE, world_y // _CHUNK_SIZE)
    color = _FOG_COLOR if chunk_key not in visited else _tile_color(_tile_value(world_x, world_y))
    px = tile_x * MM_TILE_PX
    py = tile_y * MM_TILE_PX
    draw_w = min(MM_TILE_PX, MM_SIZE - px)
    draw_h = min(MM_TILE_PX, MM_SIZE - py)
    if draw_w > 0 and draw_h > 0:
        pygame.draw.rect(surface, color, (px, py, draw_w, draw_h))


def _rebuild_local_minimap_full(player_x: float, player_y: float) -> None:
    global _mm_surf, _mm_last_center
    surf = pygame.Surface((MM_SIZE, MM_SIZE))
    surf.fill(_FOG_COLOR)

    cx0 = int(player_x)
    cy0 = int(player_y)
    visited: set = config.visited_chunks
    for tile_y in range(_MM_VISIBLE_TILES):
        for tile_x in range(_MM_VISIBLE_TILES):
            _paint_minimap_tile(surf, tile_x, tile_y, cx0, cy0, visited)

    _mm_surf = surf
    _mm_last_center = (cx0, cy0)


def _rebuild_local_minimap(player_x: float, player_y: float) -> None:
    global _mm_surf, _mm_last_center
    cx0 = int(player_x)
    cy0 = int(player_y)
    if _mm_surf is None or _mm_last_center is None:
        _rebuild_local_minimap_full(player_x, player_y)
        return

    dx = cx0 - _mm_last_center[0]
    dy = cy0 - _mm_last_center[1]
    if dx == 0 and dy == 0:
        return
    if abs(dx) >= _MM_VISIBLE_TILES or abs(dy) >= _MM_VISIBLE_TILES:
        _rebuild_local_minimap_full(player_x, player_y)
        return

    visited: set = config.visited_chunks
    prev = _mm_surf
    surf = pygame.Surface((MM_SIZE, MM_SIZE))
    surf.fill(_FOG_COLOR)
    surf.blit(prev, (-dx * MM_TILE_PX, -dy * MM_TILE_PX))

    if dx > 0:
        x_range = range(_MM_VISIBLE_TILES - dx, _MM_VISIBLE_TILES)
    elif dx < 0:
        x_range = range(0, -dx)
    else:
        x_range = range(0, 0)
    for tile_x in x_range:
        for tile_y in range(_MM_VISIBLE_TILES):
            _paint_minimap_tile(surf, tile_x, tile_y, cx0, cy0, visited)

    if dy > 0:
        y_range = range(_MM_VISIBLE_TILES - dy, _MM_VISIBLE_TILES)
    elif dy < 0:
        y_range = range(0, -dy)
    else:
        y_range = range(0, 0)
    for tile_y in y_range:
        for tile_x in range(_MM_VISIBLE_TILES):
            _paint_minimap_tile(surf, tile_x, tile_y, cx0, cy0, visited)

    _mm_surf = surf
    _mm_last_center = (cx0, cy0)


def draw_minimap(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    global _mm_surf, _mm_last_center
    player_pos = _get_player_pos()
    if player_pos is None:
        return
    px, py = player_pos
    _mark_visible_chunks_visited(px, py)

    center = (int(px), int(py))
    if _mm_surf is None or center != _mm_last_center:
        _rebuild_local_minimap(px, py)
    if _mm_surf is None:
        return

    info_font = _get_info_font()
    fh = info_font.get_height()
    row_h = fh + _INFO_GAP
    h_raw = int(config.world_time)
    m_raw = int((config.world_time - h_raw) * 60)
    time_str = f"{h_raw:02d}:{m_raw:02d}"
    weather_raw = getattr(config, "weather", "clear")
    weather_str = f"{_WEATHER_ICONS.get(weather_raw, '')} {weather_raw.capitalize()}"
    biome_str = getattr(config, "current_biome_name", "") or "-"
    elev_str = f"{getattr(config, 'current_elevation', 0.0):.2f}"
    coords_str = f"{int(px)}, {int(py)}"
    info_rows = [
        ("Weather", weather_str),
        ("Biome", biome_str),
        ("Coords", coords_str),
        ("Elev", elev_str),
        ("Time", time_str),
    ]
    info_h = len(info_rows) * row_h + _INFO_PAD * 2

    mm_x = window_width - MM_SIZE - MM_PADDING
    mm_y = MM_PADDING
    panel_w = MM_SIZE + 4
    panel_h = MM_SIZE + info_h + 4

    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 170))
    screen.blit(bg, (mm_x - 2, mm_y - 2))
    pygame.draw.rect(screen, (90, 90, 90), (mm_x - 2, mm_y - 2, panel_w, panel_h), 2)

    screen.blit(_mm_surf, (mm_x, mm_y))
    _draw_minimap_structure_tiles(screen, mm_x, mm_y, px, py)
    _draw_minimap_claims(screen, mm_x, mm_y, px, py)

    pcx = mm_x + MM_SIZE // 2
    pcy = mm_y + MM_SIZE // 2
    pygame.draw.rect(screen, _PLAYER_COLOR, (pcx - 1, pcy - 1, 3, 3))

    now = time.time()
    for mob in (getattr(config, "mob_entities", None) or {}).values():
        try:
            mx, my = mob.get_render_pos(now)
        except Exception:
            continue
        color = (255, 200, 0) if getattr(mob, "mob_type", "slime") == "slime_king" else (
            (180, 255, 130) if getattr(mob, "mob_type", "slime") in ("rabbit", "deer", "cow") else (210, 50, 50)
        )
        _draw_minimap_marker(screen, mm_x, mm_y, px, py, mx, my, color, 2)

    for dng in _iter_dungeons():
        pos = dng.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            _draw_minimap_marker(screen, mm_x, mm_y, px, py, float(pos[0]), float(pos[1]), _DUNGEON_COLOR, 5)
    for town in _iter_towns():
        pos = town.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            _draw_minimap_marker(screen, mm_x, mm_y, px, py, float(pos[0]), float(pos[1]), _TOWN_COLOR, 5)
    for wp in _iter_waypoints():
        pos = wp.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            _draw_minimap_marker(screen, mm_x, mm_y, px, py, float(pos[0]), float(pos[1]), _WAYPOINT_COLOR, 4)
    for marker in _iter_player_structure_markers():
        pos = marker.get("pos")
        color = marker.get("color", _STRUCTURE_COLOR)
        size = int(marker.get("size", 3))
        if isinstance(pos, list) and len(pos) == 2:
            _draw_minimap_marker(screen, mm_x, mm_y, px, py, float(pos[0]), float(pos[1]), color, size)

    sep_y = mm_y + MM_SIZE + 2
    pygame.draw.line(screen, (70, 70, 70), (mm_x - 2, sep_y), (mm_x + MM_SIZE + 2, sep_y))
    ty = sep_y + _INFO_PAD
    for label, value in info_rows:
        label_surf = info_font.render(f"{label}:", True, (160, 160, 180))
        value_surf = info_font.render(value, True, (220, 220, 220))
        screen.blit(label_surf, (mm_x, ty))
        screen.blit(value_surf, (mm_x + MM_SIZE - value_surf.get_width(), ty))
        ty += row_h


def _world_map_bounds(px: float, py: float) -> tuple[float, float, float, float]:
    xs: list[float] = [px]
    ys: list[float] = [py]
    xs.extend(float(tx) for tx, _ in config.full_world_data.keys())
    ys.extend(float(ty) for _, ty in config.full_world_data.keys())

    for cx, cy in getattr(config, "visited_chunks", set()):
        xs.extend([cx * _CHUNK_SIZE, (cx + 1) * _CHUNK_SIZE])
        ys.extend([cy * _CHUNK_SIZE, (cy + 1) * _CHUNK_SIZE])
    for claim in _iter_claims():
        chunk = claim.get("chunk")
        if isinstance(chunk, list) and len(chunk) == 2:
            cx, cy = int(chunk[0]), int(chunk[1])
            xs.extend([cx * _CHUNK_SIZE, (cx + 1) * _CHUNK_SIZE])
            ys.extend([cy * _CHUNK_SIZE, (cy + 1) * _CHUNK_SIZE])
    for collection in (_iter_towns(), _iter_dungeons(), _iter_waypoints()):
        for entry in collection:
            pos = entry.get("pos")
            if isinstance(pos, list) and len(pos) == 2:
                xs.append(float(pos[0]))
                ys.append(float(pos[1]))

    min_x = min(xs) if xs else px
    max_x = max(xs) if xs else px + 1.0
    min_y = min(ys) if ys else py
    max_y = max(ys) if ys else py + 1.0
    if max_x - min_x < 32:
        max_x = min_x + 32
    if max_y - min_y < 32:
        max_y = min_y + 32
    return min_x, min_y, max_x, max_y


def _compute_world_map_layout(window_width: int, window_height: int) -> dict | None:
    player_pos = _get_player_pos()
    if player_pos is None:
        return None
    px, py = player_pos
    min_x, min_y, max_x, max_y = _world_map_bounds(px, py)
    avail_w = max(1, window_width - _WORLD_MAP_PAD * 2)
    avail_h = max(1, window_height - _WORLD_MAP_PAD * 2 - 26)
    span_x = max(1.0, max_x - min_x + 1.0)
    span_y = max(1.0, max_y - min_y + 1.0)
    scale = min(avail_w / span_x, avail_h / span_y)
    scale = max(0.25, scale)
    map_w = span_x * scale
    map_h = span_y * scale
    map_x = (window_width - map_w) / 2.0
    map_y = (window_height - map_h) / 2.0
    return {
        "min_x": min_x,
        "min_y": min_y,
        "max_x": max_x,
        "max_y": max_y,
        "scale": scale,
        "map_x": map_x,
        "map_y": map_y,
        "map_w": map_w,
        "map_h": map_h,
        "player": (px, py),
    }


def _world_to_map(layout: dict, wx: float, wy: float) -> tuple[int, int]:
    sx = int(layout["map_x"] + (wx - layout["min_x"]) * layout["scale"])
    sy = int(layout["map_y"] + (wy - layout["min_y"]) * layout["scale"])
    return sx, sy


def _draw_world_map_claims(screen: pygame.Surface, layout: dict) -> None:
    scale = layout["scale"]
    chunk_map = _claim_chunks_by_owner()
    for (cx, cy), claim in chunk_map.items():
        tx0 = cx * _CHUNK_SIZE
        ty0 = cy * _CHUNK_SIZE
        sx, sy = _world_to_map(layout, tx0, ty0)
        sw = max(1, int(math.ceil(_CHUNK_SIZE * scale)))
        sh = max(1, int(math.ceil(_CHUNK_SIZE * scale)))
        rect = pygame.Rect(sx, sy, sw, sh)
        col = _claim_color(claim.get("tag"), claim.get("owner"))
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((*col, 26))
        screen.blit(overlay, rect.topleft)
        border_w = 2 if scale >= 1.0 else 1
        edges = _claim_edges_for_chunk(chunk_map, cx, cy, claim.get("owner"))
        _draw_claim_outline(screen, rect, col, edges, border_w)


def _draw_world_map_markers(screen: pygame.Surface, layout: dict) -> None:
    for dng in _iter_dungeons():
        pos = dng.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            sx, sy = _world_to_map(layout, float(pos[0]), float(pos[1]))
            pygame.draw.rect(screen, _DUNGEON_COLOR, (sx - 3, sy - 3, 7, 7))
    for town in _iter_towns():
        pos = town.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            sx, sy = _world_to_map(layout, float(pos[0]), float(pos[1]))
            pygame.draw.rect(screen, _TOWN_COLOR, (sx - 3, sy - 3, 7, 7))
    for wp in _iter_waypoints():
        pos = wp.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            sx, sy = _world_to_map(layout, float(pos[0]), float(pos[1]))
            pygame.draw.circle(screen, _WAYPOINT_COLOR, (sx, sy), 4)
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 1)
    for marker in _iter_player_structure_markers():
        pos = marker.get("pos")
        color = marker.get("color", _STRUCTURE_COLOR)
        size = int(marker.get("size", 3))
        if isinstance(pos, list) and len(pos) == 2:
            sx, sy = _world_to_map(layout, float(pos[0]), float(pos[1]))
            r = max(2, min(5, size))
            pygame.draw.rect(screen, color, (sx - r // 2, sy - r // 2, r, r))


def _world_map_cache_key(layout: dict, window_width: int, window_height: int) -> tuple:
    return (
        window_width,
        window_height,
        round(layout["min_x"], 2),
        round(layout["min_y"], 2),
        round(layout["max_x"], 2),
        round(layout["max_y"], 2),
        round(layout["scale"], 4),
        len(config.full_world_data),
        len(getattr(config, "visited_chunks", set())),
        len(_iter_claims()),
        len(_iter_towns()),
        len(_iter_dungeons()),
        len(_iter_waypoints()),
        len(getattr(config, "placed_objects", {})),
    )


def _rebuild_world_map_background(layout: dict, window_width: int, window_height: int) -> pygame.Surface:
    surface = pygame.Surface((window_width, window_height))
    surface.fill(_WORLD_BG)
    panel_rect = pygame.Rect(
        int(layout["map_x"]) - 8,
        int(layout["map_y"]) - 8,
        int(layout["map_w"]) + 16,
        int(layout["map_h"]) + 16,
    )
    pygame.draw.rect(surface, _WORLD_PANEL, panel_rect)
    pygame.draw.rect(surface, _WORLD_BORDER, panel_rect, 2)

    scale = layout["scale"]
    tile_px = max(1, int(math.ceil(scale)))
    for (tx, ty), tile in config.full_world_data.items():
        sx, sy = _world_to_map(layout, tx, ty)
        pygame.draw.rect(surface, _tile_color(tile), (sx, sy, tile_px, tile_px))

    _draw_world_map_claims(surface, layout)
    _draw_world_map_markers(surface, layout)
    return surface


def draw_world_map(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    global _world_map_layout, _world_map_bg_cache, _world_map_bg_cache_key
    player_pos = _get_player_pos()
    if player_pos is None:
        return
    px, py = player_pos
    _world_map_layout = _compute_world_map_layout(window_width, window_height)
    if _world_map_layout is None:
        return
    layout = _world_map_layout

    panel_rect = pygame.Rect(
        int(layout["map_x"]) - 8,
        int(layout["map_y"]) - 8,
        int(layout["map_w"]) + 16,
        int(layout["map_h"]) + 16,
    )
    cache_key = _world_map_cache_key(layout, window_width, window_height)
    if _world_map_bg_cache is None or _world_map_bg_cache_key != cache_key:
        _world_map_bg_cache = _rebuild_world_map_background(layout, window_width, window_height)
        _world_map_bg_cache_key = cache_key
    screen.blit(_world_map_bg_cache, (0, 0))

    psx, psy = _world_to_map(layout, px, py)
    pygame.draw.circle(screen, (230, 70, 70), (psx, psy), 5)
    pygame.draw.circle(screen, (255, 220, 220), (psx, psy), 2)

    font = _get_map_font()
    title = font.render("World Map", True, (235, 235, 235))
    hint = font.render("M close  |  Right click add waypoint  |  Shift+Right click remove", True, (190, 200, 220))
    screen.blit(title, (panel_rect.x, max(4, panel_rect.y - 22)))
    screen.blit(hint, (panel_rect.x, min(window_height - 22, panel_rect.bottom + 8)))


def world_map_tile_at_screen(window_width: int, window_height: int, screen_x: int, screen_y: int) -> tuple[int, int] | None:
    layout = _compute_world_map_layout(window_width, window_height)
    if layout is None:
        return None
    map_x = layout["map_x"]
    map_y = layout["map_y"]
    map_w = layout["map_w"]
    map_h = layout["map_h"]
    if not (map_x <= screen_x <= map_x + map_w and map_y <= screen_y <= map_y + map_h):
        return None
    tile_x = int(layout["min_x"] + (screen_x - map_x) / layout["scale"])
    tile_y = int(layout["min_y"] + (screen_y - map_y) / layout["scale"])
    return tile_x, tile_y


def get_minimap_debug_stats() -> dict[str, int | bool]:
    return {
        "corner_ready": _mm_surf is not None,
        "world_bg_ready": _world_map_bg_cache is not None,
        "explored_tiles": len(config.full_world_data),
        "visited_chunks": len(getattr(config, "visited_chunks", set())),
    }

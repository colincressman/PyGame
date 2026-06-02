# client/rendering/display.py

import pygame, time, queue
import math as _math
import config as _config
from config import BIOME_ID_TO_NAME, CHUNK_SIZE, CLIFF_ID_TO_NAME, FONT_NAME, FONT_SIZE, TILE_SIZE
from shared_lock import data_lock
from rendering.light_sources import apply_light_holes as _apply_light_holes

_MISSING_TILE_SURFACE = None

# Pre-allocated ghost overlay surfaces — reused every frame (fill + blit, no alloc).
# Lazily created on first draw call so pygame is already initialised.
_ghost_surf: pygame.Surface | None = None


def _get_ghost_surf() -> pygame.Surface:
    global _ghost_surf
    if _ghost_surf is None:
        _ghost_surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    return _ghost_surf

# Cache for biome average colours — computed once per tile_images set, never per map open.
# Key: biome name string  →  Value: (r, g, b) tuple
_BIOME_COLORS: dict[str, tuple[int, int, int]] = {}

def _get_missing_tile_surface():
    global _MISSING_TILE_SURFACE
    if _MISSING_TILE_SURFACE is None:
        _MISSING_TILE_SURFACE = pygame.Surface((TILE_SIZE, TILE_SIZE))
        _MISSING_TILE_SURFACE.fill((255, 0, 255))
    return _MISSING_TILE_SURFACE

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


from rendering.item_art import draw_item, draw_node


def draw_world_items(screen, world_items, offset_x, offset_y):
    """Draw dropped world items at their tile positions using camera offset."""
    if not world_items:
        return
    item_size = TILE_SIZE // 2
    pad = (TILE_SIZE - item_size) // 2
    for item in world_items.values():
        sx = int(item["pos"][0] * TILE_SIZE + offset_x + pad)
        sy = int(item["pos"][1] * TILE_SIZE + offset_y + pad)
        draw_item(screen, sx, sy, item_size, item.get("item_id", 1))


def draw_placed_objects(screen, placed_objects: dict, offset_x: int, offset_y: int):
    """Render campfires, crafting tables, and furnaces placed in the world."""
def draw_placed_object(screen, obj: dict, offset_x: int, offset_y: int):
    """Render a single placed world object (campfire / crafting_table / furnace)."""
    T     = TILE_SIZE
    t     = time.time()
    tx, ty = obj["pos"]
    sx    = int(tx * T + offset_x)
    sy    = int(ty * T + offset_y)
    otype = obj.get("type", "")

    if otype == "campfire":
        log_col = (100, 60, 20)
        for dx, _ in [(6, 8), (T - 6, 8)]:
            pygame.draw.line(screen, log_col, (sx + dx, sy + T - 5), (sx + T - dx, sy + T//2), 4)
        flame_on = int(t * 3) % 2 == 0
        fc  = (255, 140, 0) if flame_on else (255, 80, 0)
        fc2 = (255, 230, 60) if flame_on else (255, 160, 20)
        cx  = sx + T // 2
        cy  = sy + T // 3
        fh  = 10 if flame_on else 8
        pygame.draw.polygon(screen, fc,  [(cx, cy - fh), (cx - 6, cy + 5), (cx + 6, cy + 5)])
        pygame.draw.polygon(screen, fc2, [(cx, cy - fh + 4), (cx - 3, cy + 3), (cx + 3, cy + 3)])

    elif otype == "crafting_table":
        pygame.draw.rect(screen, (130, 80, 30), (sx + 3, sy + 3, T - 6, T - 6))
        pygame.draw.rect(screen, (80,  45, 10), (sx + 3, sy + 3, T - 6, T - 6), 2)
        for gx in range(sx + 8, sx + T - 6, 7):
            pygame.draw.line(screen, (105, 60, 20), (gx, sy + 6), (gx, sy + T - 8), 1)

    elif otype == "furnace":
        pygame.draw.rect(screen, (80, 80, 80), (sx + 3, sy + 3, T - 6, T - 6))
        pygame.draw.rect(screen, (50, 50, 50), (sx + 3, sy + 3, T - 6, T - 6), 2)
        glow_on = int(t * 2) % 2 == 0
        gc = (200, 100, 20) if glow_on else (160, 60, 10)
        pygame.draw.rect(screen, gc, (sx + T//2 - 5, sy + T//2 - 5, 10, 10))

    elif otype == "alloy_forge":
        # Dark iron body with two brick side walls and a central glow window
        pygame.draw.rect(screen, (55, 50, 55), (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (35, 30, 35), (sx + 2, sy + 2, T - 4, T - 4), 2)
        # Brick reinforcement strips on sides
        pygame.draw.rect(screen, (100, 80, 58), (sx + 2,      sy + 4, 5, T - 8))
        pygame.draw.rect(screen, (100, 80, 58), (sx + T - 7,  sy + 4, 5, T - 8))
        # Central glow window — alternates orange/gold to look like active alloy heat
        glow_on = int(t * 2) % 2 == 0
        gc  = (210, 140, 30) if glow_on else (170, 90, 15)
        gc2 = (255, 200, 80) if glow_on else (220, 140, 50)
        gw, gh = 10, 7
        gx2 = sx + T // 2 - gw // 2
        gy2 = sy + T // 2 - gh // 2
        pygame.draw.rect(screen, gc,  (gx2, gy2, gw, gh))
        pygame.draw.rect(screen, gc2, (gx2 + 2, gy2 + 1, gw - 4, gh - 2))

    elif otype == "wood_wall":
        pygame.draw.rect(screen, (100, 60, 25), (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (65, 38, 12),  (sx + 2, sy + 2, T - 4, T - 4), 2)
        for px_line in range(sx + 6, sx + T - 4, 8):
            pygame.draw.line(screen, (75, 45, 18), (px_line, sy + 3), (px_line, sy + T - 3), 1)
        pygame.draw.line(screen, (75, 45, 18), (sx + 3, sy + T // 2), (sx + T - 3, sy + T // 2), 1)

    elif otype == "stone_wall":
        pygame.draw.rect(screen, (88, 88, 92),  (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (50, 50, 54),  (sx + 2, sy + 2, T - 4, T - 4), 2)
        pygame.draw.line(screen, (55, 55, 60), (sx + 3,      sy + T//2),  (sx + T - 3, sy + T//2), 1)
        pygame.draw.line(screen, (55, 55, 60), (sx + T//4,   sy + 3),     (sx + T//4,  sy + T//2), 1)
        pygame.draw.line(screen, (55, 55, 60), (sx + 3*T//4, sy + T//2),  (sx + 3*T//4, sy + T - 3), 1)

    elif otype == "stone_brick_wall":
        pygame.draw.rect(screen, (130, 110, 80), (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (90,  72, 50),  (sx + 2, sy + 2, T - 4, T - 4), 2)
        # Brick pattern — two rows of offset bricks
        mid = sy + T // 2
        pygame.draw.line(screen, (90, 72, 50), (sx + 3, mid), (sx + T - 3, mid), 1)
        pygame.draw.line(screen, (90, 72, 50), (sx + T // 3,     sy + 3), (sx + T // 3,     mid), 1)
        pygame.draw.line(screen, (90, 72, 50), (sx + 2 * T // 3, mid),    (sx + 2 * T // 3, sy + T - 3), 1)

    elif otype == "stone_brick_floor":
        pygame.draw.rect(screen, (118, 100, 72), (sx + 1, sy + 1, T - 2, T - 2))
        # Grout lines for a floor tile feel
        mid = sy + T // 2
        pygame.draw.line(screen, (95, 80, 58), (sx + 2, mid), (sx + T - 2, mid), 1)
        pygame.draw.line(screen, (95, 80, 58), (sx + T // 2, sy + 2), (sx + T // 2, mid), 1)
        pygame.draw.line(screen, (95, 80, 58), (sx + T // 4, mid),    (sx + T // 4, sy + T - 2), 1)
        pygame.draw.line(screen, (95, 80, 58), (sx + 3*T//4, mid),    (sx + 3*T//4, sy + T - 2), 1)

    elif otype == "door":
        is_open = obj.get("state", "closed") == "open"
        if is_open:
            pygame.draw.rect(screen, (120, 72, 28), (sx + 2, sy + 2, 6, T - 4))
            pygame.draw.rect(screen, (70, 38, 10),  (sx + 2, sy + 2, 6, T - 4), 1)
        else:
            pygame.draw.rect(screen, (120, 72, 28), (sx + 4, sy + 2, T - 8, T - 4))
            pygame.draw.rect(screen, (70, 38, 10),  (sx + 4, sy + 2, T - 8, T - 4), 2)
            pygame.draw.circle(screen, (200, 160, 60), (sx + T - 8, sy + T // 2), 3)

    elif otype == "bed":
        pygame.draw.rect(screen, (100, 60, 20), (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (65, 38, 10),  (sx + 2, sy + 2, T - 4, T - 4), 2)
        pygame.draw.rect(screen, (240, 230, 200), (sx + 4, sy + 4, T - 8, T // 3))
        pygame.draw.rect(screen, (80, 120, 180),  (sx + 4, sy + 4 + T // 3, T - 8, T - 8 - T // 3))

    elif otype == "chest":
        # Wooden box body
        pygame.draw.rect(screen, (140, 90, 35),  (sx + 3, sy + 5, T - 6, T - 8))
        pygame.draw.rect(screen, (90,  55, 15),  (sx + 3, sy + 5, T - 6, T - 8), 2)
        # Lid stripe
        pygame.draw.rect(screen, (160, 110, 50), (sx + 3, sy + 5, T - 6, (T - 8) // 3))
        # Latch
        pygame.draw.rect(screen, (200, 170, 60), (sx + T // 2 - 3, sy + T // 2 - 2, 6, 5))
        pygame.draw.rect(screen, (140, 110, 30), (sx + T // 2 - 3, sy + T // 2 - 2, 6, 5), 1)
        # Corner iron bands
        for bx2 in (sx + 3, sx + T - 7):
            pygame.draw.line(screen, (80, 70, 60), (bx2, sy + 5), (bx2, sy + T - 3), 2)

    elif otype == "part_maker":
        # Workbench: dark-wood body with purple-tinted top surface and tool markings
        pygame.draw.rect(screen, (80, 50, 22),   (sx + 2, sy + 2, T - 4, T - 4))
        pygame.draw.rect(screen, (50, 30, 10),   (sx + 2, sy + 2, T - 4, T - 4), 2)
        # Table-top surface (purple-tinted)
        pygame.draw.rect(screen, (110, 85, 160), (sx + 3, sy + 3, T - 6, T // 3))
        # Scratch/groove lines to suggest a cutting surface
        for gx2 in range(sx + 7, sx + T - 5, 6):
            pygame.draw.line(screen, (85, 62, 130), (gx2, sy + 4), (gx2, sy + 3 + T // 3 - 1), 1)
        # Small hammer icon in lower half
        pygame.draw.rect(screen, (160, 130, 80), (sx + T // 2 - 5, sy + T // 2,     10, 4))
        pygame.draw.rect(screen, (120,  90, 50), (sx + T // 2 - 1, sy + T // 2 + 4,  2, 6))

    elif otype == "part_combiner":
        # Anvil silhouette: wide base, narrow waist, flat top
        base_y = sy + T - 6
        # Base block
        pygame.draw.rect(screen, (60, 55, 70),  (sx + 5,     base_y - 5, T - 10, 7))
        pygame.draw.rect(screen, (40, 36, 50),  (sx + 5,     base_y - 5, T - 10, 7), 1)
        # Waist
        pygame.draw.rect(screen, (70, 65, 80),  (sx + T//2 - 5, base_y - 10, 10, 6))
        # Top face
        pygame.draw.rect(screen, (90, 80, 110), (sx + 4,     sy + 5, T - 8, base_y - 15 - sy))
        pygame.draw.rect(screen, (55, 48, 70),  (sx + 4,     sy + 5, T - 8, base_y - 15 - sy), 1)
        # Gem inset on top face
        gem_cx = sx + T // 2
        gem_cy = sy + 5 + (base_y - 15 - sy) // 2
        pygame.draw.polygon(screen, (140, 100, 200),
                            [(gem_cx, gem_cy - 4), (gem_cx + 4, gem_cy), (gem_cx, gem_cy + 4), (gem_cx - 4, gem_cy)])
        pygame.draw.polygon(screen, (180, 140, 240),
                            [(gem_cx, gem_cy - 4), (gem_cx + 4, gem_cy), (gem_cx, gem_cy + 4), (gem_cx - 4, gem_cy)], 1)

    elif otype == "embedder":
        # Gem-setting bench: dark stone base + colourful gem-slots table top
        pygame.draw.rect(screen, (45, 38, 55),   (sx + 3, sy + 3, T - 6, T - 6), border_radius=3)
        pygame.draw.rect(screen, (28, 22, 38),   (sx + 3, sy + 3, T - 6, T - 6), 2, border_radius=3)
        # Table-top surface (gold-tinted)
        pygame.draw.rect(screen, (95, 75, 30),   (sx + 4, sy + 4, T - 8, T // 3))
        # Three small gem dots on the surface
        gem_colors = [(220, 60, 40), (60, 160, 240), (60, 200, 80)]
        for gi, gcol in enumerate(gem_colors):
            gdx = sx + T // 4 + gi * (T // 4)
            gdy = sy + 4 + (T // 3) // 2
            pygame.draw.circle(screen, gcol, (gdx, gdy), max(2, T // 10))
        # Leg posts
        for lx2 in (sx + 5, sx + T - 7):
            pygame.draw.rect(screen, (60, 48, 28), (lx2, sy + 4 + T // 3, 4, T - 8 - T // 3))

    elif otype == "torch":
        # Stick with animated flame on top — slim, wall-mounted look
        cx2 = sx + T // 2
        stick_top = sy + T // 3
        stick_bot = sy + T - 5
        pygame.draw.line(screen, (110, 68, 22), (cx2, stick_top), (cx2, stick_bot), 3)
        flame_on = int(t * 4) % 2 == 0
        fc  = (255, 160, 10) if flame_on else (255, 90, 0)
        fc2 = (255, 230, 80) if flame_on else (255, 180, 40)
        fh  = 7 if flame_on else 5
        pygame.draw.polygon(screen, fc,  [(cx2, stick_top - fh), (cx2 - 4, stick_top + 2), (cx2 + 4, stick_top + 2)])
        pygame.draw.polygon(screen, fc2, [(cx2, stick_top - fh + 3), (cx2 - 2, stick_top + 1), (cx2 + 2, stick_top + 1)])

    elif otype == "lantern":
        # Iron frame cage with glowing interior
        cx2 = sx + T // 2
        cy2 = sy + T // 2
        hw, hh = 8, 10
        # Hanging chain
        pygame.draw.line(screen, (140, 135, 148), (cx2, sy + 2), (cx2, cy2 - hh), 1)
        # Iron frame
        pygame.draw.rect(screen, (90, 85, 100), (cx2 - hw, cy2 - hh, hw * 2, hh * 2), 2)
        # Glow interior — flickers
        glow_on = int(t * 3) % 2 == 0
        gc  = (255, 210, 80) if glow_on else (230, 170, 40)
        gc2 = (255, 240, 160) if glow_on else (255, 210, 100)
        pygame.draw.rect(screen, gc,  (cx2 - hw + 2, cy2 - hh + 2, hw * 2 - 4, hh * 2 - 4))
        pygame.draw.circle(screen, gc2, (cx2, cy2), max(3, hw - 3))
        # Overlay frame on top of glow so it looks like glass-in-metal
        pygame.draw.rect(screen, (100, 95, 115), (cx2 - hw, cy2 - hh, hw * 2, hh * 2), 2)
        # Cross bars
        pygame.draw.line(screen, (100, 95, 115), (cx2 - hw, cy2), (cx2 + hw, cy2), 1)
        pygame.draw.line(screen, (100, 95, 115), (cx2, cy2 - hh), (cx2, cy2 + hh), 1)

    elif otype == "tree_sapling":
        # Small sapling: thin trunk + two overlapping leaf circles
        cx2 = sx + T // 2
        pygame.draw.line(screen, (100, 65, 20), (cx2, sy + T - 4), (cx2, sy + T // 2 + 2), 2)
        pygame.draw.circle(screen, (45, 130, 38), (cx2, sy + T // 2 - 2), 7)
        pygame.draw.circle(screen, (70, 175, 55), (cx2, sy + T // 2 - 4), 5)

    elif otype in ("pine_sapling", "jungle_sapling", "palm_sapling"):
        cx2 = sx + T // 2
        _SAP_COLS = {
            "pine_sapling":   ((50, 100, 30),  (80, 140, 45)),
            "jungle_sapling": ((30, 160, 50),  (60, 220, 80)),
            "palm_sapling":   ((120, 170, 50), (160, 210, 75)),
        }
        co, ci = _SAP_COLS[otype]
        pygame.draw.line(screen, (100, 65, 20), (cx2, sy + T - 4), (cx2, sy + T // 2 + 2), 2)
        pygame.draw.circle(screen, co, (cx2, sy + T // 2 - 2), 7)
        pygame.draw.circle(screen, ci, (cx2, sy + T // 2 - 4), 5)

    elif otype in ("iron_seed", "coal_seed", "copper_seed", "tin_seed",
                   "silver_seed", "gold_seed", "crystal_seed", "obsidian_seed"):
        _SEED_COLS = {
            "iron_seed":    ((155, 162, 172), (210, 218, 228)),
            "coal_seed":    ((38,  38,  42),  (80,  80,  88)),
            "copper_seed":  ((148, 88,  42),  (210, 140, 80)),
            "tin_seed":     ((120, 122, 130), (175, 180, 195)),
            "silver_seed":  ((190, 198, 210), (235, 240, 250)),
            "gold_seed":    ((180, 148, 25),  (240, 205, 75)),
            "crystal_seed": ((85,  155, 210), (145, 210, 245)),
            "obsidian_seed":((35,  25,  48),  (80,  58,  110)),
        }
        col_outer, col_inner = _SEED_COLS[otype]
        # Tiny faceted gem shape
        cx2 = sx + T // 2
        cy2 = sy + T // 2
        r = 6
        pts_outer = [(cx2, cy2 - r), (cx2 + r - 2, cy2 - 1), (cx2 + r - 2, cy2 + 2),
                     (cx2, cy2 + r), (cx2 - r + 2, cy2 + 2),  (cx2 - r + 2, cy2 - 1)]
        pygame.draw.polygon(screen, col_outer, pts_outer)
        pts_inner = [(cx2, cy2 - r + 3), (cx2 + r - 4, cy2), (cx2, cy2 + r - 3), (cx2 - r + 4, cy2)]
        pygame.draw.polygon(screen, col_inner, pts_inner)


def draw_placed_objects(screen, placed_objects: dict, offset_x: int, offset_y: int):
    """Draw all placed world objects (non-Y-sorted fallback — prefer the Y-sort path)."""
    for obj in placed_objects.values():
        draw_placed_object(screen, obj, offset_x, offset_y)


def draw_placement_ghost(screen, offset_x: int, offset_y: int):
    """Draw a semi-transparent tile preview at config.mouse_tile when a placeable item is active,
    or an orange demolish highlight when pickup_mode is active."""
    import config as _cfg
    # Hide when any UI overlay is open
    if _cfg.show_inventory or _cfg.show_menu or _cfg.show_stats:
        return
    tx, ty = _cfg.mouse_tile
    sx = int(tx * TILE_SIZE + offset_x)
    sy = int(ty * TILE_SIZE + offset_y)

    if getattr(_cfg, "pickup_mode", False):
        # Pickup mode: highlight tile under cursor in orange
        has_object = any(
            obj["pos"][0] == tx and obj["pos"][1] == ty
            for obj in _cfg.placed_objects.values()
        )
        ghost = _get_ghost_surf()
        if has_object:
            fill   = (220, 120,  30, 110)
            border = (255, 160,  40, 220)
        else:
            fill   = (180,  80,  30,  50)
            border = (200, 100,  40, 120)
        ghost.fill(fill)
        pygame.draw.rect(ghost, border, (0, 0, TILE_SIZE, TILE_SIZE), 2)
        # Draw a small X to signal demolish
        m = TILE_SIZE // 5
        pygame.draw.line(ghost, border, (m, m), (TILE_SIZE - m, TILE_SIZE - m), 2)
        pygame.draw.line(ghost, border, (TILE_SIZE - m, m), (m, TILE_SIZE - m), 2)
        screen.blit(ghost, (sx, sy))
        return

    _HOTBAR_OFFSET = 27  # hotbar row starts at inventory slot 27
    # Only show when a placeable item is active in the hotbar
    active_slot = _HOTBAR_OFFSET + _cfg.hotbar_slot
    inv = _cfg.player_inventory
    if active_slot >= len(inv):
        return
    slot = inv[active_slot]
    _PLACEABLE_IDS = {200, 201, 202, 203, 204, 205, 207, 220, 250, 251, 252, 253, 254}
    if slot is None or slot[0] not in _PLACEABLE_IDS:
        return
    ghost = _get_ghost_surf()
    if _cfg.placement_blocked:
        fill   = (180,  50,  50, 90)
        border = (220,  60,  60, 200)
    else:
        fill   = ( 50, 200,  50, 90)
        border = ( 60, 220,  60, 200)
    ghost.fill(fill)
    pygame.draw.rect(ghost, border, (0, 0, TILE_SIZE, TILE_SIZE), 2)
    screen.blit(ghost, (sx, sy))



# Nodes that should render larger than the default (values > 1.0 overhang the tile)
_NODE_SIZE_OVERRIDE: dict[str, float] = {
    "tree":          3.2,   # ~102 px — ~2× the player (~48 px tall)
    "pine_tree":     3.4,   # slightly taller / narrower
    "jungle_tree":   3.6,   # tall canopy
    "palm_tree":     3.0,   # shorter trunk, smaller canopy
    "cactus":        1.8,   # ~58 px  — ~1.2× the player
    "stone_deposit": 1.5,   # ~48 px  — cluster of rocks
    "coal_deposit":  1.4,   # ~45 px
    "iron_ore":      1.4,   # ~45 px
    "copper_ore":    1.4,
    "tin_ore":       1.4,
    "silver_ore":    1.4,
    "gold_ore":      1.4,
    "crystal":       1.6,
    "obsidian":      1.5,
}
_NODE_SIZE_DEFAULT = 0.65

# These node types participate in Y-depth sorting with the player and mobs
_Y_SORTED_NODES = {
    "tree", "pine_tree", "jungle_tree", "palm_tree",
    "cactus", "stone_deposit", "coal_deposit", "iron_ore",
    "copper_ore", "tin_ore", "silver_ore", "gold_ore", "crystal", "obsidian",
}


def _draw_node_at(screen, node, offset_x, offset_y):
    """Draw one node sprite and its hit-progress bar."""
    ntype     = node.get("type", "tree")
    scale     = _NODE_SIZE_OVERRIDE.get(ntype, _NODE_SIZE_DEFAULT)
    node_size = int(TILE_SIZE * scale)
    # Horizontal: centre on the tile.  Vertical: ground trunk to tile bottom.
    pad_x = (TILE_SIZE - node_size) // 2
    pad_y = TILE_SIZE - node_size

    sx = int(node["wx"] * TILE_SIZE + offset_x + pad_x)
    sy = int(node["wy"] * TILE_SIZE + offset_y + pad_y)

    draw_node(screen, sx, sy, node_size, ntype)

    # Fixed-size health bar anchored to the tile bottom (independent of node art size)
    hits   = node.get("hits", 0)
    max_hp = node.get("max_hp", 1)
    if hits > 0 and max_hp > 1:
        remaining = max(0, max_hp - hits)
        ratio     = remaining / max_hp
        bar_w = TILE_SIZE
        bar_h = 4
        bar_x = int(node["wx"] * TILE_SIZE + offset_x)
        bar_y = int(node["wy"] * TILE_SIZE + offset_y) + TILE_SIZE + 2
        pygame.draw.rect(screen, (30, 30, 30), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * ratio)
        if fill_w > 0:
            bar_col = (50, 200, 50) if ratio > 0.6 else (220, 170, 30) if ratio > 0.3 else (210, 55, 55)
            pygame.draw.rect(screen, bar_col, (bar_x, bar_y, fill_w, bar_h))


def get_node_drawables(screen, world_nodes, offset_x, offset_y):
    """Draw ground-level nodes immediately; return [(sort_y, draw_fn)] for Y-sorted tall nodes."""
    if not world_nodes:
        return []
    screen_rect = screen.get_rect()
    drawables   = []

    for node in list(world_nodes.values()):
        ntype     = node.get("type", "tree")
        if ntype == "item_drop":
            continue   # rendered separately as item sprites in client.py
        scale     = _NODE_SIZE_OVERRIDE.get(ntype, _NODE_SIZE_DEFAULT)
        node_size = int(TILE_SIZE * scale)
        pad_x = (TILE_SIZE - node_size) // 2
        pad_y = TILE_SIZE - node_size

        sx = int(node["wx"] * TILE_SIZE + offset_x + pad_x)
        sy = int(node["wy"] * TILE_SIZE + offset_y + pad_y)

        if sx + node_size < 0 or sx > screen_rect.width:
            continue
        if sy + node_size < 0 or sy > screen_rect.height:
            continue

        if ntype in _Y_SORTED_NODES:
            # Sort on the trunk/base position (bottom of the tile the node occupies)
            sort_y = node["wy"] + 1.0
            drawables.append((sort_y, lambda n=node: _draw_node_at(screen, n, offset_x, offset_y)))
        else:
            _draw_node_at(screen, node, offset_x, offset_y)

    return drawables


# ---------------------------------------------------------------------------
# Day / night overlay
# ---------------------------------------------------------------------------

_night_overlay: pygame.Surface | None = None


def draw_day_night_overlay(screen: pygame.Surface, w: int, h: int) -> None:
    """Blit a translucent dark overlay whose opacity follows the game clock.

    world_time 12 = noon (alpha 0), 0 / 24 = midnight (alpha 160).
    Light holes are punched in for campfires and other light sources.
    """
    global _night_overlay
    wt    = getattr(_config, "world_time", 12.0)
    alpha = int(80 * (1.0 - _math.cos(_math.pi * (wt - 12.0) / 12.0)))
    alpha = max(0, min(160, alpha))
    if alpha <= 0:
        return
    if _night_overlay is None or _night_overlay.get_size() != (w, h):
        _night_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    _night_overlay.fill((10, 10, 35, alpha))
    _apply_light_holes(_night_overlay)
    screen.blit(_night_overlay, (0, 0))


_sleep_overlay: pygame.Surface | None = None
_sleep_font:    pygame.font.Font | None = None
_sleep_subfont: pygame.font.Font | None = None


def draw_sleep_overlay(screen: pygame.Surface, w: int, h: int) -> None:
    """Full-screen dark overlay with 'Zzz' while the player is sleeping."""
    global _sleep_overlay, _sleep_font, _sleep_subfont
    if not getattr(_config, "sleeping", False):
        return
    if _sleep_overlay is None or _sleep_overlay.get_size() != (w, h):
        _sleep_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    _sleep_overlay.fill((5, 5, 20, 200))
    screen.blit(_sleep_overlay, (0, 0))
    if _sleep_font is None:
        _sleep_font = pygame.font.SysFont("Arial", 52, bold=True)
    if _sleep_subfont is None:
        _sleep_subfont = pygame.font.SysFont("Arial", 18)
    text = _sleep_font.render("Zzz", True, (160, 185, 255))
    sub  = _sleep_subfont.render("Press WASD to wake up", True, (120, 135, 170))
    screen.blit(text, (w // 2 - text.get_width() // 2, h // 2 - text.get_height() // 2))
    screen.blit(sub,  (w // 2 - sub.get_width()  // 2, h // 2 + text.get_height() // 2 + 8))


# ---------------------------------------------------------------------------
# Projectile rendering
# ---------------------------------------------------------------------------
# Element → (core_colour, glow_colour)
_PROJ_COLOURS: dict[str, tuple[tuple, tuple]] = {
    "arcane":    ((200, 140, 255), (140,  80, 220)),
    "ice":       (( 80, 215, 250), ( 40, 160, 210)),
    "fire":      ((255, 150,  30), (220,  70,  10)),
    "lightning": ((255, 245,  55), (200, 190,  20)),
    "nature":    (( 80, 225,  90), ( 40, 160,  50)),
    "shadow":    (( 90,  50, 150), ( 50,  20, 100)),
}

_PROJ_RADIUS     = 6   # inner circle radius (px)
_PROJ_GLOW_RADIUS = 11  # outer glow radius (px)


def draw_projectiles(screen: pygame.Surface) -> None:
    """Draw all active projectiles from config.projectiles onto the screen."""
    offset_x = _config.camera_offset_x
    offset_y = _config.camera_offset_y
    for proj in _config.projectiles:
        try:
            wx, wy = proj["pos"]
            elem   = proj.get("element", "arcane")
            core_col, glow_col = _PROJ_COLOURS.get(elem, ((200, 200, 200), (140, 140, 140)))
            sx = int(wx * TILE_SIZE + offset_x + TILE_SIZE // 2)
            sy = int(wy * TILE_SIZE + offset_y + TILE_SIZE // 2)
            # Glow (alpha circle on a temp surface)
            glow_surf = pygame.Surface((_PROJ_GLOW_RADIUS * 2, _PROJ_GLOW_RADIUS * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*glow_col, 90),
                               (_PROJ_GLOW_RADIUS, _PROJ_GLOW_RADIUS), _PROJ_GLOW_RADIUS)
            screen.blit(glow_surf, (sx - _PROJ_GLOW_RADIUS, sy - _PROJ_GLOW_RADIUS))
            # Core
            pygame.draw.circle(screen, core_col, (sx, sy), _PROJ_RADIUS)
            # Bright centre
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), max(1, _PROJ_RADIUS - 3))
        except (KeyError, TypeError, ValueError):
            continue


def draw_info_overlay(screen, font, fps, ping, biome, elevation, player_x, player_y):
    """Top-left FPS / Ping overlay only — biome/coords live on the minimap HUD."""
    for i, line in enumerate([f"FPS: {int(fps)}", f"Ping: {ping} ms"]):
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
    """Return a full window-size map surface, player always centered."""
    TILE_PX = 4          # screen pixels per quarter-chunk block
    quarter_size = chunk_size
    win_w, win_h = window_size

    # Step 1: Tally dominant biome per quarter-chunk
    quarter_biome_counts = {}
    for (tx, ty), tile_data in items_copy:
        qx, qy = tx // quarter_size, ty // quarter_size
        raw_biome = tile_data.get("biome") if isinstance(tile_data, dict) else tile_data
        biome = resolve_biome_name(raw_biome)
        d = quarter_biome_counts.setdefault((qx, qy), {})
        d[biome] = d.get(biome, 0) + 1

    if not quarter_biome_counts:
        return pygame.Surface((win_w, win_h))

    # Step 2: Player quarter-chunk position → screen center
    player_qx = int(player_x) // quarter_size
    player_qy = int(player_y) // quarter_size
    cx, cy = win_w // 2, win_h // 2

    # Step 3: Dark background (unexplored = dark navy)
    out = pygame.Surface((win_w, win_h))
    out.fill((15, 15, 28))

    # Step 4: Paint explored tiles relative to player
    for (qx, qy), biome_counts in quarter_biome_counts.items():
        dominant_biome = max(biome_counts.items(), key=lambda x: x[1])[0]
        color = (160, 160, 160)
        if dominant_biome in tile_images:
            if dominant_biome not in _BIOME_COLORS:
                avg = pygame.transform.scale(tile_images[dominant_biome], (1, 1)).get_at((0, 0))
                _BIOME_COLORS[dominant_biome] = (avg.r, avg.g, avg.b)
            color = _BIOME_COLORS[dominant_biome]

        sx = cx + (qx - player_qx) * TILE_PX
        sy = cy + (qy - player_qy) * TILE_PX
        if sx + TILE_PX < 0 or sy + TILE_PX < 0 or sx >= win_w or sy >= win_h:
            continue
        out.fill(color, (sx, sy, TILE_PX, TILE_PX))

    # Step 5: Player dot — always at center
    pygame.draw.circle(out, (230, 60, 60), (cx, cy), 5)
    pygame.draw.circle(out, (255, 220, 220), (cx, cy), 2)

    return out

def resolve_biome_name(biome_id_or_name):
    if isinstance(biome_id_or_name, int):
        return CLIFF_ID_TO_NAME.get(biome_id_or_name, BIOME_ID_TO_NAME.get(biome_id_or_name, "unknown"))
    return biome_id_or_name

def render_chunk(cx, cy, world_data, tile_images, tile_cache):
    incomplete = False
    chunk_surface = pygame.Surface((CHUNK_SIZE * TILE_SIZE, CHUNK_SIZE * TILE_SIZE))
    chunk_surface.fill((0, 0, 0))

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
                tile_surface = tile_cache.get(tile_type)

                if tile_surface is None:
                    base_surface = tile_images.get(tile_type)
                    tile_surface = base_surface if base_surface else _get_missing_tile_surface()
                    tile_cache[tile_type] = tile_surface

                chunk_surface.blit(tile_surface, (tx_off * TILE_SIZE, ty_off * TILE_SIZE))
            else:
                incomplete = True

    return chunk_surface, not incomplete


def run_minimap_renderer(minimap_queue, tile_images, state):
    _my_session = _config.session_id
    while _config.session_id == _my_session:
        try:
            try:
                items, player_x, player_y, window_size, chunk_size = minimap_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            minimap_surface = generate_minimap_surface(
                tile_images, items, player_x, player_y,
                window_size, chunk_size
            )
            if minimap_surface is None:
                minimap_queue.task_done()
                continue
            state["map_surface_cache"] = minimap_surface
            state["map_needs_redraw"] = False
            minimap_queue.task_done()
        except Exception as e:
            print(f"[MINIMAP_RENDERER ERROR] {e}")
            minimap_queue.task_done()


def run_chunk_renderer(render_queue, world_data, tile_images, tile_cache,
                       data_lock, chunk_cache, scheduled_chunk_renders, state):
    _my_session = _config.session_id
    while _config.session_id == _my_session:
        try:
            try:
                _, (cx, cy) = render_queue.get(timeout=0.5)
            except queue.Empty:
                continue
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
        except Exception as e:
            print(f"[CHUNK_RENDERER ERROR] {e}")
            render_queue.task_done()

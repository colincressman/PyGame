import os
import json
import pygame
from rendering.gem_data import GEM_COLORS
from rendering.progression_data import QUALITY_BORDERS, QUALITY_COLORS, QUALITY_SELL_MULT, STAT_LABELS
from rendering import ui_theme as _T
import config

SLOT_SIZE = 40
SLOT_PAD  = 4
HOTBAR_SLOTS = 9
GRID_ROWS    = 4
GRID_COLS    = 9

_item_images = {}
_font = None
_tooltip_font = None
_items_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "texturepack", "items")

# ── Item name lookup (mirrors server/items.json) ────────────────────────────
_ITEM_NAMES = {}
_ITEM_SELL_PRICES = {}   # base sell price per item_id
_ITEM_SLOT_TYPES  = {}   # item_id → slot_type string (e.g. "weapon", "head")
_ITEM_CONSUMABLE  = {}   # item_id → True if consumable
_ITEM_MAX_STACK   = {}   # item_id → max stack size
_ITEM_STACKABLE   = {}   # item_id → bool
_ITEM_NAMES_LOADED = False

def _load_item_names():
    global _ITEM_NAMES_LOADED
    if _ITEM_NAMES_LOADED:
        return
    _ITEM_NAMES_LOADED = True
    items_json = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "server", "items.json"
    )
    try:
        with open(items_json, "r") as f:
            data = json.load(f)
        for k, v in data.items():
            iid = int(k)
            _ITEM_NAMES[iid]       = v.get("name", f"Item {k}")
            _ITEM_SELL_PRICES[iid] = v.get("sell_price", 0)
            _ITEM_MAX_STACK[iid]   = v.get("max_stack", 1)
            _ITEM_STACKABLE[iid]   = bool(v.get("stackable", False))
            slot_t = v.get("slot_type")
            if slot_t:
                _ITEM_SLOT_TYPES[iid] = slot_t
            if v.get("consumable"):
                _ITEM_CONSUMABLE[iid] = True
    except Exception:
        pass

def _is_consumable(item_id: int) -> bool:
    _load_item_names()
    return _ITEM_CONSUMABLE.get(item_id, False)

def _get_item_name(item_id):
    _load_item_names()
    return _ITEM_NAMES.get(item_id, f"Item {item_id}")

def get_item_max_stack(item_id: int) -> int:
    _load_item_names()
    return _ITEM_MAX_STACK.get(item_id, 1)

def is_item_stackable(item_id: int) -> bool:
    _load_item_names()
    return _ITEM_STACKABLE.get(item_id, False)

def _get_font():
    global _font
    if _font is None:
        _font = pygame.font.SysFont("Arial", 11)
    return _font


def _get_tooltip_font():
    global _tooltip_font
    if _tooltip_font is None:
        _tooltip_font = pygame.font.SysFont("Arial", 13)
    return _tooltip_font


def _get_item_image(item_id):
    if item_id not in _item_images:
        path = os.path.join(_items_dir, f"{item_id}.png")
        img_size = SLOT_SIZE - 8
        try:
            img = pygame.image.load(path).convert_alpha()
            _item_images[item_id] = pygame.transform.scale(img, (img_size, img_size))
        except Exception:
            from rendering.item_art import draw_item
            surf = pygame.Surface((img_size, img_size), pygame.SRCALPHA)
            draw_item(surf, 0, 0, img_size, item_id)
            _item_images[item_id] = surf
    return _item_images[item_id]


def _draw_slot(screen, x, y, item, selected=False, hover=False):
    bg      = _T.SLOT_BG
    if selected:
        border = (255, 200, 0)
    elif hover:
        border = (200, 200, 255)
    else:
        border = _T.SLOT_BD

    # Override border color with quality tier when item has rolled stats
    if item is not None and not selected:
        _meta = item[2] if len(item) >= 3 and isinstance(item[2], dict) else None
        _q    = _meta.get("quality") if _meta else None
        if _q and _q in QUALITY_BORDERS:
            border = QUALITY_BORDERS[_q]
    pygame.draw.rect(screen, bg,     (x, y, SLOT_SIZE, SLOT_SIZE), border_radius=3)
    pygame.draw.rect(screen, border, (x, y, SLOT_SIZE, SLOT_SIZE), 2, border_radius=3)

    if item is not None:
        item_id, qty = item[0], item[1]
        meta     = item[2] if len(item) >= 3 and isinstance(item[2], dict) else None
        material = meta.get("material") if meta else None
        if material:
            from rendering.item_art import draw_item_tinted
            draw_item_tinted(screen, x + 4, y + 4, SLOT_SIZE - 8, item_id, material)
        else:
            screen.blit(_get_item_image(item_id), (x + 4, y + 4))
        if qty > 1:
            txt = _get_font().render(str(qty), True, (255, 255, 255))
            screen.blit(txt, (x + 3, y + SLOT_SIZE - txt.get_height() - 2))
        # Durability bar (3 px high, across slot bottom, offset up by 4px from border)
        if meta is not None:
            dur_max = meta.get("dur_max", 0)
            if dur_max > 0:
                ratio   = max(0.0, min(1.0, meta.get("dur", 0) / dur_max))
                bar_w   = SLOT_SIZE - 8
                bar_x   = x + 4
                bar_y   = y + SLOT_SIZE - 7
                pygame.draw.rect(screen, (45, 45, 45), (bar_x, bar_y, bar_w, 3))
                fill_w = max(1, int(bar_w * ratio))
                if ratio > 0.5:
                    bar_color = (60, 200, 60)
                elif ratio > 0.25:
                    bar_color = (220, 200, 40)
                else:
                    bar_color = (220, 60, 40)
                pygame.draw.rect(screen, bar_color, (bar_x, bar_y, fill_w, 3))
            # Gem dot overlay — small filled circle at bottom-right of art area
            if meta.get("gem_trait"):
                dot_col = GEM_COLORS.get(meta["gem_trait"], (200, 200, 200))
                dot_r   = max(3, SLOT_SIZE // 10)
                dot_x   = x + SLOT_SIZE - dot_r - 4
                dot_y   = y + 4 + dot_r
                pygame.draw.circle(screen, (20, 20, 20), (dot_x, dot_y), dot_r + 1)
                pygame.draw.circle(screen, dot_col,      (dot_x, dot_y), dot_r)

# Tooltip cache — rebuilt only when the hovered slot content changes.
_tooltip_cache: dict = {"key": None, "surface": None, "size": (0, 0)}


def _tooltip_key(slot):
    """Hashable representation of a slot's content for cache invalidation."""
    if len(slot) >= 3 and isinstance(slot[2], dict):
        meta = slot[2]
        return (slot[0], slot[1], meta.get("quality"), tuple(sorted(meta.get("stats", {}).items())),
                meta.get("dur"), meta.get("dur_max"),
                meta.get("mining_damage"), meta.get("mining_tier"),
                tuple(meta.get("traits", [])), meta.get("speed_mult"))
    return (slot[0], slot[1])


def _build_tooltip_surface(slot):
    """Render the tooltip into a standalone Surface. Caller blits it at the right position."""
    _load_item_names()
    item_id = slot[0]
    qty     = slot[1]
    meta    = slot[2] if len(slot) >= 3 and isinstance(slot[2], dict) else None
    quality = meta.get("quality") if meta else None
    stats   = meta.get("stats", {}) if meta else {}
    name    = (meta.get("name") if meta else None) or _get_item_name(item_id)
    gem_name = (meta.get("gem") if meta else None)
    if gem_name:
        name = f"{name}  [{gem_name}]"
    font    = _get_tooltip_font()
    pad     = 6

    base_price = _ITEM_SELL_PRICES.get(item_id, 0)
    q_mult     = QUALITY_SELL_MULT.get(quality, 1) if quality else 1
    sell_value = base_price * qty * q_mult

    name_col = QUALITY_COLORS.get(quality, (240, 240, 220))
    label    = f"{quality} {name}" if quality else name
    lines    = [font.render(label, True, name_col)]
    for stat_key, stat_val in stats.items():
        lbl = STAT_LABELS.get(stat_key, stat_key)
        txt = f"+{stat_val:.1f} {lbl}" if isinstance(stat_val, float) else f"+{stat_val} {lbl}"
        lines.append(font.render(txt, True, (160, 210, 255)))
    if meta and meta.get("mining_damage"):
        lines.append(font.render(f"Mining DMG  {meta['mining_damage']}", True, (160, 210, 255)))
    if meta and meta.get("mining_tier"):
        tier_lbl = meta["mining_tier"].replace("_", " ").title()
        lines.append(font.render(f"Mining Tier  {tier_lbl}", True, (160, 210, 255)))
    if meta and meta.get("traits"):
        lines.append(font.render("Traits: " + ", ".join(meta["traits"]), True, (255, 210, 120)))
    if meta and meta.get("speed_mult") and meta["speed_mult"] != 1.0:
        pct  = round((meta["speed_mult"] - 1.0) * 100)
        sign = "+" if pct > 0 else ""
        lines.append(font.render(f"Speed  {sign}{pct}%", True, (160, 210, 255)))
    if meta and meta.get("dur_max"):
        dur     = meta.get("dur", 0)
        dur_max = meta["dur_max"]
        ratio   = dur / dur_max
        if ratio > 0.5:
            dur_col = (80, 220, 80)
        elif ratio > 0.25:
            dur_col = (230, 210, 50)
        else:
            dur_col = (230, 70, 50)
        lines.append(font.render(f"DUR  {dur} / {dur_max}", True, dur_col))

    tw = max(s.get_width() for s in lines) + pad * 2
    th = sum(s.get_height() for s in lines) + pad * 2 + max(0, len(lines) - 1) * 2
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    surf.fill((18, 18, 24, 230))
    pygame.draw.rect(surf, (160, 160, 120), (0, 0, tw, th), 1, border_radius=4)
    cy = pad
    for s in lines:
        surf.blit(s, (pad, cy))
        cy += s.get_height() + 2
    return surf


def _draw_tooltip(screen, slot, mx, my, window_width, window_height):
    """Draw an item popup near the cursor, using a cached surface when the slot hasn't changed."""
    key = _tooltip_key(slot)
    if _tooltip_cache["key"] != key:
        _tooltip_cache["key"]     = key
        _tooltip_cache["surface"] = _build_tooltip_surface(slot)
        _tooltip_cache["size"]    = _tooltip_cache["surface"].get_size()

    tw, th = _tooltip_cache["size"]
    tx = mx + 14
    ty = my - th - 4
    if tx + tw > window_width:
        tx = mx - tw - 4
    if ty < 0:
        ty = my + 18
    screen.blit(_tooltip_cache["surface"], (tx, ty))


# ── Equipment slot constants ─────────────────────────────────────────────────
# 12 equip slots: 36=head, 37=chest, 38=ring1, 39=ring2,
#                40=pants, 41=shoes, 42=arms, 43=necklace, 44=back,
#                45=shield, 46=shoulders, 47=hands
# Layout: left col (HEAD/CHEST/ARMS), right col (NECKLACE/BACK/RING1),
#         bottom center row (RING2/PANTS/SHOES/SHIELD/PAUL/HANDS)
_EQUIP_COLS_ROWS  = 3                              # rows in left/right columns
_EQUIP_BOTTOM_GAP = 8                              # gap between column rows and bottom row
_EQUIP_SECTION_H  = (_EQUIP_COLS_ROWS * (40 + 4) - 4   # 128px for 3 rows
                     + _EQUIP_BOTTOM_GAP + 40)          # +8 gap +40 bottom row = 176px
_EQUIP_GAP        = 8                              # gap between equip section and grid
_SELL_ZONE_H      = 30                             # height of the sell drop zone below the grid

_EQUIP_SLOT_LABELS = {
    36: "HEAD",  37: "CHEST",  38: "RING",
    39: "RING",  40: "PANTS",  41: "SHOES",
    42: "ARMS",  43: "NECK",   44: "BACK",
    45: "SHLD",  46: "PAUL",   47: "HANDS"
}
_EQUIP_SLOT_COLORS = {
    36: (160, 200, 255),   # head    — armor blue
    37: (160, 200, 255),   # chest   — armor blue
    38: (255, 210, 80),    # ring1   — gold
    39: (255, 210, 80),    # ring2   — gold
    40: (160, 200, 255),   # pants   — armor blue
    41: (160, 200, 255),   # shoes   — armor blue
    42: (160, 200, 255),   # arms    — armor blue
    43: (255, 210, 80),    # necklace — gold
    44: (150, 230, 150),   # back    — green
    45: (160, 200, 255),   # shield  — armor blue
    46: (160, 200, 255),   # shoulders — armor blue
    47: (160, 200, 255),   # hands — armor blue
}

# Maps equip slot index → required item slot_type.
# Mirrors server/item_data.py _EQUIP_SLOT_TYPES.
_EQUIP_SLOT_TYPES: dict[int, str] = {
    36: "head",
    37: "chest",
    38: "ring",
    39: "ring",
    40: "pants",
    41: "shoes",
    42: "arms",
    43: "necklace",
    44: "back",
    45: "shield",
    46: "shoulders",
    47: "hands",
}


def can_drop_in_slot(item_id: int, target_slot: int) -> bool:
    """Return True if item_id may be placed in target_slot.

    Regular inventory / hotbar slots (0-35) accept anything.
    Equip slots (36-44) require the item's slot_type to match.
    Items with no slot_type (materials, coins) are rejected from equip slots.
    Weapons (slot_type='weapon') are hotbar-only and are rejected from equip slots.
    """
    if target_slot < 36:
        return True
    _load_item_names()  # ensure slot types are loaded
    required = _EQUIP_SLOT_TYPES.get(target_slot)
    item_type = _ITEM_SLOT_TYPES.get(item_id)
    return required is not None and item_type == required

def _get_preview():
    """Render a live LPC character preview (idle, facing down, frame 0).
    Called every frame the inventory is open — no persistent cache so it
    always reflects the current equipment and held item."""
    import config
    from rendering.player import _get_cached, _BODY_FOLDER, _HEAD_FOLDER
    from rendering.equipment_layers import get_layers, get_weapon_layer, get_wing_item
    from rendering.lpc import DIR_ROW, CELL

    target_h    = _EQUIP_COLS_ROWS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 128 px
    cell_scaled = int(CELL * (target_h / CELL))                           # = 128
    surf        = pygame.Surface((cell_scaled, cell_scaled), pygame.SRCALPHA)

    dir_row = DIR_ROW["down"]   # face the player toward the camera
    anim    = "idle"
    frame   = 0

    # Resolve wing layers (rendered bg-before-body, fg-after-equipment)
    wing_info   = get_wing_item(config.player_inventory)
    wing_bg_fld = wing_info[0] if wing_info else None
    wing_fg_fld = wing_info[1] if wing_info else None
    wing_col    = wing_info[2] if wing_info else None

    # Wing background (behind body)
    if wing_bg_fld:
        wbg_frames = _get_cached(wing_bg_fld, anim, wing_col)
        if wbg_frames is None:
            wbg_frames = _get_cached(wing_bg_fld, "walk", wing_col)
        if wbg_frames and dir_row < len(wbg_frames) and frame < len(wbg_frames[dir_row]):
            f = pygame.transform.scale(wbg_frames[dir_row][frame], (cell_scaled, cell_scaled))
            surf.blit(f, (0, 0))

    # Body + head base layers
    for base_folder in (_BODY_FOLDER, _HEAD_FOLDER):
        frames = _get_cached(base_folder, anim, None)
        if frames and dir_row < len(frames) and frame < len(frames[dir_row]):
            f = pygame.transform.scale(frames[dir_row][frame], (cell_scaled, cell_scaled))
            surf.blit(f, (0, 0))

    # Equipment layers (legs → torso → arms → feet → head)
    for spec in get_layers(config.player_inventory):
        frames = _get_cached(spec.folder, anim, spec.colour)
        if frames is None:
            frames = _get_cached(spec.folder, "walk", spec.colour)
        if frames and dir_row < len(frames) and frame < len(frames[dir_row]):
            f = pygame.transform.scale(frames[dir_row][frame], (cell_scaled, cell_scaled))
            if spec.tint:
                f = f.copy()
                f.fill(spec.tint, special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(f, (0, 0))

    # Wing foreground (in front of body and equipment)
    if wing_fg_fld:
        wfg_frames = _get_cached(wing_fg_fld, anim, wing_col)
        if wfg_frames is None:
            wfg_frames = _get_cached(wing_fg_fld, "walk", wing_col)
        if wfg_frames and dir_row < len(wfg_frames) and frame < len(wfg_frames[dir_row]):
            f = pygame.transform.scale(wfg_frames[dir_row][frame], (cell_scaled, cell_scaled))
            surf.blit(f, (0, 0))

    # Weapon / tool held in hotbar
    weapon_spec = get_weapon_layer(config.player_inventory)
    if weapon_spec is not None:
        w_frames = _get_cached(weapon_spec.folder, anim, weapon_spec.colour)
        if w_frames is None:
            w_frames = _get_cached(weapon_spec.folder, "walk", weapon_spec.colour)
        if w_frames is None:
            # Wand: slash sheet only — use frame 0 as static hold pose
            w_frames = _get_cached(weapon_spec.folder, "slash", weapon_spec.colour)
        if w_frames and dir_row < len(w_frames) and w_frames[dir_row]:
            f = pygame.transform.scale(w_frames[dir_row][0], (cell_scaled, cell_scaled))
            if weapon_spec.tint:
                f = f.copy()
                f.fill(weapon_spec.tint, special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(f, (0, 0))

    return surf


def _panel_dims():
    """Return (panel_w, panel_h, panel_pad, grid_w, grid_h)."""
    panel_pad = 12
    grid_w = GRID_COLS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 392
    grid_h = GRID_ROWS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 172
    panel_w = grid_w + panel_pad * 2                           # 416
    panel_h = (panel_pad * 2 + 20                              # title area
               + _EQUIP_SECTION_H + _EQUIP_GAP                # equipment preview
               + grid_h)                                       # inventory grid
    return panel_w, panel_h, panel_pad, grid_w, grid_h


def get_sell_zone_rect(window_width, window_height):
    """Return the pygame.Rect of the sell-item drop zone (only relevant in bag tab)."""
    sx, sy = _panel_origin(window_width, window_height)
    panel_w, panel_h, panel_pad, grid_w, _ = _panel_dims()
    grid_x, grid_y = _inv_grid_origin(window_width, window_height)
    _, _, _, _, grid_h = _panel_dims()
    zone_y = grid_y + grid_h + 6
    zone_x = sx + panel_pad
    return pygame.Rect(zone_x, zone_y, grid_w, _SELL_ZONE_H)


def _panel_origin(window_width, window_height):
    """Top-left corner of the full inventory+equipment panel."""
    panel_w, panel_h, _, _, _ = _panel_dims()
    sx = (window_width - panel_w) // 2
    return sx, (window_height - panel_h) // 2


def _equip_slot_positions(window_width, window_height):
    """Return {slot_idx: (x, y)} for the 12 equipment slots (36-47)."""
    sx, sy = _panel_origin(window_width, window_height)
    _, _, panel_pad, grid_w, _ = _panel_dims()
    grid_x  = sx + panel_pad
    equip_y = sy + panel_pad + 20   # below title

    left_x  = grid_x
    right_x = grid_x + grid_w - SLOT_SIZE

    # Left column: HEAD (36), CHEST (37), ARMS (42)
    # Right column: NECKLACE (43), BACK (44), RING1 (38)
    positions = {}
    for i, slot_idx in enumerate([36, 37, 42]):
        positions[slot_idx] = (left_x,  equip_y + i * (SLOT_SIZE + SLOT_PAD))
    for i, slot_idx in enumerate([43, 44, 38]):
        positions[slot_idx] = (right_x, equip_y + i * (SLOT_SIZE + SLOT_PAD))

    # Bottom center row: RING2 (39), PANTS (40), SHOES (41), SHIELD (45), SHOULDERS (46), HANDS (47)
    cols_h      = _EQUIP_COLS_ROWS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 128
    bottom_y    = equip_y + cols_h + _EQUIP_BOTTOM_GAP
    row_slots   = [39, 40, 41, 45, 46, 47]
    row_w       = len(row_slots) * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD     # 216
    row_start_x = grid_x + (grid_w - row_w) // 2
    for i, slot_idx in enumerate(row_slots):
        positions[slot_idx] = (row_start_x + i * (SLOT_SIZE + SLOT_PAD), bottom_y)

    return positions


def _draw_equip_slot(screen, x, y, slot_idx, item, hover=False):
    label  = _EQUIP_SLOT_LABELS.get(slot_idx, "?")
    border = (255, 255, 255) if hover else _EQUIP_SLOT_COLORS.get(slot_idx, (180, 180, 180))
    pygame.draw.rect(screen, (35, 35, 45),  (x, y, SLOT_SIZE, SLOT_SIZE), border_radius=4)
    pygame.draw.rect(screen, border,        (x, y, SLOT_SIZE, SLOT_SIZE), 2, border_radius=4)
    if item is not None:
        screen.blit(_get_item_image(item[0]), (x + 4, y + 4))
        if item[1] > 1:
            txt = _get_font().render(str(item[1]), True, (255, 255, 255))
            screen.blit(txt, (x + 3, y + SLOT_SIZE - txt.get_height() - 2))
    else:
        lbl = _get_font().render(label, True, (70, 70, 90))
        screen.blit(lbl, (x + (SLOT_SIZE - lbl.get_width()) // 2,
                          y + (SLOT_SIZE - lbl.get_height()) // 2))


def _inv_grid_origin(window_width, window_height):
    """Return (grid_x, grid_y) pixel origin of the inventory grid."""
    sx, sy = _panel_origin(window_width, window_height)
    _, _, panel_pad, _, _ = _panel_dims()
    return sx + panel_pad, sy + panel_pad + 20 + _EQUIP_SECTION_H + _EQUIP_GAP


def inventory_tab_hit(mx: int, my: int, window_width: int, window_height: int):
    """Return 'bag', 'craft', or 'creative' if (mx,my) is on the tab row, else None."""
    sx, sy = _panel_origin(window_width, window_height)
    panel_w, _, _, _, _ = _panel_dims()
    tab_y  = sy + 2
    tab_h  = 18
    if tab_y <= my < tab_y + tab_h and sx <= mx < sx + panel_w:
        tabs = _get_tabs()
        tab_w = panel_w // len(tabs)
        idx   = (mx - sx) // tab_w
        idx   = min(idx, len(tabs) - 1)
        return tabs[idx][0]
    return None


def _get_tabs():
    """Return list of (tab_id, label) based on current creative mode state."""
    tabs = [("bag", "BAG"), ("craft", "CRAFT")]
    if config.player_creative:
        tabs.append(("creative", "CREATIVE"))
    return tabs


def slot_at(mx, my, window_width, window_height):
    """Return slot index under (mx, my): 0-35 inventory, 36-46 equip, or None."""
    if config.show_inventory and config.inventory_tab == "bag":
        # Equipment slots (36-44) — check these first
        for idx, (ex, ey) in _equip_slot_positions(window_width, window_height).items():
            if ex <= mx < ex + SLOT_SIZE and ey <= my < ey + SLOT_SIZE:
                return idx

        # Inventory grid (0-35)
        gx, gy = _inv_grid_origin(window_width, window_height)
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                x = gx + col * (SLOT_SIZE + SLOT_PAD)
                y = gy + row * (SLOT_SIZE + SLOT_PAD)
                if x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE:
                    return row * GRID_COLS + col

    # Hotbar is always shown
    total_w = GRID_COLS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD
    hb_x    = (window_width - total_w) // 2
    hb_y    = window_height - SLOT_SIZE - 10
    for i in range(GRID_COLS):
        x = hb_x + i * (SLOT_SIZE + SLOT_PAD)
        if x <= mx < x + SLOT_SIZE and hb_y <= my < hb_y + SLOT_SIZE:
            return 27 + i

    return None


def draw_hotbar(screen, window_width, window_height):
    inv      = config.player_inventory
    selected = config.hotbar_slot
    total_w  = GRID_COLS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD
    start_x  = (window_width - total_w) // 2
    y        = window_height - SLOT_SIZE - 10

    font    = _get_font()
    label_h = font.get_height() + 2

    # No separate backdrop — draw_hud renders the unified panel that covers this area

    for i in range(GRID_COLS):
        x     = start_x + i * (SLOT_SIZE + SLOT_PAD)
        is_sel = (i == selected)
        lbl_col = (255, 200, 60) if is_sel else (160, 160, 160)
        lbl = font.render(str(i + 1), True, lbl_col)
        screen.blit(lbl, (x + (SLOT_SIZE - lbl.get_width()) // 2, y - label_h))

    mx, my = pygame.mouse.get_pos()
    tooltip_item = None

    for i in range(GRID_COLS):
        slot_idx = 27 + i
        x = start_x + i * (SLOT_SIZE + SLOT_PAD)
        is_drag_src = (config.drag_slot == slot_idx)
        item  = None if is_drag_src else inv[slot_idx]
        is_hover = (x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE)
        # Draw a subtle golden glow fill behind the active slot
        if i == selected:
            glow = pygame.Surface((SLOT_SIZE, SLOT_SIZE), pygame.SRCALPHA)
            glow.fill((200, 155, 20, 55))
            screen.blit(glow, (x, y))
        _draw_slot(screen, x, y, item, selected=(i == selected), hover=is_hover)
        if is_hover and item is not None and not is_drag_src:
            tooltip_item = item

    # Only show tooltip from hotbar when the inventory panel is not open
    # (the panel draws its own tooltip at a higher z-order)
    if tooltip_item is not None and not config.show_inventory:
        _draw_tooltip(screen, tooltip_item, mx, my, window_width, window_height)


def _draw_creative_tab(screen, font, start_x, start_y, panel_w, panel_h, panel_pad, mx, my):
    """Render the creative item browser inside the open inventory panel."""
    _load_item_names()
    all_items = sorted(_ITEM_NAMES.keys())   # sorted by item ID

    cols  = GRID_COLS
    inner_x  = start_x + panel_pad
    inner_y  = start_y + 24 + panel_pad      # below tab row + small gap
    inner_w  = panel_w - panel_pad * 2
    inner_h  = panel_h - 24 - panel_pad * 2  # remaining height

    rows_visible = inner_h // (SLOT_SIZE + SLOT_PAD)

    total_rows  = (len(all_items) + cols - 1) // cols
    max_scroll  = max(0, total_rows - rows_visible)
    config.creative_scroll = max(0, min(config.creative_scroll, max_scroll))

    # Scroll hints
    if config.creative_scroll > 0:
        hint_up = font.render("▲ scroll", True, (180, 180, 100))
        screen.blit(hint_up, (inner_x, inner_y - hint_up.get_height() - 2))
    if config.creative_scroll < max_scroll:
        hint_dn = font.render("▼ scroll", True, (180, 180, 100))
        screen.blit(hint_dn, (inner_x, inner_y + rows_visible * (SLOT_SIZE + SLOT_PAD) + 2))

    tooltip_item_id = None
    start_idx = config.creative_scroll * cols

    for slot_i in range(rows_visible * cols):
        item_idx = start_idx + slot_i
        if item_idx >= len(all_items):
            break
        item_id = all_items[item_idx]
        col = slot_i % cols
        row = slot_i // cols
        sx  = inner_x + col * (SLOT_SIZE + SLOT_PAD)
        sy  = inner_y + row * (SLOT_SIZE + SLOT_PAD)

        is_hover = (sx <= mx < sx + SLOT_SIZE and sy <= my < sy + SLOT_SIZE)
        bg_color = (50, 50, 70) if is_hover else (30, 30, 40)
        pygame.draw.rect(screen, bg_color, (sx, sy, SLOT_SIZE, SLOT_SIZE), border_radius=3)
        pygame.draw.rect(screen, (80, 80, 100), (sx, sy, SLOT_SIZE, SLOT_SIZE), 1, border_radius=3)

        img = _get_item_image(item_id)
        screen.blit(img, (sx + 4, sy + 4))

        if is_hover:
            tooltip_item_id = item_id

    # Tooltip
    if tooltip_item_id is not None:
        name = _get_item_name(tooltip_item_id)
        tf   = _get_tooltip_font()
        lines = [name, f"ID: {tooltip_item_id}", "Click to give x1"]
        tw    = max(tf.size(l)[0] for l in lines) + 12
        th    = (tf.get_height() + 2) * len(lines) + 8
        tx    = min(mx + 14, screen.get_width() - tw - 4)
        ty    = min(my - 4, screen.get_height() - th - 4)
        tt_bg = pygame.Surface((tw, th), pygame.SRCALPHA)
        tt_bg.fill((20, 20, 30, 230))
        screen.blit(tt_bg, (tx, ty))
        pygame.draw.rect(screen, (180, 160, 60), (tx, ty, tw, th), 1)
        ry = ty + 4
        for li, line in enumerate(lines):
            col = (255, 255, 180) if li == 0 else (160, 160, 140)
            screen.blit(tf.render(line, True, col), (tx + 6, ry))
            ry += tf.get_height() + 2


def creative_tab_click(mx: int, my: int, window_width: int, window_height: int):
    """Return the item_id clicked in the creative tab, or None."""
    if not config.player_creative or config.inventory_tab != "creative":
        return None
    start_x, start_y = _panel_origin(window_width, window_height)
    panel_w, panel_h, panel_pad, _, _ = _panel_dims()
    _load_item_names()
    all_items = sorted(_ITEM_NAMES.keys())
    cols      = GRID_COLS
    inner_x   = start_x + panel_pad
    inner_y   = start_y + 24 + panel_pad
    inner_h   = panel_h - 24 - panel_pad * 2
    rows_visible = inner_h // (SLOT_SIZE + SLOT_PAD)
    start_idx = config.creative_scroll * cols
    for slot_i in range(rows_visible * cols):
        item_idx = start_idx + slot_i
        if item_idx >= len(all_items):
            break
        item_id = all_items[item_idx]
        col  = slot_i % cols
        row  = slot_i // cols
        sx   = inner_x + col * (SLOT_SIZE + SLOT_PAD)
        sy   = inner_y + row * (SLOT_SIZE + SLOT_PAD)
        if sx <= mx < sx + SLOT_SIZE and sy <= my < sy + SLOT_SIZE:
            return item_id
    return None


def draw_inventory_grid(screen, window_width, window_height):
    inv = config.player_inventory
    panel_w, panel_h, panel_pad, grid_w, grid_h = _panel_dims()
    start_x, start_y = _panel_origin(window_width, window_height)

    # ── Panel background ───────────────────────────────────────────────────
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((18, 18, 24, 230))
    screen.blit(panel, (start_x, start_y))

    font     = _get_font()
    mx, my   = pygame.mouse.get_pos()

    # ── Tab row: [BAG] [CRAFT] [CREATIVE?] ────────────────────────────────
    tab_h  = 18
    tabs   = _get_tabs()
    tab_w  = panel_w // len(tabs)
    for i, (tab_id, tab_label) in enumerate(tabs):
        tx     = start_x + i * tab_w
        active = (config.inventory_tab == tab_id)
        tbg    = (34, 34, 44) if active else (20, 20, 28)
        tbrd   = (200, 190, 80) if active else (70, 70, 80)
        tlbl   = (240, 220, 100) if active else (140, 140, 140)
        if tab_id == "creative":
            tbrd = (200, 170, 0) if active else (100, 80, 0)
            tlbl = (255, 230, 80) if active else (160, 120, 40)
        pygame.draw.rect(screen, tbg,  (tx, start_y + 2, tab_w, tab_h))
        pygame.draw.rect(screen, tbrd, (tx, start_y + 2, tab_w, tab_h), 1)
        ts = font.render(tab_label, True, tlbl)
        screen.blit(ts, (tx + (tab_w - ts.get_width()) // 2,
                         start_y + 2 + (tab_h - ts.get_height()) // 2))

    tooltip_item = None

    # ── CRAFT tab content ──────────────────────────────────────────────────
    if config.inventory_tab == "craft":
        from rendering.crafting import draw_basic_crafting_inline, inv_craft_area
        ax, ay, aw, ah = inv_craft_area(window_width, window_height)
        draw_basic_crafting_inline(screen, ax, ay, aw, ah)
        # Dragged item follows cursor
        if config.drag_item is not None:
            item_id, qty = config.drag_item[0], config.drag_item[1]
            screen.blit(_get_item_image(item_id), (mx - SLOT_SIZE // 2 + 4, my - SLOT_SIZE // 2 + 4))
            if qty > 1:
                txt = font.render(str(qty), True, (255, 255, 255))
                screen.blit(txt, (mx - SLOT_SIZE // 2 + 3, my + SLOT_SIZE // 2 - txt.get_height() - 6))
        return

    # ── CREATIVE tab content ───────────────────────────────────────────────
    if config.inventory_tab == "creative":
        _draw_creative_tab(screen, font, start_x, start_y, panel_w, panel_h, panel_pad, mx, my)
        return

    # ── Equipment section ──────────────────────────────────────────────────
    epositions = _equip_slot_positions(window_width, window_height)
    for idx, (ex, ey) in epositions.items():
        item         = inv[idx] if len(inv) > idx else None
        is_drag_src  = (config.drag_slot == idx)
        is_hover     = (ex <= mx < ex + SLOT_SIZE and ey <= my < ey + SLOT_SIZE)
        _draw_equip_slot(screen, ex, ey, idx, None if is_drag_src else item, hover=is_hover)
        if is_hover and item is not None and not is_drag_src:
            tooltip_item = item

    # Player preview sprite centered in the equip section
    preview  = _get_preview()
    pw, ph   = preview.get_width(), preview.get_height()
    grid_x   = start_x + panel_pad
    equip_y  = start_y + panel_pad + 20
    prev_x   = grid_x + (grid_w - pw) // 2
    cols_h   = _EQUIP_COLS_ROWS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 128
    prev_y   = equip_y + (cols_h - ph) // 2
    screen.blit(preview, (prev_x, prev_y))

    # Divider between equip section and inventory grid
    div_y = equip_y + _EQUIP_SECTION_H + _EQUIP_GAP // 2
    pygame.draw.line(screen, (62, 62, 80),
                     (start_x + 6, div_y), (start_x + panel_w - 6, div_y))

    # ── Inventory grid (slots 0-35) ────────────────────────────────────────
    grid_x, grid_y = _inv_grid_origin(window_width, window_height)

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            slot_idx = row * GRID_COLS + col
            x = grid_x + col * (SLOT_SIZE + SLOT_PAD)
            y = grid_y + row * (SLOT_SIZE + SLOT_PAD)
            is_hotbar_selected = (row == 3 and col == config.hotbar_slot)
            is_drag_src = (config.drag_slot == slot_idx)
            item = None if is_drag_src else inv[slot_idx]
            is_hover = (x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE)
            _draw_slot(screen, x, y, item,
                       selected=is_hotbar_selected,
                       hover=is_hover and not is_drag_src)
            if is_hover and item is not None and not is_drag_src:
                tooltip_item = item

    # ── Tooltip ────────────────────────────────────────────────────────────
    if tooltip_item is not None and config.drag_item is None:
        _draw_tooltip(screen, tooltip_item, mx, my, window_width, window_height)

    # ── Dragged item follows the cursor ────────────────────────────────────
    if config.drag_item is not None:
        item_id, qty = config.drag_item[0], config.drag_item[1]
        screen.blit(_get_item_image(item_id), (mx - SLOT_SIZE // 2 + 4, my - SLOT_SIZE // 2 + 4))
        if qty > 1:
            txt = _get_font().render(str(qty), True, (255, 255, 255))
            screen.blit(txt, (mx - SLOT_SIZE // 2 + 3, my + SLOT_SIZE // 2 - txt.get_height() - 6))



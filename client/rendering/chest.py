# client/rendering/chest.py
"""Chest inventory UI — combined chest + player bag panel centred on screen.

Shows the chest's 3×9 grid above the player's 4×9 bag grid (Minecraft-style).
All drag/drop is handled in controls.py.
"""

import pygame
from rendering import ui_theme as _T
import config
from rendering.cache import get_item_surface
from rendering.inventory import (
    _draw_slot, _draw_tooltip, _get_font,
    SLOT_SIZE, SLOT_PAD,
)

CHEST_COLS  = 9
CHEST_ROWS  = 3
CHEST_SLOTS = CHEST_COLS * CHEST_ROWS   # 27

BAG_ROWS = 4
BAG_COLS = 9
BAG_SLOTS = BAG_ROWS * BAG_COLS          # 36

_PAD     = 12
_TITLE_H = 22
_LABEL_H = 16
_DIV_GAP = 10

_GRID_W   = BAG_COLS  * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD   # 392
_CHEST_H  = CHEST_ROWS * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD  # 128
_BAG_H    = BAG_ROWS   * (SLOT_SIZE + SLOT_PAD) - SLOT_PAD  # 172
_PANEL_W  = _GRID_W + _PAD * 2                               # 416
_PANEL_H  = (_TITLE_H + _PAD
             + _CHEST_H
             + _DIV_GAP + _LABEL_H + _DIV_GAP
             + _BAG_H
             + _PAD)


def _panel_origin(ww: int, wh: int) -> tuple[int, int]:
    return (ww - _PANEL_W) // 2, (wh - _PANEL_H) // 2


def _chest_grid_origin(ww: int, wh: int) -> tuple[int, int]:
    ox, oy = _panel_origin(ww, wh)
    return ox + _PAD, oy + _TITLE_H + _PAD


def _bag_grid_origin(ww: int, wh: int) -> tuple[int, int]:
    cgx, cgy = _chest_grid_origin(ww, wh)
    return cgx, cgy + _CHEST_H + _DIV_GAP + _LABEL_H + _DIV_GAP


def chest_slot_at(mx: int, my: int, ww: int, wh: int) -> int | None:
    """Return chest slot index 0-26 under (mx, my), or None."""
    if config.open_chest_uid is None:
        return None
    gx, gy = _chest_grid_origin(ww, wh)
    for row in range(CHEST_ROWS):
        for col in range(CHEST_COLS):
            x = gx + col * (SLOT_SIZE + SLOT_PAD)
            y = gy + row * (SLOT_SIZE + SLOT_PAD)
            if x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE:
                return row * CHEST_COLS + col
    return None


def chest_bag_slot_at(mx: int, my: int, ww: int, wh: int) -> int | None:
    """Return player inventory slot 0-35 in the bag panel section, or None."""
    if config.open_chest_uid is None:
        return None
    gx, gy = _bag_grid_origin(ww, wh)
    for row in range(BAG_ROWS):
        for col in range(BAG_COLS):
            x = gx + col * (SLOT_SIZE + SLOT_PAD)
            y = gy + row * (SLOT_SIZE + SLOT_PAD)
            if x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE:
                return row * BAG_COLS + col
    return None


def draw_chest_ui(screen: pygame.Surface, ww: int, wh: int) -> None:
    """Draw the combined chest + bag overlay centred on screen."""
    if config.open_chest_uid is None:
        return

    obj = config.placed_objects.get(config.open_chest_uid)
    if obj is None:
        _cancel_drag()
        config.open_chest_uid = None
        return

    chest_inv: list = obj.get("chest_inv") or [None] * CHEST_SLOTS
    while len(chest_inv) < CHEST_SLOTS:
        chest_inv.append(None)

    ox, oy = _panel_origin(ww, wh)

    # Panel background
    panel = pygame.Surface((_PANEL_W, _PANEL_H), pygame.SRCALPHA)
    panel.fill(_T.BG_FILL + (_T.BG_ALPHA,))
    screen.blit(panel, (ox, oy))
    pygame.draw.rect(screen, _T.BORDER, (ox, oy, _PANEL_W, _PANEL_H), 2, border_radius=6)

    font = _get_font()

    # Title bar
    pygame.draw.rect(screen, _T.TITLE_BAR, (ox, oy, _PANEL_W, _TITLE_H))
    title = font.render("CHEST  [F to close]", True, _T.TITLE_TXT)
    screen.blit(title, (ox + (_PANEL_W - title.get_width()) // 2,
                        oy + (_TITLE_H - title.get_height()) // 2 + 2))

    mx, my = pygame.mouse.get_pos()
    tooltip_item = None

    # ── Chest grid ────────────────────────────────────────────────────────────
    cgx, cgy = _chest_grid_origin(ww, wh)
    for row in range(CHEST_ROWS):
        for col in range(CHEST_COLS):
            idx  = row * CHEST_COLS + col
            x    = cgx + col * (SLOT_SIZE + SLOT_PAD)
            y    = cgy + row * (SLOT_SIZE + SLOT_PAD)
            src  = (config.chest_drag_slot == idx)
            item = None if src else chest_inv[idx]
            hov  = (x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE)
            _draw_slot(screen, x, y, item, hover=hov)
            if hov and item is not None and not src:
                tooltip_item = item

    # ── Divider + "INVENTORY" label ───────────────────────────────────────────
    bgx, bgy = _bag_grid_origin(ww, wh)
    div_y = cgy + _CHEST_H + _DIV_GAP // 2
    pygame.draw.line(screen, (62, 62, 80),
                     (ox + _PAD, div_y), (ox + _PANEL_W - _PAD, div_y))
    lbl = font.render("INVENTORY", True, _T.LABEL_TXT)
    screen.blit(lbl, (ox + (_PANEL_W - lbl.get_width()) // 2,
                      bgy - _LABEL_H - _DIV_GAP // 2))

    # ── Player bag grid ───────────────────────────────────────────────────────
    inv = config.player_inventory
    for row in range(BAG_ROWS):
        for col in range(BAG_COLS):
            idx  = row * BAG_COLS + col
            x    = bgx + col * (SLOT_SIZE + SLOT_PAD)
            y    = bgy + row * (SLOT_SIZE + SLOT_PAD)
            src  = (config.drag_slot == idx)
            item = None if src else inv[idx]
            hov  = (x <= mx < x + SLOT_SIZE and y <= my < y + SLOT_SIZE)
            sel  = (idx >= 27 and (idx - 27) == config.hotbar_slot)
            _draw_slot(screen, x, y, item, hover=hov, selected=sel)
            if hov and item is not None and not src:
                tooltip_item = item

    if tooltip_item is not None and config.drag_item is None:
        _draw_tooltip(screen, tooltip_item, mx, my, ww, wh)

    # Dragged item cursor
    if config.drag_item is not None:
        item_id, qty = config.drag_item[0], config.drag_item[1]
        screen.blit(get_item_surface(item_id, SLOT_SIZE - 8),
                    (mx - SLOT_SIZE // 2 + 4, my - SLOT_SIZE // 2 + 4))
        if qty > 1:
            txt = font.render(str(qty), True, (255, 255, 255))
            screen.blit(txt, (mx - SLOT_SIZE // 2 + 3,
                               my + SLOT_SIZE // 2 - txt.get_height() - 6))


def _cancel_drag() -> None:
    """Restore any in-progress drag back to its source (call before closing chest)."""
    if config.chest_drag_slot is not None and config.drag_item is not None:
        obj = config.placed_objects.get(config.open_chest_uid)
        if obj is not None:
            chest_inv: list = obj.setdefault("chest_inv", [None] * CHEST_SLOTS)
            while len(chest_inv) < CHEST_SLOTS:
                chest_inv.append(None)
            chest_inv[config.chest_drag_slot] = config.drag_item
        config.chest_drag_slot = None
        config.drag_item       = None
    elif config.drag_slot is not None and config.drag_item is not None:
        config.player_inventory[config.drag_slot] = config.drag_item
        config.drag_slot = None
        config.drag_item = None


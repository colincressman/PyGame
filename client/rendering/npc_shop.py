"""client/rendering/npc_shop.py

Unified NPC trading panel (single window, centered on screen).

Layout:
  ┌─────────────────────────────────────────────┐
  │  Merchant                    Coins: X  [X]  │
  │  ─── Shop ──────────────────────────────    │
  │  [item][item][item] ...  (merchant grid)     │
  │  ─── Your Bag ──────────────────────────    │
  │  [slot][slot][slot] ...  (player bag)        │
  └─────────────────────────────────────────────┘

Interactions:
  - Click merchant slot  → buy 1 unit
  - Drag bag slot onto merchant section → sell
  - Drag within bag → reorder
  - Scroll → browse merchant items
"""
import pygame
import config
from rendering.inventory import (
    SLOT_SIZE as _S, SLOT_PAD as _SP, GRID_COLS as _COLS,
    _draw_slot, _get_item_image, _get_item_name as _iname,
    _get_font, _draw_tooltip, _load_item_names,
)

# ── Layout constants ──────────────────────────────────────────────────────────
_PP        = 12
_HDR       = 30
_LBL       = 18
_SEP       = 6
_STEP      = _S + _SP                   # 44 px

_GRID_W    = _COLS * _STEP - _SP        # 392 px
M_ROWS_VIS = 3
_M_H       = M_ROWS_VIS * _STEP - _SP  # 128 px
B_ROWS     = 4
_B_H       = B_ROWS * _STEP - _SP      # 172 px

PANEL_W = _GRID_W + 2 * _PP            # 416 px
PANEL_H = _PP + _HDR + _SEP + _LBL + _M_H + _SEP + _LBL + _B_H + _PP  # 402 px

# Y offsets within panel surface
_Y_MERCH_LBL  = _PP + _HDR + _SEP
_Y_MERCH_GRID = _Y_MERCH_LBL + _LBL
_Y_BAG_LBL    = _Y_MERCH_GRID + _M_H + _SEP
_Y_BAG_GRID   = _Y_BAG_LBL + _LBL



# Font cache
_FONT_TITLE: pygame.font.Font | None = None
_FONT:       pygame.font.Font | None = None
_FONT_SM:    pygame.font.Font | None = None


def _ensure_fonts() -> None:
    global _FONT_TITLE, _FONT, _FONT_SM
    if _FONT is None:
        _FONT_TITLE = pygame.font.SysFont("Arial", 14, bold=True)
        _FONT       = pygame.font.SysFont("Arial", 13)
        _FONT_SM    = pygame.font.SysFont("Arial", 10)


# ── Layout helpers ────────────────────────────────────────────────────────────

def panel_origin(sw: int, sh: int) -> tuple:
    return (sw - PANEL_W) // 2, (sh - PANEL_H) // 2


def merchant_slot_at(mx: int, my: int, sw: int, sh: int):
    """Return the config.shop_items index under the cursor, or None."""
    px, py = panel_origin(sw, sh)
    gx = px + _PP
    gy = py + _Y_MERCH_GRID
    if not (gx <= mx < gx + _GRID_W and gy <= my < gy + _M_H):
        return None
    col = (mx - gx) // _STEP
    row = (my - gy) // _STEP
    if not (0 <= col < _COLS and 0 <= row < M_ROWS_VIS):
        return None
    idx = (config.shop_scroll + row) * _COLS + col
    return idx if 0 <= idx < len(config.shop_items) else None


def bag_slot_at(mx: int, my: int, sw: int, sh: int):
    """Return the player bag slot index (0-35) under the cursor, or None."""
    px, py = panel_origin(sw, sh)
    gx = px + _PP
    gy = py + _Y_BAG_GRID
    if not (gx <= mx < gx + _GRID_W and gy <= my < gy + _B_H):
        return None
    col = (mx - gx) // _STEP
    row = (my - gy) // _STEP
    if not (0 <= col < _COLS and 0 <= row < B_ROWS):
        return None
    return row * _COLS + col


def merchant_section_rect(sw: int, sh: int) -> pygame.Rect:
    """Screen-space rect covering the full merchant grid (drop zone for selling)."""
    px, py = panel_origin(sw, sh)
    return pygame.Rect(px + _PP, py + _Y_MERCH_GRID, _GRID_W, _M_H)


# ── Close ─────────────────────────────────────────────────────────────────────

def close_shop() -> None:
    config.show_shop     = False
    config.shop_npc_id   = None
    config.shop_npc_type = None
    config.shop_items    = []
    config.shop_scroll   = 0
    config.shop_tab      = "buy"


# ── Draw ──────────────────────────────────────────────────────────────────────

def draw_shop(screen: pygame.Surface) -> None:
    """Render the unified trading panel each frame while config.show_shop is True."""
    _ensure_fonts()
    _load_item_names()
    sw, sh = screen.get_size()
    mx, my = pygame.mouse.get_pos()
    px, py = panel_origin(sw, sh)
    dragging = config.drag_item is not None

    # Panel background
    panel = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
    panel.fill((28, 22, 18, 245))
    pygame.draw.rect(panel, (180, 140, 70), (0, 0, PANEL_W, PANEL_H), 2)

    # ── Header ────────────────────────────────────────────────────────────────
    npc_type = config.shop_npc_type or "Shop"
    title_s  = _FONT_TITLE.render(npc_type.capitalize(), True, (230, 200, 120))
    coins_s  = _FONT.render(f"Coins: {config.player_coins}", True, (255, 215, 0))
    hdr_cy   = _PP + _HDR // 2
    panel.blit(title_s, (_PP, hdr_cy - title_s.get_height() // 2))
    panel.blit(coins_s, (PANEL_W - coins_s.get_width() - 30,
                          hdr_cy - coins_s.get_height() // 2))
    _close_r = pygame.Rect(PANEL_W - 24, 6, 18, 18)
    pygame.draw.rect(panel, (160, 50, 50), _close_r, border_radius=3)
    x_s = _FONT.render("X", True, (255, 255, 255))
    panel.blit(x_s, (_close_r.x + (_close_r.w - x_s.get_width()) // 2,
                     _close_r.y + (_close_r.h - x_s.get_height()) // 2))

    # ── Section labels ────────────────────────────────────────────────────────
    lc = (160, 135, 80)
    sep = "─" * 50
    panel.blit(_FONT.render(f"Shop  {sep}",     True, lc),
               (_PP, _Y_MERCH_LBL + (_LBL - _FONT.get_height()) // 2))
    panel.blit(_FONT.render(f"Your Bag  {sep}", True, lc),
               (_PP, _Y_BAG_LBL + (_LBL - _FONT.get_height()) // 2))

    # ── Merchant grid ─────────────────────────────────────────────────────────
    items = config.shop_items
    max_scroll = max(0, (len(items) + _COLS - 1) // _COLS - M_ROWS_VIS)
    config.shop_scroll = max(0, min(config.shop_scroll, max_scroll))

    # Gold outline when dragging a bag item (sell hint)
    if dragging and config.drag_slot is not None:
        hl = pygame.Surface((_GRID_W, _M_H), pygame.SRCALPHA)
        hl.fill((255, 200, 40, 25))
        pygame.draw.rect(hl, (255, 200, 40, 200), (0, 0, _GRID_W, _M_H), 2, border_radius=4)
        panel.blit(hl, (_PP, _Y_MERCH_GRID))

    m_hover = merchant_slot_at(mx, my, sw, sh)

    for row in range(M_ROWS_VIS):
        for col in range(_COLS):
            idx = (config.shop_scroll + row) * _COLS + col
            sx  = _PP + col * _STEP
            sy  = _Y_MERCH_GRID + row * _STEP
            if idx < len(items):
                entry  = items[idx]
                pseudo = [entry["id"], entry.get("qty", 1)]
                _draw_slot(panel, sx, sy, pseudo, hover=(idx == m_hover and not dragging))
                p_s = _FONT_SM.render(f"{entry['price']}c", True, (255, 215, 0))
                panel.blit(p_s, (sx + _S - p_s.get_width() - 1, sy + _S - p_s.get_height()))
            else:
                _draw_slot(panel, sx, sy, None)

    # ── Player bag grid ───────────────────────────────────────────────────────
    b_hover = bag_slot_at(mx, my, sw, sh) if not dragging else None

    for row in range(B_ROWS):
        for col in range(_COLS):
            slot = row * _COLS + col
            bx   = _PP + col * _STEP
            by   = _Y_BAG_GRID + row * _STEP
            item = (config.player_inventory[slot]
                    if slot < len(config.player_inventory) else None)
            is_src = dragging and config.drag_slot == slot
            _draw_slot(panel, bx, by, None if is_src else item,
                       hover=(slot == b_hover))

    screen.blit(panel, (px, py))

    # ── Tooltips ──────────────────────────────────────────────────────────────
    if not dragging:
        if m_hover is not None and m_hover < len(items):
            _draw_merch_tooltip(screen, items[m_hover], mx, my, sw, sh)
        elif b_hover is not None:
            item = (config.player_inventory[b_hover]
                    if b_hover < len(config.player_inventory) else None)
            if item is not None:
                _draw_tooltip(screen, item, mx, my, sw, sh)

    # ── Dragged item follows cursor ───────────────────────────────────────────
    if dragging:
        screen.blit(_get_item_image(config.drag_item[0]),
                    (mx - _S // 2 + 4, my - _S // 2 + 4))
        qty = config.drag_item[1]
        if qty > 1:
            txt = _get_font().render(str(qty), True, (255, 255, 255))
            screen.blit(txt, (mx - _S // 2 + 3, my + _S // 2 - txt.get_height() - 2))


def _draw_merch_tooltip(screen, entry, mx, my, sw, sh):
    font = _FONT or pygame.font.SysFont("Arial", 13)
    pad  = 6
    lines = [
        font.render(entry.get("name", "?"),      True, (230, 225, 205)),
        font.render(f"Price: {entry['price']}c", True, (255, 215,   0)),
    ]
    qty = entry.get("qty", 0)
    if qty > 0:
        lines.append(font.render(f"Stock: {qty}", True, (160, 210, 160)))
    tw = max(s.get_width() for s in lines) + pad * 2
    th = sum(s.get_height() + 2 for s in lines) + pad * 2
    tx = min(mx + 14, sw - tw - 4)
    ty = max(4, my - th - 4)
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    surf.fill((18, 18, 24, 230))
    pygame.draw.rect(surf, (160, 160, 120), (0, 0, tw, th), 1, border_radius=4)
    cy = pad
    for s in lines:
        surf.blit(s, (pad, cy))
        cy += s.get_height() + 2
    screen.blit(surf, (tx, ty))


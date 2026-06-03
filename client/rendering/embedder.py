"""client/rendering/embedder.py

Embedder popup UI.

The player selects:
  Slot 0 (left)  — the item to embed into (must have gem_slots >= 1, no gem yet)
  Slot 1 (right) — the gem to embed (item IDs 50-56)

Then presses EMBED to send the embed_gem request.

Interaction model (mirrors combiner):
  1. Click an embedder slot to select it.
  2. Click a bag item to assign it.
  3. Press EMBED to execute.
"""

from __future__ import annotations
import json
import os as _os
import pygame
from rendering.cache import get_item_surface
from rendering.gem_data import GEM_COLORS, GEM_IDS, get_gem_entry
from rendering import ui_theme as _T

# ─── Lazy data ───────────────────────────────────────────────────────────────
_items: dict[int, dict] = {}
_items_loaded = False


def _load_items() -> None:
    global _items, _items_loaded
    if _items_loaded:
        return
    _items_loaded = True
    try:
        path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "..", "..", "server", "items.json",
        )
        with open(path) as f:
            _items = {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"[EMBEDDER] Could not load items.json: {e}")


def _get_item(item_id: int) -> dict:
    _load_items()
    return _items.get(item_id, {})


# ─── Fonts ───────────────────────────────────────────────────────────────────
_font_sm: pygame.font.Font | None = None
_font_md: pygame.font.Font | None = None


def _get_font_sm() -> pygame.font.Font:
    global _font_sm
    if _font_sm is None:
        _font_sm = pygame.font.SysFont("Arial", 11)
    return _font_sm


def _get_font_md() -> pygame.font.Font:
    global _font_md
    if _font_md is None:
        _font_md = pygame.font.SysFont("Arial", 14)
    return _font_md


# ─── Layout constants ────────────────────────────────────────────────────────
POPUP_W = 420
POPUP_H = 380

_TITLE_H  = 28
_PAD      = 12
_SLOT_SZ  = 64
_SLOT_GAP = 40   # gap between the two main slots
_MINI_SZ  = 34
_MINI_GAP = 2

_INV_COLS = 9
_INV_ROWS = 4


# ─── Item art cache ───────────────────────────────────────────────────────────
def _get_art(item_id: int, size: int) -> pygame.Surface:
    return get_item_surface(item_id, size)


# ─── Geometry ────────────────────────────────────────────────────────────────

def _popup_origin(ww: int, wh: int) -> tuple[int, int]:
    return (ww - POPUP_W) // 2, (wh - POPUP_H) // 2


def _slot_rects(px: int, py: int) -> tuple[pygame.Rect, pygame.Rect]:
    total_w = _SLOT_SZ * 2 + _SLOT_GAP
    sx = px + (POPUP_W - total_w) // 2
    sy = py + _TITLE_H + 16
    return (
        pygame.Rect(sx,                  sy, _SLOT_SZ, _SLOT_SZ),
        pygame.Rect(sx + _SLOT_SZ + _SLOT_GAP, sy, _SLOT_SZ, _SLOT_SZ),
    )


def _preview_rect(px: int, py: int) -> pygame.Rect:
    slot0, _ = _slot_rects(px, py)
    y = slot0.bottom + 20
    return pygame.Rect(px + _PAD, y, POPUP_W - _PAD * 2, 60)


def _inv_grid_origin(px: int, py: int) -> tuple[int, int]:
    pr = _preview_rect(px, py)
    gw = _INV_COLS * (_MINI_SZ + _MINI_GAP) - _MINI_GAP
    gx = px + (POPUP_W - gw) // 2
    gy = pr.bottom + 18
    return gx, gy


def _embed_btn_rect(px: int, py: int) -> pygame.Rect:
    gx, gy = _inv_grid_origin(px, py)
    grid_h = _INV_ROWS * (_MINI_SZ + _MINI_GAP) - _MINI_GAP
    btn_y  = gy + grid_h + 8
    btn_w  = 140
    btn_x  = px + (POPUP_W - btn_w) // 2
    return pygame.Rect(btn_x, btn_y, btn_w, 34)


# ─── Validation helpers ───────────────────────────────────────────────────────

def valid_for_embedder_slot(item_id: int, cs: int, inv_slot) -> bool:
    """Return True if item_id is valid for embedder slot cs."""
    if cs == 1:
        return item_id in GEM_IDS
    if cs == 0:
        # Must have meta with gem_slots >= 1 and no gem yet
        if inv_slot is None:
            return False
        meta = inv_slot[2] if len(inv_slot) >= 3 and isinstance(inv_slot[2], dict) else None
        if meta is None:
            return False
        return meta.get("gem_slots", 0) >= 1 and not meta.get("gem")
    return False


def _can_embed(inv, embedder_slots) -> bool:
    """Return True if the current slots form a valid embed pair."""
    i_idx, g_idx = embedder_slots
    if i_idx is None or g_idx is None:
        return False
    i_slot = inv[i_idx] if 0 <= i_idx < 36 else None
    g_slot = inv[g_idx] if 0 <= g_idx < 36 else None
    if i_slot is None or g_slot is None:
        return False
    if g_slot[0] not in GEM_IDS:
        return False
    meta = i_slot[2] if len(i_slot) >= 3 and isinstance(i_slot[2], dict) else None
    return meta is not None and meta.get("gem_slots", 0) >= 1 and not meta.get("gem")


# ─── Main draw ────────────────────────────────────────────────────────────────

def draw_embedder_popup(screen: pygame.Surface, ww: int, wh: int) -> None:
    import config
    _load_items()

    px, py = _popup_origin(ww, wh)

    # Dim overlay
    overlay = pygame.Surface((ww, wh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, (0, 0))

    # Popup background
    pygame.draw.rect(screen, _T.BG_FILL,     (px, py, POPUP_W, POPUP_H), border_radius=6)
    pygame.draw.rect(screen, _T.BORDER, (px, py, POPUP_W, POPUP_H), 2, border_radius=6)

    # Title bar
    pygame.draw.rect(screen, _T.TITLE_BAR, (px, py, POPUP_W, _TITLE_H))

    fm = _get_font_md()
    fs = _get_font_sm()

    title_s = fm.render("Embedder", True, _T.TITLE_TXT)
    screen.blit(title_s, (px + 10, py + (_TITLE_H - title_s.get_height()) // 2))
    hint_s = fs.render("[F / ESC to close]", True, _T.HINT_TXT)
    screen.blit(hint_s, (px + POPUP_W - hint_s.get_width() - 8,
                          py + (_TITLE_H - hint_s.get_height()) // 2))

    # ── Two input slots ───────────────────────────────────────────────────────
    slot_rects = _slot_rects(px, py)
    slot_labels = ("Item", "Gem")
    mpos = pygame.mouse.get_pos()
    art_sz = _SLOT_SZ - 8

    for i, (label, rect) in enumerate(zip(slot_labels, slot_rects)):
        inv_idx  = config.embedder_slots[i]
        selected = (config.embedder_selected_slot == i)

        if selected:
            border_col = (255, 215, 0)
            bg_col     = (52, 46, 70)
        elif inv_idx is not None:
            border_col = (98, 88, 128)
            bg_col     = (44, 40, 58)
        else:
            border_col = _T.BORDER
            bg_col     = _T.SUB_BG

        pygame.draw.rect(screen, bg_col,     rect, border_radius=4)
        pygame.draw.rect(screen, border_col, rect, 2, border_radius=4)

        if inv_idx is not None and 0 <= inv_idx < 36:
            slot = config.player_inventory[inv_idx]
            if slot is not None:
                art = _get_art(slot[0], art_sz)
                screen.blit(art, (rect.x + 4, rect.y + 4))
        else:
            ph = fm.render("?", True, (78, 78, 98))
            screen.blit(ph, (rect.centerx - ph.get_width() // 2,
                              rect.centery - ph.get_height() // 2))

        lbl_s = fs.render(label, True, _T.LABEL_TXT)
        screen.blit(lbl_s, (rect.centerx - lbl_s.get_width() // 2, rect.bottom + 3))

    # ── Arrow between slots ───────────────────────────────────────────────────
    r0, r1 = slot_rects
    arrow_cx = (r0.right + r1.left) // 2
    arrow_cy = r0.centery
    arrow_s = fs.render("\u27a1", True, (100, 160, 155))
    screen.blit(arrow_s, (arrow_cx - arrow_s.get_width() // 2,
                           arrow_cy - arrow_s.get_height() // 2))

    # ── Preview panel ─────────────────────────────────────────────────────────
    pr = _preview_rect(px, py)
    pygame.draw.rect(screen, _T.SUB_BG,  pr, border_radius=3)
    pygame.draw.rect(screen, _T.BORDER, pr, 1, border_radius=3)

    inv = config.player_inventory
    lx, ly = pr.x + 8, pr.y + 8

    i_idx, g_idx = config.embedder_slots
    i_slot = (inv[i_idx] if (i_idx is not None and 0 <= i_idx < 36) else None)
    g_slot = (inv[g_idx] if (g_idx is not None and 0 <= g_idx < 36) else None)
    can_embed_now = _can_embed(inv, config.embedder_slots)

    if can_embed_now and i_slot and g_slot:
        gem_id    = g_slot[0]
        gem_name  = _get_item(gem_id).get("name", "Gem")
        trait     = (get_gem_entry(gem_id) or {}).get("trait", "")
        item_name = (i_slot[2].get("name") if len(i_slot) >= 3
                     and isinstance(i_slot[2], dict) else None) or _get_item(i_slot[0]).get("name", "Item")
        gem_col   = GEM_COLORS.get(trait, (200, 200, 200))

        preview_txt = fm.render(f"{item_name}  +  {gem_name}", True, (240, 235, 200))
        screen.blit(preview_txt, (lx, ly))
        trait_txt = fs.render(f"\u2192 Adds [{trait}] trait", True, gem_col)
        screen.blit(trait_txt, (lx, ly + 20))
    elif i_slot or g_slot:
        screen.blit(fs.render("Fill both slots to preview embed.", True, (120, 118, 138)), (lx, ly + 10))
    else:
        screen.blit(fs.render("Select an item then a gem.", True, (120, 118, 138)), (lx, ly + 10))

    # ── Hint ──────────────────────────────────────────────────────────────────
    hint_txt = (
        "Click a slot above to select, then pick an item below"
        if config.embedder_selected_slot == -1
        else f"Click a {'combined item' if config.embedder_selected_slot == 0 else 'gem'} below"
    )
    hint2_s = fs.render(hint_txt, True, (120, 118, 138))
    screen.blit(hint2_s, (px + _PAD, pr.bottom + 4))

    # ── Mini inventory grid ───────────────────────────────────────────────────
    gx, gy = _inv_grid_origin(px, py)

    for row in range(_INV_ROWS):
        for col in range(_INV_COLS):
            idx = row * _INV_COLS + col
            if idx >= 36:
                break
            sx2 = gx + col * (_MINI_SZ + _MINI_GAP)
            sy2 = gy + row * (_MINI_SZ + _MINI_GAP)
            r2  = pygame.Rect(sx2, sy2, _MINI_SZ, _MINI_SZ)

            slot       = inv[idx]
            in_emb     = idx in config.embedder_slots
            hovering   = r2.collidepoint(mpos)

            if in_emb:
                bg_m, bd_m = (44, 40, 58), (98, 88, 128)
            elif hovering:
                bg_m, bd_m = (45, 44, 60), (185, 185, 255)
            else:
                bg_m, bd_m = (32, 32, 42), (78, 78, 98)

            pygame.draw.rect(screen, bg_m, r2, border_radius=2)
            pygame.draw.rect(screen, bd_m, r2, 1, border_radius=2)

            if slot is not None:
                art = _get_art(slot[0], _MINI_SZ - 4)
                screen.blit(art, (sx2 + 2, sy2 + 2))
                if slot[1] > 1:
                    q = fs.render(str(slot[1]), True, (255, 255, 255))
                    screen.blit(q, (sx2 + 2, sy2 + _MINI_SZ - q.get_height() - 1))

    # ── EMBED button ──────────────────────────────────────────────────────────
    btn = _embed_btn_rect(px, py)
    if can_embed_now:
        btn_bg, btn_bd, btn_tc = _T.BTN_BG, _T.BTN_BD, (255, 255, 255)
    else:
        btn_bg, btn_bd, btn_tc = _T.BTN_DIS_BG, _T.BTN_DIS_BD, _T.BTN_DIS_TX

    pygame.draw.rect(screen, btn_bg, btn, border_radius=5)
    pygame.draw.rect(screen, btn_bd, btn, 2, border_radius=5)
    lbl = fm.render("EMBED GEM", True, btn_tc)
    screen.blit(lbl, (btn.centerx - lbl.get_width() // 2,
                       btn.centery - lbl.get_height() // 2))

    # ── Slot tooltips ─────────────────────────────────────────────────────────
    from rendering.inventory import _draw_tooltip
    for i, rect in enumerate(slot_rects):
        if rect.collidepoint(mpos):
            inv_idx = config.embedder_slots[i]
            if inv_idx is not None and 0 <= inv_idx < 36:
                slot = inv[inv_idx]
                if slot is not None:
                    _draw_tooltip(screen, slot, mpos[0], mpos[1], ww, wh)
            break


# ─── Hit testing ─────────────────────────────────────────────────────────────

def embedder_popup_hit(
    mx: int, my: int, ww: int, wh: int
) -> tuple[str, int | None]:
    """
    Returns (kind, value):
      ("outside",        None)   — click outside popup
      ("embedder_slot",  0-1)    — click on item/gem input slot
      ("inv_slot",       0-35)   — click on mini-inventory slot
      ("embed",          None)   — click on EMBED GEM button
    """
    px, py = _popup_origin(ww, wh)
    if not pygame.Rect(px, py, POPUP_W, POPUP_H).collidepoint(mx, my):
        return ("outside", None)

    for i, rect in enumerate(_slot_rects(px, py)):
        if rect.collidepoint(mx, my):
            return ("embedder_slot", i)

    btn = _embed_btn_rect(px, py)
    if btn.collidepoint(mx, my):
        return ("embed", None)

    gx, gy = _inv_grid_origin(px, py)
    for row in range(_INV_ROWS):
        for col in range(_INV_COLS):
            idx = row * _INV_COLS + col
            if idx >= 36:
                break
            r2 = pygame.Rect(
                gx + col * (_MINI_SZ + _MINI_GAP),
                gy + row * (_MINI_SZ + _MINI_GAP),
                _MINI_SZ, _MINI_SZ,
            )
            if r2.collidepoint(mx, my):
                return ("inv_slot", idx)

    return ("inside", None)

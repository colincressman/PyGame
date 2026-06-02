"""client/rendering/repair.py

Repair popup UI — embedded as the "Repair" tab inside the Crafting Table popup.

Layout:
  - Scrollable bag grid (36 slots)
  - Selected item info (name, durability bar, repair cost)
  - REPAIR button
"""

from __future__ import annotations
import json
import os as _os
import pygame
from rendering.cache import get_item_surface
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
        print(f"[REPAIR] Could not load items.json: {e}")


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


# ─── Repair cost table (mirrors server/game_state/repair.py) ─────────────────
_RANGE_REPAIR: list[tuple[tuple[int, int], int, int]] = [
    ((1000, 1002), 11,  2),
    ((2000, 2002), 11,  2),
    ((1050, 1054), 10,  2),
    ((1100, 1103), 100, 2),
    ((2100, 2102), 100, 2),
    ((1150, 1153), 101, 2),
    ((2150, 2152), 101, 2),
    ((1200, 1203), 110, 2),
    ((2200, 2202), 110, 2),
    ((1250, 1253), 111, 2),
    ((2250, 2252), 111, 2),
    ((1300, 1303), 104, 2),
    ((2300, 2302), 104, 2),
    ((1350, 1353), 26,  2),
    ((2350, 2352), 26,  2),
    ((1400, 1403), 27,  2),
    ((2400, 2402), 27,  2),
    ((1500, 1506), 10,  2),
    ((3000, 3010), 100, 2), ((3100, 3110), 100, 2), ((3200, 3210), 100, 2),
    ((3300, 3310), 100, 2), ((3400, 3410), 100, 2),
    ((3010, 3020), 101, 2), ((3110, 3120), 101, 2), ((3210, 3220), 101, 2),
    ((3310, 3320), 101, 2), ((3410, 3420), 101, 2),
    ((3020, 3030), 110, 2), ((3120, 3130), 110, 2), ((3220, 3230), 110, 2),
    ((3320, 3330), 110, 2), ((3420, 3430), 110, 2),
    ((3030, 3040), 111, 2), ((3130, 3140), 111, 2), ((3230, 3240), 111, 2),
    ((3330, 3340), 111, 2), ((3430, 3440), 111, 2),
    ((3040, 3050), 104, 2), ((3140, 3150), 104, 2), ((3240, 3250), 104, 2),
    ((3340, 3350), 104, 2), ((3440, 3450), 104, 2),
    ((3050, 3060), 26,  2), ((3150, 3160), 26,  2), ((3250, 3260), 26,  2),
    ((3350, 3360), 26,  2), ((3450, 3460), 26,  2),
    ((3060, 3070), 27,  2), ((3160, 3170), 27,  2), ((3260, 3270), 27,  2),
    ((3360, 3370), 27,  2), ((3460, 3470), 27,  2),
    ((2050, 2054), 10,  2),
]

_PART_TO_MAT: dict[int, tuple[int, int]] = {
    # Blades
    148: (10,  2),   # Paper Blade → Wood
    150: (11,  2),   # Flint Blade → Stone
    151: (11,  2),   # Stone Blade → Stone
    152: (19,  2),   # Bone Blade → Bone
    153: (101, 2),   # Copper Blade → Copper Bar
    154: (102, 2),   # Tin Blade → Tin Bar
    155: (100, 2),   # Iron Blade → Iron Bar
    156: (110, 2),   # Bronze Blade → Bronze Bar
    157: (103, 2),   # Silver Blade → Silver Bar
    158: (104, 2),   # Gold Blade → Gold Bar
    159: (111, 2),   # Steel Blade → Steel Bar
    160: (27,  2),   # Obsidian Blade → Obsidian Shard
    161: (26,  2),   # Crystal Blade → Crystal Shard
    278: (28,  2),   # Slime Blade → Slime Ball
    # Axe Heads
    162: (11,  2),   # Flint Axe Head → Stone
    163: (11,  2),   # Stone Axe Head → Stone
    164: (19,  2),   # Bone Axe Head → Bone
    165: (101, 2),   # Copper Axe Head → Copper Bar
    166: (102, 2),   # Tin Axe Head → Tin Bar
    167: (100, 2),   # Iron Axe Head → Iron Bar
    168: (110, 2),   # Bronze Axe Head → Bronze Bar
    169: (104, 2),   # Gold Axe Head → Gold Bar
    170: (111, 2),   # Steel Axe Head → Steel Bar
    171: (27,  2),   # Obsidian Axe Head → Obsidian Shard
    281: (103, 2),   # Silver Axe Head → Silver Bar
    282: (26,  2),   # Crystal Axe Head → Crystal Shard
    # Pick Heads
    172: (11,  2),   # Flint Pick Head → Stone
    173: (11,  2),   # Stone Pick Head → Stone
    174: (101, 2),   # Copper Pick Head → Copper Bar
    175: (102, 2),   # Tin Pick Head → Tin Bar
    176: (100, 2),   # Iron Pick Head → Iron Bar
    177: (110, 2),   # Bronze Pick Head → Bronze Bar
    178: (104, 2),   # Gold Pick Head → Gold Bar
    179: (111, 2),   # Steel Pick Head → Steel Bar
    180: (27,  2),   # Obsidian Pick Head → Obsidian Shard
    181: (26,  2),   # Crystal Pick Head → Crystal Shard
    283: (19,  2),   # Bone Pick Head → Bone
    284: (103, 2),   # Silver Pick Head → Silver Bar
    # Plates
    149: (26,  2),   # Crystal Plate → Crystal Shard
    182: (101, 2),   # Copper Plate → Copper Bar
    183: (102, 2),   # Tin Plate → Tin Bar
    184: (100, 2),   # Iron Plate → Iron Bar
    185: (110, 2),   # Bronze Plate → Bronze Bar
    186: (103, 2),   # Silver Plate → Silver Bar
    187: (104, 2),   # Gold Plate → Gold Bar
    188: (111, 2),   # Steel Plate → Steel Bar
    189: (27,  2),   # Obsidian Plate → Obsidian Shard
    285: (11,  2),   # Stone Plate → Stone
    286: (19,  2),   # Bone Plate → Bone
}


def _get_repair_cost(slot: list) -> tuple[int, int] | None:
    """Return (material_id, qty) or None if not repairable."""
    item_id = slot[0]
    meta    = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}
    parts = meta.get("parts")
    if parts and len(parts) >= 2:
        result = _PART_TO_MAT.get(parts[1])
        if result:
            return result
    for (lo, hi), mat_id, qty in _RANGE_REPAIR:
        if lo <= item_id < hi:
            return mat_id, qty
    return None


def _dur_info(slot: list) -> tuple[int | None, int | None]:
    """Return (dur, dur_max) from slot meta, falling back to items.json."""
    meta = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}
    dur     = meta.get("dur")
    dur_max = meta.get("dur_max")
    if dur_max is None:
        item_def = _get_item(slot[0])
        dur_max  = item_def.get("durability")
        dur      = dur_max  # no damage tracked → full
    return dur, dur_max


def _count_inv(item_id: int, inv: list) -> int:
    return sum(s[1] for s in inv[:36] if s is not None and s[0] == item_id)


# ─── Item art ─────────────────────────────────────────────────────────────────
def _get_art(item_id: int, size: int) -> pygame.Surface:
    return get_item_surface(item_id, size)


# ─── Layout ──────────────────────────────────────────────────────────────────
_COLS    = 9
_MINI_SZ = 34
_MINI_G  = 2
_PAD     = 12
_BTN_W   = 140
_BTN_H   = 32


def _grid_origin(cx: int, cy: int, cw: int) -> tuple[int, int]:
    gw = _COLS * (_MINI_SZ + _MINI_G) - _MINI_G
    gx = cx + (cw - gw) // 2
    return gx, cy + _PAD


def _detail_rect(cx: int, cy: int, cw: int, ch: int) -> pygame.Rect:
    gx, gy = _grid_origin(cx, cy, cw)
    grid_rows = 4
    grid_h = grid_rows * (_MINI_SZ + _MINI_G) - _MINI_G
    det_y = gy + grid_h + 10
    return pygame.Rect(cx + _PAD, det_y, cw - _PAD * 2, ch - (det_y - cy) - _BTN_H - 20)


def _btn_rect(cx: int, cy: int, cw: int, ch: int) -> pygame.Rect:
    btn_x = cx + (cw - _BTN_W) // 2
    btn_y = cy + ch - _BTN_H - _PAD
    return pygame.Rect(btn_x, btn_y, _BTN_W, _BTN_H)


# ─── Public draw ─────────────────────────────────────────────────────────────

def draw_repair_panel(screen: pygame.Surface,
                      cx: int, cy: int, cw: int, ch: int) -> None:
    """Draw the Repair UI inside the content area (cx, cy, cw, ch)."""
    import config
    _load_items()

    fm = _get_font_md()
    fs = _get_font_sm()
    inv = config.player_inventory

    # ── Bag grid ────────────────────────────────────────────────────────────
    gx, gy = _grid_origin(cx, cy, cw)
    selected = config.repair_selected_slot

    for slot_i in range(36):
        col   = slot_i % _COLS
        row   = slot_i // _COLS
        sx    = gx + col * (_MINI_SZ + _MINI_G)
        sy    = gy + row * (_MINI_SZ + _MINI_G)
        slot  = inv[slot_i]

        is_sel = (slot_i == selected)
        is_rep = False
        if slot is not None:
            _, dur_max = _dur_info(slot)
            is_rep = dur_max is not None  # has durability → repairable candidate

        if is_sel:
            bg, brd = (40, 70, 40), _T.BTN_BD
        elif is_rep:
            bg, brd = (30, 38, 30), (55, 100, 55)
        else:
            bg, brd = _T.SLOT_BG, _T.SLOT_BD

        pygame.draw.rect(screen, bg,  (sx, sy, _MINI_SZ, _MINI_SZ), border_radius=3)
        pygame.draw.rect(screen, brd, (sx, sy, _MINI_SZ, _MINI_SZ), 1, border_radius=3)

        if slot is not None:
            art = _get_art(slot[0], _MINI_SZ - 4)
            screen.blit(art, (sx + 2, sy + 2))
            if slot[1] > 1:
                qt = fs.render(str(slot[1]), True, (200, 200, 200))
                screen.blit(qt, (sx + _MINI_SZ - qt.get_width() - 1,
                                 sy + _MINI_SZ - qt.get_height()))

    # ── Detail section ───────────────────────────────────────────────────────
    det = _detail_rect(cx, cy, cw, ch)

    if selected is not None and 0 <= selected < 36:
        slot = inv[selected]
        if slot is not None:
            item_def = _get_item(slot[0])
            name     = slot[2].get("name", item_def.get("name", f"Item {slot[0]}")) \
                       if len(slot) > 2 and isinstance(slot[2], dict) \
                       else item_def.get("name", f"Item {slot[0]}")

            dur, dur_max = _dur_info(slot)
            cost = _get_repair_cost(slot)

            # Name
            ns = fm.render(name, True, (230, 220, 180))
            screen.blit(ns, (det.x, det.y))

            # Durability bar
            if dur_max is not None:
                bar_w = det.width
                bar_h = 8
                bar_y = det.y + ns.get_height() + 4
                ratio = max(0.0, min(1.0, (dur or dur_max) / dur_max))
                pygame.draw.rect(screen, (40, 40, 40), (det.x, bar_y, bar_w, bar_h))
                fill_col = (50, 200, 50) if ratio > 0.6 else (220, 180, 30) if ratio > 0.3 else (210, 60, 60)
                fill_w = max(0, int(bar_w * ratio))
                if fill_w:
                    pygame.draw.rect(screen, fill_col, (det.x, bar_y, fill_w, bar_h))
                pygame.draw.rect(screen, (80, 80, 80), (det.x, bar_y, bar_w, bar_h), 1)
                dur_txt = fs.render(f"Durability: {dur}/{dur_max}", True, (160, 160, 160))
                screen.blit(dur_txt, (det.x, bar_y + bar_h + 3))

            # Cost
            if cost is not None:
                mat_id, qty = cost
                mat_name = _get_item(mat_id).get("name", f"Item {mat_id}")
                have = _count_inv(mat_id, inv)
                col  = (70, 210, 70) if have >= qty else (210, 70, 70)
                cost_s = fs.render(f"Cost: {qty}× {mat_name}  (have {have})", True, col)
                screen.blit(cost_s, (det.x, det.y + ns.get_height() + 22))
            else:
                nr = fs.render("Not repairable", True, (130, 130, 130))
                screen.blit(nr, (det.x, det.y + ns.get_height() + 22))
        else:
            hint = fs.render("Selected slot is empty.", True, (80, 80, 90))
            screen.blit(hint, (det.x, det.y))
    else:
        hint = fs.render("Click a highlighted item to select it for repair.", True, (80, 80, 90))
        screen.blit(hint, (cx + _PAD, det.y))

    # ── REPAIR button ────────────────────────────────────────────────────────
    btn   = _btn_rect(cx, cy, cw, ch)
    can   = _can_repair(inv, selected)
    bcol  = (45, 110, 55)  if can else (38, 38, 46)
    bbrd  = (78, 185, 90)  if can else (60, 60, 76)
    btcol = (255, 255, 255) if can else (84, 84, 100)
    pygame.draw.rect(screen, bcol,  btn, border_radius=4)
    pygame.draw.rect(screen, bbrd,  btn, 2, border_radius=4)
    bts = fm.render("REPAIR", True, btcol)
    screen.blit(bts, (btn.x + (btn.w - bts.get_width()) // 2,
                       btn.y + (btn.h - bts.get_height()) // 2))


def _can_repair(inv: list, selected: int | None) -> bool:
    if selected is None or not (0 <= selected < 36):
        return False
    slot = inv[selected]
    if slot is None:
        return False
    dur, dur_max = _dur_info(slot)
    if dur_max is None:
        return False
    if dur is not None and dur >= dur_max:
        return False
    cost = _get_repair_cost(slot)
    if cost is None:
        return False
    mat_id, qty = cost
    return _count_inv(mat_id, inv) >= qty


# ─── Hit testing ─────────────────────────────────────────────────────────────

def repair_panel_hit(mx: int, my: int,
                     cx: int, cy: int, cw: int, ch: int) -> tuple | None:
    """
    Returns:
      ("slot", idx)   — clicked a bag slot
      ("repair", None) — clicked REPAIR button
      None            — miss
    """
    _load_items()

    # Bag grid
    gx, gy = _grid_origin(cx, cy, cw)
    for slot_i in range(36):
        col = slot_i % _COLS
        row = slot_i // _COLS
        sx  = gx + col * (_MINI_SZ + _MINI_G)
        sy  = gy + row * (_MINI_SZ + _MINI_G)
        if sx <= mx < sx + _MINI_SZ and sy <= my < sy + _MINI_SZ:
            return ("slot", slot_i)

    # Repair button
    btn = _btn_rect(cx, cy, cw, ch)
    if btn.collidepoint(mx, my):
        return ("repair", None)

    return None

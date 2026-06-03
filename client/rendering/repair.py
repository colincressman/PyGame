"""client/rendering/repair.py

Repair popup UI embedded as the "Repair" tab inside the Crafting Table popup.
"""

from __future__ import annotations

import json
import os as _os

import pygame

from rendering import ui_theme as _T
from rendering.cache import get_item_surface

_items: dict[int, dict] = {}
_items_loaded = False
_repair_loaded = False
_repair_range_rules: list[tuple[tuple[int, int], int, int]] = []
_repair_part_rules: dict[int, tuple[int, int]] = {}


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
        with open(path, encoding="utf-8") as f:
            _items = {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"[REPAIR] Could not load items.json: {e}")


def _load_repair_data() -> None:
    global _repair_loaded
    if _repair_loaded:
        return
    _repair_loaded = True
    try:
        path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "..", "..", "data", "repair.json",
        )
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[REPAIR] Could not load repair.json: {e}")
        return

    for entry in raw.get("range_rules", []):
        if not isinstance(entry, dict):
            continue
        lo = entry.get("min_id")
        hi = entry.get("max_id")
        mat_id = entry.get("material_id")
        qty = entry.get("qty")
        if not all(isinstance(v, int) for v in (lo, hi, mat_id, qty)):
            continue
        _repair_range_rules.append(((lo, hi), mat_id, qty))

    for part_id, entry in raw.get("part_rules", {}).items():
        if not isinstance(entry, dict):
            continue
        try:
            pid = int(part_id)
        except (TypeError, ValueError):
            continue
        mat_id = entry.get("material_id")
        qty = entry.get("qty")
        if not isinstance(mat_id, int) or not isinstance(qty, int):
            continue
        _repair_part_rules[pid] = (mat_id, qty)


def _get_item(item_id: int) -> dict:
    _load_items()
    return _items.get(item_id, {})


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


def _get_repair_cost(slot: list) -> tuple[int, int] | None:
    """Return (material_id, qty) or None if not repairable."""
    _load_repair_data()
    item_id = slot[0]
    meta = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}
    parts = meta.get("parts")
    if parts and len(parts) >= 2:
        result = _repair_part_rules.get(parts[1])
        if result:
            return result
    for (lo, hi), mat_id, qty in _repair_range_rules:
        if lo <= item_id < hi:
            return mat_id, qty
    return None


def _dur_info(slot: list) -> tuple[int | None, int | None]:
    """Return (dur, dur_max) from slot meta, falling back to items.json."""
    meta = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}
    dur = meta.get("dur")
    dur_max = meta.get("dur_max")
    if dur_max is None:
        item_def = _get_item(slot[0])
        dur_max = item_def.get("durability")
        dur = dur_max
    return dur, dur_max


def _count_inv(item_id: int, inv: list) -> int:
    return sum(s[1] for s in inv[:36] if s is not None and s[0] == item_id)


def _get_art(item_id: int, size: int) -> pygame.Surface:
    return get_item_surface(item_id, size)


_COLS = 9
_MINI_SZ = 34
_MINI_G = 2
_PAD = 12
_BTN_W = 140
_BTN_H = 32


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


def draw_repair_panel(screen: pygame.Surface, cx: int, cy: int, cw: int, ch: int) -> None:
    """Draw the Repair UI inside the content area (cx, cy, cw, ch)."""
    import config

    _load_items()
    _load_repair_data()

    fm = _get_font_md()
    fs = _get_font_sm()
    inv = config.player_inventory
    gx, gy = _grid_origin(cx, cy, cw)
    selected = config.repair_selected_slot

    for slot_i in range(36):
        col = slot_i % _COLS
        row = slot_i // _COLS
        sx = gx + col * (_MINI_SZ + _MINI_G)
        sy = gy + row * (_MINI_SZ + _MINI_G)
        slot = inv[slot_i]

        is_sel = slot_i == selected
        is_rep = False
        if slot is not None:
            _, dur_max = _dur_info(slot)
            is_rep = dur_max is not None

        if is_sel:
            bg, brd = (40, 70, 40), _T.BTN_BD
        elif is_rep:
            bg, brd = (30, 38, 30), (55, 100, 55)
        else:
            bg, brd = _T.SLOT_BG, _T.SLOT_BD

        pygame.draw.rect(screen, bg, (sx, sy, _MINI_SZ, _MINI_SZ), border_radius=3)
        pygame.draw.rect(screen, brd, (sx, sy, _MINI_SZ, _MINI_SZ), 1, border_radius=3)

        if slot is not None:
            art = _get_art(slot[0], _MINI_SZ - 4)
            screen.blit(art, (sx + 2, sy + 2))
            if slot[1] > 1:
                qt = fs.render(str(slot[1]), True, (200, 200, 200))
                screen.blit(qt, (sx + _MINI_SZ - qt.get_width() - 1, sy + _MINI_SZ - qt.get_height()))

    det = _detail_rect(cx, cy, cw, ch)

    if selected is not None and 0 <= selected < 36:
        slot = inv[selected]
        if slot is not None:
            item_def = _get_item(slot[0])
            if len(slot) > 2 and isinstance(slot[2], dict):
                name = slot[2].get("name", item_def.get("name", f"Item {slot[0]}"))
            else:
                name = item_def.get("name", f"Item {slot[0]}")

            dur, dur_max = _dur_info(slot)
            cost = _get_repair_cost(slot)

            ns = fm.render(name, True, (230, 220, 180))
            screen.blit(ns, (det.x, det.y))

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

            if cost is not None:
                mat_id, qty = cost
                mat_name = _get_item(mat_id).get("name", f"Item {mat_id}")
                have = _count_inv(mat_id, inv)
                col = (70, 210, 70) if have >= qty else (210, 70, 70)
                cost_s = fs.render(f"Cost: {qty}x {mat_name}  (have {have})", True, col)
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

    btn = _btn_rect(cx, cy, cw, ch)
    can = _can_repair(inv, selected)
    bcol = (45, 110, 55) if can else (38, 38, 46)
    bbrd = (78, 185, 90) if can else (60, 60, 76)
    btcol = (255, 255, 255) if can else (84, 84, 100)
    pygame.draw.rect(screen, bcol, btn, border_radius=4)
    pygame.draw.rect(screen, bbrd, btn, 2, border_radius=4)
    bts = fm.render("REPAIR", True, btcol)
    screen.blit(bts, (btn.x + (btn.w - bts.get_width()) // 2, btn.y + (btn.h - bts.get_height()) // 2))


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


def repair_panel_hit(mx: int, my: int, cx: int, cy: int, cw: int, ch: int) -> tuple | None:
    """
    Returns:
      ("slot", idx)   if a bag slot was clicked
      ("repair", None) if the repair button was clicked
      None on miss
    """
    _load_items()
    _load_repair_data()

    gx, gy = _grid_origin(cx, cy, cw)
    for slot_i in range(36):
        col = slot_i % _COLS
        row = slot_i // _COLS
        sx = gx + col * (_MINI_SZ + _MINI_G)
        sy = gy + row * (_MINI_SZ + _MINI_G)
        if sx <= mx < sx + _MINI_SZ and sy <= my < sy + _MINI_SZ:
            return ("slot", slot_i)

    btn = _btn_rect(cx, cy, cw, ch)
    if btn.collidepoint(mx, my):
        return ("repair", None)

    return None

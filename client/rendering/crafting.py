"""
client/rendering/crafting.py

Two modes of crafting UI:
  1. Inline "CRAFT" tab inside the inventory panel.
       draw_basic_crafting_inline(screen, ax, ay, aw, ah)
       Only shows recipes that need no station.

  2. Station popup — opened via F near a station block.
       draw_station_popup(screen, station_type, ww, wh)
       station_type: "furnace" | "campfire" | "crafting_table"
"""

import json
import os as _os

import pygame
import config
from rendering import ui_theme as _T
from rendering.inventory import _get_font, _get_item_image, _get_tooltip_font, _get_item_name

# -- Recipe / item data (loaded once) -----------------------------------------
_recipes: dict = {}
_rec_loaded = False
_items: dict = {}
_items_loaded = False


def _load_recipes():
    global _recipes, _rec_loaded
    if _rec_loaded:
        return
    _rec_loaded = True
    path = _os.path.normpath(
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "server", "recipes.json")
    )
    try:
        with open(path) as f:
            _recipes = {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"[CRAFTING] Could not load recipes.json: {e}")


def _load_items():
    global _items, _items_loaded
    if _items_loaded:
        return
    _items_loaded = True
    path = _os.path.normpath(
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "server", "items.json")
    )
    try:
        with open(path) as f:
            _items = {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"[CRAFTING] Could not load items.json: {e}")


# -- Recipe filters ------------------------------------------------------------

_popup_recipe_cache:  dict[str, list] = {}   # station_type → sorted list; filled on first request
_basic_recipe_cache:  list | None     = None  # no-station recipes; filled on first request


def _recipes_basic() -> list:
    """All recipes requiring no station, sorted by id."""
    global _basic_recipe_cache
    if _basic_recipe_cache is not None:
        return _basic_recipe_cache
    _load_recipes()
    _basic_recipe_cache = sorted(
        [(k, v) for k, v in _recipes.items() if not v.get("station")],
        key=lambda t: t[0],
    )
    return _basic_recipe_cache


def _recipes_for_popup(station_type: str) -> list:
    """Recipes appropriate for the given station popup, sorted by id."""
    if station_type in _popup_recipe_cache:
        return _popup_recipe_cache[station_type]
    _load_recipes()
    items = [
        (k, v) for k, v in _recipes.items()
        if v.get("station") == station_type
    ]
    result = sorted(items, key=lambda t: t[0])
    _popup_recipe_cache[station_type] = result
    return result


# -- Craft check helpers -------------------------------------------------------

def _can_craft(recipe: dict) -> bool:
    inv = config.player_inventory
    for ing_id, ing_qty in recipe.get("ingredients", []):
        have = sum(s[1] for s in inv[:36] if s is not None and s[0] == ing_id)
        if have < ing_qty:
            return False
    return True


def _has_station(recipe: dict) -> bool:
    station = recipe.get("station")
    if not station:
        return True
    if station in config.nearby_stations:
        return True
    # If the station popup is open for this station, we're obviously at it
    if station == getattr(config, "show_station_popup", None):
        return True
    return False


# -- Quality display constants -------------------------------------------------

_QUALITY_TIERS = [
    ("Common",    0.80, 1.00, (185, 185, 185)),
    ("Uncommon",  1.00, 1.30, ( 75, 200,  75)),
    ("Rare",      1.30, 1.70, ( 90, 130, 245)),
    ("Exquisite", 1.70, 2.20, (190,  75, 240)),
]
_QUALITY_ABBR = {"Common": "Com", "Uncommon": "Unc", "Rare": "Rare", "Exquisite": "Exq"}
_STAT_ABBR = {
    "attack_power":   "ATK", "health_max":     "HP",
    "stamina_max":    "SP",  "speed_bonus":    "SPD",
    "hp_regen":       "Regen", "sp_regen_bonus": "SpRgn",
}

_BTN_H = 28
_BTN_W = 88
_PAD   = 8


# -- Shared sub-renderers ------------------------------------------------------

def _draw_recipe_list(screen, recipes, selected_id, scroll, lx, ly, lw, lh, row_h=26):
    """Render a scrollable recipe list. Returns max_scroll."""
    font     = _get_font()
    old_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(lx, ly, lw, lh))
    for i, (rid, recipe) in enumerate(recipes):
        ry = ly + i * row_h - scroll
        if ry + row_h <= ly or ry >= ly + lh:
            continue
        sel_bg = (44, 52, 64) if rid == selected_id else (18, 18, 22)
        pygame.draw.rect(screen, sel_bg, (lx, ry, lw, row_h))
        pygame.draw.line(screen, (38, 38, 38), (lx, ry + row_h - 1), (lx + lw, ry + row_h - 1))
        can    = _can_craft(recipe)
        has_st = _has_station(recipe)
        dot_col = (65, 205, 65) if (can and has_st) else (220, 165, 40) if can else (205, 65, 65)
        pygame.draw.circle(screen, dot_col, (lx + 8, ry + row_h // 2), 3)
        name_col = (220, 220, 220) if can else (120, 120, 120)
        ns = font.render(recipe.get("name", "?"), True, name_col)
        screen.blit(ns, (lx + 18, ry + (row_h - ns.get_height()) // 2))
    screen.set_clip(old_clip)
    return max(0, len(recipes) * row_h - lh)


def _draw_detail(screen, sel, detail_x, detail_y, detail_w, detail_h, btn_y):
    """Render recipe detail (result, ingredients, craft button) into the given rect."""
    _load_items()
    font     = _get_font()
    big_font = _get_tooltip_font()
    if not sel:
        hint = font.render("<- select a recipe", True, (65, 65, 72))
        screen.blit(hint, (
            detail_x + (detail_w - hint.get_width()) // 2,
            detail_y + (detail_h - hint.get_height()) // 2,
        ))
        return

    dx = detail_x + _PAD
    dy = detail_y + 6

    # Result row
    result_id, _ = sel["result"]
    screen.blit(pygame.transform.scale(_get_item_image(result_id), (28, 28)), (dx, dy))
    rname = big_font.render(sel.get("name", ""), True, (235, 195, 70))
    screen.blit(rname, (dx + 32, dy + (28 - rname.get_height()) // 2))
    dy += 32

    # Item description (if present)
    desc = _items.get(result_id, {}).get("description", "")
    if desc:
        desc_surf = font.render(desc, True, (155, 195, 155))
        screen.blit(desc_surf, (dx, dy))
        dy += desc_surf.get_height() + 4

    hdr = font.render("Requires:", True, (140, 140, 140))
    screen.blit(hdr, (dx, dy))
    dy += hdr.get_height() + 3

    inv = config.player_inventory
    for ing_id, ing_qty in sel.get("ingredients", []):
        have = sum(s[1] for s in inv[:36] if s is not None and s[0] == ing_id)
        ok   = have >= ing_qty
        screen.blit(pygame.transform.scale(_get_item_image(ing_id), (14, 14)), (dx, dy))
        col  = (70, 210, 70) if ok else (210, 70, 70)
        ls   = font.render(f"{have}/{ing_qty}  {_get_item_name(ing_id)}", True, col)
        screen.blit(ls, (dx + 18, dy + (14 - ls.get_height()) // 2))
        dy += 18

    # Quality stat ranges (only if item has stats and there is vertical room)
    base_stats = _items.get(result_id, {}).get("stats", {})
    if base_stats and dy + 50 < btn_y - 4:
        dy += 4
        hdr2 = font.render("Quality:", True, (110, 110, 110))
        screen.blit(hdr2, (dx, dy))
        dy += hdr2.get_height() + 2
        for qname, lo, hi, qcol in _QUALITY_TIERS:
            if dy + font.size("A")[1] > btn_y - 4:
                break
            abbr  = _QUALITY_ABBR.get(qname, qname[0])
            parts = []
            for sk, sv in base_stats.items():
                slbl = _STAT_ABBR.get(sk, sk)
                lo_v, hi_v = sv * lo, sv * hi
                parts.append(
                    f"{max(1,round(lo_v))}-{max(1,round(hi_v))} {slbl}"
                    if isinstance(sv, int)
                    else f"{lo_v:.1f}-{hi_v:.1f} {slbl}"
                )
            pygame.draw.circle(screen, qcol, (dx + 4, dy + 5), 3)
            rs = font.render(f"{abbr}: {'  '.join(parts)}", True, qcol)
            screen.blit(rs, (dx + 11, dy))
            dy += font.size("A")[1] + 1

    # CRAFT button
    can  = _can_craft(sel) and _has_station(sel)
    bx   = detail_x + (detail_w - _BTN_W) // 2
    bcol  = _T.BTN_BG    if can else _T.BTN_DIS_BG
    bbrd  = _T.BTN_BD    if can else _T.BTN_DIS_BD
    btcol = _T.BTN_TXT   if can else _T.BTN_DIS_TX
    pygame.draw.rect(screen, bcol,  (bx, btn_y, _BTN_W, _BTN_H), border_radius=4)
    pygame.draw.rect(screen, bbrd,  (bx, btn_y, _BTN_W, _BTN_H), 2, border_radius=4)
    btxt = big_font.render("CRAFT", True, btcol)
    screen.blit(btxt, (bx + (_BTN_W - btxt.get_width()) // 2,
                        btn_y + (_BTN_H - btxt.get_height()) // 2))

    req_st = sel.get("station")
    if req_st and not _has_station(sel):
        st_lbl = font.render(f"Need: {req_st.replace('_', ' ')}", True, (200, 140, 50))
        screen.blit(st_lbl, (bx + (_BTN_W - st_lbl.get_width()) // 2, btn_y - st_lbl.get_height() - 2))


def _draw_scroll_arrows(screen, mid_x, top_y, bot_y, scroll, max_scroll):
    if scroll > 0:
        pygame.draw.polygon(screen, (140, 140, 140),
                            [(mid_x, top_y + 3), (mid_x - 5, top_y + 9), (mid_x + 5, top_y + 9)])
    if scroll < max_scroll:
        pygame.draw.polygon(screen, (140, 140, 140),
                            [(mid_x, bot_y - 3), (mid_x - 5, bot_y - 9), (mid_x + 5, bot_y - 9)])


# -- Inline basic crafting (inventory CRAFT tab) -------------------------------

_INLINE_LIST_W = 165
_INLINE_ROW_H  = 24


def inv_craft_area(ww: int, wh: int) -> tuple:
    """Return (ax, ay, aw, ah) for the inline craft content rect."""
    from rendering.inventory import _panel_origin, _panel_dims
    sx, sy = _panel_origin(ww, wh)
    pw, ph, pad, gw, _ = _panel_dims()
    return sx + pad, sy + pad + 20, gw, ph - pad * 2 - 20


def draw_basic_crafting_inline(screen, ax: int, ay: int, aw: int, ah: int):
    """Render basic (no-station) crafting inside the inventory CRAFT tab area."""
    _load_recipes()
    recipes  = _recipes_basic()
    list_w   = _INLINE_LIST_W
    detail_x = ax + list_w + 1
    detail_w = aw - list_w - 1
    btn_y    = ay + ah - _PAD - _BTN_H

    pygame.draw.rect(screen, (14, 14, 18), (ax, ay, list_w, ah))
    pygame.draw.rect(screen, (18, 18, 26), (detail_x, ay, detail_w, ah))
    pygame.draw.line(screen, (55, 55, 60), (detail_x, ay), (detail_x, ay + ah))

    max_scroll = _draw_recipe_list(
        screen, recipes, config.selected_recipe,
        config.crafting_scroll, ax, ay, list_w, ah, _INLINE_ROW_H,
    )
    config.crafting_scroll = max(0, min(config.crafting_scroll, max_scroll))
    _draw_scroll_arrows(screen, ax + list_w // 2, ay, ay + ah,
                        config.crafting_scroll, max_scroll)

    _draw_detail(screen, _recipes.get(config.selected_recipe),
                 detail_x, ay, detail_w, ah, btn_y)


def basic_crafting_inline_hit(mx: int, my: int, ax: int, ay: int, aw: int, ah: int):
    """Hit-test the inline craft tab. Returns ("recipe", id) | ("craft", None) | None."""
    _load_recipes()
    recipes  = _recipes_basic()
    list_w   = _INLINE_LIST_W
    detail_x = ax + list_w + 1
    detail_w = aw - list_w - 1
    btn_y    = ay + ah - _PAD - _BTN_H

    if ax <= mx < ax + list_w and ay <= my < ay + ah:
        local_y = my - ay + config.crafting_scroll
        idx     = local_y // _INLINE_ROW_H
        if 0 <= idx < len(recipes):
            return ("recipe", recipes[idx][0])
        return None

    bx = detail_x + (detail_w - _BTN_W) // 2
    if bx <= mx < bx + _BTN_W and btn_y <= my < btn_y + _BTN_H:
        return ("craft", None)
    return None


# -- Station popup -------------------------------------------------------------

_POPUP_W       = 480
_POPUP_H       = 330
_POPUP_TITLE_H = 28
_POPUP_LIST_W  = 190
_POPUP_ROW_H   = 26

_STATION_META = {
    "furnace":        ("Smelting",       (210, 120,  40)),
    "campfire":       ("Cooking",        (230, 185,  60)),
    "crafting_table": ("Crafting Table", (100, 185, 100)),
    "alloy_forge":    ("Alloy Forge",    (220, 155,  60)),
    "part_maker":     ("Part Maker",     (140, 100, 200)),
}

# -- Crafting-table tab configuration -----------------------------------------

_POPUP_TAB_H = 24
_CRAFTING_TABLE_TABS = [
    ("Weapon", "weapon"),
    ("Tools",  "tool"),
    ("Armor",  "armor"),
    ("Build",  "place"),
    ("Other",  "other"),   # trinkets + food
    ("Repair", "repair"),
]
_TAB_OTHER_CATS = {"trinket", "food"}

# Part-maker tabs — filter by result item ID range
_PART_MAKER_TABS = [
    ("Blade",   "blade"),
    ("Axe",     "axe"),
    ("Pick",    "pick"),
    ("Plate",   "plate"),
    ("Mold",    "mold"),
    ("Handle",  "handle"),
    ("Core",    "core"),
    ("Binding", "binding"),
    ("Lining",  "lining"),
]
# Each value is a list of (lo, hi) inclusive-low exclusive-high ranges
# covering the result item IDs for that tab.
_PART_MAKER_RANGES = {
    "blade":   [(148, 162), (278, 279)],           # 148-161, 278 Slime Blade
    "axe":     [(162, 172), (281, 283)],           # 162-171, 281-282 Silver/Crystal Axe
    "pick":    [(172, 182), (283, 285)],           # 172-181, 283-284 Bone/Silver Pick
    "plate":   [(182, 190), (285, 289)],           # 182-189, 285-288 Stone/Bone/Paper/Slime Plate
    "mold":    [(190, 200), (208, 214)],            # 190-199 katana, 208 saber, 209 scimitar, 210 rapier, 211 hammer, 212 wand, 213 back
    "handle":  [(260, 269), (279, 280), (289, 292)],  # 260-268, 279 Slime, 289-291
    "core":    [(269, 272)],                       # 269-271
    "binding": [(272, 278), (280, 281), (292, 297)],  # 272-277, 280 Slime, 292-296 Crystal
    "lining":  [(297, 310)],                       # 297-309 Paper/Reed/Bone/../Slime Lining
}


def _filtered_popup_recipes(station_type: str, tab: str) -> list:
    """Like _recipes_for_popup but filters by tab when station supports tabs."""
    all_r = _recipes_for_popup(station_type)
    if station_type == "crafting_table":
        if tab == "other":
            return [(k, v) for k, v in all_r if v.get("category", "") in _TAB_OTHER_CATS]
        return [(k, v) for k, v in all_r if v.get("category", "") == tab]
    if station_type == "part_maker":
        if tab in _PART_MAKER_RANGES:
            ranges = _PART_MAKER_RANGES[tab]
            return [(k, v) for k, v in all_r
                    if any(lo <= v.get("result", [0])[0] < hi for lo, hi in ranges)]
        # Weapon, armor, trinket, tool tabs use recipe category
        return [(k, v) for k, v in all_r if v.get("category", "") == tab]
    return all_r


def _draw_tab_bar(screen, px: int, py: int, selected_tab: str, tabs: list):
    """Draw the horizontal tab bar for a station popup."""
    font = _get_font()
    ty = py + _POPUP_TITLE_H
    n = len(tabs)
    tab_w = _POPUP_W // n
    for i, (label, key) in enumerate(tabs):
        tx = px + i * tab_w
        tw = tab_w if i < n - 1 else _POPUP_W - i * tab_w
        active = key == selected_tab
        bg = (28, 38, 52) if active else (16, 18, 22)
        pygame.draw.rect(screen, bg, (tx, ty, tw, _POPUP_TAB_H))
        brd = (65, 105, 155) if active else (36, 36, 42)
        pygame.draw.rect(screen, brd, (tx, ty, tw, _POPUP_TAB_H), 1)
        if active:
            pygame.draw.line(screen, (85, 165, 215),
                             (tx + 3, ty + _POPUP_TAB_H - 2),
                             (tx + tw - 4, ty + _POPUP_TAB_H - 2), 2)
        col = (225, 225, 225) if active else (105, 105, 105)
        ts = font.render(label, True, col)
        screen.blit(ts, (tx + (tw - ts.get_width()) // 2,
                         ty + (_POPUP_TAB_H - ts.get_height()) // 2))


def _popup_origin(ww: int, wh: int) -> tuple:
    return (ww - _POPUP_W) // 2, (wh - _POPUP_H) // 2


def draw_station_popup(screen, station_type: str, ww: int, wh: int):
    """Draw a station-specific crafting popup centred on screen."""
    _load_recipes()
    px, py   = _popup_origin(ww, wh)
    title, tcol = _STATION_META.get(station_type, ("Crafting", (200, 200, 200)))

    has_tabs  = station_type in ("crafting_table", "part_maker")
    tab_off   = _POPUP_TAB_H if has_tabs else 0
    _tabs     = _PART_MAKER_TABS if station_type == "part_maker" else _CRAFTING_TABLE_TABS
    recipes   = _filtered_popup_recipes(station_type, config.station_popup_tab) if has_tabs \
                else _recipes_for_popup(station_type)

    content_y = py + _POPUP_TITLE_H + tab_off
    content_h = _POPUP_H - _POPUP_TITLE_H - tab_off
    detail_x  = px + _POPUP_LIST_W + 1
    detail_w  = _POPUP_W - _POPUP_LIST_W - 1
    btn_y     = py + _POPUP_H - _PAD - _BTN_H

    bg = pygame.Surface((_POPUP_W, _POPUP_H), pygame.SRCALPHA)
    bg.fill(_T.BG_FILL + (_T.BG_ALPHA,))
    screen.blit(bg, (px, py))
    pygame.draw.rect(screen, _T.BORDER, (px, py, _POPUP_W, _POPUP_H), 2)

    pygame.draw.rect(screen, _T.TITLE_BAR, (px, py, _POPUP_W, _POPUP_TITLE_H))
    accent = tuple(max(0, c - 60) for c in tcol)
    pygame.draw.line(screen, accent,
                     (px, py + _POPUP_TITLE_H - 1), (px + _POPUP_W, py + _POPUP_TITLE_H - 1))
    big_font = _get_tooltip_font()
    t = big_font.render(f"{title}   [F / ESC to close]", True, tcol)
    screen.blit(t, (px + _PAD, py + (_POPUP_TITLE_H - t.get_height()) // 2))

    if has_tabs:
        _draw_tab_bar(screen, px, py, config.station_popup_tab, _tabs)

    # ── Repair tab — delegates entirely to repair.py ──────────────────────
    if station_type == "crafting_table" and config.station_popup_tab == "repair":
        from rendering.repair import draw_repair_panel
        pygame.draw.rect(screen, (14, 14, 18), (px, content_y, _POPUP_W, content_h))
        draw_repair_panel(screen, px, content_y, _POPUP_W, content_h)
        return

    pygame.draw.rect(screen, (14, 14, 18), (px, content_y, _POPUP_LIST_W, content_h))
    pygame.draw.rect(screen, (18, 18, 26), (detail_x, content_y, detail_w, content_h))
    pygame.draw.line(screen, (55, 55, 60), (detail_x, content_y), (detail_x, py + _POPUP_H))

    max_scroll = _draw_recipe_list(
        screen, recipes, config.station_popup_recipe,
        config.station_popup_scroll, px, content_y,
        _POPUP_LIST_W, content_h, _POPUP_ROW_H,
    )
    config.station_popup_scroll = max(0, min(config.station_popup_scroll, max_scroll))
    _draw_scroll_arrows(screen, px + _POPUP_LIST_W // 2, content_y, py + _POPUP_H,
                        config.station_popup_scroll, max_scroll)

    _draw_detail(screen, _recipes.get(config.station_popup_recipe),
                 detail_x, content_y, detail_w, content_h, btn_y)


def station_popup_hit(mx: int, my: int, station_type: str, ww: int, wh: int):
    """
    Hit-test the station popup.
    Returns ("recipe", id) | ("craft", None) | ("tab", key) | ("outside", None) | None.
    "outside" means the click was outside the popup rect.
    """
    _load_recipes()
    px, py = _popup_origin(ww, wh)
    if not (px <= mx < px + _POPUP_W and py <= my < py + _POPUP_H):
        return ("outside", None)
    if my < py + _POPUP_TITLE_H:
        return None

    has_tabs = station_type in ("crafting_table", "part_maker")
    tab_off  = _POPUP_TAB_H if has_tabs else 0
    _tabs    = _PART_MAKER_TABS if station_type == "part_maker" else _CRAFTING_TABLE_TABS

    # Tab bar click
    if has_tabs and my < py + _POPUP_TITLE_H + _POPUP_TAB_H:
        n = len(_tabs)
        tab_w = _POPUP_W // n
        idx = min((mx - px) // tab_w, n - 1)
        return ("tab", _tabs[idx][1])

    content_y = py + _POPUP_TITLE_H + tab_off
    content_h = _POPUP_H - _POPUP_TITLE_H - tab_off
    detail_x  = px + _POPUP_LIST_W + 1
    detail_w  = _POPUP_W - _POPUP_LIST_W - 1
    btn_y     = py + _POPUP_H - _PAD - _BTN_H

    # Repair tab — delegate hit-test to repair.py
    if station_type == "crafting_table" and config.station_popup_tab == "repair":
        from rendering.repair import repair_panel_hit
        result = repair_panel_hit(mx, my, px, content_y, _POPUP_W, content_h)
        if result is not None:
            kind, val = result
            if kind == "slot":
                return ("repair_slot", val)
            if kind == "repair":
                return ("repair", None)
        return None

    if px <= mx < px + _POPUP_LIST_W and content_y <= my < content_y + content_h:
        local_y = my - content_y + config.station_popup_scroll
        idx     = local_y // _POPUP_ROW_H
        recipes = _filtered_popup_recipes(station_type, config.station_popup_tab) if has_tabs \
                  else _recipes_for_popup(station_type)
        if 0 <= idx < len(recipes):
            return ("recipe", recipes[idx][0])
        return None

    bx = detail_x + (detail_w - _BTN_W) // 2
    if bx <= mx < bx + _BTN_W and btn_y <= my < btn_y + _BTN_H:
        return ("craft", None)
    return None

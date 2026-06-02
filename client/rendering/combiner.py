"""client/rendering/combiner.py

Part Combiner popup UI.

The player fills 4 input slots (Mold / Primary / Handle / Binding) by:
  1. Clicking a combiner slot to select it (highlighted).
  2. Clicking a bag item below to assign that inventory index to the slot.
  3. Pressing COMBINE to forge the item (sends combine_parts to server).

config state used:
  combiner_slots          — list[int|None]  (inv indices for the 4 slots)
  combiner_selected_slot  — int  (-1 = none selected)
  player_inventory        — the player's full inventory list
  show_station_popup      — set to "part_combiner" when open
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
        print(f"[COMBINER] Could not load items.json: {e}")


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
POPUP_W  = 500
POPUP_H  = 415

_TITLE_H  = 28
_PAD      = 12
_SLOT_SZ  = 56   # combiner input slot size
_SLOT_GAP = 14   # gap between combiner slots
_MINI_SZ  = 34   # mini-inventory slot size
_MINI_GAP = 2    # gap between mini-inventory slots

_INV_COLS = 9
_INV_ROWS = 4    # bag slots 0-35


_SLOT_LABELS = ("Mold", "Primary", "Handle", "Binding")

_MOLD_HINT: dict[int, str] = {
    190: "Sword",   191: "Dagger",  192: "Axe",   193: "Pickaxe",
    194: "Helm",    195: "Chest",   196: "Arms",   197: "Legs",   198: "Feet",
    199: "Katana",  208: "Saber",   209: "Scimitar",
    210: "Rapier",  211: "Hammer",  212: "Wand",   213: "Cloak",
}

# Suffix to strip from a primary part's name to extract the material
_SLOT_NAME_SUFFIX: dict[str, str] = {
    "blade":     " Blade",
    "pick_head": " Pick Head",
    "axe_head":  " Axe Head",
    "plate":     " Plate",
}

_MOLD_BASE: dict[int, tuple[int, bool]] = {
    190: (1101, False), 191: (1100, False),
    192: (2100, False), 193: (2101, False),
    194: (3002, True),  195: (3103, True),
    196: (3201, True),  197: (3306, True),
    198: (3401, True),
    199: (1850, False), 208: (1860, False), 209: (1870, False),
    210: (1500, False), 211: (2500, False), 212: (1800, False),
    213: (3504, True),
}
_MOLD_SLOT2: dict[int, str] = {
    190: "blade",    191: "blade",
    192: "axe_head", 193: "pick_head",
    194: "plate",    195: "plate",
    196: "plate",    197: "plate",    198: "plate",
    199: "blade",   208: "blade",    209: "blade",
    210: "blade",   211: "axe_head", 212: "blade",
    213: "plate",
}

# Armor molds where slot 2 = "Lining" (binding), not handle/core
_ARMOR_MOLD_IDS: frozenset[int] = frozenset(
    mid for mid, (_, is_a) in _MOLD_BASE.items() if is_a
)


def _slot_labels_for_mold(mold_id: int | None) -> tuple[str, str, str, str]:
    """Return slot labels depending on whether an armor or weapon mold is active.

    Armor uses: Mold + Plate + Lining (soft interior padding) + Binding (outer straps).
    Weapons/tools use: Mold + Primary + Handle/Core + Binding.
    """
    if mold_id in _ARMOR_MOLD_IDS:
        return ("Mold", "Plate", "Lining", "Binding")
    return _SLOT_LABELS

# ─── Item art cache ───────────────────────────────────────────────────────────
def _get_art(item_id: int, size: int) -> pygame.Surface:
    return get_item_surface(item_id, size)


# ─── Geometry helpers ────────────────────────────────────────────────────────

def _popup_origin(ww: int, wh: int) -> tuple[int, int]:
    return (ww - POPUP_W) // 2, (wh - POPUP_H) // 2


def _slot_rects(px: int, py: int) -> list[pygame.Rect]:
    total_w = _SLOT_SZ * 4 + _SLOT_GAP * 3
    sx = px + (POPUP_W - total_w) // 2
    sy = py + _TITLE_H + 10
    return [
        pygame.Rect(sx + i * (_SLOT_SZ + _SLOT_GAP), sy, _SLOT_SZ, _SLOT_SZ)
        for i in range(4)
    ]


def _preview_rect(px: int, py: int) -> pygame.Rect:
    slots = _slot_rects(px, py)
    y = slots[0].bottom + 18   # gap for slot labels
    return pygame.Rect(px + _PAD, y, POPUP_W - _PAD * 2, 76)


def _inv_grid_origin(px: int, py: int) -> tuple[int, int]:
    pr    = _preview_rect(px, py)
    gw    = _INV_COLS * (_MINI_SZ + _MINI_GAP) - _MINI_GAP
    gx    = px + (POPUP_W - gw) // 2
    gy    = pr.bottom + 18    # 14 px header + 4 px spacing
    return gx, gy


def _combine_btn_rect(px: int, py: int) -> pygame.Rect:
    gx, gy  = _inv_grid_origin(px, py)
    grid_h  = _INV_ROWS * (_MINI_SZ + _MINI_GAP) - _MINI_GAP
    btn_y   = gy + grid_h + 8
    btn_w   = 160
    btn_x   = px + (POPUP_W - btn_w) // 2
    return pygame.Rect(btn_x, btn_y, btn_w, 34)


# ─── Public validation helper ─────────────────────────────────────────────────

def valid_for_slot(item_id: int, cs: int, mold_id: int | None = None) -> bool:
    """Return True if item_id is a valid candidate for combiner slot cs."""
    item = _get_item(item_id)
    ps   = item.get("part_stats", {})
    if cs == 0:
        return item_id in _MOLD_BASE
    if cs == 1:
        return ps.get("slot") in ("blade", "axe_head", "pick_head", "plate")
    if cs == 2:
        # Armor molds use a lining; weapon/tool molds use a handle or core.
        if mold_id in _ARMOR_MOLD_IDS:
            return ps.get("slot") == "lining"
        return ps.get("slot") in ("handle", "core")
    if cs == 3:
        return ps.get("slot") == "binding"
    return False


# ─── Preview computation ──────────────────────────────────────────────────────

def _derive_material(primary_item_id: int, req_p2_slot: str) -> str:
    """Return the material prefix from a primary part name (e.g. 'Steel')."""
    primary_name = _get_item(primary_item_id).get("name", "")
    suffix = _SLOT_NAME_SUFFIX.get(req_p2_slot, "")
    if suffix and primary_name.endswith(suffix):
        return primary_name[: -len(suffix)]
    return primary_name.split()[0] if primary_name else ""


def _derive_name(mold_id: int, primary_item_id: int, req_p2_slot: str) -> str:
    """Return a material-qualified name like 'Steel Pickaxe' or 'Obsidian Sword'."""
    material    = _derive_material(primary_item_id, req_p2_slot)
    weapon_type = _MOLD_HINT.get(mold_id, _get_item(_MOLD_BASE[mold_id][0]).get("name", ""))
    return f"{material} {weapon_type}" if material else weapon_type


def _compute_preview(inv: list, combiner_slots: list) -> dict | None:
    """
    Compute projected output stats.  Returns a dict or None if incomplete/invalid.
    """
    if any(cs is None for cs in combiner_slots):
        return None

    slots = []
    for idx in combiner_slots:
        if not (isinstance(idx, int) and 0 <= idx < 36):
            return None
        s = inv[idx]
        if s is None:
            return None
        slots.append(s)

    mold_id = slots[0][0]
    if mold_id not in _MOLD_BASE:
        return None

    base_id, is_armor = _MOLD_BASE[mold_id]
    req_p2 = _MOLD_SLOT2.get(mold_id, "")

    p2 = _get_item(slots[1][0]).get("part_stats", {})
    p3 = _get_item(slots[2][0]).get("part_stats", {})
    p4 = _get_item(slots[3][0]).get("part_stats", {})

    if p2.get("slot") != req_p2:
        return None
    # Armor molds use binding (lining) in slot 2; weapons/tools use handle or core
    if is_armor:
        if p3.get("slot") != "binding":
            return None
    else:
        if p3.get("slot") not in ("handle", "core"):
            return None
    if p4.get("slot") != "binding":
        return None

    dur = (
        p2.get("base_dur", 100)
        + p3.get("dur_bonus", 0)
        + p4.get("dur_bonus", 0)
    )
    spd = round(p3.get("speed_mult", 1.0) - 1.0, 3)

    if is_armor:
        stats: dict = {
            "defense":    p2.get("base_def", 0),
            "health_max": p2.get("base_hp", 0),
        }
    elif req_p2 == "pick_head":
        mining_dmg  = p2.get("base_mining", 0)
        mining_tier = p2.get("mining_tier", "pickaxe")
        stats = {"mining_damage": max(1, mining_dmg), "mining_tier": mining_tier}
    else:
        atk = p2.get("base_atk", 0) + p3.get("atk_bonus", 0)
        stats = {"attack_power": atk}

    if spd != 0.0:
        stats["speed_bonus"] = spd

    traits = list(dict.fromkeys(
        t for t in (p2.get("trait"), p3.get("trait"), p4.get("trait")) if t
    ))
    gem_slots = (
        p2.get("gem_slots", 0) + p3.get("gem_slots", 0) + p4.get("gem_slots", 0)
    )

    return {
        "name":      _derive_name(mold_id, slots[1][0], req_p2),
        "material":  _derive_material(slots[1][0], req_p2),
        "stats":     stats,
        "dur":       dur,
        "traits":    traits,
        "gem_slots": gem_slots,
        "base_id":   base_id,
    }


# ─── Main draw function ───────────────────────────────────────────────────────

def draw_combiner_popup(screen: pygame.Surface, ww: int, wh: int) -> None:
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

    title_s = fm.render("Part Combiner", True, _T.TITLE_TXT)
    screen.blit(title_s, (px + 10, py + (_TITLE_H - title_s.get_height()) // 2))
    hint_s = fs.render("[F / ESC to close]", True, _T.HINT_TXT)
    screen.blit(hint_s, (px + POPUP_W - hint_s.get_width() - 8,
                          py + (_TITLE_H - hint_s.get_height()) // 2))

    # ── Combiner input slots ──────────────────────────────────────────────────
    slot_rects = _slot_rects(px, py)
    art_sz = _SLOT_SZ - 8

    # Dynamic labels depend on whether an armor or weapon mold is active
    mold_slot_idx = config.combiner_slots[0]
    _active_mold_id: int | None = (
        config.player_inventory[mold_slot_idx][0]
        if mold_slot_idx is not None
        and 0 <= mold_slot_idx < 36
        and config.player_inventory[mold_slot_idx] is not None
        else None
    )
    _active_labels = _slot_labels_for_mold(_active_mold_id)

    for i, (label, rect) in enumerate(zip(_active_labels, slot_rects)):
        inv_idx  = config.combiner_slots[i]
        selected = (config.combiner_selected_slot == i)

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
                if slot[1] > 1:
                    qty_s = fs.render(str(slot[1]), True, (255, 255, 255))
                    screen.blit(qty_s, (rect.x + 2, rect.bottom - qty_s.get_height() - 2))
        else:
            ph = fm.render("?", True, (78, 78, 98))
            screen.blit(ph, (rect.centerx - ph.get_width() // 2,
                              rect.centery - ph.get_height() // 2))

        lbl_s = fs.render(label, True, _T.LABEL_TXT)
        screen.blit(lbl_s, (rect.centerx - lbl_s.get_width() // 2, rect.bottom + 2))

    # ── Preview panel ──────────────────────────────────────────────────────────
    pr = _preview_rect(px, py)
    pygame.draw.rect(screen, _T.SUB_BG,  pr, border_radius=3)
    pygame.draw.rect(screen, _T.BORDER, pr, 1, border_radius=3)

    preview = _compute_preview(config.player_inventory, config.combiner_slots)
    lx, ly  = pr.x + 8, pr.y + 6

    if preview is None:
        # Build contextual hint
        mold_idx = config.combiner_slots[0]
        if (mold_idx is not None and 0 <= mold_idx < 36
                and config.player_inventory[mold_idx] is not None):
            mid      = config.player_inventory[mold_idx][0]
            s2type   = _MOLD_SLOT2.get(mid, "?").replace("_", " ").title()
            wname    = _MOLD_HINT.get(mid, "")
            if mid in _ARMOR_MOLD_IDS:
                lines = [
                    f"{wname} Mold  →  slot 2 needs a {s2type}",
                    "Slot 3: binding (lining)     Slot 4: binding",
                ]
            else:
                lines = [
                    f"{wname} Mold selected  \u2192  slot 2 needs a {s2type}",
                    "Slot 3: handle or core     Slot 4: binding",
                ]
        else:
            lines = ["Fill all 4 slots to preview the output item."]
        for line in lines:
            s = fs.render(line, True, (145, 135, 165))
            screen.blit(s, (lx, ly))
            ly += 16
    else:
        # Draw tinted item icon on the left of the preview panel
        icon_sz  = 48
        icon_x   = pr.x + 6
        icon_y   = pr.y + (pr.height - icon_sz) // 2
        mat      = preview.get("material", "")
        base_id  = preview["base_id"]
        if mat:
            from rendering.item_art import draw_item_tinted
            draw_item_tinted(screen, icon_x, icon_y, icon_sz, base_id, mat)
        else:
            screen.blit(_get_art(base_id, icon_sz), (icon_x, icon_y))
        lx = icon_x + icon_sz + 6

        name_s = fm.render(preview["name"], True, (240, 230, 255))
        screen.blit(name_s, (lx, ly))
        ly += 18

        stat_parts = []
        s = preview["stats"]
        if "attack_power" in s:
            stat_parts.append(f"ATK {s['attack_power']}")
        if "mining_damage" in s:
            stat_parts.append(f"Mining {s['mining_damage']}")
        if "mining_tier" in s:
            tier_label = s["mining_tier"].replace("_", " ").title()
            stat_parts.append(f"Tier: {tier_label}")
        if "defense" in s:
            stat_parts.append(f"DEF {s['defense']}")
        if "health_max" in s:
            stat_parts.append(f"HP+ {s['health_max']}")
        if "speed_bonus" in s:
            spd_v = s["speed_bonus"]
            stat_parts.append(f"SPD {'+' if spd_v >= 0 else ''}{spd_v:.2f}")
        stat_parts.append(f"DUR {preview['dur']}")
        if preview["gem_slots"] > 0:
            stat_parts.append(f"Gems {preview['gem_slots']}")
        stat_s = fs.render("  ".join(stat_parts), True, (190, 255, 185))
        screen.blit(stat_s, (lx, ly))
        ly += 14

        if preview["traits"]:
            tr_s = fs.render("Traits: " + ", ".join(preview["traits"]), True, (255, 210, 120))
            screen.blit(tr_s, (lx, ly))

    # ── Inventory section header ────────────────────────────────────────────────
    pr2      = _preview_rect(px, py)
    hint_txt = (
        f"Click a slot above to select, then click an item below"
        if config.combiner_selected_slot == -1
        else f"Click an item to fill '{_active_labels[config.combiner_selected_slot]}'"
    )
    hint2_s = fs.render(hint_txt, True, (120, 118, 138))
    screen.blit(hint2_s, (px + _PAD, pr2.bottom + 4))

    # ── Mini inventory grid ────────────────────────────────────────────────────
    gx, gy   = _inv_grid_origin(px, py)
    mpos     = pygame.mouse.get_pos()

    for row in range(_INV_ROWS):
        for col in range(_INV_COLS):
            idx = row * _INV_COLS + col
            if idx >= 36:
                break
            sx = gx + col * (_MINI_SZ + _MINI_GAP)
            sy = gy + row * (_MINI_SZ + _MINI_GAP)
            r  = pygame.Rect(sx, sy, _MINI_SZ, _MINI_SZ)

            slot       = config.player_inventory[idx]
            in_combiner = idx in config.combiner_slots
            hovering   = r.collidepoint(mpos)

            if in_combiner:
                bg_m, bd_m = (44, 40, 58), (98, 88, 128)
            elif hovering:
                bg_m, bd_m = (45, 44, 60), (185, 185, 255)
            else:
                bg_m, bd_m = (32, 32, 42), (78, 78, 98)

            pygame.draw.rect(screen, bg_m, r, border_radius=2)
            pygame.draw.rect(screen, bd_m, r, 1, border_radius=2)

            if slot is not None:
                art = _get_art(slot[0], _MINI_SZ - 4)
                screen.blit(art, (sx + 2, sy + 2))
                if slot[1] > 1:
                    q = fs.render(str(slot[1]), True, (255, 255, 255))
                    screen.blit(q, (sx + 2, sy + _MINI_SZ - q.get_height() - 1))

    # ── COMBINE button ─────────────────────────────────────────────────────────
    btn        = _combine_btn_rect(px, py)
    can_combine = preview is not None
    if can_combine:
        btn_bg, btn_bd, btn_tc = _T.BTN_BG, _T.BTN_BD, (255, 255, 255)
    else:
        btn_bg, btn_bd, btn_tc = _T.BTN_DIS_BG, _T.BTN_DIS_BD, _T.BTN_DIS_TX

    pygame.draw.rect(screen, btn_bg, btn, border_radius=5)
    pygame.draw.rect(screen, btn_bd, btn, 2, border_radius=5)
    lbl = fm.render("COMBINE", True, btn_tc)
    screen.blit(lbl, (btn.centerx - lbl.get_width() // 2,
                       btn.centery - lbl.get_height() // 2))

    # ── Tooltips for combiner input slots ──────────────────────────────────────
    from rendering.inventory import _draw_tooltip
    for i, rect in enumerate(slot_rects):
        if rect.collidepoint(mpos):
            inv_idx = config.combiner_slots[i]
            if inv_idx is not None and 0 <= inv_idx < 36:
                slot = config.player_inventory[inv_idx]
                if slot is not None:
                    _draw_tooltip(screen, slot, mpos[0], mpos[1], ww, wh)
            break


# ─── Hit testing ──────────────────────────────────────────────────────────────

def combiner_popup_hit(
    mx: int, my: int, ww: int, wh: int
) -> tuple[str, int | None]:
    """
    Returns (kind, value):
      ("outside",       None)       — click outside popup
      ("combiner_slot", 0-3)        — click on input slot
      ("inv_slot",      0-35)       — click on mini-inventory slot
      ("combine",       None)       — click on COMBINE button
    """
    px, py = _popup_origin(ww, wh)
    if not pygame.Rect(px, py, POPUP_W, POPUP_H).collidepoint(mx, my):
        return ("outside", None)

    for i, rect in enumerate(_slot_rects(px, py)):
        if rect.collidepoint(mx, my):
            return ("combiner_slot", i)

    if _combine_btn_rect(px, py).collidepoint(mx, my):
        return ("combine", None)

    gx, gy = _inv_grid_origin(px, py)
    for row in range(_INV_ROWS):
        for col in range(_INV_COLS):
            idx = row * _INV_COLS + col
            if idx >= 36:
                break
            sx = gx + col * (_MINI_SZ + _MINI_GAP)
            sy = gy + row * (_MINI_SZ + _MINI_GAP)
            if pygame.Rect(sx, sy, _MINI_SZ, _MINI_SZ).collidepoint(mx, my):
                return ("inv_slot", idx)

    return ("inside", None)

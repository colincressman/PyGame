# client/rendering/controls_settings.py
"""Controls rebinding screen — opened from the pause menu."""
import pygame

import config
from rendering import ui_theme as _T

_PANEL_W = 440
_ROW_H   = 28
_DIV_H   = 10
_KEY_W   = 130
_PAD     = 16
_BTN_H   = 36

# (action_key, display_label) — (None, None) = horizontal divider
_ACTIONS = [
    ("move_up",    "Move Up"),
    ("move_down",  "Move Down"),
    ("move_left",  "Move Left"),
    ("move_right", "Move Right"),
    (None,         None),
    ("sprint",     "Sprint"),
    ("crouch",     "Crouch / Sneak"),
    ("roll",       "Dodge Roll"),
    (None,         None),
    ("inventory",  "Inventory"),
    ("interact",   "Interact / Station"),
    ("door",       "Open / Close Door"),
    ("map",        "Map"),
    ("stats",      "Stats"),
    (None,         None),
    ("attack",     "Attack"),
    ("block",      "Block / Parry"),
]

# Fixed rows shown at the bottom — not rebindable
_FIXED: list = []

_font_title: pygame.font.Font | None = None
_font_row:   pygame.font.Font | None = None
_font_key:   pygame.font.Font | None = None


def _fonts():
    global _font_title, _font_row, _font_key
    if _font_title is None:
        _font_title = pygame.font.SysFont("Arial", 20, bold=True)
        _font_row   = pygame.font.SysFont("Arial", 16)
        _font_key   = pygame.font.SysFont("Arial", 13, bold=True)
    return _font_title, _font_row, _font_key


def _key_label(k: int) -> str:
    """Convert a key constant to a short display string.

    Sentinels: -1 = LMB, -2 = RMB, 0 = unbound.
    """
    if k == -1:
        return "LMB"
    if k == -2:
        return "RMB"
    if k <= 0:
        return "---"
    name = pygame.key.name(k)
    if len(name) == 1:
        return name.upper()
    _remap = {
        "space":       "SPACE",
        "left shift":  "L.SHIFT",
        "right shift": "R.SHIFT",
        "left ctrl":   "L.CTRL",
        "right ctrl":  "R.CTRL",
        "left alt":    "L.ALT",
        "right alt":   "R.ALT",
        "up":          "UP",
        "down":        "DOWN",
        "left":        "LEFT",
        "right":       "RIGHT",
        "return":      "ENTER",
        "escape":      "ESC",
        "backspace":   "BKSP",
        "tab":         "TAB",
        "caps lock":   "CAPS",
    }
    return _remap.get(name.lower(), name.upper()[:9])


def _panel_height() -> int:
    content_h = 0
    for key, _ in _ACTIONS:
        content_h += _DIV_H if key is None else _ROW_H
    content_h += _DIV_H                    # divider before fixed section
    content_h += len(_FIXED) * _ROW_H
    return _T.TITLE_H + _PAD + content_h + _PAD + _BTN_H + _PAD


def draw_controls(screen: pygame.Surface, ww: int, wh: int,
                  clicked_pos) -> str | None:
    """Draw the controls rebinding panel.

    Returns
    -------
    'close'           — Close button was pressed
    'listen:<action>' — A key button was clicked; caller should start listening
    None              — Nothing actionable happened this frame
    """
    font_t, font_r, font_k = _fonts()
    panel_h = _panel_height()
    px = ww // 2 - _PANEL_W // 2
    py = wh // 2 - panel_h // 2

    # Dimmed backdrop
    overlay = pygame.Surface((ww, wh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, _T.OVERLAY_ALPHA))
    screen.blit(overlay, (0, 0))

    # Panel background
    bg = pygame.Surface((_PANEL_W, panel_h), pygame.SRCALPHA)
    bg.fill(_T.BG_FILL + (_T.BG_ALPHA,))
    screen.blit(bg, (px, py))
    pygame.draw.rect(screen, _T.BORDER, (px, py, _PANEL_W, panel_h), 2,
                     border_radius=_T.RADIUS)

    # Title bar
    pygame.draw.rect(screen, _T.TITLE_BAR, (px, py, _PANEL_W, _T.TITLE_H),
                     border_top_left_radius=_T.RADIUS,
                     border_top_right_radius=_T.RADIUS)
    ts = font_t.render("CONTROLS", True, _T.TITLE_TXT)
    screen.blit(ts, (ww // 2 - ts.get_width() // 2,
                     py + (_T.TITLE_H - ts.get_height()) // 2))

    result = None
    mx, my = pygame.mouse.get_pos()
    ry = py + _T.TITLE_H + _PAD

    # ── Rebindable rows ───────────────────────────────────────────────────────
    for action, label in _ACTIONS:
        if action is None:
            # Divider
            pygame.draw.line(screen, _T.DIVIDER,
                             (px + _PAD, ry + _DIV_H // 2),
                             (px + _PANEL_W - _PAD, ry + _DIV_H // 2), 1)
            ry += _DIV_H
            continue

        listening = config.controls_listen == action

        # Row label
        lc = (255, 220, 60) if listening else _T.TITLE_TXT
        ls = font_r.render(label, True, lc)
        screen.blit(ls, (px + _PAD, ry + (_ROW_H - ls.get_height()) // 2))

        # Key button
        kx       = px + _PANEL_W - _PAD - _KEY_W
        key_rect = pygame.Rect(kx, ry + 2, _KEY_W, _ROW_H - 4)
        hov      = key_rect.collidepoint(mx, my)

        if listening:
            kbd, bdc, ktc = (70, 60, 10), (255, 220, 60), (255, 220, 60)
            ktext = "Press a key\u2026"
        else:
            kbd   = _T.NAV_HOV if hov else _T.SLOT_BG
            bdc   = _T.SLOT_HOV if hov else _T.SLOT_BD
            ktc   = (220, 215, 195)
            ktext = _key_label(config.keybinds[action])

        pygame.draw.rect(screen, kbd, key_rect, border_radius=4)
        pygame.draw.rect(screen, bdc, key_rect, 1, border_radius=4)
        ks = font_k.render(ktext, True, ktc)
        screen.blit(ks, (key_rect.centerx - ks.get_width() // 2,
                         key_rect.centery - ks.get_height() // 2))

        if clicked_pos and key_rect.collidepoint(clicked_pos) and not listening:
            result = f"listen:{action}"

        ry += _ROW_H

    # ── Divider before fixed section ─────────────────────────────────────────
    pygame.draw.line(screen, _T.DIVIDER,
                     (px + _PAD, ry + _DIV_H // 2),
                     (px + _PANEL_W - _PAD, ry + _DIV_H // 2), 1)
    ry += _DIV_H

    # ── Fixed (non-rebindable) rows ───────────────────────────────────────────
    for label, ktext in _FIXED:
        ls = font_r.render(label, True, _T.LABEL_TXT)
        screen.blit(ls, (px + _PAD, ry + (_ROW_H - ls.get_height()) // 2))

        kx       = px + _PANEL_W - _PAD - _KEY_W
        key_rect = pygame.Rect(kx, ry + 2, _KEY_W, _ROW_H - 4)
        pygame.draw.rect(screen, _T.SLOT_BG, key_rect, border_radius=4)
        pygame.draw.rect(screen, _T.SLOT_BD, key_rect, 1, border_radius=4)
        ks = font_k.render(ktext, True, _T.HINT_TXT)
        screen.blit(ks, (key_rect.centerx - ks.get_width() // 2,
                         key_rect.centery - ks.get_height() // 2))
        ry += _ROW_H

    # ── Close button ─────────────────────────────────────────────────────────
    close_w    = 160
    close_rect = pygame.Rect(ww // 2 - close_w // 2, ry + _PAD, close_w, _BTN_H)
    hov        = close_rect.collidepoint(mx, my)
    pygame.draw.rect(screen, _T.NAV_HOV if hov else _T.NAV_BG, close_rect,
                     border_radius=_T.RADIUS)
    pygame.draw.rect(screen, _T.NAV_BD, close_rect, 2, border_radius=_T.RADIUS)
    cs = font_r.render("Close", True, _T.BTN_TXT)
    screen.blit(cs, (ww // 2 - cs.get_width() // 2,
                     close_rect.centery - cs.get_height() // 2))

    if clicked_pos and close_rect.collidepoint(clicked_pos):
        result = "close"

    return result

"""client/rendering/char_creator.py

Character customisation screen.

Sections (scrollable panel, 520×580 px):
  • Body type toggle   (male / female / muscular / teen)
  • Hair style grid    (all styles listed alphabetically, 4 per row)
  • Wing type selector (None + 7 types)
  • Wing colour grid
  • Aura selector      (None + 5 types)

Confirm button sends {"type": "update_appearance", "appearance": {...}} to server
and closes the screen.  Changes are also applied locally immediately.
"""
import pygame
import config

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
PANEL_W = 540
PANEL_H = 600
_PAD    = 10
_ROW_H  = 30
_BTN_H  = 28
_SEC_H  = 22      # section header height

_FONT:      pygame.font.Font | None = None
_FONT_HDR:  pygame.font.Font | None = None
_FONT_TINY: pygame.font.Font | None = None


def _ensure_fonts() -> None:
    global _FONT, _FONT_HDR, _FONT_TINY
    if _FONT is None:
        _FONT_HDR  = pygame.font.SysFont("Arial", 14, bold=True)
        _FONT      = pygame.font.SysFont("Arial", 12)
        _FONT_TINY = pygame.font.SysFont("Arial", 10)


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
_BODY_OPTIONS = ["male", "female", "muscular", "teen"]

_HAIR_STYLES = [
    "plain", "long", "bangs", "bob", "ponytail", "pigtails",
    "curly_short", "curly_long", "afro", "buzzcut", "pixie",
    "messy", "wavy", "braid", "cornrows", "dreadlocks_short",
    "shorthawk", "longhawk", "spiked", "natural",
]

_WING_TYPES = [None, "feathered", "bat", "pixie", "lunar", "monarch", "dragonfly", "lizard"]
_WING_COLOURS = [
    "white", "black", "ash", "gray", "dark_gray",
    "blonde", "gold", "orange", "carrot", "red",
    "blue", "green", "purple", "pink", "brown",
]

_AURA_OPTIONS = [None, "fire", "ice", "golden", "shadow", "rainbow"]

# ---------------------------------------------------------------------------
# Scroll state
# ---------------------------------------------------------------------------
_scroll_y: int = 0
_MAX_SCROLL = 600   # will be updated after draw


def close_char_creator() -> None:
    config.show_char_creator = False


# ---------------------------------------------------------------------------
# Handle click (called from handle_events in controls.py)
# ---------------------------------------------------------------------------
def handle_click(mx: int, my: int, screen: pygame.Surface) -> None:
    sw, sh = screen.get_size()
    px = (sw - PANEL_W) // 2
    py = (sh - PANEL_H) // 2
    lx, ly = mx - px, my - py
    if not (0 <= lx < PANEL_W and 0 <= ly < PANEL_H):
        return

    # Close button
    if PANEL_W - 26 <= lx <= PANEL_W - 6 and 5 <= ly <= 25:
        close_char_creator()
        return

    # Confirm button — bottom of panel
    confirm_y = PANEL_H - 40
    if _PAD <= lx <= PANEL_W - _PAD and confirm_y <= ly <= confirm_y + _BTN_H + 4:
        _send_appearance()
        close_char_creator()
        return

    # Convert ly to content-space using scroll
    global _scroll_y
    cy = ly + _scroll_y
    _dispatch_click(lx, cy)


def _send_appearance() -> None:
    config.state_outbox.put({
        "type":       "update_appearance",
        "appearance": dict(config.player_appearance),
    })


def _dispatch_click(lx: int, cy: int) -> None:
    """Handle a click at content-space (lx, cy)."""
    app = config.player_appearance
    y   = _PAD

    # --- Body type ---
    y += _SEC_H + 4
    cell_w = (PANEL_W - _PAD * 2) // len(_BODY_OPTIONS)
    if y <= cy <= y + _BTN_H:
        col = (lx - _PAD) // cell_w
        if 0 <= col < len(_BODY_OPTIONS):
            app["body"] = _BODY_OPTIONS[col]
    y += _BTN_H + 8

    # --- Hair style ---
    y += _SEC_H + 4
    cols, cell = 5, (PANEL_W - _PAD * 2) // 5
    rows_hair = (len(_HAIR_STYLES) + cols - 1) // cols
    hair_h = rows_hair * (_BTN_H + 2)
    if y <= cy <= y + hair_h:
        col_i = (lx - _PAD) // cell
        row_i = (cy - y) // (_BTN_H + 2)
        idx   = row_i * cols + col_i
        if 0 <= idx < len(_HAIR_STYLES):
            app["hair_style"] = _HAIR_STYLES[idx]
    y += hair_h + 8

    # --- Wing type ---
    y += _SEC_H + 4
    cell_w2 = (PANEL_W - _PAD * 2) // 4
    rows_wing = (len(_WING_TYPES) + 3) // 4
    wing_h = rows_wing * (_BTN_H + 2)
    if y <= cy <= y + wing_h:
        col_i = (lx - _PAD) // cell_w2
        row_i = (cy - y) // (_BTN_H + 2)
        idx   = row_i * 4 + col_i
        if 0 <= idx < len(_WING_TYPES):
            app["back_ext"] = _WING_TYPES[idx]
    y += wing_h + 8

    # --- Wing colour ---
    y += _SEC_H + 4
    cell_wc = (PANEL_W - _PAD * 2) // 5
    rows_wc = (len(_WING_COLOURS) + 4) // 5
    wc_h = rows_wc * (_BTN_H + 2)
    if y <= cy <= y + wc_h:
        col_i = (lx - _PAD) // cell_wc
        row_i = (cy - y) // (_BTN_H + 2)
        idx   = row_i * 5 + col_i
        if 0 <= idx < len(_WING_COLOURS):
            app["back_ext_color"] = _WING_COLOURS[idx]
    y += wc_h + 8

    # --- Aura ---
    y += _SEC_H + 4
    cell_wa = (PANEL_W - _PAD * 2) // len(_AURA_OPTIONS)
    if y <= cy <= y + _BTN_H:
        col_i = (lx - _PAD) // cell_wa
        if 0 <= col_i < len(_AURA_OPTIONS):
            app["aura"] = _AURA_OPTIONS[col_i]


# ---------------------------------------------------------------------------
# Scroll handling (called from handle_events in controls.py)
# ---------------------------------------------------------------------------
def handle_scroll(dy: int) -> None:
    global _scroll_y
    _scroll_y = max(0, min(_scroll_y - dy * 20, _MAX_SCROLL))


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def draw_char_creator(screen: pygame.Surface) -> None:
    global _scroll_y, _MAX_SCROLL
    _ensure_fonts()
    app = config.player_appearance

    sw, sh = screen.get_size()
    px = (sw - PANEL_W) // 2
    py = (sh - PANEL_H) // 2

    panel = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
    panel.fill((20, 20, 30, 235))
    pygame.draw.rect(panel, (100, 120, 200), (0, 0, PANEL_W, PANEL_H), 2)

    title_s = _FONT_HDR.render("Character Appearance", True, (180, 200, 255))
    panel.blit(title_s, (_PAD, 6))

    # Close button
    pygame.draw.rect(panel, (160, 50, 50), (PANEL_W - 26, 5, 20, 20))
    panel.blit(_FONT.render("X", True, (255, 255, 255)), (PANEL_W - 22, 7))

    # Confirm button at bottom (always visible, not scrolled)
    confirm_rect = pygame.Rect(_PAD, PANEL_H - 40, PANEL_W - _PAD * 2, _BTN_H + 4)
    pygame.draw.rect(panel, (60, 140, 60), confirm_rect)
    pygame.draw.rect(panel, (100, 200, 100), confirm_rect, 1)
    conf_s = _FONT_HDR.render("Confirm & Apply", True, (200, 255, 200))
    panel.blit(conf_s, (confirm_rect.centerx - conf_s.get_width() // 2,
                        confirm_rect.centery - conf_s.get_height() // 2))

    # Scrollable content area
    content_h = PANEL_H - 55 - 45   # header + confirm btn
    content_rect = pygame.Rect(0, 30, PANEL_W, content_h)
    content_surf = pygame.Surface((PANEL_W, 900), pygame.SRCALPHA)
    content_surf.fill((0, 0, 0, 0))

    y = _PAD

    def _section(label: str) -> None:
        nonlocal y
        s = _FONT_HDR.render(label, True, (140, 160, 220))
        content_surf.blit(s, (_PAD, y))
        y += _SEC_H + 4

    def _option_btn(lbl: str, selected: bool, rx: int, ry: int, rw: int, rh: int) -> None:
        bg  = (70, 80, 140) if selected else (40, 40, 60)
        brd = (140, 160, 255) if selected else (70, 70, 90)
        pygame.draw.rect(content_surf, bg,  (rx, ry, rw, rh))
        pygame.draw.rect(content_surf, brd, (rx, ry, rw, rh), 1)
        ts = _FONT_TINY.render(lbl, True, (230, 230, 255))
        content_surf.blit(ts, (rx + max(2, (rw - ts.get_width()) // 2),
                               ry + (rh - ts.get_height()) // 2))

    # Body type
    _section("Body Type")
    cell_w = (PANEL_W - _PAD * 2) // len(_BODY_OPTIONS)
    for i, b in enumerate(_BODY_OPTIONS):
        _option_btn(b, app["body"] == b,
                    _PAD + i * cell_w, y, cell_w - 2, _BTN_H)
    y += _BTN_H + 8

    # Hair style
    _section("Hair Style")
    cols = 5
    cell = (PANEL_W - _PAD * 2) // cols
    for i, hs in enumerate(_HAIR_STYLES):
        col_i = i % cols
        row_i = i // cols
        _option_btn(hs.replace("_", " "), app["hair_style"] == hs,
                    _PAD + col_i * cell, y + row_i * (_BTN_H + 2), cell - 2, _BTN_H)
    y += ((len(_HAIR_STYLES) + cols - 1) // cols) * (_BTN_H + 2) + 8

    # Wing type
    _section("Back Extension (Wings)")
    cols2 = 4
    cell2 = (PANEL_W - _PAD * 2) // cols2
    for i, wt in enumerate(_WING_TYPES):
        col_i = i % cols2
        row_i = i // cols2
        lbl = "none" if wt is None else wt
        _option_btn(lbl, app["back_ext"] == wt,
                    _PAD + col_i * cell2, y + row_i * (_BTN_H + 2), cell2 - 2, _BTN_H)
    y += ((len(_WING_TYPES) + cols2 - 1) // cols2) * (_BTN_H + 2) + 8

    # Wing colour
    _section("Wing Colour")
    cols3 = 5
    cell3 = (PANEL_W - _PAD * 2) // cols3
    for i, wc in enumerate(_WING_COLOURS):
        col_i = i % cols3
        row_i = i // cols3
        _option_btn(wc, app["back_ext_color"] == wc,
                    _PAD + col_i * cell3, y + row_i * (_BTN_H + 2), cell3 - 2, _BTN_H)
    y += ((len(_WING_COLOURS) + cols3 - 1) // cols3) * (_BTN_H + 2) + 8

    # Aura
    _section("Aura Effect")
    cell_a = (PANEL_W - _PAD * 2) // len(_AURA_OPTIONS)
    for i, au in enumerate(_AURA_OPTIONS):
        lbl = "none" if au is None else au
        _option_btn(lbl, app["aura"] == au,
                    _PAD + i * cell_a, y, cell_a - 2, _BTN_H)
    y += _BTN_H + 8

    _MAX_SCROLL = max(0, y - content_h)
    _scroll_y   = min(_scroll_y, _MAX_SCROLL)

    clipped = content_surf.subsurface(pygame.Rect(0, _scroll_y, PANEL_W, content_h))
    panel.blit(clipped, (0, 30))

    # Scrollbar
    if _MAX_SCROLL > 0:
        bar_h  = max(20, int(content_h * content_h / (content_h + _MAX_SCROLL)))
        bar_y  = 30 + int(_scroll_y / _MAX_SCROLL * (content_h - bar_h))
        pygame.draw.rect(panel, (80, 80, 110), (PANEL_W - 6, bar_y, 4, bar_h))

    screen.blit(panel, (px, py))

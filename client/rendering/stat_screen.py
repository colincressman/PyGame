# client/rendering/stat_screen.py
"""Character stats / stat-point allocation screen  (open with [C])."""
import pygame
from rendering import ui_theme as _T
import config

_font_title = None
_font_body  = None
_font_small = None

_PANEL_W = 400
_PANEL_H = 484   # 7 rows × 44 + header space
_ROW_H   = 44
_BTN_W   = 38
_BTN_H   = 30

# (stat_key sent to server, display name, value getter, per-point bonus label)
_STATS = [
    ("health_max",     "Max Health",  lambda: config.player_health_max,                       "+20 HP"),
    ("stamina_max",    "Max Stamina", lambda: config.player_stamina_max,                      "+20 SP"),
    ("speed_bonus",    "Speed",       lambda: config.PLAYER_SPEED + config.player_speed_bonus, "+0.5 spd"),
    ("attack_power",   "Attack",      lambda: config.player_attack_power,                     "+2 atk"),
    ("hp_regen",       "HP Regen",    lambda: config.player_hp_regen,                         "+0.5/s"),
    ("sp_regen_bonus", "SP Regen",    lambda: 10.0 + config.player_sp_regen_bonus,            "+2/s"),
    (None,             "Defense",     lambda: config.player_defense,                           None),   # display-only
]


def _fonts():
    global _font_title, _font_body, _font_small
    if _font_title is None:
        _font_title = pygame.font.SysFont("Arial", 26, bold=True)
        _font_body  = pygame.font.SysFont("Arial", 19)
        _font_small = pygame.font.SysFont("Arial", 13)
    return _font_title, _font_body, _font_small


def draw_stat_screen(screen: pygame.Surface, window_width: int, window_height: int,
                     clicked_pos=None) -> str | None:
    """Draw the character stat-allocation screen.

    Parameters
    ----------
    clicked_pos : (x, y) or None
        Mouse position of a left-click this frame (from config.stat_click_pos).

    Returns
    -------
    'spend:<stat_key>'  — player clicked a + button (e.g. 'spend:health_max')
    None                — nothing actionable
    """
    font_t, font_b, font_s = _fonts()

    # Semi-transparent overlay
    overlay = pygame.Surface((window_width, window_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, _T.OVERLAY_ALPHA))
    screen.blit(overlay, (0, 0))

    # Panel background
    px = (window_width  - _PANEL_W) // 2
    py = (window_height - _PANEL_H) // 2
    panel = pygame.Surface((_PANEL_W, _PANEL_H), pygame.SRCALPHA)
    panel.fill(_T.BG_FILL + (_T.BG_ALPHA,))
    screen.blit(panel, (px, py))
    pygame.draw.rect(screen, _T.BORDER, (px, py, _PANEL_W, _PANEL_H), 2, border_radius=_T.RADIUS)

    # Title bar
    pygame.draw.rect(screen, _T.TITLE_BAR, (px, py, _PANEL_W, _T.TITLE_H), border_top_left_radius=_T.RADIUS, border_top_right_radius=_T.RADIUS)

    # Title
    title = font_t.render("CHARACTER  [P]", True, _T.TITLE_TXT)
    screen.blit(title, (px + (_PANEL_W - title.get_width()) // 2, py + (_T.TITLE_H - title.get_height()) // 2))

    # Available stat points
    pts = config.player_stat_points
    pts_color = (255, 220, 60) if pts > 0 else (150, 150, 150)
    pts_surf  = font_b.render(f"Available stat points: {pts}", True, pts_color)
    screen.blit(pts_surf, (px + (_PANEL_W - pts_surf.get_width()) // 2, py + _T.TITLE_H + 20))

    # Separator
    sep_y = py + _T.TITLE_H + 50
    pygame.draw.line(screen, _T.DIVIDER, (px + 16, sep_y), (px + _PANEL_W - 16, sep_y))

    # Stat rows
    row_start_y = sep_y + 8
    mx, my = pygame.mouse.get_pos()
    result = None

    for i, (stat_key, label, get_val, bonus_str) in enumerate(_STATS):
        ry       = row_start_y + i * _ROW_H
        row_mid  = ry + _ROW_H // 2

        # Stat name
        lbl_surf = font_b.render(label, True, _T.LABEL_TXT)
        screen.blit(lbl_surf, (px + 18, row_mid - lbl_surf.get_height() // 2))

        # Current value
        raw = get_val()
        val_str  = f"{raw:.1f}" if isinstance(raw, float) else str(int(raw))
        val_surf = font_b.render(val_str, True, (255, 255, 255))
        screen.blit(val_surf, (px + 186, row_mid - val_surf.get_height() // 2))

        if stat_key is None:
            # Display-only row (e.g. Defense) — no bonus label, no [+] button
            continue

        # Per-point bonus info
        bon_surf = font_s.render(bonus_str, True, (130, 200, 130))
        screen.blit(bon_surf, (px + 258, row_mid - bon_surf.get_height() // 2 + 1))

        # [+] button
        btn_x = px + _PANEL_W - _BTN_W - 14
        btn_y = row_mid - _BTN_H // 2
        btn_rect = pygame.Rect(btn_x, btn_y, _BTN_W, _BTN_H)
        can_spend = pts > 0
        hovered   = can_spend and btn_rect.collidepoint(mx, my)
        btn_bg    = _T.BTN_HOV if hovered else _T.BTN_BG if can_spend else _T.BTN_DIS_BG
        btn_border= _T.BTN_BD if can_spend else _T.BTN_DIS_BD
        pygame.draw.rect(screen, btn_bg,     btn_rect, border_radius=5)
        pygame.draw.rect(screen, btn_border, btn_rect, 2, border_radius=5)
        plus_col  = (255, 255, 255) if can_spend else (90, 90, 90)
        plus_surf = font_b.render("+", True, plus_col)
        screen.blit(plus_surf, (btn_rect.centerx - plus_surf.get_width() // 2,
                                btn_rect.centery - plus_surf.get_height() // 2))

        if clicked_pos and can_spend and btn_rect.collidepoint(clicked_pos):
            result = f"spend:{stat_key}"

    # Close hint
    hint = font_s.render("Press [P] or [ESC] to close", True, _T.HINT_TXT)
    screen.blit(hint, (px + (_PANEL_W - hint.get_width()) // 2, py + _PANEL_H - 24))

    return result

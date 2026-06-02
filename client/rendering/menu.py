# client/rendering/menu.py
"""In-game pause menu overlay."""
import pygame
from rendering import ui_theme as _T

_font_large = None
_font_small  = None

_PANEL_W = 320
_PANEL_H = 318
_BTN_W   = 220
_BTN_H   = 44
_BTN_GAP = 14


def _fonts():
    global _font_large, _font_small
    if _font_large is None:
        _font_large = pygame.font.SysFont("Arial", 36, bold=True)
        _font_small  = pygame.font.SysFont("Arial", 22)
    return _font_large, _font_small


def draw_menu(screen: pygame.Surface, window_width: int, window_height: int,
              clicked_pos=None) -> str | None:
    """Draw the pause menu overlay.

    Parameters
    ----------
    clicked_pos : (x, y) or None
        Mouse position of a left-click this frame (from config.menu_click_pos).

    Returns
    -------
    'resume'  — player pressed Resume
    'stats'   — player pressed Character Stats
    'quit'    — player pressed Quit to Menu
    None      — no button pressed
    """
    font_lg, font_sm = _fonts()

    # Semi-transparent dark overlay
    overlay = pygame.Surface((window_width, window_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, _T.OVERLAY_ALPHA))
    screen.blit(overlay, (0, 0))

    cx = window_width  // 2
    cy = window_height // 2
    px = cx - _PANEL_W // 2
    py = cy - _PANEL_H // 2

    panel = pygame.Surface((_PANEL_W, _PANEL_H), pygame.SRCALPHA)
    panel.fill(_T.BG_FILL + (_T.BG_ALPHA,))
    screen.blit(panel, (px, py))
    pygame.draw.rect(screen, _T.BORDER, (px, py, _PANEL_W, _PANEL_H), 2, border_radius=_T.RADIUS)
    pygame.draw.rect(screen, _T.TITLE_BAR, (px, py, _PANEL_W, _T.TITLE_H), border_top_left_radius=_T.RADIUS, border_top_right_radius=_T.RADIUS)

    # Title
    title = font_lg.render("PAUSED", True, _T.TITLE_TXT)
    screen.blit(title, (cx - title.get_width() // 2, py + (_T.TITLE_H - title.get_height()) // 2 - 1))

    buttons = [
        ("Resume",          "resume"),
        ("Character Stats", "stats"),
        ("Controls",        "controls"),
        ("Quit to Menu",    "quit"),
    ]

    result = None
    mx, my = pygame.mouse.get_pos()

    for i, (label, action) in enumerate(buttons):
        bx   = cx - _BTN_W // 2
        by   = py + _T.TITLE_H + 24 + i * (_BTN_H + _BTN_GAP)
        rect = pygame.Rect(bx, by, _BTN_W, _BTN_H)

        hovered = rect.collidepoint(mx, my)
        bg      = _T.NAV_HOV if hovered else _T.NAV_BG
        pygame.draw.rect(screen, bg, rect, border_radius=_T.RADIUS)
        pygame.draw.rect(screen, _T.NAV_BD, rect, 2, border_radius=_T.RADIUS)

        text = font_sm.render(label, True, _T.BTN_TXT)
        screen.blit(text, (cx - text.get_width() // 2,
                           by + (_BTN_H - text.get_height()) // 2))

        if clicked_pos and rect.collidepoint(clicked_pos):
            result = action

    # Hint
    hint_font = pygame.font.SysFont("Arial", 14)
    hint = hint_font.render("Press ESC to resume", True, _T.HINT_TXT)
    hint_y = py + _PANEL_H - hint.get_height() - 12
    screen.blit(hint, (cx - hint.get_width() // 2, hint_y))

    return result

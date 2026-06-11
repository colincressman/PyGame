"""Character creator focused on actual built-in appearance layers.

This screen intentionally excludes wings and aura cosmetics. Wings are now
equipment-driven, and aura/trail effects are not part of first-join setup.
"""

import pygame

import config
from rendering.player import (
    draw_appearance_preview,
    normalize_body_choice,
    normalize_hair_style_choice,
)


PANEL_W = 700
PANEL_H = 600
_PAD = 12
_HEADER_H = 34
_FOOTER_H = 54
_BTN_H = 32
_SEC_GAP = 12
_PREVIEW_W = 220

_FONT: pygame.font.Font | None = None
_FONT_HDR: pygame.font.Font | None = None
_FONT_TINY: pygame.font.Font | None = None


def _ensure_fonts() -> None:
    global _FONT, _FONT_HDR, _FONT_TINY
    if _FONT is None:
        _FONT_HDR = pygame.font.SysFont("Arial", 16, bold=True)
        _FONT = pygame.font.SysFont("Arial", 13)
        _FONT_TINY = pygame.font.SysFont("Arial", 11)


_BODY_OPTIONS = [
    ("male", "Male"),
    ("female", "Female"),
    ("muscular", "Muscular"),
    ("teen", "Teen"),
]
_HAIR_STYLES = [
    ("plain", "Plain"),
    ("long", "Long"),
    ("bangs", "Bangs"),
    ("bob", "Bob"),
    ("ponytail", "Ponytail"),
    ("pigtails", "Pigtails"),
    ("curly_short", "Curly Short"),
    ("curly_long", "Curly Long"),
    ("afro", "Afro"),
    ("buzzcut", "Buzzcut"),
    ("pixie", "Pixie"),
    ("messy1", "Messy"),
    ("wavy", "Wavy"),
    ("braid", "Braid"),
    ("cornrows", "Cornrows"),
    ("dreadlocks_short", "Dreadlocks"),
    ("shorthawk", "Shorthawk"),
    ("longhawk", "Longhawk"),
    ("spiked", "Spiked"),
    ("natural", "Natural"),
]

_BODY_RECTS: list[tuple[pygame.Rect, str]] = []
_HAIR_RECTS: list[tuple[pygame.Rect, str]] = []
_CONFIRM_RECT = pygame.Rect(0, 0, 0, 0)
_CLOSE_RECT = pygame.Rect(0, 0, 0, 0)
_draft_appearance: dict | None = None


def _normalized_appearance(source: dict | None = None) -> dict:
    current = dict(source or config.player_appearance)
    return {
        "body": normalize_body_choice(current.get("body", "male")),
        "hair_style": normalize_hair_style_choice(current.get("hair_style", "plain")),
        "hair_color": current.get("hair_color", "dark_brown"),
        "skin_tint": current.get("skin_tint"),
        "back_ext": None,
        "back_ext_color": "white",
        "aura": None,
    }


def _ensure_draft() -> dict:
    global _draft_appearance
    if _draft_appearance is None:
        _draft_appearance = _normalized_appearance()
    return _draft_appearance


def open_char_creator(reset_scroll: bool = True) -> None:
    global _draft_appearance
    _draft_appearance = _normalized_appearance()
    config.show_char_creator = True


def close_char_creator(reset_scroll: bool = True) -> None:
    global _draft_appearance
    if config.first_join_setup_required:
        return
    _draft_appearance = None
    config.show_char_creator = False


def toggle_char_creator() -> None:
    if config.first_join_setup_required:
        open_char_creator()
    elif config.show_char_creator:
        close_char_creator()
    else:
        open_char_creator()


def _send_appearance() -> None:
    appearance = dict(_ensure_draft())
    config.player_appearance.update(appearance)
    config.state_outbox.put({
        "type": "update_appearance",
        "appearance": appearance,
    })


def handle_click(mx: int, my: int, screen: pygame.Surface) -> None:
    sw, sh = screen.get_size()
    px = (sw - PANEL_W) // 2
    py = (sh - PANEL_H) // 2
    lx = mx - px
    ly = my - py
    if not (0 <= lx < PANEL_W and 0 <= ly < PANEL_H):
        return

    if _CLOSE_RECT.collidepoint(lx, ly):
        close_char_creator()
        return
    if _CONFIRM_RECT.collidepoint(lx, ly):
        _send_appearance()
        if not config.first_join_setup_required:
            close_char_creator()
        return

    draft = _ensure_draft()

    for rect, body in _BODY_RECTS:
        if rect.collidepoint(lx, ly):
            draft["body"] = body
            return

    for rect, hair_style in _HAIR_RECTS:
        if rect.collidepoint(lx, ly):
            draft["hair_style"] = hair_style
            return


def handle_scroll(dy: int) -> None:
    return


def _draw_option_btn(surface: pygame.Surface, rect: pygame.Rect, label: str, selected: bool) -> None:
    bg = (72, 90, 150) if selected else (42, 46, 64)
    border = (145, 175, 255) if selected else (88, 92, 118)
    pygame.draw.rect(surface, bg, rect, border_radius=6)
    pygame.draw.rect(surface, border, rect, 1, border_radius=6)
    text = _FONT.render(label, True, (235, 240, 255))
    surface.blit(text, text.get_rect(center=rect.center))


def draw_char_creator(screen: pygame.Surface) -> None:
    global _BODY_RECTS, _HAIR_RECTS, _CONFIRM_RECT, _CLOSE_RECT
    _ensure_fonts()

    appearance = _ensure_draft()

    sw, sh = screen.get_size()
    px = (sw - PANEL_W) // 2
    py = (sh - PANEL_H) // 2

    panel = pygame.Surface((PANEL_W, PANEL_H), pygame.SRCALPHA)
    panel.fill((18, 20, 30, 242))
    pygame.draw.rect(panel, (94, 125, 210), (0, 0, PANEL_W, PANEL_H), 2, border_radius=10)

    title = "Create Your Character" if config.first_join_setup_required else "Character Appearance"
    title_surf = _FONT_HDR.render(title, True, (214, 228, 255))
    panel.blit(title_surf, (_PAD, 8))
    subtitle = _FONT.render("Choose what the built-in sprite should look like.", True, (150, 165, 205))
    panel.blit(subtitle, (_PAD, 28))

    _CLOSE_RECT = pygame.Rect(PANEL_W - 30, 8, 20, 20)
    pygame.draw.rect(panel, (145, 58, 58), _CLOSE_RECT, border_radius=4)
    panel.blit(_FONT.render("X", True, (255, 255, 255)), (PANEL_W - 24, 10))

    preview_rect = pygame.Rect(_PAD, _HEADER_H + 12, _PREVIEW_W, PANEL_H - _HEADER_H - _FOOTER_H - 24)
    pygame.draw.rect(panel, (28, 32, 46), preview_rect, border_radius=8)
    pygame.draw.rect(panel, (82, 96, 132), preview_rect, 1, border_radius=8)
    preview_label = _FONT_HDR.render("Preview", True, (175, 195, 240))
    panel.blit(preview_label, (preview_rect.x + 10, preview_rect.y + 8))

    pedestal = pygame.Rect(preview_rect.x + 28, preview_rect.bottom - 46, preview_rect.width - 56, 16)
    pygame.draw.ellipse(panel, (38, 44, 64), pedestal)
    draw_appearance_preview(panel, preview_rect.centerx, preview_rect.centery + 26, appearance)

    info_lines = [
        "Wings are equipment now.",
        "Aura/trail effects are not part of skin setup.",
    ]
    for i, line in enumerate(info_lines):
        surf = _FONT_TINY.render(line, True, (156, 168, 196))
        panel.blit(surf, (preview_rect.x + 10, preview_rect.bottom - 76 + i * 14))

    controls_x = preview_rect.right + 18
    controls_w = PANEL_W - controls_x - _PAD
    y = _HEADER_H + 16

    body_hdr = _FONT_HDR.render("Body Type", True, (175, 195, 240))
    panel.blit(body_hdr, (controls_x, y))
    y += 28
    _BODY_RECTS = []
    body_cols = 2
    body_w = (controls_w - 8) // body_cols
    for index, (body, label) in enumerate(_BODY_OPTIONS):
        row = index // body_cols
        col = index % body_cols
        rect = pygame.Rect(controls_x + col * (body_w + 8), y + row * (_BTN_H + 8), body_w, _BTN_H)
        _BODY_RECTS.append((rect, body))
        _draw_option_btn(panel, rect, label, appearance["body"] == body)
    y += ((len(_BODY_OPTIONS) + body_cols - 1) // body_cols) * (_BTN_H + 8) + _SEC_GAP

    hair_hdr = _FONT_HDR.render("Hair Style", True, (175, 195, 240))
    panel.blit(hair_hdr, (controls_x, y))
    y += 28
    _HAIR_RECTS = []
    hair_cols = 3
    hair_w = (controls_w - (hair_cols - 1) * 8) // hair_cols
    for index, (hair_style, label) in enumerate(_HAIR_STYLES):
        row = index // hair_cols
        col = index % hair_cols
        rect = pygame.Rect(controls_x + col * (hair_w + 8), y + row * (_BTN_H + 6), hair_w, _BTN_H)
        _HAIR_RECTS.append((rect, hair_style))
        _draw_option_btn(
            panel,
            rect,
            label,
            appearance["hair_style"] == hair_style,
        )

    _CONFIRM_RECT = pygame.Rect(_PAD, PANEL_H - _FOOTER_H + 10, PANEL_W - _PAD * 2, 34)
    pygame.draw.rect(panel, (52, 126, 72), _CONFIRM_RECT, border_radius=6)
    pygame.draw.rect(panel, (110, 208, 140), _CONFIRM_RECT, 1, border_radius=6)
    confirm_label = "Save Character" if config.first_join_setup_required else "Apply Appearance"
    confirm_surf = _FONT_HDR.render(confirm_label, True, (228, 255, 232))
    panel.blit(confirm_surf, confirm_surf.get_rect(center=_CONFIRM_RECT.center))

    screen.blit(panel, (px, py))

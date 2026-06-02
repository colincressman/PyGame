"""
chat.py — Minecraft-style chat overlay.

Layout (bottom-left corner):
  • When chat_open is False: show last CHAT_DISPLAY messages, fading out after
    FADE_START seconds each.
  • When chat_open is True: show message history + a text-input box at the bottom.

The caller (client.py) must import draw_chat and call it every frame AFTER all
world rendering so it sits on top.
"""
import time
import pygame
import config

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
MARGIN_X   = 8          # distance from left edge of screen
MARGIN_Y   = 8          # distance from bottom edge of screen
BOX_W      = 420        # width of the chat history panel
LINE_H     = 18         # height of one message line
INPUT_H    = 24         # height of the text-input bar
BG_ALPHA   = 140        # chat history background alpha (0-255)
INPUT_BG   = (20, 20, 30, 200)
FADE_START = 8.0        # seconds before a passive message starts fading
FADE_FULL  = 10.0       # seconds at which alpha reaches 0

_SENDER_COLOR  = (100, 220, 255)
_TEXT_COLOR    = (240, 240, 240)
_CMD_COLOR     = (255, 200, 80)   # commands echo in gold
_SYS_COLOR     = (160, 220, 160)  # system messages in green
_CURSOR_COLOR  = (200, 200, 200)

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    global _font
    if _font is None:
        _font = pygame.font.SysFont("Arial", 13)
    return _font


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draw_chat(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    """Draw chat history and (if open) the input box."""
    font = _get_font()
    now  = time.time()

    display_msgs = config.chat_messages[-config.CHAT_DISPLAY:]

    n_lines = len(display_msgs)
    panel_h = n_lines * LINE_H + (6 if n_lines else 0)

    # Y position: panel sits just above the input box (or above hotbar area)
    input_y  = window_height - MARGIN_Y - INPUT_H
    panel_y  = input_y - panel_h - 2

    # ---- History background ----
    if n_lines:
        bg = pygame.Surface((BOX_W, panel_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, BG_ALPHA if config.chat_open else 80))
        screen.blit(bg, (MARGIN_X, panel_y))

    for i, msg in enumerate(display_msgs):
        age   = now - msg.get("ts", now)
        alpha = 255
        if not config.chat_open:
            if age >= FADE_FULL:
                continue
            if age >= FADE_START:
                fade = 1.0 - (age - FADE_START) / (FADE_FULL - FADE_START)
                alpha = max(0, int(255 * fade))

        ly = panel_y + i * LINE_H + 3
        sender = msg.get("sender", "")
        text   = msg.get("text", "")

        # Determine colour
        is_system = (sender == "" or sender == "SYSTEM")
        is_cmd    = text.startswith("/")

        if is_system:
            line_surf = font.render(text, True, _SYS_COLOR)
        elif is_cmd:
            line_surf = font.render(f"{sender}: {text}", True, _CMD_COLOR)
        else:
            # "Name: message" with sender in accent colour
            s_surf = font.render(f"{sender}: ", True, _SENDER_COLOR)
            t_surf = font.render(text, True, _TEXT_COLOR)
            combined = pygame.Surface(
                (s_surf.get_width() + t_surf.get_width(), LINE_H), pygame.SRCALPHA
            )
            combined.blit(s_surf, (0, 0))
            combined.blit(t_surf, (s_surf.get_width(), 0))
            combined.set_alpha(alpha)
            screen.blit(combined, (MARGIN_X + 4, ly))
            continue

        line_surf.set_alpha(alpha)
        screen.blit(line_surf, (MARGIN_X + 4, ly))

    # ---- Input box (only when open) ----
    if config.chat_open:
        box_rect = pygame.Rect(MARGIN_X, input_y, BOX_W, INPUT_H)
        # Background
        ib = pygame.Surface((BOX_W, INPUT_H), pygame.SRCALPHA)
        ib.fill(INPUT_BG)
        screen.blit(ib, (MARGIN_X, input_y))
        # Border
        pygame.draw.rect(screen, (120, 160, 200), box_rect, 1, border_radius=2)
        # Text
        display_text = config.chat_input
        txt_surf = font.render(display_text, True, _TEXT_COLOR)
        # Clip to box width
        clip_w = BOX_W - 12
        screen.blit(txt_surf, (MARGIN_X + 6, input_y + (INPUT_H - txt_surf.get_height()) // 2),
                    area=pygame.Rect(max(0, txt_surf.get_width() - clip_w), 0,
                                     clip_w, txt_surf.get_height()))
        # Blinking cursor
        if int(now * 2) % 2 == 0:
            cx = MARGIN_X + 6 + min(txt_surf.get_width(), clip_w)
            cy_top    = input_y + 4
            cy_bottom = input_y + INPUT_H - 4
            pygame.draw.line(screen, _CURSOR_COLOR, (cx, cy_top), (cx, cy_bottom))

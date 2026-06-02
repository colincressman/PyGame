"""client/rendering/npcs.py

Procedural NPC rendering.  NPCs are world-space entities (like mobs) and
plug into the y-sorted _draw_list in client.py via get_npc_drawables().
"""

import pygame
import config

TILE_SIZE  = 32
_SPRITE_W  = 20
_SPRITE_H  = 32

_INTERACT_DIST_SQ = 3.0 ** 2  # open shop within 3 tiles

# ── Per-type colour schemes ──────────────────────────────────────────────────
_SCHEME = {
    "merchant":   {"body": ( 35,  80, 200), "trim": (220, 180,  30), "skin": (215, 170, 130)},
    "blacksmith": {"body": ( 75,  55,  35), "trim": (160, 115,  40), "skin": (195, 145, 105)},
    "healer":     {"body": (220, 225, 255), "trim": (200,  55,  55), "skin": (225, 195, 160)},
    "innkeeper":  {"body": (145,  90,  50), "trim": (200, 155,  95), "skin": (210, 165, 120)},
}

_surf_cache: dict = {}
_font_name:  pygame.font.Font | None = None
_font_greet: pygame.font.Font | None = None

_GREET_DIST_SQ = 4.0 ** 2   # tile² — show greeting bubble within 4 tiles


def _make_surf(npc_type: str) -> pygame.Surface:
    s      = _SCHEME.get(npc_type, _SCHEME["merchant"])
    body_c = s["body"]
    trim_c = s["trim"]
    skin_c = s["skin"]

    surf = pygame.Surface((_SPRITE_W, _SPRITE_H), pygame.SRCALPHA)

    # Head
    pygame.draw.ellipse(surf, skin_c,  (6, 0, 8, 9))
    pygame.draw.circle(surf, (50, 35, 20), (9,  4), 1)
    pygame.draw.circle(surf, (50, 35, 20), (12, 4), 1)

    # Body (robe)
    pygame.draw.rect(surf, body_c, (3, 10, 14, 13), border_radius=2)
    # Trim stripe
    pygame.draw.rect(surf, trim_c, (3, 10, 3, 13),  border_radius=1)

    # Arms
    pygame.draw.rect(surf, body_c, (0, 11, 3, 9), border_radius=1)
    pygame.draw.rect(surf, body_c, (17, 11, 3, 9), border_radius=1)

    # Hands
    pygame.draw.circle(surf, skin_c, (1,  20), 2)
    pygame.draw.circle(surf, skin_c, (18, 20), 2)

    # Legs
    pygame.draw.rect(surf, body_c, (4,  23, 5, 9), border_radius=1)
    pygame.draw.rect(surf, body_c, (11, 23, 5, 9), border_radius=1)

    # Feet
    pygame.draw.rect(surf, (50, 40, 25), (3,  30, 6, 2))
    pygame.draw.rect(surf, (50, 40, 25), (11, 30, 6, 2))

    # Type-specific accents
    if npc_type == "merchant":
        # Wide-brim hat
        pygame.draw.rect(surf, (100, 70, 30), (5,  -1, 10, 3))
        pygame.draw.rect(surf, (100, 70, 30), (3,   1, 14, 2))
    elif npc_type == "blacksmith":
        # Hammer in right hand
        pygame.draw.rect(surf, (110, 110, 110), (17, 15, 3, 6))
        pygame.draw.rect(surf, ( 85,  85,  85), (15, 12, 6, 4))
    elif npc_type == "healer":
        # Red cross on robe
        pygame.draw.rect(surf, (215, 50, 50), (9,  12, 3, 9))
        pygame.draw.rect(surf, (215, 50, 50), (6,  15, 9, 3))
    elif npc_type == "innkeeper":
        # Mug in right hand
        pygame.draw.rect(surf, (185, 145, 70), (17, 16, 4, 5))
        pygame.draw.rect(surf, (145, 110, 50), (20, 17, 2, 3))

    return surf


def _get_surf(npc_type: str) -> pygame.Surface:
    if npc_type not in _surf_cache:
        _surf_cache[npc_type] = _make_surf(npc_type)
    return _surf_cache[npc_type]


def _ensure_fonts():
    global _font_name, _font_greet
    if _font_name is None:
        _font_name  = pygame.font.SysFont("Arial", 11, bold=True)
        _font_greet = pygame.font.SysFont("Arial", 10)


def get_npc_drawables(screen, npcs, player_pos, offset_x, offset_y):
    """
    Yield (sort_y, draw_fn) tuples for visible NPCs, compatible with the
    y-sorted _draw_list in client.py.

    Parameters
    ----------
    screen      : pygame.Surface
    npcs        : list of NPC dicts from config.npcs
    player_pos  : [px, py] in tile-space
    offset_x/y  : camera offsets (pixels)
    """
    if not npcs:
        return

    _ensure_fonts()
    px, py = player_pos

    for npc in npcs:
        wx, wy     = npc["pos"]
        sx         = int(wx * TILE_SIZE + offset_x + TILE_SIZE // 2 - _SPRITE_W // 2)
        sy         = int(wy * TILE_SIZE + offset_y + TILE_SIZE // 2 - _SPRITE_H + 2)
        sort_y     = wy + 1.0
        npc_type   = npc["type"]
        npc_name   = npc["name"]
        npc_greet  = npc.get("greeting", "")
        dpx, dpy   = wx - px, wy - py
        show_greet = (dpx * dpx + dpy * dpy) <= _GREET_DIST_SQ

        def _draw(_sx=sx, _sy=sy, _nt=npc_type, _name=npc_name,
                  _greet=npc_greet, _show=show_greet):
            surf = _get_surf(_nt)
            screen.blit(surf, (_sx, _sy))

            # Name label
            ns = _font_name.render(_name, True, (240, 235, 170))
            screen.blit(ns, (_sx + _SPRITE_W // 2 - ns.get_width() // 2,
                             _sy - ns.get_height() - 2))

            # Greeting bubble when close
            if _show:
                gs = _font_greet.render(_greet, True, (20, 20, 20))
                bw = gs.get_width() + 10
                bh = gs.get_height() + 6
                bx = _sx + _SPRITE_W // 2 - bw // 2
                by = _sy - ns.get_height() - bh - 4
                bubble = pygame.Surface((bw, bh), pygame.SRCALPHA)
                bubble.fill((255, 255, 255, 210))
                screen.blit(bubble, (bx, by))
                pygame.draw.rect(screen, (130, 130, 130),
                                 pygame.Rect(bx, by, bw, bh), 1, border_radius=3)
                screen.blit(gs, (bx + 5, by + 3))

        yield sort_y, _draw


def try_open_npc_shop(player_pos: list) -> bool:
    """Check if the player is within range of an NPC and open their shop.

    Called when the player presses the interact key (F).
    Returns True if a shop was opened.
    """
    px, py = player_pos
    for npc in config.npcs:
        wx, wy = npc["pos"]
        dx, dy = wx - px, wy - py
        if dx * dx + dy * dy <= _INTERACT_DIST_SQ:
            npc_type = npc.get("type", "")
            if npc_type in ("merchant", "blacksmith", "healer", "innkeeper"):
                config.show_shop      = True
                config.shop_npc_type  = npc_type
                config.shop_npc_id    = npc.get("id", "")
                config.shop_items     = npc.get("shop", [])
                config.shop_scroll    = 0
                config.shop_tab       = "buy"
                return True
    return False

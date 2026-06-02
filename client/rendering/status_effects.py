# client/rendering/status_effects.py
"""Client-side status effect overlays.

draw_status_effects(screen, w, h) draws a subtle pulsing tint for each active
debuff.  Currently handles:
  - Poison: pulsing green vignette
"""
import math
import time
import pygame
import config as _config

_poison_surf: pygame.Surface | None = None


def draw_status_effects(screen: pygame.Surface, w: int, h: int) -> None:
    """Overlay visual cues for all active player debuffs."""
    global _poison_surf

    pt = getattr(_config, "poison_timer", 0.0)
    if pt > 0.0:
        # Pulse at 4 Hz between alpha 25 and 50 for a sickly shimmer.
        pulse = 0.5 + 0.5 * math.sin(time.time() * 4.0)
        alpha = int(25 + 25 * pulse)
        if _poison_surf is None or _poison_surf.get_size() != (w, h):
            _poison_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        _poison_surf.fill((30, 185, 50, alpha))
        screen.blit(_poison_surf, (0, 0))

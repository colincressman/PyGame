"""Client-side status effect overlays."""

import math
import time

import pygame

import config as _config
from status_effect_data import STATUS_EFFECTS

_overlay_surfaces: dict[str, pygame.Surface] = {}


def _draw_color_overlay(
    screen: pygame.Surface,
    effect_name: str,
    timer_value: float,
    cfg: dict,
    w: int,
    h: int,
) -> None:
    if timer_value <= 0.0:
        return
    color = cfg.get("overlay_color")
    if not color:
        return
    pulse_hz = float(cfg.get("pulse_hz", 0.0))
    alpha_min = int(cfg.get("overlay_alpha_min", 0))
    alpha_max = int(cfg.get("overlay_alpha_max", alpha_min))
    if pulse_hz > 0.0:
        pulse = 0.5 + 0.5 * math.sin(time.time() * pulse_hz)
    else:
        pulse = 1.0
    alpha = int(alpha_min + (alpha_max - alpha_min) * pulse)

    surf = _overlay_surfaces.get(effect_name)
    if surf is None or surf.get_size() != (w, h):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        _overlay_surfaces[effect_name] = surf
    surf.fill((*color, alpha))
    screen.blit(surf, (0, 0))


def draw_status_effects(screen: pygame.Surface, w: int, h: int) -> None:
    """Overlay visual cues for configured active player debuffs."""
    for effect_name, cfg in STATUS_EFFECTS.items():
        timer_key = cfg.get("timer_key")
        if not timer_key:
            continue
        timer_value = getattr(_config, timer_key, 0.0)
        _draw_color_overlay(screen, effect_name, timer_value, cfg, w, h)

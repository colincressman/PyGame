# client/rendering/weather.py
"""Client-side weather rendering: rain drops, snow flakes, fog/cloud overlay.

draw_weather(screen, w, h, dt) is called from the main loop after the world is
drawn but before HUD elements.  It reads config.weather to decide what to show.
"""
import math
import random
import pygame
import config as _config

# ---------- particle state (initialised lazily on first non-clear frame) ----------
_rain:  list = []   # each entry: [x, y, speed]
_snow:  list = []   # each entry: [x, y, speed, wobble_phase]
_ready: bool = False

_fog_surf: pygame.Surface | None = None


def _init(w: int, h: int) -> None:
    global _rain, _snow, _ready
    _rain = [
        [random.randint(0, w), random.randint(-20, h), random.uniform(10, 18)]
        for _ in range(200)
    ]
    _snow = [
        [
            random.randint(0, w),
            random.randint(-20, h),
            random.uniform(0.6, 2.2),
            random.uniform(0, math.pi * 2),
        ]
        for _ in range(150)
    ]
    _ready = True


def draw_weather(screen: pygame.Surface, w: int, h: int, dt: float) -> None:
    """Render weather particles / overlays for the current weather state."""
    global _fog_surf

    weather = getattr(_config, "weather", "clear")
    if weather == "clear":
        return

    if not _ready:
        _init(w, h)

    if weather == "rain":
        for drop in _rain:
            x, y, spd = drop
            # Slight diagonal slant to look like wind-driven rain.
            x2 = int(x) - int(spd * 0.4)
            y2 = int(y) + int(spd * 0.8)
            pygame.draw.line(screen, (140, 170, 210), (int(x), int(y)), (x2, y2), 1)
            drop[1] += spd * dt * 60
            drop[0] -= spd * dt * 20
            if drop[1] > h or drop[0] < -10:
                drop[1] = random.randint(-20, -5)
                drop[0] = random.randint(0, w + 20)
                drop[2] = random.uniform(10, 18)

    elif weather == "snow":
        t = pygame.time.get_ticks() * 0.001
        for flake in _snow:
            x, y, spd, phase = flake
            # Gentle horizontal wobble.
            px = int(x + math.sin(t * spd + phase) * 8)
            py = int(y)
            r  = max(1, int(spd * 0.7))
            pygame.draw.circle(screen, (230, 235, 248), (px, py), r)
            flake[1] += spd * dt * 15
            if flake[1] > h:
                flake[1] = random.randint(-20, -5)
                flake[0] = random.randint(0, w)

    # Fog / cloudy tint overlay (can stack on top of precipitation).
    if weather in ("fog", "cloudy"):
        a = 55 if weather == "fog" else 28
        if _fog_surf is None or _fog_surf.get_size() != (w, h):
            _fog_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        _fog_surf.fill((210, 215, 225, a))
        screen.blit(_fog_surf, (0, 0))

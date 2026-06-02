"""client/rendering/particles.py

Lightweight world-space particle system.

Emit functions are called from the networking thread (handlers.py); draw/update
run on the main thread.  A threading.Lock protects the shared list.

All positions are in tile-space coordinates (same as mobs/players).
Screen conversion: sx = tile_x * TILE_SIZE + config.camera_offset_x
"""

import math
import random
import threading

import pygame
import config

_particles: list = []
_lock = threading.Lock()


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size")

    def __init__(self, x, y, vx, vy, life, color, size):
        self.x       = x
        self.y       = y
        self.vx      = vx
        self.vy      = vy
        self.life    = life
        self.max_life = max(life, 0.001)
        self.color   = color   # (r, g, b) — fades with alpha
        self.size    = size    # pixels


# ── Emitters ────────────────────────────────────────────────────────────────

def emit_hit(tile_x: float, tile_y: float):
    """8 red sparks bursting outward — called on combat hit."""
    with _lock:
        for i in range(8):
            a   = i * math.pi / 4 + random.uniform(-0.25, 0.25)
            spd = random.uniform(2.0, 5.0)
            _particles.append(_Particle(
                tile_x, tile_y,
                math.cos(a) * spd, math.sin(a) * spd,
                random.uniform(0.15, 0.35),
                (225, random.randint(30, 85), 30),
                random.randint(2, 4),
            ))


def emit_pickup(tile_x: float, tile_y: float):
    """5 gold sparkles drifting upward — called when an item is collected."""
    with _lock:
        for _ in range(5):
            _particles.append(_Particle(
                tile_x + random.uniform(-0.3, 0.3),
                tile_y + random.uniform(-0.1, 0.15),
                random.uniform(-0.6, 0.6),
                random.uniform(-3.5, -1.5),
                random.uniform(0.4, 0.8),
                (255, random.randint(185, 225), 0),
                random.randint(3, 5),
            ))


def emit_levelup(tile_x: float, tile_y: float):
    """Rainbow ring burst — called on player level-up."""
    with _lock:
        n = 24
        for i in range(n):
            a    = i * 2 * math.pi / n
            spd  = random.uniform(1.5, 4.5)
            # HSV → RGB for a rainbow hue per particle
            hue  = i / n          # 0–1
            h6   = hue * 6.0
            x_h  = 1.0 - abs(h6 % 2 - 1.0)
            if   h6 < 1: r, g, b = 1.0, x_h, 0.0
            elif h6 < 2: r, g, b = x_h, 1.0, 0.0
            elif h6 < 3: r, g, b = 0.0, 1.0, x_h
            elif h6 < 4: r, g, b = 0.0, x_h, 1.0
            elif h6 < 5: r, g, b = x_h, 0.0, 1.0
            else:        r, g, b = 1.0, 0.0, x_h
            _particles.append(_Particle(
                tile_x, tile_y,
                math.cos(a) * spd, math.sin(a) * spd,
                random.uniform(0.7, 1.3),
                (int(r * 255), int(g * 255), int(b * 255)),
                random.randint(3, 6),
            ))


def emit_craft(tile_x: float, tile_y: float):
    """6 white puffs — called on successful craft."""
    with _lock:
        for _ in range(6):
            a   = random.uniform(0, 2 * math.pi)
            spd = random.uniform(0.8, 2.5)
            _particles.append(_Particle(
                tile_x, tile_y,
                math.cos(a) * spd, math.sin(a) * spd,
                random.uniform(0.3, 0.6),
                (230, 230, 230),
                random.randint(3, 6),
            ))


def emit_roll(tile_x: float, tile_y: float):
    """4 pale-blue afterimage sparks — emitted periodically while dodge-rolling."""
    with _lock:
        for _ in range(4):
            a   = random.uniform(0, 2 * math.pi)
            spd = random.uniform(0.3, 1.2)
            _particles.append(_Particle(
                tile_x + random.uniform(-0.2, 0.2),
                tile_y + random.uniform(-0.2, 0.2),
                math.cos(a) * spd,
                math.sin(a) * spd,
                random.uniform(0.12, 0.28),
                (140, 200, 255),
                random.randint(3, 5),
            ))


# Aura hue counter (increments each frame for rainbow cycling)
_aura_hue: float = 0.0

def emit_aura(tile_x: float, tile_y: float, aura_type: str) -> None:
    """Emit 1-2 persistent aura particles around the player each frame.

    Designed to be called from the main render loop — uses the lock internally.
    aura_type: "fire" | "ice" | "golden" | "shadow" | "rainbow"
    """
    global _aura_hue
    _aura_hue = (_aura_hue + 0.03) % 1.0

    if aura_type == "fire":
        colors  = [(255, 90, 10), (255, 160, 0), (220, 50, 0)]
        n, life = 2, (0.25, 0.55)
        grav    = -6.0   # rises
        spread  = 0.25
    elif aura_type == "ice":
        colors  = [(80, 200, 255), (160, 230, 255), (200, 245, 255)]
        n, life = 2, (0.4, 0.9)
        grav    = -1.5
        spread  = 0.3
    elif aura_type == "golden":
        colors  = [(255, 215, 0), (255, 240, 80), (255, 185, 0)]
        n, life = 2, (0.3, 0.7)
        grav    = -3.0
        spread  = 0.35
    elif aura_type == "shadow":
        colors  = [(80, 0, 130), (50, 0, 80), (120, 20, 160)]
        n, life = 2, (0.3, 0.65)
        grav    = 1.5
        spread  = 0.3
    elif aura_type == "rainbow":
        h6   = _aura_hue * 6.0
        xh   = 1.0 - abs(h6 % 2 - 1.0)
        if   h6 < 1: r, g, b = 1.0, xh, 0.0
        elif h6 < 2: r, g, b = xh, 1.0, 0.0
        elif h6 < 3: r, g, b = 0.0, 1.0, xh
        elif h6 < 4: r, g, b = 0.0, xh, 1.0
        elif h6 < 5: r, g, b = xh, 0.0, 1.0
        else:        r, g, b = 1.0, 0.0, xh
        colors = [(int(r * 255), int(g * 255), int(b * 255))]
        n, life = 2, (0.3, 0.7)
        grav    = -2.5
        spread  = 0.4
    else:
        return

    with _lock:
        for _ in range(n):
            a    = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0.0, spread)
            spd  = random.uniform(0.2, 0.8)
            col  = random.choice(colors)
            _particles.append(_Particle(
                tile_x + math.cos(a) * dist,
                tile_y + math.sin(a) * dist * 0.5,
                math.cos(a) * spd * 0.5,
                math.sin(a) * spd * 0.3 + grav * 0.05,
                random.uniform(*life),
                col,
                random.randint(2, 4),
            ))


# ── Update & draw ────────────────────────────────────────────────────────────

def update(dt: float):
    """Advance all particles; remove expired ones.  Called from main thread."""
    with _lock:
        for p in _particles:
            p.x    += p.vx * dt
            p.y    += p.vy * dt
            p.vy   += 3.0 * dt   # gentle gravity (tile units/s²)
            p.life -= dt
        _particles[:] = [p for p in _particles if p.life > 0]


def draw(screen: pygame.Surface):
    """Draw all particles.  Called from main thread after world render."""
    with _lock:
        snapshot = list(_particles)
    if not snapshot:
        return

    ox = config.camera_offset_x
    oy = config.camera_offset_y
    ts = config.TILE_SIZE
    sw = screen.get_width()
    sh = screen.get_height()

    for p in snapshot:
        alpha = max(0.0, p.life / p.max_life)
        sx    = int(p.x * ts + ox)
        sy    = int(p.y * ts + oy)
        if not (0 <= sx < sw and 0 <= sy < sh):
            continue
        col = (
            int(p.color[0] * alpha),
            int(p.color[1] * alpha),
            int(p.color[2] * alpha),
        )
        sz = max(1, p.size)
        if sz <= 2:
            screen.set_at((sx, sy), col)
        else:
            pygame.draw.circle(screen, col, (sx, sy), sz)

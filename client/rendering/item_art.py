# client/rendering/item_art.py
"""Procedural pixel art for items and resource nodes — scales to any square size."""

import pygame
import math

# Surface cache keyed on (item_id, size) — drawn once, blitted forever.
_item_surface_cache: dict[tuple[int, int], pygame.Surface] = {}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _handle(sc, x, y, s, col=(130, 85, 35)):
    """Diagonal handle: lower-left → upper-right, two-tone for depth."""
    dark = (max(0, col[0] - 35), max(0, col[1] - 25), max(0, col[2] - 12))
    w = max(1, s // 7)
    pygame.draw.line(sc, col,  (x + s // 4,     y + s - s // 6),
                               (x + s * 3 // 4, y + s // 4), w)
    pygame.draw.line(sc, dark, (x + s // 4 + 1, y + s - s // 6),
                               (x + s * 3 // 4 + 1, y + s // 4), max(1, w - 1))


# ---------------------------------------------------------------------------
# Item draw functions  (sc, x, y, s)
# ---------------------------------------------------------------------------

def _slimeball(sc, x, y, s):
    cx, cy, r = x + s // 2, y + s // 2, s // 2 - 1
    # Dark shadow ellipse for ground visibility
    pygame.draw.ellipse(sc, (20, 80, 20), (cx - r + 2, cy + r - 2, (r - 2) * 2, max(2, r // 3)))
    # Bright lime-green body
    pygame.draw.circle(sc, (60, 230, 60), (cx, cy), r)
    # Dark border
    pygame.draw.circle(sc, (20, 120, 20), (cx, cy), r, max(1, s // 10))
    # Specular highlight
    pygame.draw.circle(sc, (180, 255, 160), (cx - r // 3, cy - r // 3), max(1, r // 3))


def _coin(sc, x, y, s):
    cx, cy, r = x + s // 2, y + s // 2, s // 2 - 1
    pygame.draw.circle(sc, (240, 195, 10), (cx, cy), r)
    pygame.draw.circle(sc, (170, 125, 0),  (cx, cy), r, max(1, s // 8))
    if r > 4:
        pygame.draw.circle(sc, (215, 165, 5), (cx, cy), r - 3, 1)


def _wood(sc, x, y, s):
    col, dark, lite = (139, 90, 43), (90, 55, 15), (175, 125, 70)
    pygame.draw.rect(sc, col, (x + 1, y + s // 5, s - 2, s * 3 // 5), border_radius=2)
    pygame.draw.rect(sc, dark, (x + 1, y + s // 5, s - 2, s * 3 // 5), 1, border_radius=2)
    # End-grain circle
    ex, ey = x + s // 8 + 1, y + s // 2
    pygame.draw.circle(sc, dark, (ex, ey), max(2, s // 6))
    pygame.draw.circle(sc, lite, (ex, ey), max(1, s // 10))
    # Grain lines
    for i in (1, 2):
        gy = y + s // 5 + (s * 3 // 5) * i // 3
        pygame.draw.line(sc, lite, (x + s // 4, gy), (x + s - 3, gy), 1)


def _stone(sc, x, y, s):
    cx, cy = x + s // 2, y + s // 2
    r = s // 2 - 1
    pts = [
        (cx - r,     cy - r // 3), (cx - r // 2, cy - r),
        (cx + r // 4, cy - r + 1), (cx + r,     cy - r // 4),
        (cx + r - 1, cy + r // 2), (cx,         cy + r),
        (cx - r // 2, cy + r - 1),
    ]
    pygame.draw.polygon(sc, (150, 150, 150), pts)
    pygame.draw.polygon(sc, (90, 90, 90), pts, 1)
    pygame.draw.line(sc, (190, 190, 190),
                     (cx - r // 2, cy - r // 2), (cx + r // 4, cy - r // 3), 1)


def _herb(sc, x, y, s):
    stem, leaf = (35, 155, 55), (65, 212, 88)
    bx, by = x + s // 2, y + s - 2
    for tx, ty in [(x + s // 4, y + s // 5), (x + s // 2, y + 2), (x + 3 * s // 4, y + s // 5)]:
        pygame.draw.line(sc, stem, (bx, by), (tx, ty), max(1, s // 9))
        pygame.draw.circle(sc, leaf, (tx, ty), max(2, s // 7))


def _mushroom(sc, x, y, s):
    cx = x + s // 2
    sw, sh = max(3, s // 4), max(3, s // 3)
    pygame.draw.rect(sc, (230, 215, 195), (cx - sw // 2, y + s - sh, sw, sh), border_radius=1)
    cr = s // 2 - 1
    cy2 = y + s // 2
    pygame.draw.circle(sc, (195, 40, 40), (cx, cy2), cr)
    pygame.draw.circle(sc, (130, 20, 20), (cx, cy2), cr, max(1, s // 10))
    dr = max(1, s // 10)
    pygame.draw.circle(sc, (255, 255, 255), (cx - s // 5, cy2 - s // 8), dr)
    pygame.draw.circle(sc, (255, 255, 255), (cx + s // 6, cy2 + 1), dr)


def _cactus_spine(sc, x, y, s):
    pts = [(x + s // 2, y + 1), (x + s - 2, y + s // 2),
           (x + s // 2, y + s - 1), (x + 2, y + s // 2)]
    pygame.draw.polygon(sc, (180, 205, 50), pts)
    pygame.draw.polygon(sc, (120, 145, 20), pts, 1)
    pygame.draw.line(sc, (215, 238, 112), (x + s // 2, y + 3), (x + s // 2, y + s // 2 - 1), 1)


def _snow_crystal(sc, x, y, s):
    cx, cy = x + s // 2, y + s // 2
    r = s // 2 - 1
    col = (195, 238, 255)
    for i in range(6):
        a = math.radians(i * 60)
        ex, ey = int(cx + r * math.cos(a)), int(cy + r * math.sin(a))
        pygame.draw.line(sc, col, (cx, cy), (ex, ey), max(1, s // 12))
        if r > 5:
            mx = int(cx + r * 0.55 * math.cos(a))
            my = int(cy + r * 0.55 * math.sin(a))
            ax = int(math.cos(a + math.pi / 2) * s // 8)
            ay = int(math.sin(a + math.pi / 2) * s // 8)
            pygame.draw.line(sc, col, (mx - ax, my - ay), (mx + ax, my + ay), 1)
    pygame.draw.circle(sc, (245, 252, 255), (cx, cy), max(2, s // 8))


def _seashell(sc, x, y, s):
    cx, cy = x + s // 2, y + s - 3
    col, dark = (255, 168, 180), (205, 115, 135)
    r = s * 2 // 5
    for i in range(5):
        a = math.radians(15 + i * 33)
        ex, ey = int(cx + r * math.cos(a)), int(cy - r * math.sin(a))
        pygame.draw.line(sc, col if i % 2 == 0 else dark, (cx, cy), (ex, ey), max(1, s // 10))
    pygame.draw.arc(sc, dark, (x + 2, y + s // 3, s - 4, s * 2 // 3), 0, math.pi, max(1, s // 10))
    pygame.draw.circle(sc, dark, (cx, cy), max(2, s // 9))


def _reed(sc, x, y, s):
    cx = x + s // 2
    stem = (40, 145, 75)
    pygame.draw.line(sc, stem, (cx, y + s - 2), (cx, y + s // 3), max(1, s // 9))
    pr = max(2, s // 5)
    pygame.draw.ellipse(sc, (95, 58, 22), (cx - pr // 2, y + 2, pr, pr + pr // 2))
    pygame.draw.line(sc, stem, (cx, y + s // 2), (x + s * 3 // 4, y + s * 2 // 5), max(1, s // 10))


def _bone(sc, x, y, s):
    col, dark = (225, 220, 205), (160, 155, 140)
    w = max(1, s // 6)
    pygame.draw.line(sc, col, (x + s // 4, y + s * 3 // 4), (x + s * 3 // 4, y + s // 4), w + 1)
    kr = max(2, s // 6)
    for kx, ky in [(x + s // 6, y + s * 5 // 6), (x + s * 5 // 6, y + s // 6)]:
        pygame.draw.circle(sc, col, (kx, ky), kr)
        pygame.draw.circle(sc, dark, (kx, ky), kr, 1)
    for kx, ky in [(x + s // 3, y + s * 2 // 3), (x + s * 2 // 3, y + s // 3)]:
        pygame.draw.circle(sc, col, (kx, ky), max(1, kr - 1))


def _coal(sc, x, y, s):
    cx, cy = x + s // 2, y + s // 2
    r = s // 2 - 1
    pts = [
        (cx - r,     cy - r // 3), (cx - r // 3, cy - r),
        (cx + r // 2, cy - r + 2), (cx + r,     cy),
        (cx + r // 2, cy + r),     (cx - r // 2, cy + r - 1),
    ]
    pygame.draw.polygon(sc, (48, 48, 48), pts)
    pygame.draw.polygon(sc, (22, 22, 22), pts, 1)
    pygame.draw.line(sc, (80, 80, 80), (cx - r // 2, cy - r // 2), (cx, cy - r // 3), 1)


def _iron_ore(sc, x, y, s):
    col, dark, vein = (160, 100, 55), (110, 65, 25), (222, 135, 65)
    pygame.draw.rect(sc, col,  (x + 2, y + 2, s - 4, s - 4), border_radius=3)
    pygame.draw.rect(sc, dark, (x + 2, y + 2, s - 4, s - 4), 1, border_radius=3)
    pygame.draw.line(sc, vein, (x + 3, y + s // 2), (x + s // 2, y + 3), 1)
    pygame.draw.line(sc, vein, (x + s // 2, y + s - 4), (x + s - 3, y + s * 2 // 3), 1)
    pygame.draw.circle(sc, (228, 132, 62), (x + s // 2 + 2, y + s // 2 - 2), max(2, s // 7))


def _stick(sc, x, y, s):
    col, dark = (158, 108, 48), (110, 70, 22)
    w = max(2, s // 7)
    pygame.draw.line(sc, col, (x + s // 6, y + s - s // 6), (x + s - s // 6, y + s // 6), w)
    pygame.draw.circle(sc, dark, (x + s // 2, y + s // 2), max(1, s // 8))


def _sword(sc, x, y, s, blade, blade_dark, guard_col, handle_col=(130, 85, 35)):
    # Handle: lower-left → center
    _handle(sc, x, y, s, handle_col)
    # Pommel
    pygame.draw.circle(sc, guard_col, (x + s // 5, y + s - s // 5), max(2, s // 9))
    # Guard: perpendicular bar across the blade midpoint
    gx, gy = x + s // 2, y + s // 2
    gw = max(3, s // 3)
    gh = max(2, s // 9)
    # Guard is rotated 90° from the handle direction (handle goes NE, guard goes NW-SE)
    pygame.draw.line(sc, guard_col, (gx - gw // 2, gy + gw // 2), (gx + gw // 2, gy - gw // 2), gh)
    # Blade: thin tapering triangle from guard to upper-right tip
    tip = (x + s - 2, y + 2)
    bw = max(1, s // 9)
    blade_pts = [
        (gx - bw, gy - bw),
        (gx + bw, gy + bw),
        (tip[0], tip[1]),
    ]
    pygame.draw.polygon(sc, blade, blade_pts)
    pygame.draw.polygon(sc, blade_dark, blade_pts, 1)
    # Edge highlight
    lite = (min(255, blade[0] + 55), min(255, blade[1] + 55), min(255, blade[2] + 55))
    pygame.draw.line(sc, lite, (gx - bw // 2, gy - bw // 2), tip, 1)


def _dagger(sc, x, y, s, blade, blade_dark, handle_col):
    # Shorter blade — same layout but tip only reaches ~2/3 up
    _handle(sc, x, y, s, handle_col)
    pygame.draw.circle(sc, blade_dark, (x + s // 5, y + s - s // 5), max(2, s // 10))
    gx, gy = x + s * 5 // 9, y + s * 4 // 9
    gw = max(3, s // 4)
    gh = max(2, s // 9)
    pygame.draw.line(sc, blade_dark, (gx - gw // 2, gy + gw // 2), (gx + gw // 2, gy - gw // 2), gh)
    tip = (x + s - s // 5, y + s // 5)
    bw = max(1, s // 9)
    blade_pts = [(gx - bw, gy - bw), (gx + bw, gy + bw), (tip[0], tip[1])]
    pygame.draw.polygon(sc, blade, blade_pts)
    pygame.draw.polygon(sc, blade_dark, blade_pts, 1)
    lite = (min(255, blade[0] + 55), min(255, blade[1] + 55), min(255, blade[2] + 55))
    pygame.draw.line(sc, lite, (gx - bw // 2, gy - bw // 2), tip, 1)


def _mace(sc, x, y, s, head_col, head_dark, handle_col=(130, 85, 35)):
    _handle(sc, x, y, s, handle_col)
    hcx, hcy = x + s * 3 // 4, y + s // 4
    hr  = max(4, s // 4)
    spk = max(2, s // 7)
    # Draw 4 triangular spikes before the ball so the ball overlaps their bases
    for deg in (0, 90, 180, 270):
        a   = math.radians(deg)
        dx  = math.cos(a)
        dy  = math.sin(a)
        px, py = -dy, dx                              # perpendicular
        b1x = int(hcx + (hr - 1) * dx + spk // 2 * px)
        b1y = int(hcy + (hr - 1) * dy + spk // 2 * py)
        b2x = int(hcx + (hr - 1) * dx - spk // 2 * px)
        b2y = int(hcy + (hr - 1) * dy - spk // 2 * py)
        tx  = int(hcx + (hr + spk) * dx)
        ty  = int(hcy + (hr + spk) * dy)
        pygame.draw.polygon(sc, head_col,  [(b1x, b1y), (b2x, b2y), (tx, ty)])
        pygame.draw.polygon(sc, head_dark, [(b1x, b1y), (b2x, b2y), (tx, ty)], 1)
    # Ball (drawn on top so it hides the spike bases cleanly)
    pygame.draw.circle(sc, head_col,  (hcx, hcy), hr)
    pygame.draw.circle(sc, head_dark, (hcx, hcy), hr, max(1, s // 12))
    # Center highlight
    pygame.draw.circle(sc, (min(255, head_col[0] + 45), min(255, head_col[1] + 35), min(255, head_col[2] + 25)),
                       (hcx - hr // 3, hcy - hr // 3), max(2, hr // 3))


def _tunic(sc, x, y, s, body_col, body_dark, stripe_col=None):
    # Front-view shirt: two shoulder rectangles + body trapezoid
    cx = x + s // 2
    # Body
    bx, by = x + s // 6, y + s // 3
    bw, bh = s * 2 // 3, s * 2 // 3
    body_pts = [(bx, by), (bx + bw, by), (bx + bw - s // 8, by + bh), (bx + s // 8, by + bh)]
    pygame.draw.polygon(sc, body_col, body_pts)
    pygame.draw.polygon(sc, body_dark, body_pts, 1)
    # Shoulders
    sw, sh = s // 3, s // 4
    pygame.draw.rect(sc, body_col, (bx - sw + s // 8, by - sh // 2, sw, sh), border_radius=2)
    pygame.draw.rect(sc, body_dark, (bx - sw + s // 8, by - sh // 2, sw, sh), 1, border_radius=2)
    pygame.draw.rect(sc, body_col, (bx + bw - s // 8, by - sh // 2, sw, sh), border_radius=2)
    pygame.draw.rect(sc, body_dark, (bx + bw - s // 8, by - sh // 2, sw, sh), 1, border_radius=2)
    # Neck opening
    pygame.draw.circle(sc, body_dark, (cx, by), max(2, s // 8))
    # Texture stripes
    if stripe_col:
        for i in range(1, 4):
            gy = by + bh * i // 4
            lx = bx + s // 8 * (i % 2)
            pygame.draw.line(sc, stripe_col, (lx + 2, gy), (bx + bw - 4, gy), 1)


def _helm(sc, x, y, s, col, dark):
    cx = x + s // 2
    # Dome
    dome_r = s * 2 // 5
    dome_y = y + s * 2 // 5
    pygame.draw.circle(sc, col, (cx, dome_y), dome_r)
    pygame.draw.circle(sc, dark, (cx, dome_y), dome_r, max(1, s // 10))
    # Cheek guards
    cg_w, cg_h = max(3, s // 5), max(4, s // 3)
    cg_y = dome_y + dome_r // 2
    for cg_x in (cx - dome_r, cx + dome_r - cg_w):
        pygame.draw.rect(sc, col, (cg_x, cg_y, cg_w, cg_h), border_radius=2)
        pygame.draw.rect(sc, dark, (cg_x, cg_y, cg_w, cg_h), 1, border_radius=2)
    # Visor slit
    pygame.draw.line(sc, dark, (cx - dome_r // 2, dome_y + dome_r // 4),
                     (cx + dome_r // 2, dome_y + dome_r // 4), max(1, s // 10))
    # Highlight on dome
    pygame.draw.arc(sc, (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 30)),
                    (cx - dome_r + 2, dome_y - dome_r + 2, dome_r, dome_r), 0.5, 2.0, max(1, s // 12))


def _cloak(sc, x, y, s, col, dark):
    # Triangular cloak with wavy/leaf bottom edge
    cx = x + s // 2
    # Main body
    pts = [(cx, y + 2), (x + s - 2, y + s * 3 // 4), (x + 2, y + s * 3 // 4)]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    # Leaf-like scalloped bottom: small arcs/bumps
    by = y + s * 3 // 4
    bw = s - 4
    num = 4
    seg = bw // num
    for i in range(num):
        lx = x + 2 + i * seg
        pygame.draw.arc(sc, col,  (lx, by, seg, max(3, s // 5)), math.pi, 2 * math.pi, 0)
        pygame.draw.arc(sc, dark, (lx, by, seg, max(3, s // 5)), math.pi, 2 * math.pi, 1)
    # Clasp at top
    pygame.draw.circle(sc, dark, (cx, y + s // 5), max(2, s // 10))
    # Highlight down center
    pygame.draw.line(sc, (min(255, col[0] + 35), min(255, col[1] + 35), min(255, col[2] + 20)),
                     (cx, y + 4), (cx, y + s * 3 // 5), 1)


def _wings_art(sc, x, y, s, col, dark):
    """Stylised wing icon: two symmetric curved/fan shapes spreading from centre."""
    cx = x + s // 2
    cy = y + s // 2 + s // 8
    # Left wing
    lpts = [
        (cx - 2, cy),
        (cx - s * 2 // 5, cy - s // 3),
        (cx - s * 9 // 20, cy - s // 8),
        (cx - s * 2 // 5, cy + s // 5),
        (cx - 2, cy + s // 6),
    ]
    pygame.draw.polygon(sc, col, lpts)
    pygame.draw.polygon(sc, dark, lpts, 1)
    # Right wing (mirror)
    rpts = [(2 * cx - px, py) for (px, py) in lpts]
    pygame.draw.polygon(sc, col, rpts)
    pygame.draw.polygon(sc, dark, rpts, 1)
    # Central body nub
    pygame.draw.circle(sc, dark, (cx, cy), max(2, s // 10))


def _bracers(sc, x, y, s, col, dark, stripe_col=None):
    # Two rectangular bracers side by side
    bw = max(4, s * 2 // 5)
    bh = max(6, s * 3 // 5)
    gap = max(2, s // 10)
    total = bw * 2 + gap
    bx = x + (s - total) // 2
    by = y + (s - bh) // 2
    for i in range(2):
        rx = bx + i * (bw + gap)
        pygame.draw.rect(sc, col,  (rx, by, bw, bh), border_radius=2)
        pygame.draw.rect(sc, dark, (rx, by, bw, bh), 1, border_radius=2)
        # Strap lines
        if stripe_col:
            for j in (1, 2):
                gy = by + bh * j // 3
                pygame.draw.line(sc, stripe_col, (rx + 1, gy), (rx + bw - 2, gy), 1)
        # Highlight
        pygame.draw.line(sc, (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 25)),
                         (rx + 2, by + 2), (rx + bw - 3, by + 2), 1)


def _necklace(sc, x, y, s, chain_col, pendant_fn):
    cx = x + s // 2
    r = s * 3 // 8
    # Chain arc (upper half)
    pygame.draw.arc(sc, chain_col, (cx - r, y + s // 8, r * 2, r * 2), math.pi, 2 * math.pi,
                    max(1, s // 10))
    # Pendant dangling at bottom of arc
    pendant_fn(sc, cx, y + s // 8 + r * 2, s)


def _shell_pendant(sc, cx, py, s):
    pr = max(3, s // 6)
    # Fan lines
    for i in range(4):
        a = math.radians(10 + i * 40)
        ex = int(cx + pr * math.cos(a))
        ey = int(py - pr * math.sin(a))
        pygame.draw.line(sc, (255, 168, 180), (cx, py), (ex, ey), 1)
    pygame.draw.circle(sc, (205, 115, 135), (cx, py), max(2, s // 10))


def _ring(sc, x, y, s, band_col, band_dark, gem_col, gem_dark):
    cx, cy = x + s // 2, y + s // 2 + s // 8
    r = max(4, s // 3)
    # Band
    pygame.draw.circle(sc, band_col, (cx, cy), r, max(2, s // 8))
    pygame.draw.circle(sc, band_dark, (cx, cy), r + 1, 1)
    pygame.draw.circle(sc, band_dark, (cx, cy), r - max(2, s // 8), 1)
    # Gem on top
    gw, gh = max(4, s // 4), max(3, s // 5)
    gem_x, gem_y = cx - gw // 2, y + s // 8
    gem_pts = [(cx, gem_y), (cx + gw // 2, gem_y + gh // 2),
               (cx, gem_y + gh), (cx - gw // 2, gem_y + gh // 2)]
    pygame.draw.polygon(sc, gem_col, gem_pts)
    pygame.draw.polygon(sc, gem_dark, gem_pts, 1)
    # Gem facet highlight
    pygame.draw.line(sc, (min(255, gem_col[0] + 60), min(255, gem_col[1] + 60), min(255, gem_col[2] + 60)),
                     (cx, gem_y + 1), (cx + gw // 4, gem_y + gh // 2), 1)


def _pouch(sc, x, y, s, col, dark, string_col):
    cx = x + s // 2
    # Bag body: rounded rect, wider at bottom
    bw, bh = s * 3 // 5, s * 2 // 5
    bx = x + (s - bw) // 2
    by = y + s * 2 // 5
    pygame.draw.rect(sc, col,  (bx, by, bw, bh), border_radius=max(3, s // 6))
    pygame.draw.rect(sc, dark, (bx, by, bw, bh), 1, border_radius=max(3, s // 6))
    # Gathered neck
    nw = max(4, bw // 2)
    nh = max(3, s // 7)
    nx = cx - nw // 2
    ny = by - nh
    pygame.draw.rect(sc, dark, (nx, ny, nw, nh + 2), border_radius=1)
    pygame.draw.rect(sc, col,  (nx + 1, ny + 1, nw - 2, nh), border_radius=1)
    # String/tie bow
    pygame.draw.line(sc, string_col, (nx - 2, ny + nh // 2), (nx + nw + 2, ny + nh // 2),
                     max(1, s // 10))
    pygame.draw.circle(sc, string_col, (cx, ny + nh // 2), max(1, s // 12))
    # Highlight on bag
    pygame.draw.arc(sc, (min(255, col[0] + 45), min(255, col[1] + 40), min(255, col[2] + 25)),
                    (bx + 3, by + 3, bw // 2, bh // 2), 0.4, 1.8, 1)


def _axe(sc, x, y, s, blade, blade_dark, handle_col=(130, 85, 35)):
    _handle(sc, x, y, s, handle_col)
    bx, by   = x + s * 9 // 14, y + s // 7
    bw, bh   = max(4, s // 3), max(5, s * 2 // 5)
    pts = [
        (bx,          by + bh // 2),
        (bx - bw // 4, by),
        (bx + bw,     by - bh // 6),
        (bx + bw,     by + bh + bh // 6),
        (bx - bw // 4, by + bh),
    ]
    pygame.draw.polygon(sc, blade, pts)
    pygame.draw.polygon(sc, blade_dark, pts, 1)
    lite = (min(255, blade[0] + 50), min(255, blade[1] + 40), min(255, blade[2] + 30))
    pygame.draw.line(sc, lite, (bx + bw - 1, by), (bx + bw - 1, by + bh), 1)


def _pickaxe(sc, x, y, s, head, head_dark, handle_col=(130, 85, 35)):
    _handle(sc, x, y, s, handle_col)
    cx, cy = x + s * 2 // 3, y + s // 5
    hw, hh = max(4, s // 3), max(2, s // 8)
    pygame.draw.rect(sc, head, (cx - hw // 2, cy - hh, hw, hh * 2), border_radius=1)
    pygame.draw.rect(sc, head_dark, (cx - hw // 2, cy - hh, hw, hh * 2), 1, border_radius=1)
    tl = max(2, s // 7)
    # Left tip (down-left)
    pts_l = [(cx - hw // 2, cy - hh), (cx - hw // 2, cy + hh), (cx - hw // 2 - tl, cy + tl * 2)]
    pygame.draw.polygon(sc, head, pts_l)
    pygame.draw.polygon(sc, head_dark, pts_l, 1)
    # Right tip (up-right)
    pts_r = [(cx + hw // 2, cy - hh), (cx + hw // 2, cy + hh), (cx + hw // 2 + tl, cy - tl * 2)]
    pygame.draw.polygon(sc, head, pts_r)
    pygame.draw.polygon(sc, head_dark, pts_r, 1)


def _leggings(sc, x, y, s, col, dark):
    """Two trouser legs with a connecting waistband and belt buckle."""
    lw  = max(4, s * 3 // 10)
    lh  = max(6, s * 2 // 5)
    gap = max(2, s // 10)
    total = lw * 2 + gap
    bx = x + (s - total) // 2
    # Waistband
    wh = max(3, s // 7)
    wy = y + s // 8
    pygame.draw.rect(sc, col,  (bx, wy, total, wh), border_radius=2)
    pygame.draw.rect(sc, dark, (bx, wy, total, wh), 1, border_radius=2)
    # Belt buckle
    bk_w, bk_h = max(4, s // 6), max(3, s // 9)
    bk_x = x + (s - bk_w) // 2
    bk_y = wy + (wh - bk_h) // 2
    lite = (min(255, col[0] + 70), min(255, col[1] + 65), min(255, col[2] + 35))
    pygame.draw.rect(sc, lite, (bk_x, bk_y, bk_w, bk_h), border_radius=1)
    pygame.draw.rect(sc, dark, (bk_x, bk_y, bk_w, bk_h), 1, border_radius=1)
    # Legs
    by = wy + wh
    for i in range(2):
        rx = bx + i * (lw + gap)
        pygame.draw.rect(sc, col,  (rx, by, lw, lh), border_radius=max(2, s // 12))
        pygame.draw.rect(sc, dark, (rx, by, lw, lh), 1, border_radius=max(2, s // 12))
        pygame.draw.line(sc, (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 25)),
                         (rx + 2, by + 2), (rx + 2, by + lh // 3), 1)


def _sandals(sc, x, y, s, col, dark):
    """Two flat shoe silhouettes."""
    sw = max(5, s * 2 // 5)
    sh = max(3, s // 5)
    sole_h = max(2, s // 12)
    gap = max(2, s // 8)
    total = sw * 2 + gap
    bx = x + (s - total) // 2
    by = y + s * 7 // 16
    for i in range(2):
        rx = bx + i * (sw + gap)
        # Sole
        pygame.draw.rect(sc, dark, (rx - 1, by + sh, sw + 2, sole_h), border_radius=1)
        # Upper
        pygame.draw.rect(sc, col,  (rx, by, sw, sh), border_radius=max(2, s // 12))
        pygame.draw.rect(sc, dark, (rx, by, sw, sh), 1, border_radius=max(2, s // 12))
        # Strap
        pygame.draw.line(sc, dark, (rx + 1, by + sh // 2), (rx + sw - 2, by + sh // 2), 1)
        # Highlight
        pygame.draw.line(sc, (min(255, col[0] + 45), min(255, col[1] + 40), min(255, col[2] + 25)),
                         (rx + 2, by + 2), (rx + sw - 3, by + 2), 1)


def _snowflake_pendant(sc, cx, py, s):
    r = max(3, s // 6)
    col = (180, 225, 255)
    for i in range(6):
        a = math.radians(i * 60 - 90)
        ex = int(cx + r * math.cos(a))
        ey = int(py + r * math.sin(a))
        pygame.draw.line(sc, col, (cx, py), (ex, ey), 1)
    pygame.draw.circle(sc, (220, 245, 255), (cx, py), max(1, r // 3))


def _cup(sc, x, y, s, col, dark, liquid_col):
    """Mug with a coloured liquid fill and steam wisps."""
    cw = max(6, s * 11 // 16)
    ch = max(5, s *  7 // 16)
    cx2 = x + (s - cw) // 2
    cy2 = y + s * 5 // 16
    pts = [(cx2, cy2 + ch), (cx2 + cw, cy2 + ch), (cx2 + cw - 1, cy2), (cx2 + 1, cy2)]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    # Liquid fill
    lh = max(2, ch // 2)
    pygame.draw.rect(sc, liquid_col, (cx2 + 1, cy2 + ch - lh, cw - 2, lh - 1))
    # Handle arc
    hw = max(3, s // 6)
    pygame.draw.arc(sc, dark,
                    pygame.Rect(cx2 + cw - 1, cy2 + ch // 4, hw, ch // 2),
                    -math.pi * 0.5, math.pi * 0.5, max(1, s // 14))
    # Steam wisps
    for i in range(2):
        sx2 = cx2 + cw // 4 + i * (cw // 3)
        pygame.draw.line(sc, (210, 215, 222), (sx2, cy2 - 2), (sx2 + 1, cy2 - 5), 1)


def _bowl(sc, x, y, s, col, dark, fill_col):
    """A bowl filled with stew."""
    cx2 = x + s // 2
    bw  = max(8, s * 3 // 4)
    bh  = max(4, s * 3 // 8)
    by  = y + s * 3 // 8
    pts = [(cx2 - bw // 2, by), (cx2 + bw // 2, by),
           (cx2 + bw // 3, by + bh), (cx2 - bw // 3, by + bh)]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    # Fill
    fi = [(cx2 - bw // 2 + 1, by + 1), (cx2 + bw // 2 - 1, by + 1),
          (cx2 + bw // 3 - 1, by + bh - 1), (cx2 - bw // 3 + 1, by + bh - 1)]
    pygame.draw.polygon(sc, fill_col, fi)
    # Rim highlight
    pygame.draw.line(sc, (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 25)),
                     (cx2 - bw // 2 + 1, by), (cx2 + bw // 2 - 1, by), 1)


def _flask(sc, x, y, s, col, dark):
    """Potion flask with a cork, round body and shine dot."""
    cx2 = x + s // 2
    nw, nh = max(2, s // 6), max(3, s // 5)
    nx, ny = cx2 - nw // 2, y + s // 8
    # Cork
    pygame.draw.rect(sc, (165, 120, 60), (nx - 1, ny - max(2, s // 10), nw + 2, max(2, s // 10)), border_radius=1)
    # Neck
    pygame.draw.rect(sc, dark, (nx, ny, nw, nh))
    pygame.draw.rect(sc, col,  (nx + 1, ny, nw - 2, nh))
    # Body
    r   = max(4, s * 3 // 8)
    bcy = ny + nh + r - max(1, s // 12)
    pygame.draw.circle(sc, col,  (cx2, bcy), r)
    pygame.draw.circle(sc, dark, (cx2, bcy), r, max(1, r // 5))
    # Shine
    shine = (min(255, col[0] + 65), min(255, col[1] + 65), min(255, col[2] + 65))
    pygame.draw.circle(sc, shine, (cx2 - r // 3, bcy - r // 3), max(1, r // 4))


# ---------------------------------------------------------------------------
# Node draw functions  (sc, x, y, s)
# ---------------------------------------------------------------------------

def _node_tree(sc, x, y, s):
    """Standard round-canopy tree (oak / forest / plains)."""
    cx = x + s // 2
    tw = max(3, s // 5)
    th = max(4, s // 3)
    pygame.draw.rect(sc, (92, 60, 20), (cx - tw // 2, y + s - th, tw, th))
    r  = s * 2 // 5
    cy = y + s - th - r + r // 4   # canopy bottom overlaps trunk top
    pygame.draw.circle(sc, (35, 90, 35), (cx, cy), r)
    pygame.draw.circle(sc, (20, 60, 20), (cx, cy), r, max(1, s // 12))
    pygame.draw.circle(sc, (52, 118, 52), (cx - r // 3, cy - r // 3), max(2, r // 4))


def _node_pine_tree(sc, x, y, s):
    """Tall triangular pine / spruce — trunk visible between layers, snow at peak."""
    cx = x + s // 2
    tw = max(2, s // 7)
    # Trunk — roots at tile-ground level, extends to bounding-box bottom
    pygame.draw.rect(sc, (82, 50, 16), (cx - tw // 2, y + s * 56 // 100, tw, s - s * 56 // 100))
    # Four branch layers drawn bottom→top; trunk shows through gaps between them
    for base_f, peak_f, hw_f, col in [
        (0.82, 0.58, 0.32, ( 26,  70,  26)),   # widest / lowest
        (0.65, 0.42, 0.26, ( 28,  86,  30)),
        (0.48, 0.26, 0.20, ( 22, 102,  34)),
        (0.30, 0.10, 0.14, ( 16, 116,  38)),   # narrowest / highest
    ]:
        bx = y + int(s * base_f)
        px = y + int(s * peak_f)
        hw = int(s * hw_f)
        pygame.draw.polygon(sc, col, [(cx - hw, bx), (cx + hw, bx), (cx, px)])
    # Snow cap at the actual tip of the topmost layer
    sc_hw = max(2, s // 14)
    pygame.draw.polygon(sc, (205, 218, 228), [
        (cx - sc_hw, y + int(s * 0.14)),
        (cx + sc_hw, y + int(s * 0.14)),
        (cx,          y + int(s * 0.08)),
    ])


def _node_jungle_tree(sc, x, y, s):
    """Tall jungle tree with wide dark-green canopy and thick trunk."""
    cx = x + s // 2
    tw = max(4, s // 5)
    # Trunk — starts well above canopy bottom so a bit peeks through at the base
    pygame.draw.rect(sc, (72, 46, 16), (cx - tw // 2, y + s * 45 // 100, tw, s - s * 45 // 100))
    # Root buttress flares
    for sign in (-1, 1):
        rx = cx + sign * (tw // 2)
        pygame.draw.polygon(sc, (62, 38, 13), [
            (rx,                       y + s),
            (rx + sign * (s // 8),     y + s * 7 // 8),
            (rx,                       y + s * 3 // 4),
        ])
    # Primary canopy — large circle; top touches bounding-box top
    r  = int(s * 0.46)
    cy = y + r
    pygame.draw.circle(sc, (20, 98, 28), (cx, cy), r)
    pygame.draw.circle(sc, (10, 72, 18), (cx, cy), r, max(1, s // 14))
    # Secondary canopy blob (right-offset for asymmetry)
    r2 = int(s * 0.30)
    pygame.draw.circle(sc, (28, 112, 34), (cx + s // 5, y + int(s * 0.38)), r2)
    # Left-side lighter highlight
    pygame.draw.circle(sc, (46, 138, 50), (cx - s // 6, y + int(s * 0.26)), max(2, s // 9))


def _node_palm_tree(sc, x, y, s):
    """Curved palm tree: leaning trunk, fan of fronds at top."""
    import math as _math
    cx = x + s // 2
    tw = max(2, s // 8)
    lean = s // 10   # trunk leans slightly to the right
    # Lower trunk (vertical-ish, wider base)
    pygame.draw.rect(sc, (175, 135, 65), (cx - tw // 2,        y + s * 60 // 100, tw, s * 40 // 100))
    # Upper trunk (leans left, offset by lean)
    pygame.draw.rect(sc, (158, 118, 52), (cx - tw // 2 - lean, y + s * 30 // 100, tw, s * 32 // 100))
    # Crown centre (top of upper trunk)
    fcx = cx - lean
    fcy = y + s * 30 // 100
    frond_col  = (48, 145, 38)
    frond_dark = (26,  98, 22)
    # 8 fronds in a fan — angles biased upward, no straight-down fronds
    for angle_deg in (-140, -100, -65, -30, 10, 50, 85, 120):
        a  = _math.radians(angle_deg)
        lx = s * 0.36
        ly = s * 0.28
        ex = fcx + int(_math.cos(a) * lx)
        ey = fcy + int(_math.sin(a) * ly)
        pygame.draw.line(sc, frond_col, (fcx, fcy), (ex, ey), max(1, s // 14))
        # Darker tip
        mx = fcx + int(_math.cos(a) * lx * 0.6)
        my = fcy + int(_math.sin(a) * ly * 0.6)
        pygame.draw.line(sc, frond_dark, (mx, my), (ex, ey), max(1, s // 18))


def _node_stick_pile(sc, x, y, s):
    col, dark = (162, 112, 52), (108, 68, 20)
    w = max(1, s // 9)
    for x1, y1, x2, y2 in [
        (x + s // 8,  y + s * 2 // 3, x + s * 5 // 8, y + s // 5),
        (x + s // 4,  y + s - 3,      x + s - 3,       y + s * 2 // 5),
        (x + s // 6,  y + s // 2,     x + s * 3 // 4,  y + s - s // 5),
    ]:
        pygame.draw.line(sc, col,  (x1,     y1),     (x2,     y2),     w)
        pygame.draw.line(sc, dark, (x1 + 1, y1 + 1), (x2 + 1, y2 + 1), max(1, w - 1))


def _node_bone_pile(sc, x, y, s):
    """Two crossed bones lying on the ground."""
    col  = (218, 208, 188)
    dark = (155, 145, 128)
    bw   = max(2, s // 7)
    # Bone 1: NW → SE
    x1a, y1a = x + s // 6,     y + s // 6
    x1b, y1b = x + s * 5 // 6, y + s * 5 // 6
    pygame.draw.line(sc, col, (x1a, y1a), (x1b, y1b), bw)
    for ex, ey in [(x1a, y1a), (x1b, y1b)]:
        pygame.draw.circle(sc, col,  (ex, ey), max(2, s // 8))
        pygame.draw.circle(sc, dark, (ex, ey), max(2, s // 8), 1)
    # Bone 2: NE → SW (crossing)
    x2a, y2a = x + s * 5 // 6, y + s // 6
    x2b, y2b = x + s // 6,     y + s * 5 // 6
    pygame.draw.line(sc, col, (x2a, y2a), (x2b, y2b), bw)
    for ex, ey in [(x2a, y2a), (x2b, y2b)]:
        pygame.draw.circle(sc, col,  (ex, ey), max(2, s // 8))
        pygame.draw.circle(sc, dark, (ex, ey), max(2, s // 8), 1)


def _node_stone(sc, x, y, s):
    """Cluster of 4 rocks of varying sizes."""
    rocks = [
        (x + s * 2 // 5, y + s * 11 // 16, s * 5 // 16, (148, 148, 148), (90, 90, 90)),   # big front-left
        (x + s * 3 // 5, y + s *  9 // 16, s * 3 //  8, (162, 162, 162), (100, 100, 100)), # big center
        (x + s * 4 // 5, y + s *  5 //  8, s *  1 //  4, (145, 145, 145), (88,  88,  88)), # small right
        (x + s * 1 // 5, y + s *  3 //  8, s *  3 // 16, (155, 155, 155), (96,  96,  96)), # small back-left
    ]
    for cx, cy, r, col, dark in rocks:
        pygame.draw.circle(sc, col,  (cx, cy), r)
        pygame.draw.circle(sc, dark, (cx, cy), r, max(1, r // 4))
        pygame.draw.circle(sc, (200, 200, 200), (cx - r // 3, cy - r // 3), max(1, r // 4))


def _node_iron_ore(sc, x, y, s):
    """Rocky cluster with bright orange ore spots and veins."""
    # Base rocks (warm brownish-gray)
    rocks = [
        (x + s * 2 // 5, y + s * 11 // 16, s * 5 // 16, (118, 98, 72), (75, 58, 38)),
        (x + s * 3 // 5, y + s *  9 // 16, s * 3 //  8, (128, 108, 82), (82, 62, 42)),
        (x + s * 4 // 5, y + s *  5 //  8, s *  1 //  4, (115, 95, 70), (72, 55, 35)),
    ]
    for cx, cy, r, col, dark in rocks:
        pygame.draw.circle(sc, col,  (cx, cy), r)
        pygame.draw.circle(sc, dark, (cx, cy), r, max(1, r // 4))
    # Ore spots on top
    ore = [(210, 128, 55), (228, 148, 70)]
    spots = [
        (x + s // 3,     y + s * 7 // 12, max(2, s // 9)),
        (x + s * 3 // 5, y + s * 5 // 12, max(2, s // 8)),
        (x + s * 4 // 5, y + s * 7 // 12, max(2, s // 11)),
    ]
    for i, (sx2, sy2, r) in enumerate(spots):
        pygame.draw.circle(sc, ore[i % 2], (sx2, sy2), r)
    # Vein streaks
    pygame.draw.line(sc, (195, 115, 50),
                     (x + s // 4, y + s * 7 // 12),
                     (x + s * 2 // 3, y + s * 3 // 8), max(1, s // 14))


def _node_coal(sc, x, y, s):
    """Cluster of dark angular coal chunks with a subtle sheen."""
    # Draw three dark rounded-polygon chunks
    chunks = [
        (x + s * 2 // 5, y + s * 11 // 16, s * 5 // 16, (40, 40, 42)),
        (x + s * 3 // 5, y + s *  9 // 16, s * 3 //  8, (35, 35, 38)),
        (x + s * 4 // 5, y + s *  5 //  8, s *  1 //  4, (44, 44, 46)),
    ]
    for cx, cy, r, col in chunks:
        # Jagged polygon by offsetting 8 points around a circle
        pts = []
        for i in range(8):
            a   = math.pi * 2 * i / 8
            jit = r * (0.78 if i % 2 == 0 else 1.0)  # alternating inset for jagged look
            pts.append((int(cx + math.cos(a) * jit), int(cy + math.sin(a) * jit)))
        pygame.draw.polygon(sc, col, pts)
        pygame.draw.polygon(sc, (18, 18, 18), pts, 1)
        # Coal sheen highlight
        pygame.draw.line(sc, (72, 72, 80),
                         (cx - r // 2, cy - r // 2),
                         (cx + r // 4, cy - r // 3), 1)


def _node_herb(sc, x, y, s):
    stem, leaf = (35, 155, 55), (65, 212, 88)
    bx, by = x + s // 2, y + s - 2
    for tx, ty in [(x + s // 4, y + s // 4), (x + s // 2, y + 2), (x + 3 * s // 4, y + s // 4)]:
        pygame.draw.line(sc, stem, (bx, by), (tx, ty), max(1, s // 9))
        pygame.draw.circle(sc, leaf, (tx, ty), max(2, s // 6))


def _node_cactus(sc, x, y, s):
    col, dark = (110, 175, 40), (68, 120, 18)
    cx = x + s // 2
    bw, bh = max(4, s // 3), s * 3 // 4
    # Body
    pygame.draw.rect(sc, col,  (cx - bw // 2, y + s // 4, bw, bh), border_radius=2)
    pygame.draw.rect(sc, dark, (cx - bw // 2, y + s // 4, bw, bh), 1, border_radius=2)
    # Arms
    aw, ah = max(3, s // 4), max(3, s // 4)
    arm_y = y + s // 2 - ah // 2
    for sign in (-1, 1):
        ax = cx + sign * (bw // 2)
        if sign == -1:
            ax -= aw
        pygame.draw.rect(sc, col,  (ax, arm_y, aw, ah), border_radius=1)
        pygame.draw.rect(sc, dark, (ax, arm_y, aw, ah), 1, border_radius=1)
        # Vertical stub atop arm
        pygame.draw.rect(sc, col, (ax, arm_y - ah // 2, aw, ah // 2 + 1), border_radius=1)


def _node_reed(sc, x, y, s):
    stem = (38, 140, 70)
    for ox in (-s // 5, 0, s // 5):
        cx2 = x + s // 2 + ox
        pygame.draw.line(sc, stem, (cx2, y + s - 2), (cx2, y + s // 4), max(1, s // 10))
        pr = max(1, s // 7)
        pygame.draw.ellipse(sc, (92, 55, 18), (cx2 - pr // 2, y + s // 5, pr, pr + 1))


def _node_seashell(sc, x, y, s):
    cx, cy = x + s // 2, y + s - 3
    col, dark = (255, 168, 180), (205, 115, 135)
    r = s * 2 // 5
    for i in range(5):
        a = math.radians(15 + i * 33)
        ex, ey = int(cx + r * math.cos(a)), int(cy - r * math.sin(a))
        pygame.draw.line(sc, col if i % 2 == 0 else dark, (cx, cy), (ex, ey), max(1, s // 10))
    pygame.draw.arc(sc, dark, (x + 2, y + s // 3, s - 4, s * 2 // 3), 0, math.pi, max(1, s // 10))
    pygame.draw.circle(sc, dark, (cx, cy), max(2, s // 9))


def _node_mushroom(sc, x, y, s):
    cx = x + s // 2
    sw, sh = max(3, s // 4), max(3, s // 3)
    pygame.draw.rect(sc, (225, 210, 190), (cx - sw // 2, y + s - sh, sw, sh), border_radius=1)
    cr = s * 2 // 5
    cy2 = y + s // 2
    pygame.draw.circle(sc, (190, 38, 38), (cx, cy2), cr)
    pygame.draw.circle(sc, (128, 18, 18), (cx, cy2), cr, max(1, s // 10))
    dr = max(1, s // 9)
    pygame.draw.circle(sc, (255, 255, 255), (cx - s // 5, cy2 - s // 8), dr)
    pygame.draw.circle(sc, (255, 255, 255), (cx + s // 6, cy2 + 1), dr)


def _node_snow(sc, x, y, s):
    cx, cy = x + s // 2, y + s // 2
    r = s // 2 - 2
    col = (195, 238, 255)
    for i in range(6):
        a = math.radians(i * 60)
        ex, ey = int(cx + r * math.cos(a)), int(cy + r * math.sin(a))
        pygame.draw.line(sc, col, (cx, cy), (ex, ey), max(1, s // 10))
    pygame.draw.circle(sc, (248, 252, 255), (cx, cy), max(2, s // 7))


# ---------------------------------------------------------------------------
# New materials: Iron Bar (20), Stone Brick (21)
# Placeable items: Campfire (30), Crafting Table (31), Furnace (32)
# ---------------------------------------------------------------------------

def _iron_bar(sc, x: int, y: int, s: int) -> None:
    """Silver ingot — grey rectangle with angled highlight."""
    m = max(1, s // 6)
    bw, bh = int(s * 0.72), int(s * 0.42)
    bx, by = x + (s - bw) // 2, y + (s - bh) // 2 + m
    pygame.draw.rect(sc, (140, 145, 155), (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, (80, 85, 90),    (bx, by, bw, bh), 1, border_radius=2)
    # top-left highlight stripe
    hw = max(2, bw // 3)
    pygame.draw.polygon(sc, (200, 210, 220), [
        (bx + 2, by + 2), (bx + hw, by + 2),
        (bx + hw - 4, by + bh // 3), (bx + 2, by + bh // 3),
    ])


def _stone_brick(sc, x: int, y: int, s: int) -> None:
    """Grey rectangle with mortar lines."""
    bw, bh = int(s * 0.80), int(s * 0.58)
    bx, by = x + (s - bw) // 2, y + (s - bh) // 2
    pygame.draw.rect(sc, (110, 112, 118), (bx, by, bw, bh))
    pygame.draw.rect(sc, (60, 62, 68),    (bx, by, bw, bh), 1)
    # mortar lines
    my = by + bh // 2
    pygame.draw.line(sc, (70, 72, 78), (bx, my), (bx + bw, my), 1)
    mx = bx + bw // 2
    pygame.draw.line(sc, (70, 72, 78), (mx, by), (mx, my), 1)
    pygame.draw.line(sc, (70, 72, 78), (bx + bw // 4, my), (bx + bw // 4, by + bh), 1)


def _campfire_item(sc, x: int, y: int, s: int) -> None:
    """Small log pile with flame — inventory icon for Campfire."""
    cx = x + s // 2
    # logs
    log_col = (100, 60, 20)
    pygame.draw.line(sc, log_col, (x + 3, y + s - 5), (x + s - 3, y + s // 2 + 2), 3)
    pygame.draw.line(sc, log_col, (x + s - 5, y + s - 5), (x + 3, y + s // 2 + 2), 3)
    # flame
    fy = y + s // 2 - 2
    fh = s // 3
    pygame.draw.polygon(sc, (255, 120, 0), [(cx, fy - fh), (cx - 5, fy + 2), (cx + 5, fy + 2)])
    pygame.draw.polygon(sc, (255, 220, 50), [(cx, fy - fh + 4), (cx - 2, fy + 1), (cx + 2, fy + 1)])


def _torch_item(sc, x: int, y: int, s: int) -> None:
    """Wooden stick with flame tip — inventory icon for Torch."""
    cx = x + s // 2
    stick_top = y + s // 3
    stick_bot = y + s - 4
    pygame.draw.line(sc, (110, 68, 22), (cx, stick_top), (cx, stick_bot), 3)
    fh = s // 4
    pygame.draw.polygon(sc, (255, 140, 10), [(cx, stick_top - fh), (cx - 4, stick_top + 2), (cx + 4, stick_top + 2)])
    pygame.draw.polygon(sc, (255, 230, 80), [(cx, stick_top - fh + 3), (cx - 2, stick_top + 1), (cx + 2, stick_top + 1)])


def _lantern_item(sc, x: int, y: int, s: int) -> None:
    """Iron-framed lantern with warm glow — inventory icon for Lantern."""
    cx = x + s // 2
    cy = y + s // 2 + 2
    hw, hh = max(5, s // 5), max(6, s // 4)
    # Short chain
    pygame.draw.line(sc, (130, 125, 140), (cx, y + 3), (cx, cy - hh), 1)
    # Glow fill
    pygame.draw.rect(sc, (255, 200, 60), (cx - hw, cy - hh, hw * 2, hh * 2))
    pygame.draw.circle(sc, (255, 240, 150), (cx, cy), max(2, hw - 2))
    # Iron frame
    pygame.draw.rect(sc, (88, 82, 100), (cx - hw, cy - hh, hw * 2, hh * 2), 2)
    pygame.draw.line(sc, (88, 82, 100), (cx - hw, cy), (cx + hw, cy), 1)
    pygame.draw.line(sc, (88, 82, 100), (cx, cy - hh), (cx, cy + hh), 1)


def _crafting_table_item(sc, x: int, y: int, s: int) -> None:
    """Brown square with tool surface lines — inventory icon for Crafting Table."""
    bw = int(s * 0.78)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (130, 80, 30), (bx, by, bw, bw), border_radius=2)
    pygame.draw.rect(sc, (80, 45, 10),  (bx, by, bw, bw), 1, border_radius=2)
    for gx in range(bx + 5, bx + bw - 2, 6):
        pygame.draw.line(sc, (105, 60, 20), (gx, by + 3), (gx, by + bw - 3), 1)
    # top edge lighter strip (work surface)
    pygame.draw.rect(sc, (155, 100, 45), (bx + 1, by + 1, bw - 2, 4))


def _furnace_item(sc, x: int, y: int, s: int) -> None:
    """Dark stone square with orange glow slot — inventory icon for Furnace."""
    bw = int(s * 0.78)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (80, 80, 80), (bx, by, bw, bw), border_radius=2)
    pygame.draw.rect(sc, (45, 45, 45), (bx, by, bw, bw), 1, border_radius=2)
    gw, gh = bw // 3, bw // 4
    gx, gy = bx + (bw - gw) // 2, by + (bw - gh) // 2 + 2
    pygame.draw.rect(sc, (200, 100, 20), (gx, gy, gw, gh), border_radius=1)


def _wood_wall_item(sc, x: int, y: int, s: int) -> None:
    bw = int(s * 0.80)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (110, 65, 25), (bx, by, bw, bw))
    pygame.draw.rect(sc, (70, 40, 12),  (bx, by, bw, bw), 1)
    for gx in range(bx + 4, bx + bw - 2, max(4, bw // 4)):
        pygame.draw.line(sc, (80, 48, 18), (gx, by + 2), (gx, by + bw - 2), 1)


def _stone_wall_item(sc, x: int, y: int, s: int) -> None:
    bw = int(s * 0.80)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (92, 92, 98), (bx, by, bw, bw))
    pygame.draw.rect(sc, (55, 55, 60), (bx, by, bw, bw), 1)
    m = by + bw // 2
    pygame.draw.line(sc, (62, 62, 68), (bx + 2, m), (bx + bw - 2, m), 1)
    pygame.draw.line(sc, (62, 62, 68), (bx + bw // 3, by + 2), (bx + bw // 3, m), 1)
    pygame.draw.line(sc, (62, 62, 68), (bx + 2 * bw // 3, m), (bx + 2 * bw // 3, by + bw - 2), 1)


def _door_item(sc, x: int, y: int, s: int) -> None:
    dw = max(4, s * 3 // 5)
    dx = x + (s - dw) // 2
    pygame.draw.rect(sc, (120, 72, 28), (dx, y + 2, dw, s - 4))
    pygame.draw.rect(sc, (70, 38, 10),  (dx, y + 2, dw, s - 4), 1)
    pygame.draw.circle(sc, (200, 160, 60), (dx + dw - 4, y + s // 2), 2)


def _bed_item(sc, x: int, y: int, s: int) -> None:
    bw = int(s * 0.80)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (100, 60, 20), (bx, by, bw, bw))
    pygame.draw.rect(sc, (65, 38, 10),  (bx, by, bw, bw), 1)
    pygame.draw.rect(sc, (240, 230, 200), (bx + 2, by + 2, bw - 4, bw // 3))
    pygame.draw.rect(sc, (80, 120, 180),  (bx + 2, by + 2 + bw // 3, bw - 4, bw - 4 - bw // 3))


def _stone_brick_wall_item(sc, x: int, y: int, s: int) -> None:
    bw = int(s * 0.80)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (138, 116, 84), (bx, by, bw, bw))
    pygame.draw.rect(sc, (90,  72, 50),  (bx, by, bw, bw), 1)
    m = by + bw // 2
    pygame.draw.line(sc, (90, 72, 50), (bx + 2, m), (bx + bw - 2, m), 1)
    pygame.draw.line(sc, (90, 72, 50), (bx + bw // 3,     by + 2), (bx + bw // 3,     m), 1)
    pygame.draw.line(sc, (90, 72, 50), (bx + 2 * bw // 3, m),      (bx + 2 * bw // 3, by + bw - 2), 1)


def _stone_brick_floor_item(sc, x: int, y: int, s: int) -> None:
    bw = int(s * 0.80)
    bx, by = x + (s - bw) // 2, y + (s - bw) // 2
    pygame.draw.rect(sc, (125, 106, 78), (bx, by, bw, bw))
    m = by + bw // 2
    pygame.draw.line(sc, (98, 82, 60), (bx + 2, m), (bx + bw - 2, m), 1)
    pygame.draw.line(sc, (98, 82, 60), (bx + bw // 2, by + 2), (bx + bw // 2, m), 1)
    pygame.draw.line(sc, (98, 82, 60), (bx + bw // 4, m), (bx + bw // 4, by + bw - 2), 1)
    pygame.draw.line(sc, (98, 82, 60), (bx + 3 * bw // 4, m), (bx + 3 * bw // 4, by + bw - 2), 1)


# ---------------------------------------------------------------------------
# Public dispatch tables
# ---------------------------------------------------------------------------



def _carbon_item(sc, x, y, s):
    """Carbon: processed coal — large dark chunk with faint blue-grey sheen."""
    cx, cy = x + s // 2, y + s // 2
    r = s // 2 - 2
    pts = [
        (cx - r,      cy - r // 4), (cx - r // 4, cy - r),
        (cx + r // 2, cy - r + 2),  (cx + r,      cy),
        (cx + r // 2, cy + r),      (cx - r // 2, cy + r - 1),
    ]
    pygame.draw.polygon(sc, (30, 30, 34), pts)
    pygame.draw.polygon(sc, (15, 15, 18), pts, 1)
    # Blue-grey sheen highlights (carbon vs coal)
    pygame.draw.line(sc, (72, 72, 95), (cx - r // 2, cy - r // 2), (cx + r // 4, cy - r // 3), 1)
    pygame.draw.circle(sc, (62, 62, 85), (cx + r // 4, cy - r // 4), max(1, s // 10))


def _alloy_forge_item(sc, x, y, s):
    """Alloy Forge item icon: dark iron box with brick trim and gold glow window."""
    m  = max(1, s // 6)
    bw, bh = s - m * 2, s - m * 2
    bx, by = x + m, y + m
    pygame.draw.rect(sc, (55, 50, 55), (bx, by, bw, bh), border_radius=1)
    pygame.draw.rect(sc, (30, 25, 30), (bx, by, bw, bh), 1, border_radius=1)
    sw = max(2, s // 8)
    pygame.draw.rect(sc, (105, 82, 58), (bx,             by + sw, sw, bh - sw * 2))
    pygame.draw.rect(sc, (105, 82, 58), (bx + bw - sw,   by + sw, sw, bh - sw * 2))
    gw, gh = max(4, s // 4), max(3, s // 6)
    gx2 = bx + (bw - gw) // 2
    gy2 = by + (bh - gh) // 2
    pygame.draw.rect(sc, (215, 140, 28), (gx2, gy2, gw, gh))
    pygame.draw.rect(sc, (255, 200, 80), (gx2 + 1, gy2 + 1, max(1, gw - 2), max(1, gh - 2)))


def _chest_item(sc, x: int, y: int, s: int) -> None:
    """Chest item icon: brown wooden box with metal corner brackets and a gold latch."""
    m  = max(1, s // 8)
    bw, bh = s - m * 2, s - m * 2
    bx, by = x + m, y + m
    # Body — warm brown wood
    pygame.draw.rect(sc, (140, 90, 45), (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, (80, 50, 20),  (bx, by, bw, bh), 1, border_radius=2)
    # Lid divider (horizontal)
    ly = by + bh * 2 // 5
    pygame.draw.line(sc, (60, 38, 15), (bx + 1, ly), (bx + bw - 2, ly), 1)
    # Metal corner brackets
    cs = max(2, s // 8)
    for cx2, cy2 in [(bx, by), (bx + bw - cs, by),
                     (bx, by + bh - cs), (bx + bw - cs, by + bh - cs)]:
        pygame.draw.rect(sc, (60, 60, 65), (cx2, cy2, cs, cs))
    # Gold latch centred on the divider
    lw, lh = max(3, s // 7), max(2, s // 9)
    lx2 = bx + (bw - lw) // 2
    ly2 = ly - lh // 2
    pygame.draw.rect(sc, (200, 160, 40), (lx2, ly2, lw, lh), border_radius=1)
    pygame.draw.rect(sc, (140, 100, 20), (lx2, ly2, lw, lh), 1, border_radius=1)


def _part_maker_item(sc, x, y, s):
    """Part Maker station icon — workbench with a vice/clamp."""
    base_col, dark_col = (90, 70, 45), (55, 38, 18)
    top_col,  top_dark = (115, 88, 52), (70, 50, 22)
    metal_col = (148, 148, 158)
    # Base platform
    bw, bh = int(s * 0.85), int(s * 0.30)
    bx, by = x + (s - bw) // 2, y + s - bh - max(1, s // 10)
    pygame.draw.rect(sc, base_col, (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, dark_col, (bx, by, bw, bh), 1, border_radius=2)
    # Table top
    tw, th = int(s * 0.78), max(3, s // 7)
    tx, ty = x + (s - tw) // 2, by - th
    pygame.draw.rect(sc, top_col, (tx, ty, tw, th), border_radius=1)
    pygame.draw.rect(sc, top_dark, (tx, ty, tw, th), 1, border_radius=1)
    # Vice screw (left side)
    vx, vy = tx, ty + th // 2
    pygame.draw.circle(sc, metal_col, (vx, vy), max(2, s // 8))
    pygame.draw.circle(sc, dark_col, (vx, vy), max(2, s // 8), 1)
    # Part being worked (small bar on table)
    pw, ph = max(4, s // 4), max(2, s // 9)
    px2, py2 = tx + tw // 4, ty - ph - 1
    pygame.draw.rect(sc, (162, 162, 168), (px2, py2, pw, ph), border_radius=1)
    pygame.draw.rect(sc, (90, 90, 98), (px2, py2, pw, ph), 1, border_radius=1)


# ── Art pass helpers ──────────────────────────────────────────────────────────

def _wand(sc, x, y, s, orb_col, orb_dark, staff_col=(118, 82, 32)):
    """Wand: diagonal staff with a large glowing magical orb at the tip.
    Visually distinct from swords — no blade, no guard, just staff + orb."""
    sdark = (max(0, staff_col[0] - 35), max(0, staff_col[1] - 28), max(0, staff_col[2] - 15))
    slite = (min(255, staff_col[0] + 45), min(255, staff_col[1] + 38), min(255, staff_col[2] + 22))
    sw = max(1, s // 9)
    # Shaft: bottom-left → just below the orb
    sx1, sy1 = x + s // 5, y + s - s // 7
    sx2, sy2 = x + s * 10 // 16, y + s * 7 // 20
    pygame.draw.line(sc, staff_col, (sx1, sy1), (sx2, sy2), sw + 1)
    pygame.draw.line(sc, sdark,     (sx1 + 1, sy1), (sx2 + 1, sy2), sw)
    # Decorative band near middle
    mx, my = (sx1 + sx2) // 2, (sy1 + sy2) // 2
    pygame.draw.circle(sc, slite, (mx, my), max(1, sw + 1))
    # Orb at tip (upper-right)
    orb_cx = x + s * 3 // 4
    orb_cy = y + s // 5
    orb_r  = max(3, s * 3 // 14)
    # Aura ring (slightly darker, drawn before the orb)
    pygame.draw.circle(sc, orb_dark, (orb_cx, orb_cy), orb_r + max(2, s // 11))
    # Main orb
    pygame.draw.circle(sc, orb_col,  (orb_cx, orb_cy), orb_r)
    pygame.draw.circle(sc, orb_dark, (orb_cx, orb_cy), orb_r, 1)
    # Specular highlight
    hi = (min(255, orb_col[0] + 80), min(255, orb_col[1] + 75), min(255, orb_col[2] + 70))
    pygame.draw.circle(sc, hi, (orb_cx - orb_r // 3, orb_cy - orb_r // 3), max(1, orb_r // 3))
    # Secondary shimmer
    sp = (min(255, orb_col[0] + 35), min(255, orb_col[1] + 32), min(255, orb_col[2] + 30))
    pygame.draw.circle(sc, sp, (orb_cx + orb_r // 3, orb_cy + orb_r // 4), max(1, orb_r // 5))


def _blade_part(sc, x, y, s, col, dark, lite):
    """Blade component — elongated pointed-top diamond (blade silhouette, not a bar)."""
    m  = max(1, s // 7)
    hw = max(2, s // 4)
    cx = x + s // 2
    pts = [
        (cx,           y + m),
        (cx + hw,      y + s * 2 // 5),
        (cx + hw // 2, y + s - m),
        (cx - hw // 2, y + s - m),
        (cx - hw,      y + s * 2 // 5),
    ]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    # Center spine
    pygame.draw.line(sc, lite, (cx, y + m + 2), (cx, y + s * 3 // 5), 1)
    # Edge bevel (right side)
    pygame.draw.line(sc, dark, (cx + hw // 2, y + s * 2 // 5 + 2), (cx + hw // 4, y + s - m - 2), 1)


def _axe_head_part(sc, x, y, s, col, dark, lite):
    """Axe head component — fan/wedge shape, cutting edge right, poll left."""
    m = max(1, s // 8)
    pts = [
        (x + m,          y + s // 3),
        (x + s * 3 // 5, y + m),
        (x + s - m,      y + s // 2),
        (x + s * 3 // 5, y + s - m),
        (x + m,          y + s * 2 // 3),
        (x + m + s // 7, y + s // 2),      # concave poll notch
    ]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    # Cutting edge highlight
    pygame.draw.line(sc, lite, (x + s * 3 // 5 + 1, y + m + 1), (x + s - m - 1, y + s // 2), 1)
    pygame.draw.line(sc, lite, (x + s - m - 1, y + s // 2), (x + s * 3 // 5 + 1, y + s - m - 1), 1)


def _pick_head_part(sc, x, y, s, col, dark, lite):
    """Pickaxe head component — horizontal bar with two asymmetric curved tips."""
    cy  = y + s // 2
    hw  = max(2, s // 9)
    bw  = int(s * 0.62)
    bx  = x + (s - bw) // 2
    tl  = max(2, s // 7)
    # Central bar
    pygame.draw.rect(sc, col,  (bx, cy - hw, bw, hw * 2), border_radius=1)
    pygame.draw.rect(sc, dark, (bx, cy - hw, bw, hw * 2), 1, border_radius=1)
    # Left tip (curves down — digging end)
    pts_l = [(bx, cy - hw + 1), (bx, cy + hw - 1), (bx - tl, cy + tl)]
    pygame.draw.polygon(sc, col, pts_l)
    pygame.draw.polygon(sc, dark, pts_l, 1)
    # Right tip (curves up — hook end)
    pts_r = [(bx + bw, cy - hw + 1), (bx + bw, cy + hw - 1), (bx + bw + tl, cy - tl)]
    pygame.draw.polygon(sc, col, pts_r)
    pygame.draw.polygon(sc, dark, pts_r, 1)
    # Top-bar highlight
    pygame.draw.line(sc, lite, (bx + 1, cy - hw + 1), (bx + bw - 2, cy - hw + 1), 1)


def _plate_part(sc, x, y, s, col, dark, lite):
    """Armor plate component — contoured chest-plate silhouette."""
    m  = max(1, s // 8)
    bw = s - m * 2
    bh = max(6, s * 11 // 20)
    bx = x + m
    by = y + (s - bh) // 2
    pts = [
        (bx + bw // 5,     by),
        (bx + bw * 4 // 5, by),
        (bx + bw,          by + m),
        (bx + bw - m,      by + bh),
        (bx + m,           by + bh),
        (bx,               by + m),
    ]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    cx = x + s // 2
    # Center chest crease
    pygame.draw.line(sc, dark, (cx, by + 2), (cx, by + bh // 2), 1)
    # Horizontal pec ridge
    pygame.draw.line(sc, dark, (bx + 3, by + bh // 3), (bx + bw - 4, by + bh // 3), 1)
    # Top highlight
    pygame.draw.line(sc, lite, (bx + bw // 5 + 1, by + 1), (bx + bw * 4 // 5 - 1, by + 1), 1)


def _crown(sc, x, y, s, col, dark):
    """Crown — band with three pointed tines and a ruby on the center tine."""
    bh     = max(3, s // 5)
    band_y = y + s * 5 // 8
    bx     = x + max(2, s // 7)
    bw     = s - max(4, s * 2 // 7)
    tine_w = max(2, s // 10)
    # Tine positions and heights
    positions = [bx + bw // 6, bx + bw // 2 - tine_w // 2, bx + bw - bw // 6 - tine_w]
    heights   = [band_y - max(4, s // 6), band_y - max(6, s * 3 // 14), band_y - max(4, s // 6)]
    # Draw tines first
    for tx, ty in zip(positions, heights):
        pygame.draw.rect(sc, col,  (tx, ty, tine_w, band_y - ty + 1), border_radius=1)
        pygame.draw.rect(sc, dark, (tx, ty, tine_w, band_y - ty + 1), 1, border_radius=1)
        pygame.draw.circle(sc, col,  (tx + tine_w // 2, ty), tine_w // 2 + 1)
        pygame.draw.circle(sc, dark, (tx + tine_w // 2, ty), tine_w // 2 + 1, 1)
    # Band (on top of tine bases)
    pygame.draw.rect(sc, col,  (bx, band_y, bw, bh), border_radius=1)
    pygame.draw.rect(sc, dark, (bx, band_y, bw, bh), 1, border_radius=1)
    # Ruby on tallest (center) tine
    gem_cx = bx + bw // 2
    gem_cy = heights[1] - max(2, s // 12)
    gem_r  = max(2, s // 9)
    pygame.draw.circle(sc, (215, 40, 40), (gem_cx, gem_cy), gem_r)
    pygame.draw.circle(sc, (140, 15, 15), (gem_cx, gem_cy), gem_r, 1)
    pygame.draw.circle(sc, (255, 140, 140), (gem_cx - gem_r // 3, gem_cy - gem_r // 3), max(1, gem_r // 3))
    # Band highlight
    lite = (min(255, col[0] + 55), min(255, col[1] + 50), min(255, col[2] + 25))
    pygame.draw.line(sc, lite, (bx + 2, band_y + 1), (bx + bw - 3, band_y + 1), 1)


def _wand_core(sc, x, y, s, col, dark):
    """Wand core component — glowing crystalline sphere with internal facets."""
    cx, cy = x + s // 2, y + s // 2
    r = max(4, s * 3 // 8)
    # Aura ring
    pygame.draw.circle(sc, dark, (cx, cy), r + max(1, s // 9), max(1, s // 9))
    # Main sphere
    pygame.draw.circle(sc, col,  (cx, cy), r)
    pygame.draw.circle(sc, dark, (cx, cy), r, 1)
    # Internal facet lines
    hi = (min(255, col[0] + 70), min(255, col[1] + 70), min(255, col[2] + 70))
    pygame.draw.line(sc, hi, (cx - r // 2, cy - r // 2), (cx + r // 3, cy - r // 5), 1)
    pygame.draw.line(sc, hi, (cx - r // 3, cy - r + 2),  (cx + r // 4, cy - r // 2), 1)
    # Specular dot
    pygame.draw.circle(sc, hi, (cx - r // 3, cy - r // 3), max(1, r // 4))


def _boots(sc, x, y, s, col, dark):
    """Pair of ankle boots — taller and more enclosed than sandals."""
    bw     = max(5, s * 9 // 20)
    bh     = max(6, s * 9 // 20)
    sole_h = max(2, s // 10)
    gap    = max(2, s // 8)
    total  = bw * 2 + gap
    bx = x + (s - total) // 2
    by = y + s // 5
    for i in range(2):
        rx = bx + i * (bw + gap)
        # Thick sole
        pygame.draw.rect(sc, dark, (rx - 1, by + bh, bw + 2, sole_h + 1), border_radius=1)
        # Boot upper
        pygame.draw.rect(sc, col,  (rx, by, bw, bh), border_radius=max(2, s // 12))
        pygame.draw.rect(sc, dark, (rx, by, bw, bh), 1, border_radius=max(2, s // 12))
        # Ankle crease
        pygame.draw.line(sc, dark, (rx + 2, by + bh * 2 // 3), (rx + bw - 3, by + bh * 2 // 3), 1)
        # Tongue flap at top
        tongue = (min(255, col[0] + 22), min(255, col[1] + 18), min(255, col[2] + 10))
        pygame.draw.rect(sc, tongue, (rx + bw // 4, by, bw // 2, max(2, bh // 4)), border_radius=1)
        # Highlight
        pygame.draw.line(sc, (min(255, col[0] + 50), min(255, col[1] + 45), min(255, col[2] + 28)),
                         (rx + 2, by + 2), (rx + bw - 3, by + 2), 1)


# ── Mob drop helpers ──────────────────────────────────────────────────────────

def _spider_silk(sc, x, y, s):
    """Spider Silk — tangled silvery-white thread bundle."""
    cx, cy = x + s // 2, y + s // 2
    hw = s * 3 // 8
    # Main blob (ellipse)
    pygame.draw.ellipse(sc, (208, 215, 225),
                        (cx - hw, cy - int(hw * 0.9), hw * 2, int(hw * 1.8)))
    pygame.draw.ellipse(sc, (160, 170, 185),
                        (cx - hw, cy - int(hw * 0.9), hw * 2, int(hw * 1.8)), 1)
    # Crosshatch silk threads
    col = (238, 244, 252)
    lw  = max(1, s // 14)
    pygame.draw.line(sc, col, (cx - hw + 3,  cy - s // 8),  (cx + hw - 3, cy + s // 8),  lw)
    pygame.draw.line(sc, col, (cx - s // 6,  cy - hw + 3),  (cx + s // 8, cy + hw - 3),  lw)
    pygame.draw.line(sc, col, (cx - hw // 2, cy - hw // 2), (cx + hw // 2, cy + hw // 2), lw)
    # Small sheen highlight
    pygame.draw.circle(sc, (252, 254, 255), (cx - s // 10, cy - s // 8), max(2, s // 12))


def _scorpion_venom(sc, x, y, s):
    """Scorpion Venom — glowing yellow-green teardrop vial."""
    cx = x + s // 2
    r  = s * 3 // 8
    by = y + s - r - 2            # centre of the round body
    # Teardrop body (circle + triangle tip)
    pygame.draw.circle(sc, (148, 215, 38), (cx, by), r)
    pygame.draw.circle(sc, (88, 148, 18),  (cx, by), r, max(1, s // 12))
    body_top = by - r
    tip_y    = y + s // 6
    tip_pts  = [(cx - s // 8, body_top), (cx + s // 8, body_top), (cx, tip_y)]
    pygame.draw.polygon(sc, (148, 215, 38), tip_pts)
    # Inner shine
    pygame.draw.circle(sc, (202, 255, 105), (cx - r // 3, by - r // 4), max(2, r // 4))


def _raw_meat(sc, x, y, s):
    """Raw meat slab — pink-red with pale marbling and a rounded bone nub."""
    cx, cy = x + s // 2, y + s // 2
    hw, hh = s * 3 // 7, s * 5 // 14
    pts = [
        (cx - hw,            cy - hh + s // 8),
        (cx - hw + s // 6,   cy - hh),
        (cx + hw,            cy - hh + s // 12),
        (cx + hw - s // 8,   cy + hh),
        (cx - hw + s // 12,  cy + hh - s // 12),
    ]
    pygame.draw.polygon(sc, (210, 80, 90), pts)
    pygame.draw.polygon(sc, (165, 45, 55), pts, 1)
    # Pale marbling streaks
    lw = max(1, s // 12)
    pygame.draw.line(sc, (245, 175, 185),
                     (cx - hw + s // 8, cy - hh // 2),
                     (cx + s // 6,       cy + hh // 2), lw)
    pygame.draw.line(sc, (245, 175, 185),
                     (cx - s // 10,      cy - hh + s // 10),
                     (cx + hw - s // 6,  cy + s // 10), max(1, s // 14))
    # Bone nub
    bone_r = max(2, s // 8)
    bx2, by2 = cx - hw + s // 6, cy + hh - s // 6
    pygame.draw.circle(sc, (235, 225, 200), (bx2, by2), bone_r)
    pygame.draw.circle(sc, (200, 188, 165), (bx2, by2), bone_r, 1)


def _cooked_meat(sc, x, y, s):
    """Cooked meat — charred brown with golden grill marks and bone nub."""
    cx, cy = x + s // 2, y + s // 2
    hw, hh = s * 3 // 7, s * 5 // 14
    pts = [
        (cx - hw,            cy - hh + s // 8),
        (cx - hw + s // 6,   cy - hh),
        (cx + hw,            cy - hh + s // 12),
        (cx + hw - s // 8,   cy + hh),
        (cx - hw + s // 12,  cy + hh - s // 12),
    ]
    pygame.draw.polygon(sc, (140, 75, 30), pts)
    pygame.draw.polygon(sc, (90, 45, 10), pts, 1)
    # Golden grill marks
    lw = max(1, s // 12)
    pygame.draw.line(sc, (210, 155, 45),
                     (cx - hw + s // 8, cy - hh // 2),
                     (cx + s // 6,       cy + hh // 2), lw)
    pygame.draw.line(sc, (210, 155, 45),
                     (cx - s // 10,      cy - hh + s // 10),
                     (cx + hw - s // 6,  cy + s // 10), max(1, s // 14))
    # Bone nub
    bone_r = max(2, s // 8)
    bx2, by2 = cx - hw + s // 6, cy + hh - s // 6
    pygame.draw.circle(sc, (220, 208, 185), (bx2, by2), bone_r)
    pygame.draw.circle(sc, (180, 168, 148), (bx2, by2), bone_r, 1)


def _yeti_fur(sc, x, y, s):
    """Yeti Fur bundle — white-grey clump with fluffy tuft circles."""
    cx, cy = x + s // 2, y + s // 2
    hw = s * 3 // 8
    # Base blob
    pygame.draw.ellipse(sc, (218, 222, 232),
                        (cx - hw, cy - int(hw * 0.85), hw * 2, int(hw * 1.7)))
    pygame.draw.ellipse(sc, (178, 184, 198),
                        (cx - hw, cy - int(hw * 0.85), hw * 2, int(hw * 1.7)), 1)
    # Tuft circles suggesting fluffiness
    r = max(3, s // 8)
    for (ox, oy) in ((-s // 5, -s // 5), (s // 6, -s // 4),
                     (-s // 8, s // 6),   (s // 5, s // 8), (0, -s // 8)):
        pygame.draw.circle(sc, (242, 245, 252), (cx + ox, cy + oy), r)
        pygame.draw.circle(sc, (158, 165, 178), (cx + ox, cy + oy), r, 1)
    # Binding cord across the middle
    pygame.draw.line(sc, (140, 112, 72),
                     (cx - hw + s // 6, cy), (cx + hw - s // 6, cy), max(1, s // 10))


# ── Mold helpers (clay base + shape imprint) ─────────────────────────────────

def _mold_base(sc, x, y, s):
    clay    = (148, 112, 68)
    clay_dk = (95,  68,  32)
    clay_li = (182, 148, 100)
    pygame.draw.rect(sc, clay,    (x + 1, y + 1, s - 2, s - 2), border_radius=2)
    pygame.draw.rect(sc, clay_dk, (x + 1, y + 1, s - 2, s - 2), 1, border_radius=2)
    pygame.draw.line(sc, clay_li, (x + 3, y + 2), (x + s - 4, y + 2), 1)


def _mold_sword(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    cx, cy = x + s * 9 // 16, y + s * 7 // 16
    tip = (x + s - 4, y + 4)
    w   = max(1, s // 10)
    pygame.draw.line(sc, d, (cx, cy), tip, w)
    pygame.draw.line(sc, d, (cx - s // 5, cy + s // 5), (cx + s // 5, cy - s // 5), max(1, s // 9))
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (cx - w, cy + w), w)


def _mold_dagger(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    gx, gy = x + s * 5 // 9, y + s * 4 // 9
    tip = (x + s - s // 4, y + s // 4)
    w   = max(1, s // 10)
    pygame.draw.line(sc, d, (gx, gy), tip, w)
    pygame.draw.line(sc, d, (gx - s // 6, gy + s // 6), (gx + s // 6, gy - s // 6), max(1, s // 9))
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (gx - w, gy + w), w)


def _mold_axe(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    m  = max(1, s // 8)
    lw = max(1, s // 12)
    pts = [
        (x + m + s // 7, y + s // 3),
        (x + s * 3 // 5, y + m),
        (x + s - m,      y + s // 2),
        (x + s * 3 // 5, y + s - m),
        (x + m + s // 7, y + s * 2 // 3),
    ]
    pygame.draw.polygon(sc, d, pts, lw)
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (x + s * 2 // 5, y + s * 2 // 3), lw)


def _mold_pick(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d   = (75, 50, 18)
    cy  = y + s // 2 - s // 8
    hw  = max(1, s // 10)
    bw  = int(s * 0.55)
    bx  = x + (s - bw) // 2
    tl  = max(2, s // 7)
    lw  = max(1, s // 12)
    pygame.draw.rect(sc, d, (bx, cy - hw, bw, hw * 2), lw)
    pygame.draw.polygon(sc, d, [(bx, cy - hw), (bx, cy + hw), (bx - tl, cy + tl)], lw)
    pygame.draw.polygon(sc, d, [(bx + bw, cy - hw), (bx + bw, cy + hw), (bx + bw + tl, cy - tl)], lw)
    pygame.draw.line(sc, d, (x + s // 2, cy + hw), (x + s // 2, y + s - 4), lw)


def _mold_helm(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d      = (75, 50, 18)
    cx     = x + s // 2
    dome_r = s * 2 // 5 - 1
    dome_y = y + s * 2 // 5
    lw     = max(1, s // 12)
    pygame.draw.circle(sc, d, (cx, dome_y), dome_r, lw)
    cg_w, cg_h = max(2, s // 6), max(3, s // 5)
    cg_y = dome_y + dome_r // 2
    for cg_x in (cx - dome_r, cx + dome_r - cg_w):
        pygame.draw.rect(sc, d, (cg_x, cg_y, cg_w, cg_h), lw)


def _mold_chest(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    m  = max(1, s // 8)
    bw = s - m * 3
    bh = max(4, s * 2 // 5)
    bx = x + m + m // 2
    by = y + s // 4
    lw = max(1, s // 12)
    pts = [(bx, by + m), (bx + bw // 4, by), (bx + bw * 3 // 4, by),
           (bx + bw, by + m), (bx + bw - m, by + bh), (bx + m, by + bh)]
    pygame.draw.polygon(sc, d, pts, lw)
    sw = s // 5
    for sx2 in (bx - sw + m, bx + bw - m):
        pygame.draw.rect(sc, d, (sx2, by - m // 2, sw, m + 2), lw)


def _mold_arms(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d   = (75, 50, 18)
    bw  = max(3, s * 2 // 5)
    bh  = max(5, s * 2 // 5)
    gap = max(1, s // 10)
    tot = bw * 2 + gap
    bx  = x + (s - tot) // 2
    by  = y + (s - bh) // 2
    lw  = max(1, s // 12)
    for i in range(2):
        rx = bx + i * (bw + gap)
        pygame.draw.rect(sc, d, (rx, by, bw, bh), lw, border_radius=max(1, s // 14))
        for j in (1, 2):
            pygame.draw.line(sc, d, (rx + 1, by + bh * j // 3), (rx + bw - 2, by + bh * j // 3), 1)


def _mold_legs(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d    = (75, 50, 18)
    lw_p = max(3, s * 3 // 10)
    lh   = max(5, s * 2 // 5)
    gap  = max(1, s // 10)
    tot  = lw_p * 2 + gap
    bx   = x + (s - tot) // 2
    by   = y + s // 4
    lw   = max(1, s // 12)
    for i in range(2):
        pygame.draw.rect(sc, d, (bx + i * (lw_p + gap), by, lw_p, lh), lw, border_radius=max(1, s // 14))


def _mold_feet(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d   = (75, 50, 18)
    sw  = max(4, s * 2 // 5)
    sh  = max(3, s // 4)
    gap = max(1, s // 8)
    tot = sw * 2 + gap
    bx  = x + (s - tot) // 2
    by  = y + s // 3
    lw  = max(1, s // 12)
    for i in range(2):
        rx = bx + i * (sw + gap)
        pygame.draw.rect(sc, d, (rx, by, sw, sh), lw, border_radius=max(2, s // 10))
        pygame.draw.line(sc, d, (rx, by + sh), (rx + sw, by + sh), lw)


def _rapier(sc, x, y, s, blade, blade_dark):
    """Rapier: long thin thrusting sword with a small circular parrying disk."""
    handle_col = (130, 85, 35)
    _handle(sc, x, y, s, handle_col)
    # Disc guard at blade base
    gx, gy = x + s // 2, y + s // 2
    pygame.draw.circle(sc, blade_dark, (gx, gy), max(3, s // 7), max(1, s // 12))
    # Very thin long blade
    tip = (x + s - 2, y + 2)
    bw = max(1, s // 14)
    blade_pts = [(gx - bw, gy - bw), (gx + bw, gy + bw), (tip[0], tip[1])]
    pygame.draw.polygon(sc, blade, blade_pts)
    pygame.draw.polygon(sc, blade_dark, blade_pts, 1)
    lite = (min(255, blade[0] + 55), min(255, blade[1] + 55), min(255, blade[2] + 55))
    pygame.draw.line(sc, lite, (gx, gy), tip, 1)


def _katana(sc, x, y, s, blade, blade_dark):
    """Katana: long single-edge blade with round tsuba guard."""
    handle_col = (38, 25, 12)
    _handle(sc, x, y, s, handle_col)
    # Round tsuba
    gx, gy = x + s * 9 // 18, y + s * 9 // 18
    pygame.draw.circle(sc, (100, 88, 72), (gx, gy), max(3, s // 7))
    pygame.draw.circle(sc, blade_dark, (gx, gy), max(3, s // 7), 1)
    # Longer blade with single-edge width
    tip = (x + s - 2, y + 2)
    bw = max(1, s // 10)
    blade_pts = [
        (gx - bw, gy - bw), (gx + bw, gy + bw),
        (tip[0] + bw, tip[1] + bw), (tip[0], tip[1]),
    ]
    pygame.draw.polygon(sc, blade, blade_pts)
    pygame.draw.polygon(sc, blade_dark, blade_pts, 1)
    lite = (min(255, blade[0] + 55), min(255, blade[1] + 55), min(255, blade[2] + 55))
    pygame.draw.line(sc, lite, (gx - bw // 2, gy - bw // 2), tip, 1)


def _scimitar(sc, x, y, s, blade, blade_dark):
    """Scimitar: broad curved single-edge blade."""
    handle_col = (130, 85, 35)
    _handle(sc, x, y, s, handle_col)
    gx, gy = x + s * 10 // 20, y + s * 10 // 20
    pygame.draw.circle(sc, blade_dark, (gx, gy), max(2, s // 8))
    bw = max(2, s // 7)
    blade_pts = [
        (gx - bw // 2, gy - bw // 2),
        (gx + bw // 2, gy + bw // 2),
        (x + s * 4 // 5, y + s * 2 // 5),
        (x + s - 3,      y + s // 5),
        (x + s - 3,      y + 3),
        (x + s * 3 // 4, y + 2),
    ]
    pygame.draw.polygon(sc, blade, blade_pts)
    pygame.draw.polygon(sc, blade_dark, blade_pts, 1)
    lite = (min(255, blade[0] + 50), min(255, blade[1] + 50), min(255, blade[2] + 50))
    pygame.draw.line(sc, lite, (gx, gy - 1), (x + s - 4, y + 4), 1)


def _hammer(sc, x, y, s, head_col, head_dark):
    """Warhammer: large square head on a diagonal handle."""
    handle_col = (130, 85, 35)
    _handle(sc, x, y, s, handle_col)
    hw = max(5, s * 3 // 8)
    hh = max(5, s * 3 // 8)
    hx = x + s - hw - max(1, s // 10)
    hy = y + max(1, s // 10)
    pygame.draw.rect(sc, head_col,  (hx, hy, hw, hh), border_radius=1)
    pygame.draw.rect(sc, head_dark, (hx, hy, hw, hh), 1, border_radius=1)
    lite = (min(255, head_col[0] + 45), min(255, head_col[1] + 40), min(255, head_col[2] + 25))
    pygame.draw.rect(sc, lite, (hx + 2, hy + 2, max(2, hw - 4), max(1, hh // 4)), border_radius=1)
    pygame.draw.circle(sc, head_dark, (hx + hw // 2, hy + hh // 2), max(1, s // 12))


def _mold_katana(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    w  = max(1, s // 10)
    gx, gy = x + s * 9 // 18, y + s * 9 // 18
    tip = (x + s - 4, y + 4)
    pygame.draw.circle(sc, d, (gx, gy), max(2, s // 7), max(1, s // 12))
    pygame.draw.line(sc, d, (gx, gy), tip, w)
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (gx - w, gy + w), w)


def _mold_saber(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    w  = max(1, s // 10)
    lw = max(1, s // 12)
    cx, cy = x + s * 9 // 16, y + s * 7 // 16
    tip = (x + s - 4, y + 4)
    pygame.draw.line(sc, d, (cx, cy), tip, w)
    r = max(2, s // 7)
    pygame.draw.arc(sc, d, (cx - r, cy - r, r * 2, r * 2),
                    math.radians(90), math.radians(270), lw)
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (cx - w, cy + w), w)


def _mold_scimitar(sc, x, y, s):
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    lw = max(1, s // 12)
    pygame.draw.arc(sc, d, (x + s // 5, y + s // 5, s * 3 // 5, s * 3 // 5),
                    math.radians(0), math.radians(135), lw)
    cx, cy = x + s // 2, y + s // 2
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (cx, cy), lw)


def _mold_rapier(sc, x, y, s):
    """Rapier Mold — clay base with thin diagonal blade + disc guard imprint."""
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    w  = max(1, s // 14)
    gx, gy = x + s // 2, y + s // 2
    tip = (x + s - 4, y + 4)
    pygame.draw.line(sc, d, (gx, gy), tip, w)
    pygame.draw.circle(sc, d, (gx, gy), max(2, s // 7), max(1, s // 12))
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (gx, gy), w)


def _mold_hammer(sc, x, y, s):
    """Hammer Mold — clay base with square hammer head + handle imprint."""
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    lw = max(1, s // 12)
    hw = max(4, s * 3 // 8)
    hh = max(4, s * 3 // 8)
    hx = x + s - hw - max(1, s // 10)
    hy = y + max(1, s // 10)
    pygame.draw.rect(sc, d, (hx, hy, hw, hh), lw, border_radius=1)
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (hx + hw // 2, hy + hh), lw)


def _mold_wand(sc, x, y, s):
    """Wand Mold — clay base with diagonal staff + orb imprint."""
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    lw = max(1, s // 12)
    ox, oy = x + s - max(3, s // 4), y + max(3, s // 4)
    pygame.draw.circle(sc, d, (ox, oy), max(2, s // 6), lw)
    pygame.draw.line(sc, d, (x + 4, y + s - 4), (ox - max(1, s // 8), oy + max(1, s // 8)), lw)


def _gem_item(sc, x, y, s, col, highlight):
    """Generic faceted gem icon — diamond shape with a highlight corner."""
    m  = max(2, s // 6)
    cx = x + s // 2
    cy = y + s // 2
    # Outline diamond
    pts = [(cx, y + m), (x + s - m, cy), (cx, y + s - m), (x + m, cy)]
    pygame.draw.polygon(sc, col, pts)
    pygame.draw.polygon(sc, (0, 0, 0, 200), pts, 1)
    # Highlight facet (top-right triangle)
    hi_pts = [(cx, y + m), (x + s - m, cy), (cx + (s - 2 * m) // 3, cy - (s - 2 * m) // 3)]
    pygame.draw.polygon(sc, highlight, hi_pts)


def _embedder_item(sc, x, y, s):
    """Embedder station icon — gem-setting bench: table top with three coloured gem dots."""
    # Table body
    bw, bh = int(s * 0.84), int(s * 0.22)
    bx, by = x + (s - bw) // 2, y + s - bh - max(1, s // 10)
    pygame.draw.rect(sc, (50, 38, 60),  (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, (28, 20, 40),  (bx, by, bw, bh), 1, border_radius=2)
    # Narrow waist
    ww2, wh2 = int(s * 0.38), max(3, s // 8)
    wx2 = x + (s - ww2) // 2
    wy2 = by - wh2
    pygame.draw.rect(sc, (50, 38, 60),  (wx2, wy2, ww2, wh2))
    # Table top (gold-tinted surface)
    tw2, th2 = int(s * 0.78), max(4, s // 6)
    tx2 = x + (s - tw2) // 2
    ty2 = wy2 - th2
    pygame.draw.rect(sc, (85, 68, 28), (tx2, ty2, tw2, th2), border_radius=1)
    pygame.draw.rect(sc, (55, 42, 12), (tx2, ty2, tw2, th2), 1, border_radius=1)
    # Three gem dots on table surface
    dot_y = ty2 + th2 // 2
    for i, dcol in enumerate(((220, 55, 30), (55, 148, 240), (55, 200, 60))):
        dx2 = tx2 + tw2 // 4 + i * (tw2 // 4)
        pygame.draw.circle(sc, dcol, (dx2, dot_y), max(2, s // 10))


def _part_combiner_item(sc, x, y, s):
    """Part Combiner station icon — anvil with purple-tinted accent."""
    base_col = (70, 45, 90)
    dark_col = (40, 22, 55)
    top_col  = (105, 72, 145)
    top_dark = (65, 38, 98)
    metal_col = (162, 148, 195)
    # Anvil base (wide bottom)
    bw, bh = int(s * 0.82), int(s * 0.28)
    bx, by = x + (s - bw) // 2, y + s - bh - max(1, s // 10)
    pygame.draw.rect(sc, base_col, (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, dark_col, (bx, by, bw, bh), 1, border_radius=2)
    # Narrow waist
    ww2, wh2 = int(s * 0.40), max(3, s // 8)
    wx2 = x + (s - ww2) // 2
    wy2 = by - wh2
    pygame.draw.rect(sc, base_col, (wx2, wy2, ww2, wh2))
    pygame.draw.rect(sc, dark_col, (wx2, wy2, ww2, wh2), 1)
    # Anvil horn (top flat face, wider)
    tw2, th2 = int(s * 0.75), max(3, s // 7)
    tx2 = x + (s - tw2) // 2
    ty2 = wy2 - th2
    pygame.draw.rect(sc, top_col, (tx2, ty2, tw2, th2), border_radius=1)
    pygame.draw.rect(sc, top_dark, (tx2, ty2, tw2, th2), 1, border_radius=1)
    # Gem-slot sparkle (3 small dots on top face)
    dot_y = ty2 + th2 // 2
    for i, dot_col in enumerate(((220, 140, 255), (180, 200, 255), (255, 210, 120))):
        dx2 = tx2 + tw2 // 4 + i * (tw2 // 4)
        pygame.draw.circle(sc, dot_col, (dx2, dot_y), max(1, s // 11))
    # Metal hammer marks (two short lines on waist)
    lx1 = wx2 + ww2 // 4
    pygame.draw.line(sc, metal_col, (lx1, wy2 + 2), (lx1, wy2 + wh2 - 2), max(1, s // 18))


def _ore_item(sc, x, y, s, rock_col, rock_dark, ore_col):
    """Generic ore item icon — fills the slot like _iron_ore, coloured per ore type."""
    pygame.draw.rect(sc, rock_col,  (x + 2, y + 2, s - 4, s - 4), border_radius=3)
    pygame.draw.rect(sc, rock_dark, (x + 2, y + 2, s - 4, s - 4), 1, border_radius=3)
    # Vein streaks
    pygame.draw.line(sc, ore_col, (x + 3, y + s // 2), (x + s // 2, y + 3), 1)
    pygame.draw.line(sc, ore_col, (x + s // 2, y + s - 4), (x + s - 3, y + s * 2 // 3), 1)
    # Bright ore spot
    pygame.draw.circle(sc, ore_col, (x + s // 2 + 2, y + s // 2 - 2), max(2, s // 7))


def _bar_item(sc, x, y, s, col, dark, highlight):
    """Generic metal bar/ingot icon."""
    m  = max(1, s // 6)
    bw, bh = int(s * 0.72), int(s * 0.42)
    bx, by = x + (s - bw) // 2, y + (s - bh) // 2 + m
    pygame.draw.rect(sc, col,  (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, dark, (bx, by, bw, bh), 1, border_radius=2)
    hw = max(2, bw // 3)
    pygame.draw.polygon(sc, highlight, [
        (bx + 2, by + 2), (bx + hw, by + 2),
        (bx + hw - 4, by + bh // 3), (bx + 2, by + bh // 3),
    ])


# ---------------------------------------------------------------------------
# New ore node draw functions
# ---------------------------------------------------------------------------

def _node_colored_ore(sc, x, y, s, rock_col, rock_dark, ore_col, ore_lite):
    """Generic ore world node: cluster of rocks with coloured ore veins."""
    rocks = [
        (x + s * 2 // 5, y + s * 11 // 16, s * 5 // 16, rock_col, rock_dark),
        (x + s * 3 // 5, y + s *  9 // 16, s * 3 //  8, rock_col, rock_dark),
        (x + s * 4 // 5, y + s *  5 //  8, s *  1 //  4, rock_col, rock_dark),
    ]
    for cx, cy, r, col, dark in rocks:
        pygame.draw.circle(sc, col,  (cx, cy), r)
        pygame.draw.circle(sc, dark, (cx, cy), r, max(1, r // 4))
    spots = [
        (x + s // 3,     y + s * 7 // 12, max(2, s // 9)),
        (x + s * 3 // 5, y + s * 5 // 12, max(2, s // 8)),
        (x + s * 4 // 5, y + s * 7 // 12, max(2, s // 11)),
    ]
    for sx2, sy2, r in spots:
        pygame.draw.circle(sc, ore_col, (sx2, sy2), r)
    pygame.draw.line(sc, ore_lite,
                     (x + s // 4, y + s * 7 // 12),
                     (x + s * 2 // 3, y + s * 3 // 8), max(1, s // 14))


def _node_clay(sc, x, y, s):
    """Clay deposit node — flat tan mound."""
    col, dark, lite = (182, 148, 98), (128, 98, 58), (218, 188, 145)
    cx, cy, r = x + s // 2, y + s * 3 // 5, s * 5 // 12
    pygame.draw.ellipse(sc, col,  (cx - r, cy - r // 2, r * 2, r))
    pygame.draw.ellipse(sc, dark, (cx - r, cy - r // 2, r * 2, r), 1)
    pygame.draw.line(sc, lite, (cx - r // 2, cy - r // 4), (cx + r // 4, cy - r // 3), 1)


def _node_copper_ore(sc, x, y, s):
    _node_colored_ore(sc, x, y, s, (118, 98, 72), (75, 58, 38), (184, 115, 51), (210, 148, 80))

def _node_tin_ore(sc, x, y, s):
    _node_colored_ore(sc, x, y, s, (110, 112, 118), (72, 74, 80), (165, 175, 188), (200, 210, 225))

def _node_silver_ore(sc, x, y, s):
    _node_colored_ore(sc, x, y, s, (95, 98, 108), (58, 62, 72), (210, 218, 228), (240, 245, 255))

def _node_gold_ore(sc, x, y, s):
    _node_colored_ore(sc, x, y, s, (118, 98, 72), (75, 58, 38), (218, 175, 35), (252, 215, 90))

def _node_crystal(sc, x, y, s):
    """Crystal spires rising from pale rocky ground."""
    col  = (105, 172, 215)
    lite = (170, 225, 255)
    dark = (55, 112, 168)
    # Base rock
    pygame.draw.circle(sc, (148, 148, 158), (x + s // 2, y + s * 3 // 4), s * 3 // 8)
    pygame.draw.circle(sc, (95, 95, 105),   (x + s // 2, y + s * 3 // 4), s * 3 // 8, 1)
    # Three crystal spires
    for ox, oy, h in [(-s // 8, 0, s * 2 // 3), (0, -s // 8, s * 4 // 5), (s // 7, s // 10, s // 2)]:
        cx2, cy2 = x + s // 2 + ox, y + s * 3 // 4 + oy
        hw = max(2, s // 8)
        pts = [(cx2 - hw, cy2), (cx2 + hw, cy2), (cx2, cy2 - h)]
        pygame.draw.polygon(sc, col, pts)
        pygame.draw.polygon(sc, dark, pts, 1)
        pygame.draw.line(sc, lite, (cx2, cy2 - h + 1), (cx2, cy2 - h // 2), 1)

def _node_obsidian(sc, x, y, s):
    """Dark glassy angular obsidian chunks."""
    col  = (38, 28, 52)
    dark = (18, 12, 28)
    sheen = (75, 55, 105)
    chunks = [
        (x + s * 2 // 5, y + s * 11 // 16, s * 5 // 16),
        (x + s * 3 // 5, y + s *  9 // 16, s * 3 //  8),
        (x + s * 4 // 5, y + s *  5 //  8, s *  1 //  4),
    ]
    for cx2, cy2, r in chunks:
        pts = []
        for i in range(6):
            a   = math.pi * 2 * i / 6
            jit = r * (0.75 if i % 2 == 0 else 1.0)
            pts.append((int(cx2 + math.cos(a) * jit), int(cy2 + math.sin(a) * jit)))
        pygame.draw.polygon(sc, col, pts)
        pygame.draw.polygon(sc, dark, pts, 1)
        pygame.draw.line(sc, sheen, (cx2 - r // 2, cy2 - r // 2), (cx2 + r // 4, cy2 - r // 3), 1)


# ---------------------------------------------------------------------------
# Farming items
# ---------------------------------------------------------------------------

def _sapling_item(sc, x, y, s):
    """Tree Sapling — small green shrub with a thin trunk."""
    trunk_col = (100, 65, 20)
    leaf_col  = (50, 145, 40)
    leaf_hi   = (80, 195, 65)
    cx2 = x + s // 2
    trunk_top = y + s // 2
    pygame.draw.line(sc, trunk_col, (cx2, y + s - s // 6), (cx2, trunk_top), max(1, s // 12))
    r = max(3, s // 4)
    pygame.draw.circle(sc, leaf_col, (cx2, trunk_top - r // 3), r)
    pygame.draw.circle(sc, leaf_hi,  (cx2, trunk_top - r // 3), max(1, r - 2))


def _seed_item(sc, x, y, s, col_outer, col_inner):
    """Generic faceted gem seed icon."""
    cx2 = x + s // 2
    cy2 = y + s // 2
    r   = max(4, s // 4)
    pts_outer = [
        (cx2,       cy2 - r),
        (cx2 + r,   cy2 - r // 3),
        (cx2 + r,   cy2 + r // 3),
        (cx2,       cy2 + r),
        (cx2 - r,   cy2 + r // 3),
        (cx2 - r,   cy2 - r // 3),
    ]
    pygame.draw.polygon(sc, col_outer, pts_outer)
    pts_inner = [(cx2, cy2 - r + r // 2), (cx2 + r - r // 2, cy2),
                 (cx2, cy2 + r - r // 2), (cx2 - r + r // 2, cy2)]
    pygame.draw.polygon(sc, col_inner, pts_inner)


def _wood_item(sc, x, y, s, col, dark):
    """Parameterized wood log icon for alternate wood types."""
    lite = tuple(min(255, c + 40) for c in col)
    pygame.draw.rect(sc, col, (x + 1, y + s // 5, s - 2, s * 3 // 5), border_radius=2)
    pygame.draw.rect(sc, dark, (x + 1, y + s // 5, s - 2, s * 3 // 5), 1, border_radius=2)
    ex, ey = x + s // 8 + 1, y + s // 2
    pygame.draw.circle(sc, dark, (ex, ey), max(2, s // 6))
    pygame.draw.circle(sc, lite, (ex, ey), max(1, s // 10))
    for i in (1, 2):
        gy = y + s // 5 + (s * 3 // 5) * i // 3
        pygame.draw.line(sc, lite, (x + s // 4, gy), (x + s - 3, gy), 1)


def _lining_item(sc, x, y, s, col, dark):
    """Padded fabric lining — quilted rectangle with stitching lines."""
    bw, bh = int(s * 0.70), int(s * 0.60)
    bx, by = x + (s - bw) // 2, y + (s - bh) // 2
    pygame.draw.rect(sc, col,  (bx, by, bw, bh), border_radius=2)
    pygame.draw.rect(sc, dark, (bx, by, bw, bh), 1, border_radius=2)
    for i in range(1, 4):
        qy = by + bh * i // 4
        pygame.draw.line(sc, dark, (bx + 2, qy), (bx + bw - 2, qy), 1)
    lite = (min(255, col[0] + 35), min(255, col[1] + 30), min(255, col[2] + 20))
    pygame.draw.line(sc, lite, (bx + 2, by + 2), (bx + bw - 2, by + 2), 1)


def _shield_item(sc, x, y, s, col, dark):
    """Kite shield — rounded top, pointed bottom, central boss."""
    cx, m = x + s // 2, max(2, s // 8)
    pts = [
        (cx,        y + s - m),
        (x + s - m, y + s * 2 // 5),
        (x + s - m, y + m),
        (x + m,     y + m),
        (x + m,     y + s * 2 // 5),
    ]
    pygame.draw.polygon(sc, col,  pts)
    pygame.draw.polygon(sc, dark, pts, 1)
    boss_r = max(3, s // 6)
    boss_x, boss_y = cx, y + s * 2 // 5
    pygame.draw.circle(sc, dark, (boss_x, boss_y), boss_r)
    lite = (min(255, col[0] + 50), min(255, col[1] + 45), min(255, col[2] + 35))
    pygame.draw.circle(sc, lite, (boss_x, boss_y), max(1, boss_r - 2))
    pygame.draw.line(sc, dark, (x + m + 1, boss_y), (x + s - m - 1, boss_y), max(1, s // 18))
    shine = (min(255, col[0] + 45), min(255, col[1] + 40), min(255, col[2] + 30))
    pygame.draw.line(sc, shine, (x + m + 2, y + m + 2), (x + m + 2, y + s * 2 // 5), max(1, s // 12))


def _pauldrons_item(sc, x, y, s, col, dark):
    """Two shoulder pads — elliptical segments side by side."""
    pw = max(3, s * 5 // 12)
    ph = max(4, s // 2)
    gap = max(1, s // 12)
    total = pw * 2 + gap
    bx = x + (s - total) // 2
    by = y + (s - ph) // 2
    for i in range(2):
        px = bx + i * (pw + gap)
        pygame.draw.ellipse(sc, col,  (px, by, pw, ph))
        pygame.draw.ellipse(sc, dark, (px, by, pw, ph), 1)
        mid_y = by + ph // 2
        pygame.draw.line(sc, dark, (px + 1, mid_y), (px + pw - 2, mid_y), 1)
        shine = (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 25))
        pygame.draw.line(sc, shine, (px + 2, by + 2), (px + pw - 3, by + 2), 1)


def _gloves_item(sc, x, y, s, col, dark):
    """Two mitten-style gloves side by side with thumb nub."""
    gw = max(3, s * 2 // 5)
    gh = max(5, s * 11 // 16)
    gap = max(1, s // 10)
    total = gw * 2 + gap
    bx = x + (s - total) // 2
    by = y + (s - gh) // 2
    for i in range(2):
        gx = bx + i * (gw + gap)
        pygame.draw.rect(sc, col,  (gx, by, gw, gh), border_radius=max(2, gw // 3))
        pygame.draw.rect(sc, dark, (gx, by, gw, gh), 1, border_radius=max(2, gw // 3))
        tw, th = max(2, gw // 3), max(2, gh // 4)
        tx = gx - tw + 1 if i == 0 else gx + gw - 1
        ty = by + gh // 4
        pygame.draw.rect(sc, col,  (tx, ty, tw, th), border_radius=1)
        pygame.draw.rect(sc, dark, (tx, ty, tw, th), 1, border_radius=1)
        for j in range(1, 3):
            ky = by + j * gh // 3
            pygame.draw.line(sc, dark, (gx + 2, ky), (gx + gw - 2, ky), 1)
        shine = (min(255, col[0] + 40), min(255, col[1] + 35), min(255, col[2] + 25))
        pygame.draw.line(sc, shine, (gx + 2, by + 2), (gx + gw - 3, by + 2), 1)


def _mold_back(sc, x, y, s):
    """Back Mold — clay mold with triangular cape/cloak shape imprint."""
    _mold_base(sc, x, y, s)
    d  = (75, 50, 18)
    lw = max(1, s // 12)
    cx = x + s // 2
    pts = [(cx, y + s // 5), (x + s - s // 5, y + s * 4 // 5), (x + s // 5, y + s * 4 // 5)]
    pygame.draw.polygon(sc, d, pts, lw)
    pygame.draw.circle(sc, d, (cx, y + s // 5 + max(1, s // 10)), max(1, s // 10), max(1, s // 16))


_ITEM_FNS: dict = {
    # Materials
    1:    _coin,
    10:   _wood,
    11:   _stone,
    12:   _stick,
    13:   _herb,
    14:   _mushroom,
    15:   _cactus_spine,
    16:   _snow_crystal,
    17:   _seashell,
    18:   _reed,
    19:   _bone,
    # Raw ores — mining
    20:   _coal,
    21:   _iron_ore,
    28:   _slimeball,
    # Farming — saplings and seeds
    34:   _sapling_item,
    35:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (155, 162, 172), (210, 218, 228)),  # Iron Seed
    36:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (38,  38,  42),  (80,  80,  88)),   # Coal Seed
    37:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (148, 88,  42),  (210, 140, 80)),   # Copper Seed
    38:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (120, 122, 130), (175, 180, 195)),  # Tin Seed
    39:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (190, 198, 210), (235, 240, 250)),  # Silver Seed
    40:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (180, 148, 25),  (240, 205, 75)),   # Gold Seed
    41:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (85,  155, 210), (145, 210, 245)),  # Crystal Seed
    42:   lambda sc, x, y, s: _seed_item(sc, x, y, s, (35,  25,  48),  (80,  58,  110)),  # Obsidian Seed
    # Biome wood types
    43:   lambda sc, x, y, s: _wood_item(sc, x, y, s, (155, 120, 70), (95, 72, 32)),    # Pine Wood
    44:   lambda sc, x, y, s: _wood_item(sc, x, y, s, (60, 110, 48),  (35, 68, 22)),    # Jungle Wood
    45:   lambda sc, x, y, s: _wood_item(sc, x, y, s, (200, 165, 90), (138, 108, 48)),  # Palm Wood
    46:   lambda sc, x, y, s: _sapling_item(sc, x, y, s),                               # Pine Sapling
    47:   lambda sc, x, y, s: _sapling_item(sc, x, y, s),                               # Jungle Sapling
    48:   lambda sc, x, y, s: _sapling_item(sc, x, y, s),                               # Palm Sapling
    22:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (118, 98, 72), (75, 58, 38), (184, 115, 51)),   # Copper Ore
    23:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (110, 112, 118), (72, 74, 80), (165, 175, 188)),# Tin Ore
    24:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (95, 98, 108), (58, 62, 72), (210, 218, 228)),  # Silver Ore
    25:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (118, 98, 72), (75, 58, 38), (218, 175, 35)),   # Gold Ore
    26:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (148, 148, 158), (95, 95, 105), (105, 172, 215)),# Crystal Shard
    27:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (38, 28, 52), (18, 12, 28), (75, 55, 105)),      # Obsidian Shard
    # Processed materials
    100:  _iron_bar,
    120:  _stone_brick,
    101:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (184, 115, 51), (118, 68, 22), (220, 162, 100)), # Copper Bar
    102:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (165, 175, 188), (108, 118, 130), (210, 220, 235)),# Tin Bar
    110:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (178, 135, 68), (118, 88, 35), (218, 178, 112)), # Bronze Bar
    103:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (215, 220, 228), (148, 155, 168), (245, 248, 255)),# Silver Bar
    104:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (218, 175, 35), (148, 115, 15), (252, 215, 90)), # Gold Bar
    111:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (128, 135, 148), (75, 82, 95), (185, 192, 208)), # Steel Bar
    121:  lambda sc, x, y, s: _carbon_item(sc, x, y, s),                                              # Carbon
    # Placeable items — stations
    200:  _crafting_table_item,
    201:  _furnace_item,
    202:  lambda sc, x, y, s: _alloy_forge_item(sc, x, y, s),                                         # Alloy Forge
    203:  lambda sc, x, y, s: _chest_item(sc, x, y, s),                                               # Chest
    207:  _campfire_item,
    214:  _torch_item,
    215:  _lantern_item,
    # Placeable items — walls/furniture
    220:  _bed_item,
    250:  _wood_wall_item,
    251:  _stone_wall_item,
    252:  _door_item,
    253:  _stone_brick_wall_item,
    254:  _stone_brick_floor_item,
    # Weapons — scrap tier
    1000: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (148, 128, 105), (92, 78, 58), (110, 80, 40)),                           # scrap knife
    1001: lambda sc, x, y, s: _mace(sc, x, y, s,
            (148, 128, 105), (92, 78, 58)),                                           # scrap club
    # Weapons — wood/bone/stone tier
    1050: lambda sc, x, y, s: _sword(sc, x, y, s,
            (208, 192, 148), (145, 125, 80), (110, 75, 28), (130, 85, 35)),          # wooden sword
    1051: lambda sc, x, y, s: _mace(sc, x, y, s,
            (148,  96,  45), (88,  52,  12)),                                         # wooden mace
    1052: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (232, 222, 205), (170, 158, 138), (210, 198, 178)),                       # bone dagger
    1053: lambda sc, x, y, s: _mace(sc, x, y, s,
            (128, 128, 132), (80, 80, 86)),                                            # stone mace
    # Weapons — iron tier
    1100: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (168, 172, 182), (100, 102, 118), (128, 130, 142)),                       # iron dagger
    1101: lambda sc, x, y, s: _sword(sc, x, y, s,
            (168, 172, 182), (102, 105, 118), (145, 110, 50), (100, 80, 30)),         # iron sword
    1102: lambda sc, x, y, s: _mace(sc, x, y, s,
            (162, 162, 168), (98,  98, 110)),                                          # iron mace
    # Weapons — copper tier
    1150: lambda sc, x, y, s: _sword(sc, x, y, s,
            (184, 115, 51), (118, 68, 22), (130, 85, 35), (100, 60, 20)),             # copper sword
    1151: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (184, 115, 51), (118, 68, 22), (110, 70, 20)),                            # copper dagger
    1152: lambda sc, x, y, s: _mace(sc, x, y, s,
            (184, 115, 51), (118, 68, 22)),                                            # copper mace
    # Weapons — bronze tier
    1200: lambda sc, x, y, s: _sword(sc, x, y, s,
            (178, 135, 68), (118, 88, 35), (110, 75, 28), (90, 55, 15)),              # bronze sword
    1201: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (178, 135, 68), (118, 88, 35), (100, 65, 20)),                            # bronze dagger
    1202: lambda sc, x, y, s: _mace(sc, x, y, s,
            (178, 135, 68), (118, 88, 35)),                                            # bronze mace
    # Weapons — steel tier
    1250: lambda sc, x, y, s: _sword(sc, x, y, s,
            (128, 135, 148), (75, 82, 95), (100, 80, 30), (80, 58, 18)),              # steel sword
    1251: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (128, 135, 148), (75, 82, 95), (90, 92, 105)),                            # steel dagger
    1252: lambda sc, x, y, s: _mace(sc, x, y, s,
            (128, 135, 148), (75, 82, 95)),                                            # steel mace
    # Weapons — gold tier
    1300: lambda sc, x, y, s: _dagger(sc, x, y, s,
            (218, 175, 35), (148, 115, 15), (165, 125, 40)),                          # gold shortsword
    1301: lambda sc, x, y, s: _dagger(sc, x, y, s, (212, 175, 55), (155, 125, 30), (110, 75, 20)),   # gold dagger
    1302: lambda sc, x, y, s: _mace(sc, x, y, s,   (212, 175, 55), (155, 125, 30)),                  # gold mace
    # Weapons — crystal tier
    1350: lambda sc, x, y, s: _sword(sc, x, y, s,  (140, 210, 230), (80, 155, 175), (200, 240, 250)), # crystal sword
    1351: lambda sc, x, y, s: _dagger(sc, x, y, s, (140, 210, 230), (80, 155, 175), (200, 240, 250)), # crystal dagger
    1352: lambda sc, x, y, s: _mace(sc, x, y, s,   (140, 210, 230), (80, 155, 175)),                  # crystal mace
    # Weapons — obsidian tier
    1400: lambda sc, x, y, s: _sword(sc, x, y, s,
            (38, 28, 52), (18, 12, 28), (55, 38, 18), (38, 25, 10)),                  # obsidian blade
    1401: lambda sc, x, y, s: _dagger(sc, x, y, s, (55, 45, 70), (30, 22, 42), (90, 75, 110)),        # obsidian dagger
    1402: lambda sc, x, y, s: _mace(sc, x, y, s,   (55, 45, 70), (30, 22, 42)),                       # obsidian mace
    # Rapiers — thin thrusting sword with disc guard
    1500: lambda sc, x, y, s: _rapier(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),                  # iron rapier
    1550: lambda sc, x, y, s: _rapier(sc, x, y, s, (184, 115,  51), (118,  68,  22)),                  # copper rapier
    1600: lambda sc, x, y, s: _rapier(sc, x, y, s, (178, 135,  68), (118,  88,  35)),                  # bronze rapier
    1650: lambda sc, x, y, s: _rapier(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),                  # steel rapier
    1700: lambda sc, x, y, s: _rapier(sc, x, y, s, (218, 175,  35), (148, 115,  15)),                  # gold rapier
    1750: lambda sc, x, y, s: _rapier(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),                  # crystal rapier
    # Wands — staff + glowing magical orb
    1800: lambda sc, x, y, s: _wand(sc, x, y, s, (148,  96,  45), ( 88,  52,  12)),                    # wooden wand
    1801: lambda sc, x, y, s: _wand(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),                    # crystal wand
    1802: lambda sc, x, y, s: _wand(sc, x, y, s, (255, 140,  40), (200,  75,  10)),                    # fire wand
    1803: lambda sc, x, y, s: _wand(sc, x, y, s, (255, 245,  55), (190, 170,  15)),                    # storm wand
    1804: lambda sc, x, y, s: _wand(sc, x, y, s, ( 80, 215,  90), ( 40, 145,  50), (60, 115, 55)),     # nature wand
    1805: lambda sc, x, y, s: _wand(sc, x, y, s, ( 90,  50, 160), ( 50,  20, 100)),                    # shadow wand
    # Katanas — long single-edge blade with round tsuba
    1850: lambda sc, x, y, s: _katana(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),                  # iron katana
    1851: lambda sc, x, y, s: _katana(sc, x, y, s, (184, 115,  51), (118,  68,  22)),                  # copper katana
    1852: lambda sc, x, y, s: _katana(sc, x, y, s, (178, 135,  68), (118,  88,  35)),                  # bronze katana
    1853: lambda sc, x, y, s: _katana(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),                  # steel katana
    1854: lambda sc, x, y, s: _katana(sc, x, y, s, (218, 175,  35), (148, 115,  15)),                  # gold katana
    1855: lambda sc, x, y, s: _katana(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),                  # crystal katana
    # Sabers — cavalry sword (sword shape, distinct guard colour)
    1860: lambda sc, x, y, s: _sword(sc, x, y, s, (162, 162, 168), ( 98,  98, 110), (120, 100,  60)),  # iron saber
    1861: lambda sc, x, y, s: _sword(sc, x, y, s, (184, 115,  51), (118,  68,  22), (120, 100,  60)),  # copper saber
    1862: lambda sc, x, y, s: _sword(sc, x, y, s, (178, 135,  68), (118,  88,  35), (120, 100,  60)),  # bronze saber
    1863: lambda sc, x, y, s: _sword(sc, x, y, s, (128, 135, 148), ( 75,  82,  95), (120, 100,  60)),  # steel saber
    1864: lambda sc, x, y, s: _sword(sc, x, y, s, (218, 175,  35), (148, 115,  15), (218, 175,  35)),  # gold saber
    1865: lambda sc, x, y, s: _sword(sc, x, y, s, (140, 210, 230), ( 80, 155, 175), (160, 230, 255)),  # crystal saber
    # Scimitars — broad curved blade
    1870: lambda sc, x, y, s: _scimitar(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),                # iron scimitar
    1871: lambda sc, x, y, s: _scimitar(sc, x, y, s, (184, 115,  51), (118,  68,  22)),                # copper scimitar
    1872: lambda sc, x, y, s: _scimitar(sc, x, y, s, (178, 135,  68), (118,  88,  35)),                # bronze scimitar
    1873: lambda sc, x, y, s: _scimitar(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),                # steel scimitar
    1874: lambda sc, x, y, s: _scimitar(sc, x, y, s, (218, 175,  35), (148, 115,  15)),                # gold scimitar
    # Tools — scrap tier
    2000: lambda sc, x, y, s: _axe(sc, x, y, s, (148, 128, 105), (92, 78, 58)),       # scrap axe
    2001: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (148, 128, 105), (92, 78, 58)),   # scrap pickaxe
    # Tools — wood/stone tier
    2050: lambda sc, x, y, s: _axe(sc, x, y, s, (148,  96,  45), (88, 52, 12)),       # wooden axe
    2051: lambda sc, x, y, s: _axe(sc, x, y, s, (140, 140, 140), (88, 88, 88)),       # stone axe
    2052: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (148,  96,  45), (88, 52, 12)),   # wooden pickaxe
    2053: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (140, 140, 140), (88, 88, 88)),   # stone pickaxe
    # Tools — iron tier
    2100: lambda sc, x, y, s: _axe(sc, x, y, s, (162, 162, 168), (98, 98, 110)),      # iron axe
    2101: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (162, 162, 168), (98, 98, 110)),  # iron pickaxe
    # Tools — copper tier
    2150: lambda sc, x, y, s: _axe(sc, x, y, s, (184, 115, 51), (118, 68, 22)),       # copper axe
    2151: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (184, 115, 51), (118, 68, 22)),   # copper pickaxe
    # Tools — bronze tier
    2200: lambda sc, x, y, s: _axe(sc, x, y, s, (178, 135, 68), (118, 88, 35)),       # bronze axe
    2201: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (178, 135, 68), (118, 88, 35)),   # bronze pickaxe
    # Tools — steel tier
    2250: lambda sc, x, y, s: _axe(sc, x, y, s, (128, 135, 148), (75, 82, 95)),       # steel axe
    2251: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (128, 135, 148), (75, 82, 95)),   # steel pickaxe
    # Tools — gold tier
    2300: lambda sc, x, y, s: _axe(sc, x, y, s,      (212, 175, 55), (155, 125, 30)),                # gold axe
    2301: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (218, 175, 35), (148, 115, 15)),  # gold pickaxe
    # Tools — crystal tier
    2350: lambda sc, x, y, s: _axe(sc, x, y, s,      (140, 210, 230), (80, 155, 175)),               # crystal axe
    2351: lambda sc, x, y, s: _pickaxe(sc, x, y, s, (105, 172, 215), (55, 112, 168)), # crystal pick
    # Tools — obsidian tier
    2400: lambda sc, x, y, s: _axe(sc, x, y, s,      (55, 45, 70), (30, 22, 42)),                    # obsidian axe
    2401: lambda sc, x, y, s: _pickaxe(sc, x, y, s,  (55, 45, 70), (30, 22, 42)),                    # obsidian pickaxe
    # Tools — hammers
    2500: lambda sc, x, y, s: _hammer(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),                  # iron hammer
    2550: lambda sc, x, y, s: _hammer(sc, x, y, s, (184, 115,  51), (118,  68,  22)),                  # copper hammer
    2600: lambda sc, x, y, s: _hammer(sc, x, y, s, (178, 135,  68), (118,  88,  35)),                  # bronze hammer
    2650: lambda sc, x, y, s: _hammer(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),                  # steel hammer
    2700: lambda sc, x, y, s: _hammer(sc, x, y, s, (218, 175,  35), (148, 115,  15)),                  # gold hammer
    2750: lambda sc, x, y, s: _hammer(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),                  # crystal hammer
    # Armor — head
    3000: lambda sc, x, y, s: _helm(sc, x, y, s, (148, 128, 105), (92, 78, 58)),      # scrap cap
    3001: lambda sc, x, y, s: _helm(sc, x, y, s, (128, 128, 132), (80, 80, 86)),      # stone helm
    3002: lambda sc, x, y, s: _helm(sc, x, y, s, (162, 162, 168), (98, 98, 110)),     # iron helm
    3003: lambda sc, x, y, s: _helm(sc, x, y, s, (184, 115, 51), (118, 68, 22)),      # copper helm
    3004: lambda sc, x, y, s: _helm(sc, x, y, s, (178, 135, 68), (118, 88, 35)),      # bronze helm
    3005: lambda sc, x, y, s: _helm(sc, x, y, s, (128, 135, 148), (75, 82, 95)),      # steel helm
    3006: lambda sc, x, y, s: _crown(sc, x, y, s, (218, 175, 35), (148, 115, 15)),    # gold crown
    3007: lambda sc, x, y, s: _helm(sc, x, y, s,     (140, 210, 230), (80, 155, 175)),               # crystal helm
    3008: lambda sc, x, y, s: _helm(sc, x, y, s,     (55, 45, 70), (30, 22, 42)),                    # obsidian helm
    # Armor — chest
    3100: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (148, 128, 105), (92, 78, 58)),                                            # scrap vest
    3101: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (48, 138, 72), (28, 92, 48), (38, 115, 60)),                              # reed tunic
    3102: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (222, 210, 188), (155, 143, 125), (185, 173, 152)),                       # bone vest
    3103: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (162, 162, 168), (98, 98, 110), (128, 130, 142)),                         # iron chestplate
    3104: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (184, 115, 51), (118, 68, 22), (210, 152, 88)),                           # copper vest
    3105: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (178, 135, 68), (118, 88, 35), (215, 175, 110)),                          # bronze vest
    3106: lambda sc, x, y, s: _tunic(sc, x, y, s,
            (128, 135, 148), (75, 82, 95), (175, 182, 198)),                          # steel vest
    3107: lambda sc, x, y, s: _tunic(sc, x, y, s,    (212, 175, 55), (155, 125, 30), (235, 200, 80)),# gold chestplate
    3108: lambda sc, x, y, s: _tunic(sc, x, y, s,    (140, 210, 230), (80, 155, 175), (200, 240, 250)),# crystal chestplate
    3109: lambda sc, x, y, s: _tunic(sc, x, y, s,    (55, 45, 70), (30, 22, 42), (90, 75, 110)),     # obsidian chestplate
    # Armor — arms
    3200: lambda sc, x, y, s: _bracers(sc, x, y, s,
            (222, 210, 188), (155, 143, 125), (185, 173, 152)),                      # bone bracers
    3201: lambda sc, x, y, s: _bracers(sc, x, y, s,
            (162, 162, 168), (98, 98, 110), (128, 130, 142)),                        # iron bracers
    3202: lambda sc, x, y, s: _bracers(sc, x, y, s,
            (184, 115, 51), (118, 68, 22), (210, 152, 88)),                          # copper bracers
    3203: lambda sc, x, y, s: _bracers(sc, x, y, s,
            (178, 135, 68), (118, 88, 35), (215, 175, 110)),                         # bronze bracers
    3204: lambda sc, x, y, s: _bracers(sc, x, y, s,
            (128, 135, 148), (75, 82, 95), (175, 182, 198)),                         # steel bracers
    3205: lambda sc, x, y, s: _bracers(sc, x, y, s,  (212, 175, 55), (155, 125, 30), (235, 200, 80)),# gold bracers
    3206: lambda sc, x, y, s: _bracers(sc, x, y, s,  (140, 210, 230), (80, 155, 175), (200, 240, 250)),# crystal bracers
    3207: lambda sc, x, y, s: _bracers(sc, x, y, s,  (55, 45, 70), (30, 22, 42), (90, 75, 110)),     # obsidian bracers
    # Armor — legs
    3300: lambda sc, x, y, s: _leggings(sc, x, y, s,
            (148, 128, 105), (92, 78, 58)),                                           # scrap leggings
    3301: lambda sc, x, y, s: _leggings(sc, x, y, s,
            (48, 138, 72), (28, 92, 48)),                                             # reed leggings
    3302: lambda sc, x, y, s: _leggings(sc, x, y, s,
            (222, 210, 188), (155, 143, 125)),                                        # bone leggings
    3303: lambda sc, x, y, s: _leggings(sc, x, y, s, (184, 115, 51), (118, 68, 22)), # copper leggings
    3304: lambda sc, x, y, s: _leggings(sc, x, y, s, (178, 135, 68), (118, 88, 35)), # bronze leggings
    3305: lambda sc, x, y, s: _leggings(sc, x, y, s, (128, 135, 148), (75, 82, 95)), # steel leggings
    3306: lambda sc, x, y, s: _leggings(sc, x, y, s, (162, 162, 168), (98, 98, 110)), # iron leggings
    3307: lambda sc, x, y, s: _leggings(sc, x, y, s, (212, 175, 55), (155, 125, 30)),                # gold leggings
    3308: lambda sc, x, y, s: _leggings(sc, x, y, s, (140, 210, 230), (80, 155, 175)),               # crystal leggings
    3309: lambda sc, x, y, s: _leggings(sc, x, y, s, (55, 45, 70), (30, 22, 42)),                    # obsidian leggings
    # Armor — feet
    3400: lambda sc, x, y, s: _sandals(sc, x, y, s,
            (82, 148, 45), (50, 98, 22)),                                             # leaf sandals
    3401: lambda sc, x, y, s: _boots(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),  # iron boots
    3402: lambda sc, x, y, s: _boots(sc, x, y, s, (178, 135,  68), (118,  88,  35)),  # bronze boots
    3403: lambda sc, x, y, s: _boots(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),  # steel boots
    3404: lambda sc, x, y, s: _boots(sc, x, y, s, (184, 115,  51), (118,  68,  22)),  # copper boots
    3405: lambda sc, x, y, s: _boots(sc, x, y, s, (212, 175,  55), (155, 125,  30)),  # gold boots
    3406: lambda sc, x, y, s: _boots(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),  # crystal boots
    3407: lambda sc, x, y, s: _boots(sc, x, y, s, ( 55,  45,  70), ( 30,  22,  42)),  # obsidian boots
    # Armor — back
    3500: lambda sc, x, y, s: _cloak(sc, x, y, s, (52, 158, 62), (28, 108, 38)),      # leaf cloak
    3501: lambda sc, x, y, s: _pouch(sc, x, y, s,
            (52, 162, 72), (28, 108, 48), (88, 62, 28)),                             # herb pouch
    # Armor — capes (material tiers)
    3502: lambda sc, x, y, s: _cloak(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),                  # iron cape
    3503: lambda sc, x, y, s: _cloak(sc, x, y, s, (178, 135,  68), (118,  88,  35)),                  # bronze cloak
    3504: lambda sc, x, y, s: _cloak(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),                  # steel cape
    3505: lambda sc, x, y, s: _cloak(sc, x, y, s, (218, 175,  35), (148, 115,  15)),                  # gold cloak
    3506: lambda sc, x, y, s: _cloak(sc, x, y, s, (195,  40,  40), (130,  20,  20)),                  # crimson cloak
    3507: lambda sc, x, y, s: _cloak(sc, x, y, s, ( 30,  22,  40), ( 15,  10,  25)),                  # shadow cloak
    3508: lambda sc, x, y, s: _cloak(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),                  # crystal cloak
    3510: lambda sc, x, y, s: _crown(sc, x, y, s, ( 62, 178,  85), ( 35, 115,  48)),                  # Slime Crown
    # Wings (premium back items) — drawn as a stylized double-wing icon
    3520: lambda sc, x, y, s: _wings_art(sc, x, y, s, ( 20,  15,  30), ( 55,  38,  70)),  # Bat Wings
    3521: lambda sc, x, y, s: _wings_art(sc, x, y, s, (230, 230, 245), (170, 170, 200)),  # Angel Wings
    3522: lambda sc, x, y, s: _wings_art(sc, x, y, s, ( 25,  20,  32), ( 65,  50,  85)),  # Dark Angel Wings
    3523: lambda sc, x, y, s: _wings_art(sc, x, y, s, ( 80, 145, 230), ( 40,  85, 165)),  # Sky Wings
    3524: lambda sc, x, y, s: _wings_art(sc, x, y, s, (210, 140,  20), (145,  85,  10)),  # Monarch Wings
    3525: lambda sc, x, y, s: _wings_art(sc, x, y, s, ( 60, 180, 220), ( 25, 115, 155)),  # Dragonfly Wings
    3526: lambda sc, x, y, s: _wings_art(sc, x, y, s, ( 60, 215,  90), ( 30, 140,  55)),  # Pixie Wings
    # Trinkets — rings
    3600: lambda sc, x, y, s: _ring(sc, x, y, s,
            (215, 172, 52), (148, 112, 22), (132, 202, 242), (72, 148, 195)),        # crystal ring
    3601: lambda sc, x, y, s: _ring(sc, x, y, s,
            (88, 62, 28), (55, 38, 15), (180, 118, 35), (120, 72, 15)),              # mushroom ring
    # Trinkets — necklaces
    3650: lambda sc, x, y, s: _necklace(sc, x, y, s, (212, 182, 95), _shell_pendant), # shell necklace
    3651: lambda sc, x, y, s: _necklace(sc, x, y, s, (180, 220, 255), _snowflake_pendant), # snow pendant
    # Trinkets — necklaces (crafted tiers)
    3652: lambda sc, x, y, s: _necklace(sc, x, y, s, (218, 175,  35), _shell_pendant),     # gold chain
    3653: lambda sc, x, y, s: _necklace(sc, x, y, s, (162, 162, 168), _shell_pendant),     # iron cross
    3654: lambda sc, x, y, s: _necklace(sc, x, y, s, (218, 175,  35), _snowflake_pendant), # sun amulet
    3655: lambda sc, x, y, s: _necklace(sc, x, y, s, (140, 210, 230), _snowflake_pendant), # holy pendant
    3656: lambda sc, x, y, s: _necklace(sc, x, y, s, (215, 220, 228), _shell_pendant),     # silver chain
    3657: lambda sc, x, y, s: _necklace(sc, x, y, s, ( 75,  55, 105), _snowflake_pendant), # shadow star
    # Consumables
    4000: lambda sc, x, y, s: _cup(sc, x, y, s,
            (195, 168, 128), (130, 105, 70), (55, 155, 72)),                         # herb tea
    4001: lambda sc, x, y, s: _bowl(sc, x, y, s,
            (140,  82,  32), (88,  50,  15), (188, 122, 52)),                        # mushroom stew
    4002: lambda sc, x, y, s: _flask(sc, x, y, s,
            (68, 210, 108), (32, 140, 62)),                                          # healing potion
    4003: lambda sc, x, y, s: _flask(sc, x, y, s,
            (80, 160, 230), (40, 90, 160)),                                          # stamina brew (blue)

    # Raw materials (new + existing)
    30:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (182, 148, 98),  (128, 98, 58),  (218, 188, 145)), # Clay
    31:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (62,  55,  50),  (38,  32,  28), (95,  88,  82)),  # Flint
    32:   lambda sc, x, y, s: _bar_item(sc, x, y, s, (218, 205, 178), (158, 145, 118),(242, 232, 215)), # Paper
    33:   lambda sc, x, y, s: _ore_item(sc, x, y, s, (62,  178, 85),  (38,  115, 52), (120, 215, 138)), # Slime

    # ── FOOD / DROPS (57-61) ─────────────────────────────────────────────────
    57:   lambda sc, x, y, s: _spider_silk(sc, x, y, s),                                                        # Spider Silk
    58:   lambda sc, x, y, s: _scorpion_venom(sc, x, y, s),                                                     # Scorpion Venom
    59:   lambda sc, x, y, s: _raw_meat(sc, x, y, s),                                                   # Raw Meat
    60:   lambda sc, x, y, s: _cooked_meat(sc, x, y, s),                                                # Cooked Meat
    61:   lambda sc, x, y, s: _yeti_fur(sc, x, y, s),                                                   # Yeti Fur

    # ── GEMS (50-56) ─────────────────────────────────────────────────────────
    50:   lambda sc, x, y, s: _gem_item(sc, x, y, s, (255,  70,  30), (255, 140, 100)),  # Fire Ruby
    51:   lambda sc, x, y, s: _gem_item(sc, x, y, s, ( 55, 145, 240), (140, 205, 255)),  # Ice Sapphire
    52:   lambda sc, x, y, s: _gem_item(sc, x, y, s, (225, 225,  35), (255, 255, 140)),  # Storm Topaz
    53:   lambda sc, x, y, s: _gem_item(sc, x, y, s, ( 50, 200,  65), (120, 240, 130)),  # Poison Emerald
    54:   lambda sc, x, y, s: _gem_item(sc, x, y, s, (120,  40, 175), (190, 120, 240)),  # Shadow Onyx
    55:   lambda sc, x, y, s: _gem_item(sc, x, y, s, (255, 248, 200), (255, 255, 255)),  # Light Pearl
    56:   lambda sc, x, y, s: _gem_item(sc, x, y, s, (148,  90,  40), (215, 165, 100)),  # Earth Garnet

    # Station — Part Maker / Part Combiner / Embedder
    204:  lambda sc, x, y, s: _part_maker_item(sc, x, y, s),
    205:  lambda sc, x, y, s: _part_combiner_item(sc, x, y, s),
    206:  lambda sc, x, y, s: _embedder_item(sc, x, y, s),

    # ── PAPER BLADE (148) ─────────────────────────────────────────────────────
    148:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (218, 205, 178), (158, 145, 118), (245, 235, 218)),  # Paper Blade

    # ── CRYSTAL PLATE (149) ───────────────────────────────────────────────────
    149:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (105, 172, 215), ( 55, 112, 168), (185, 232, 255)),  # Crystal Plate

    # ── BLADES (150-161) — elongated diamond silhouettes ─────────────────────
    150:  lambda sc, x, y, s: _blade_part(sc, x, y, s, ( 62,  55,  50), ( 38,  32,  28), ( 95,  88,  82)),  # Flint Blade
    151:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (125, 125, 128), ( 80,  80,  82), (168, 168, 172)),  # Stone Blade
    152:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (220, 210, 188), (155, 145, 125), (248, 238, 220)),  # Bone Blade
    153:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (184, 115,  51), (118,  68,  22), (225, 168, 108)),  # Copper Blade
    154:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (165, 175, 188), (108, 118, 130), (215, 225, 242)),  # Tin Blade
    155:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (162, 162, 168), ( 98,  98, 110), (215, 218, 228)),  # Iron Blade
    156:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (178, 135,  68), (118,  88,  35), (222, 182, 118)),  # Bronze Blade
    157:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (215, 220, 228), (148, 155, 168), (248, 250, 255)),  # Silver Blade
    158:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (218, 175,  35), (148, 115,  15), (255, 220, 98)),   # Gold Blade
    159:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (128, 135, 148), ( 75,  82,  95), (190, 198, 215)),  # Steel Blade
    160:  lambda sc, x, y, s: _blade_part(sc, x, y, s, ( 55,  42,  72), ( 22,  14,  38), ( 95,  72, 135)),  # Obsidian Blade
    161:  lambda sc, x, y, s: _blade_part(sc, x, y, s, (105, 172, 215), ( 55, 112, 168), (185, 232, 255)),  # Crystal Blade

    # ── AXE HEADS (162-171) — fan/wedge silhouettes ────────────────────────────
    162:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, ( 62,  55,  50), ( 38,  32,  28), ( 95,  88,  82)),  # Flint Axe Head
    163:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (125, 125, 128), ( 80,  80,  82), (168, 168, 172)),  # Stone Axe Head
    164:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (220, 210, 188), (155, 145, 125), (248, 238, 220)),  # Bone Axe Head
    165:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (184, 115,  51), (118,  68,  22), (225, 168, 108)),  # Copper Axe Head
    166:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (165, 175, 188), (108, 118, 130), (215, 225, 242)),  # Tin Axe Head
    167:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (162, 162, 168), ( 98,  98, 110), (215, 218, 228)),  # Iron Axe Head
    168:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (178, 135,  68), (118,  88,  35), (222, 182, 118)),  # Bronze Axe Head
    169:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (218, 175,  35), (148, 115,  15), (255, 220,  98)),  # Gold Axe Head
    170:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (128, 135, 148), ( 75,  82,  95), (190, 198, 215)),  # Steel Axe Head
    171:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, ( 55,  42,  72), ( 22,  14,  38), ( 95,  72, 135)),  # Obsidian Axe Head

    # ── PICK HEADS (172-181) — curved T silhouettes ────────────────────────────
    172:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, ( 62,  55,  50), ( 38,  32,  28), ( 95,  88,  82)),  # Flint Pick Head
    173:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (125, 125, 128), ( 80,  80,  82), (168, 168, 172)),  # Stone Pick Head
    174:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (184, 115,  51), (118,  68,  22), (225, 168, 108)),  # Copper Pick Head
    175:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (165, 175, 188), (108, 118, 130), (215, 225, 242)),  # Tin Pick Head
    176:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (162, 162, 168), ( 98,  98, 110), (215, 218, 228)),  # Iron Pick Head
    177:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (178, 135,  68), (118,  88,  35), (222, 182, 118)),  # Bronze Pick Head
    178:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (218, 175,  35), (148, 115,  15), (255, 220,  98)),  # Gold Pick Head
    179:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (128, 135, 148), ( 75,  82,  95), (190, 198, 215)),  # Steel Pick Head
    180:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, ( 55,  42,  72), ( 22,  14,  38), ( 95,  72, 135)),  # Obsidian Pick Head
    181:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (105, 172, 215), ( 55, 112, 168), (185, 232, 255)),  # Crystal Pick Head

    # ── PLATES (182-189) — contoured chest-plate silhouettes ──────────────────
    182:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (184, 115,  51), (118,  68,  22), (225, 168, 108)),  # Copper Plate
    183:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (165, 175, 188), (108, 118, 130), (215, 225, 242)),  # Tin Plate
    184:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (162, 162, 168), ( 98,  98, 110), (215, 218, 228)),  # Iron Plate
    185:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (178, 135,  68), (118,  88,  35), (222, 182, 118)),  # Bronze Plate
    186:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (215, 220, 228), (148, 155, 168), (248, 250, 255)),  # Silver Plate
    187:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (218, 175,  35), (148, 115,  15), (255, 220,  98)),  # Gold Plate
    188:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (128, 135, 148), ( 75,  82,  95), (190, 198, 215)),  # Steel Plate
    189:  lambda sc, x, y, s: _plate_part(sc, x, y, s, ( 55,  42,  72), ( 22,  14,  38), ( 95,  72, 135)),  # Obsidian Plate

    # ── MOLDS (190-198) — clay molds with imprinted shape silhouettes ─────────
    190:  _mold_sword,   # Sword Mold
    191:  _mold_dagger,  # Dagger Mold
    192:  _mold_axe,     # Axe Mold
    193:  _mold_pick,    # Pickaxe Mold
    194:  _mold_helm,    # Helm Mold
    195:  _mold_chest,   # Chest Mold
    196:  _mold_arms,    # Arms Mold
    197:  _mold_legs,    # Leg Mold
    198:  _mold_feet,    # Feet Mold
    199:  _mold_katana,  # Katana Mold
    208:  _mold_saber,   # Saber Mold
    209:  _mold_scimitar, # Scimitar Mold
    210:  _mold_rapier,  # Rapier Mold
    211:  _mold_hammer,  # Hammer Mold
    212:  _mold_wand,    # Wand Mold

    # ── HANDLES (260-268, 279) ────────────────────────────────────────────────
    260:  lambda sc, x, y, s: _handle(sc, x, y, s),                                                    # Wood Handle
    261:  lambda sc, x, y, s: _handle(sc, x, y, s, (220, 210, 188)),                                   # Bone Handle
    262:  lambda sc, x, y, s: _handle(sc, x, y, s, (218, 205, 178)),                                   # Paper Handle
    263:  lambda sc, x, y, s: _handle(sc, x, y, s, (184, 115, 51)),                                    # Copper Handle
    264:  lambda sc, x, y, s: _handle(sc, x, y, s, (162, 162, 168)),                                   # Iron Handle
    265:  lambda sc, x, y, s: _handle(sc, x, y, s, (178, 135, 68)),                                    # Bronze Handle
    266:  lambda sc, x, y, s: _handle(sc, x, y, s, (215, 220, 228)),                                   # Silver Handle
    267:  lambda sc, x, y, s: _handle(sc, x, y, s, (218, 175, 35)),                                    # Gold Handle
    268:  lambda sc, x, y, s: _handle(sc, x, y, s, (128, 135, 148)),                                   # Steel Handle
    279:  lambda sc, x, y, s: _handle(sc, x, y, s, (62,  178, 85)),                                    # Slime Handle

    # ── WAND CORES (269-271) — crystalline sphere component ──────────────────
    269:  lambda sc, x, y, s: _wand_core(sc, x, y, s, ( 90, 128, 162), (45,  72, 108)),                # Rough Crystal Core
    270:  lambda sc, x, y, s: _wand_core(sc, x, y, s, (112, 165, 205), (58, 108, 155)),                # Refined Crystal Core
    271:  lambda sc, x, y, s: _wand_core(sc, x, y, s, (140, 205, 238), (72, 135, 188)),                # Crystal Core

    # ── BINDINGS (272-277, 280) ───────────────────────────────────────────────
    272:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (218, 205, 178), (158, 145, 118),(242, 232, 215)), # Paper Binding
    273:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (48,  138, 72),  (28,  92,  48), (88,  192, 112)), # Reed Binding
    274:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (184, 115, 51),  (118, 68,  22), (220, 162, 100)), # Copper Binding
    275:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (162, 162, 168), (98,  98,  110),(210, 215, 225)), # Iron Binding
    276:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (178, 135, 68),  (118, 88,  35), (218, 178, 112)), # Bronze Binding
    277:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (215, 220, 228), (148, 155, 168),(245, 248, 255)), # Silver Binding
    280:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (62,  178, 85),  (38,  115, 52), (120, 215, 138)), # Slime Binding

    # ── SLIME BLADE (278) ─────────────────────────────────────────────────────
    278:  lambda sc, x, y, s: _blade_part(sc, x, y, s, ( 62, 178,  85), ( 38, 115,  52), (125, 218, 142)),  # Slime Blade

    # ── EXTRA AXE HEADS (281-282) ─────────────────────────────────────────────
    281:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (215, 220, 228), (148, 155, 168), (248, 250, 255)),  # Silver Axe Head
    282:  lambda sc, x, y, s: _axe_head_part(sc, x, y, s, (105, 172, 215), ( 55, 112, 168), (185, 232, 255)),  # Crystal Axe Head

    # ── EXTRA PICK HEADS (283-284) ────────────────────────────────────────────
    283:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (220, 210, 188), (155, 142, 118), (248, 238, 220)),  # Bone Pick Head
    284:  lambda sc, x, y, s: _pick_head_part(sc, x, y, s, (215, 220, 228), (148, 155, 168), (248, 250, 255)),  # Silver Pick Head

    # ── EXTRA PLATES (285-288) ────────────────────────────────────────────────
    285:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (125, 125, 128), ( 80,  80,  82), (168, 168, 172)),  # Stone Plate
    286:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (220, 210, 188), (155, 142, 118), (248, 238, 220)),  # Bone Plate
    287:  lambda sc, x, y, s: _plate_part(sc, x, y, s, (218, 205, 178), (158, 145, 118), (245, 235, 218)),  # Paper Plate
    288:  lambda sc, x, y, s: _plate_part(sc, x, y, s, ( 62, 178,  85), ( 38, 115,  52), (125, 218, 142)),  # Slime Plate

    # ── EXTRA HANDLES (289-291) ───────────────────────────────────────────────
    289:  lambda sc, x, y, s: _handle(sc, x, y, s, (165, 175, 188)),                                   # Tin Handle
    290:  lambda sc, x, y, s: _handle(sc, x, y, s, (38,  28,  52)),                                    # Obsidian Handle
    291:  lambda sc, x, y, s: _handle(sc, x, y, s, (105, 172, 215)),                                   # Crystal Handle

    # ── EXTRA BINDINGS (292-295) ──────────────────────────────────────────────
    292:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (165, 175, 188), (108, 118, 130),(210, 220, 235)), # Tin Binding
    293:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (218, 175, 35),  (148, 115, 15), (252, 215, 90)),  # Gold Binding
    294:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (128, 135, 148), (75,  82,  95), (185, 192, 208)), # Steel Binding
    295:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (38,  28,  52),  (18,  12,  28), (75,  55,  105)), # Obsidian Binding

    # ── BACK MOLD (213) ───────────────────────────────────────────────────────
    213:  _mold_back,  # Back Mold

    # ── CRYSTAL BINDING (296) ─────────────────────────────────────────────────
    296:  lambda sc, x, y, s: _bar_item(sc, x, y, s, (140, 210, 230), ( 80, 155, 175), (200, 240, 250)),  # Crystal Binding

    # ── LININGS (297-309) ─────────────────────────────────────────────────────
    297:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (218, 205, 178), (158, 145, 118)),  # Paper Lining
    298:  lambda sc, x, y, s: _lining_item(sc, x, y, s, ( 48, 138,  72), ( 28,  92,  48)),  # Reed Lining
    299:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (220, 210, 188), (155, 145, 125)),  # Bone Lining
    300:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (184, 115,  51), (118,  68,  22)),  # Copper Lining
    301:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (165, 175, 188), (108, 118, 130)),  # Tin Lining
    302:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),  # Iron Lining
    303:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (178, 135,  68), (118,  88,  35)),  # Bronze Lining
    304:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (215, 220, 228), (148, 155, 168)),  # Silver Lining
    305:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (218, 175,  35), (148, 115,  15)),  # Gold Lining
    306:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),  # Steel Lining
    307:  lambda sc, x, y, s: _lining_item(sc, x, y, s, ( 55,  45,  70), ( 30,  22,  42)),  # Obsidian Lining
    308:  lambda sc, x, y, s: _lining_item(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),  # Crystal Lining
    309:  lambda sc, x, y, s: _lining_item(sc, x, y, s, ( 62, 178,  85), ( 38, 115,  52)),  # Slime Lining

    # ── SHIELDS (3550-3558) ───────────────────────────────────────────────────
    3550: lambda sc, x, y, s: _shield_item(sc, x, y, s, (139,  90,  43), ( 90,  55,  15)),  # Wooden Shield
    3551: lambda sc, x, y, s: _shield_item(sc, x, y, s, (220, 210, 188), (155, 145, 125)),  # Bone Shield
    3552: lambda sc, x, y, s: _shield_item(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),  # Iron Shield
    3553: lambda sc, x, y, s: _shield_item(sc, x, y, s, (184, 115,  51), (118,  68,  22)),  # Copper Shield
    3554: lambda sc, x, y, s: _shield_item(sc, x, y, s, (178, 135,  68), (118,  88,  35)),  # Bronze Shield
    3555: lambda sc, x, y, s: _shield_item(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),  # Steel Shield
    3556: lambda sc, x, y, s: _shield_item(sc, x, y, s, (218, 175,  35), (148, 115,  15)),  # Gold Shield
    3557: lambda sc, x, y, s: _shield_item(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),  # Crystal Shield
    3558: lambda sc, x, y, s: _shield_item(sc, x, y, s, ( 55,  45,  70), ( 30,  22,  42)),  # Obsidian Shield

    # ── PAULDRONS (3560-3567) ─────────────────────────────────────────────────
    3560: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (220, 210, 188), (155, 145, 125)),  # Bone Pauldrons
    3561: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),  # Iron Pauldrons
    3562: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (184, 115,  51), (118,  68,  22)),  # Copper Pauldrons
    3563: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (178, 135,  68), (118,  88,  35)),  # Bronze Pauldrons
    3564: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),  # Steel Pauldrons
    3565: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (218, 175,  35), (148, 115,  15)),  # Gold Pauldrons
    3566: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),  # Crystal Pauldrons
    3567: lambda sc, x, y, s: _pauldrons_item(sc, x, y, s, ( 55,  45,  70), ( 30,  22,  42)),  # Obsidian Pauldrons

    # ── GLOVES (3570-3578) ────────────────────────────────────────────────────
    3570: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (148, 128, 105), ( 92,  78,  58)),  # Cloth Gloves
    3571: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (220, 210, 188), (155, 145, 125)),  # Bone Gloves
    3572: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (162, 162, 168), ( 98,  98, 110)),  # Iron Gloves
    3573: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (184, 115,  51), (118,  68,  22)),  # Copper Gloves
    3574: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (178, 135,  68), (118,  88,  35)),  # Bronze Gloves
    3575: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (128, 135, 148), ( 75,  82,  95)),  # Steel Gloves
    3576: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (218, 175,  35), (148, 115,  15)),  # Gold Gloves
    3577: lambda sc, x, y, s: _gloves_item(sc, x, y, s, (140, 210, 230), ( 80, 155, 175)),  # Crystal Gloves
    3578: lambda sc, x, y, s: _gloves_item(sc, x, y, s, ( 55,  45,  70), ( 30,  22,  42)),  # Obsidian Gloves
}


def draw_item(screen, x: int, y: int, s: int, item_id: int) -> None:
    """Draw item art at top-left (x, y) in a square of size s pixels."""
    key = (item_id, s)
    surf = _item_surface_cache.get(key)
    if surf is None:
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        fn = _ITEM_FNS.get(item_id)
        if fn:
            fn(surf, 0, 0, s)
        else:
            pygame.draw.rect(surf, (160, 80, 160), (0, 0, s, s), border_radius=2)
            pygame.draw.rect(surf, (100, 40, 100), (0, 0, s, s), 1, border_radius=2)
        _item_surface_cache[key] = surf
    screen.blit(surf, (x, y))


# ── Material tinting ─────────────────────────────────────────────────────────
# Multiplicative tint per crafting material.  Applied with BLEND_RGBA_MULT so
# dark areas stay dark and transparent pixels remain transparent.
_MATERIAL_TINT: dict[str, tuple[int, int, int]] = {
    "Flint":    ( 90,  90,  85),
    "Stone":    (150, 150, 145),
    "Bone":     (220, 210, 180),
    "Copper":   (195, 110,  55),
    "Tin":      (155, 170, 185),
    "Iron":     (175, 180, 185),
    "Bronze":   (165, 115,  45),
    "Silver":   (210, 215, 220),
    "Gold":     (220, 190,  30),
    "Steel":    (110, 140, 175),
    "Crystal":  (100, 215, 225),
    "Obsidian": ( 75,  45, 120),
    "Slime":    ( 65, 190,  65),
    "Paper":    (240, 235, 210),
}
_tinted_surface_cache: dict[tuple, pygame.Surface] = {}


def draw_item_tinted(screen, x: int, y: int, s: int, item_id: int, material: str) -> None:
    """Draw item art with a material-derived color tint.

    Falls back to plain draw_item if the material is unrecognised.
    """
    tint = _MATERIAL_TINT.get(material)
    if tint is None:
        draw_item(screen, x, y, s, item_id)
        return

    key = (item_id, s, material)
    surf = _tinted_surface_cache.get(key)
    if surf is None:
        # Ensure the base surface is cached then copy it
        base_key = (item_id, s)
        if base_key not in _item_surface_cache:
            draw_item(pygame.Surface((1, 1)), 0, 0, s, item_id)  # populates cache
        base = _item_surface_cache[base_key]

        surf = base.copy()
        tint_surf = pygame.Surface((s, s), pygame.SRCALPHA)
        tint_surf.fill((*tint, 255))
        surf.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        _tinted_surface_cache[key] = surf
    screen.blit(surf, (x, y))


def draw_node(screen, x: int, y: int, s: int, node_type: str) -> None:
    from rendering.node_art_v2 import draw_node as _draw_node_v2

    _draw_node_v2(screen, x, y, s, node_type)

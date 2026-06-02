# client/rendering/light_sources.py
"""Punch soft radial light holes into the night overlay for campfires and torches.

apply_light_holes(overlay) is called from display.draw_day_night_overlay just
before the overlay Surface is blitted to the screen.  It reads the current
camera offset from config.camera_offset_x / config.camera_offset_y so callers
don't need to pass extra parameters.
"""
import pygame
import config as _config

TILE_SIZE = _config.TILE_SIZE  # canonical value from config; not duplicated here

# Object types that emit light, mapped to their radius in tiles.
_LIGHT_RADIUS: dict[str, int] = {
    "campfire": 5,
    "torch":    4,
    "lantern":  7,
    "furnace":  3,
}

# Color used to fill the night overlay (must match display.py's overlay RGB).
_OVERLAY_RGB = (10, 10, 35)

# Cache: (radius_px, max_alpha) → pre-rendered hole Surface
_hole_cache: dict = {}


def _make_hole(radius_px: int, max_alpha: int) -> pygame.Surface:
    """Pre-render a soft circular alpha mask for one light source.

    Centre is fully transparent (alpha = 0); the rim matches the overlay alpha
    so BLEND_RGBA_MIN leaves the rim pixels unchanged.  Quadratic falloff gives
    a realistic torch-light appearance.
    """
    size = radius_px * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    # Fill with the rim value first so undrawn corners keep the overlay intact.
    surf.fill((*_OVERLAY_RGB, max_alpha))
    for r in range(radius_px, 0, -2):
        frac = r / radius_px
        a = int(max_alpha * frac * frac)   # quadratic: 0 at centre → max_alpha at rim
        pygame.draw.circle(surf, (*_OVERLAY_RGB, a), (radius_px, radius_px), r)
    return surf


def apply_light_holes(overlay: pygame.Surface) -> None:
    """Punch light holes into *overlay* in-place using BLEND_RGBA_MIN.

    Must be called after the overlay is filled with the night colour but before
    it is blitted to the screen.  Camera offsets come from config.
    """
    if not _config.placed_objects:
        return

    # Sample the overlay's current alpha — skip entirely during daytime.
    try:
        max_a = overlay.get_at((0, 0))[3]
    except Exception:
        return
    if max_a == 0:
        return

    screen_w, screen_h = overlay.get_size()
    off_x = getattr(_config, "camera_offset_x", 0)
    off_y = getattr(_config, "camera_offset_y", 0)

    for obj in _config.placed_objects.values():
        otype = obj.get("type", "")
        tile_r = _LIGHT_RADIUS.get(otype)
        if tile_r is None:
            continue

        radius_px = tile_r * TILE_SIZE
        cx = int(obj["pos"][0] * TILE_SIZE + TILE_SIZE // 2 + off_x)
        cy = int(obj["pos"][1] * TILE_SIZE + TILE_SIZE // 2 + off_y)

        # Cull lights that are completely off-screen.
        if cx + radius_px < 0 or cx - radius_px > screen_w:
            continue
        if cy + radius_px < 0 or cy - radius_px > screen_h:
            continue

        key = (radius_px, max_a)
        if key not in _hole_cache:
            _hole_cache[key] = _make_hole(radius_px, max_a)

        overlay.blit(
            _hole_cache[key],
            (cx - radius_px, cy - radius_px),
            special_flags=pygame.BLEND_RGBA_MIN,
        )

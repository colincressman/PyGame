"""
lpc.py — LPC spritesheet loader and frame cache.

Handles two sheet layouts:
  Direct:  {folder}/{anim}.png          (single colour sheet)
  Variant: {folder}/{anim}/{colour}.png (per-colour sheets)

Animation frame counts:
  idle  = 2 frames, 4 directions (128 × 256)
  walk  = 9 frames, 4 directions (576 × 256)
  slash = 6 frames, 4 directions (384 × 256)

Row/direction order (0-indexed):
  Row 0 = up, Row 1 = left, Row 2 = down, Row 3 = right
"""

import os
import pygame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LPC_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..",
    "data",
    "texturepack",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CELL = 64  # px per frame cell

ANIM_FRAMES: dict[str, int] = {
    "idle":   2,
    "walk":   9,
    "run":    8,
    "slash":  6,
    "thrust": 8,
}

DIRS = ("up", "left", "down", "right")
DIR_ROW: dict[str, int] = {
    "up":    0,
    "left":  1,
    "down":  2,
    "right": 3,
}

# ---------------------------------------------------------------------------
# Internal sheet cache:  abs_png_path -> list[list[Surface]]
#   outer list = 4 directions, inner list = n_frames Surfaces
# ---------------------------------------------------------------------------
_sheet_cache: dict[str, list] = {}


def _load_sheet(abs_path: str) -> list:
    """Load a spritesheet PNG and split it into rows × frames of CELL×CELL."""
    if abs_path in _sheet_cache:
        return _sheet_cache[abs_path]
    img = pygame.image.load(abs_path).convert_alpha()
    w, h = img.get_size()
    n_dirs   = h // CELL
    n_frames = w // CELL
    rows = []
    for r in range(n_dirs):
        frames = []
        for f in range(n_frames):
            frames.append(img.subsurface(pygame.Rect(f * CELL, r * CELL, CELL, CELL)))
        rows.append(frames)
    _sheet_cache[abs_path] = rows
    return rows


def resolve_png(layer_folder: str, anim: str, colour: str | None = None) -> str | None:
    """
    Resolve the absolute path to the PNG for (layer_folder, anim, colour).

    Priority:
      1. {folder}/{anim}/{colour}.png          if colour is given
      2. {folder}/{anim}.png                   direct sheet
      3. {folder}/{anim}/<first_alpha_file>.png fallback (no colour arg, subdir only)

    Returns None if the file cannot be found.
    """
    folder = os.path.join(LPC_DIR, layer_folder)

    if colour is not None:
        p = os.path.join(folder, anim, f"{colour}.png")
        return p if os.path.isfile(p) else None

    # Try direct PNG first
    direct = os.path.join(folder, f"{anim}.png")
    if os.path.isfile(direct):
        return direct

    # Fall back to colour-subdir with the first available file
    subdir = os.path.join(folder, anim)
    if os.path.isdir(subdir):
        options = sorted(f for f in os.listdir(subdir) if f.endswith(".png"))
        if options:
            return os.path.join(subdir, options[0])

    return None


def get_frames(
    layer_folder: str,
    anim: str,
    colour: str | None = None,
) -> list | None:
    """
    Return the animation frames for one layer.

    Returns a list of 4 sublists (one per direction order: down/left/right/up),
    each containing ANIM_FRAMES[anim] pygame.Surface objects.
    Returns None if the layer file does not exist (layer is silently skipped).
    """
    png = resolve_png(layer_folder, anim, colour)
    if png is None:
        return None
    return _load_sheet(png)


def get_frames_128(
    layer_folder: str,
    anim: str,
    colour: str | None = None,
) -> list | None:
    """Load a sheet with 128×128 cells. Returns 4 rows × N cols of 128×128 Surfaces.
    Blit these at (x - 32, y - 32) so the centre of each cell aligns with the
    standard 64×64 player position, giving the blade room to extend outward."""
    png = resolve_png(layer_folder, anim, colour)
    if png is None:
        return None
    key = (png, 128)
    if key in _sheet_cache:
        return _sheet_cache[key]
    img = pygame.image.load(png).convert_alpha()
    w, h = img.get_size()
    cell = 128
    n_dirs   = h // cell
    n_frames = w // cell
    rows = [
        [img.subsurface(pygame.Rect(f * cell, r * cell, cell, cell))
         for f in range(n_frames)]
        for r in range(n_dirs)
    ]
    _sheet_cache[key] = rows
    return rows


# ---------------------------------------------------------------------------
# Attack-slash loader (192×192 px cells — longsword, mace, waraxe, etc.)
# ---------------------------------------------------------------------------
_ATTACK_CELL = 192  # px per frame for weapon attack_slash sheets (6 frames × 4 dirs)


def _load_attack_sheet(abs_path: str) -> list:
    """Load a 192-px-cell attack spritesheet and return rows of Surface lists."""
    if abs_path in _sheet_cache:
        return _sheet_cache[abs_path]
    img = pygame.image.load(abs_path).convert_alpha()
    w, h = img.get_size()
    n_dirs   = h // _ATTACK_CELL
    n_frames = w // _ATTACK_CELL
    rows = [
        [img.subsurface(pygame.Rect(f * _ATTACK_CELL, r * _ATTACK_CELL, _ATTACK_CELL, _ATTACK_CELL))
         for f in range(n_frames)]
        for r in range(n_dirs)
    ]
    _sheet_cache[abs_path] = rows
    return rows


def get_attack_frames(layer_folder: str, colour: str | None = None) -> list | None:
    """
    Return 192-px attack_slash frames for weapon layers that use that convention.
    Returns None if no attack_slash sheet exists for this folder.
    """
    png = resolve_png(layer_folder, "attack_slash", colour)
    if png is None:
        return None
    return _load_attack_sheet(png)


def get_attack_behind_frames(layer_folder: str, colour: str | None = None) -> list | None:
    """Return 192-px attack_slash/behind frames (behind-body part of slash anim),
    or None if no such sheet exists for this folder."""
    import os as _os
    behind_dir = _os.path.join(LPC_DIR, layer_folder, "attack_slash", "behind")
    if not _os.path.isdir(behind_dir):
        return None
    if colour is not None:
        png = _os.path.join(behind_dir, f"{colour}.png")
    else:
        files = sorted(f for f in _os.listdir(behind_dir) if f.endswith(".png"))
        if not files:
            return None
        png = _os.path.join(behind_dir, files[0])
    if not _os.path.isfile(png):
        return None
    return _load_attack_sheet(png)

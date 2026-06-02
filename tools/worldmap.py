"""
worldmap.py — Generate a top-down biome map PNG from dyn_chunk_gen.

Usage (run from project root):
    python tools/worldmap.py

Output: tools/worldmap.png  (2048×2048 pixels, 1px per tile, centred on origin)

Tune SIZE to change coverage; 2048 = ±1024 tiles from origin.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PIL import Image

# Import the v3 noise / generation functions
from server.world.dyn_chunk_gen import (
    generate_chunk_arrays, CHUNK_SIZE, PADDING,
    BIOME_ID_MAP, CLIFF_ID_MAP,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SIZE       = 8192    # image side length in tiles (must be multiple of CHUNK_SIZE)
OUT_PATH   = os.path.join(os.path.dirname(__file__), "worldmap.png")

# ---------------------------------------------------------------------------
# Biome colour palette  (RGB)
# ---------------------------------------------------------------------------
BIOME_COLOURS = {
    0:  (26,  107, 158),   # ocean       — deep blue
    1:  (232, 213, 163),   # beach       — sand
    2:  (74,  94,  44),    # swamp       — dark olive
    3:  (91,  155, 213),   # river       — light blue
    4:  (139, 195, 74),    # plains      — light green
    5:  (46,  125, 50),    # forest      — dark green
    6:  (212, 164, 76),    # desert      — tan
    7:  (198, 134, 66),    # alt_desert  — terracotta
    8:  (0,   200, 83),    # tropical    — bright green
    9:  (176, 190, 197),   # tundra      — blue-grey
    10: (96,  125, 139),   # mountain    — slate
}
# Cliff overrides all get the same highlight colour
CLIFF_COLOUR = (80, 60, 40)   # dark brown
DEFAULT_COLOUR = (200, 0, 200) # magenta — should never appear


def biome_colour(biome_id: int) -> tuple:
    if biome_id in CLIFF_ID_MAP.values():
        return CLIFF_COLOUR
    return BIOME_COLOURS.get(biome_id, DEFAULT_COLOUR)


def main():
    half = SIZE // 2
    # Tile range: [-half, half)
    # In chunk coords that spans [-half//CHUNK_SIZE, half//CHUNK_SIZE)
    cx_range = range(-half // CHUNK_SIZE, half // CHUNK_SIZE)
    cy_range = range(-half // CHUNK_SIZE, half // CHUNK_SIZE)

    total_chunks = len(cx_range) * len(cy_range)
    print(f"Generating {SIZE}×{SIZE} map ({total_chunks} chunks)…")

    # Build a colour array; index [px_y, px_x] = (R,G,B)
    img_data = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)

    done = 0
    for cy in cy_range:
        for cx in cx_range:
            biome_ids, _ = generate_chunk_arrays(cx, cy)

            # biome_ids is (CHUNK_SIZE+2*PADDING) x same — central CHUNK_SIZE tiles
            for lx in range(CHUNK_SIZE):
                for ly in range(CHUNK_SIZE):
                    tx = cx * CHUNK_SIZE + lx
                    ty = cy * CHUNK_SIZE + ly
                    # Map world tile → image pixel (flip y so north is up)
                    px = tx + half
                    py = half - 1 - ty
                    if 0 <= px < SIZE and 0 <= py < SIZE:
                        bid = int(biome_ids[lx + PADDING, ly + PADDING])
                        img_data[py, px] = biome_colour(bid)

        done += len(cx_range)
        pct = done / total_chunks * 100
        print(f"  {pct:5.1f}%", end="\r", flush=True)

    print()

    # Draw origin crosshair
    mid = half
    img_data[mid - 4 : mid + 5, mid] = (255, 255, 0)
    img_data[mid, mid - 4 : mid + 5] = (255, 255, 0)

    img = Image.fromarray(img_data, "RGB")
    img.save(OUT_PATH)
    print(f"Saved → {OUT_PATH}")

    # ---------- Legend ----------
    print("\nBiome legend:")
    id_to_name = {v: k for k, v in BIOME_ID_MAP.items()}
    for bid, col in sorted(BIOME_COLOURS.items()):
        print(f"  {col}  {id_to_name.get(bid, str(bid))}")


if __name__ == "__main__":
    main()

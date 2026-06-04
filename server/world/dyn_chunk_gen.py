# server/world/dyn_chunk_gen.py
#
# V3 world generator — industry-standard 5-channel technique (Minecraft 1.18+ style):
#   1. Domain warping       — organic, non-repeating coastlines (Inigo Quilez)
#   2. Ridge noise          — natural mountain chains via peaks_valleys channel
#   3. Spline curves        — smooth height mapping from continentalness × erosion
#   4. Dedicated river noise— carved river channels independent of terrain shape
#   5. Climate biomes       — 4D profile match: temperature × humidity × continentalness × erosion
#
# Channels (per tile):
#   c   — continentalness   large-scale land/ocean shape
#   e   — erosion           flatness; suppresses mountains where high
#   pv  — peaks_valleys     ridge noise; drives mountain placement
#   t   — temperature       latitude-biased climate gradient
#   m   — humidity          local moisture
#   r   — rivers            independent river carving channel
#   h   — final height      = spline(c) + detail * 0.12 + pv * e_scale * 0.18
#
# Chunk directory: world_chunks_v3/

import numpy as np
from numba import njit, prange
from threading import Lock
import psutil
import os
import json   # still needed for json.JSONDecodeError
try:
    import orjson as _orjson   # ~3-5x faster for chunk load/save
except ImportError:
    _orjson = None             # fallback: stdlib json used below
import heapq
from server.world.world_types import BIOME_ID_MAP, CLIFF_ID_MAP, ID_TO_BIOME, ID_TO_CLIFF

queued_chunks = set()

PADDING    = 1
from server.config import CHUNK_SIZE, CHUNK_DIR, WORLD_SEED as SEED

# ---------------------------------------------------------------------------
# Noise scales
# ---------------------------------------------------------------------------
WARP_SCALE          = 600.0    # domain-warp coordinate noise
WARP_STRENGTH       = 150.0    # max tile displacement (± tiles)
HEIGHT_SCALE        = 800.0    # fine detail noise (domain-warped input)
CONTINENTAL_SCALE   = 5000.0   # large land/ocean shape — big enough for vast oceans
PEAKS_SCALE         = 500.0    # ridge noise — mountain chain wavelength
EROSION_SCALE       = 1800.0   # terrain flatness variation
CLIMATE_SCALE       = 1300.0   # temperature variation
HUMIDITY_SCALE      = 800.0    # moisture variation
RIVER_SCALE         = 1200.0   # river noise (larger = wider spacing between isolines)

# ---------------------------------------------------------------------------
# Octave counts
# ---------------------------------------------------------------------------
HEIGHT_OCTAVES      = 5
PEAKS_OCTAVES       = 4
CONTINENTAL_OCTAVES = 2    # 2 = smooth coherent basins; 3 adds fragmentation
EROSION_OCTAVES     = 2
CLIMATE_OCTAVES     = 2
HUMIDITY_OCTAVES    = 2
WARP_OCTAVES        = 2

# ---------------------------------------------------------------------------
# Biome thresholds
# ---------------------------------------------------------------------------
# Ocean/coastal use continentalness c directly (Minecraft-style: c drives land/sea)
# rather than h, so the ocean reliably appears wherever c is low regardless of seed.
OCEAN_C_THRESHOLD   = 0.49     # c < this  → ocean  (higher = more ocean, helps connectivity)
LAKE_C_BAND         = 0.02     # c in [OCEAN, OCEAN+BAND] + low PV valley → inland lake
LAKE_PV_MAX         = 0.28     # pv < this when in lake band → lake
COASTAL_C_THRESHOLD = 0.52     # base beach width (now noise-varied: OCEAN_C + 0.025 ± 0.025)
COASTAL_E_MAX       = 0.55     # erosion < this required for beach to form
MOUNTAIN_SIGNAL     = 0.75     # pv * e_scale > this → mountain  (raised to reduce count)
RIVER_HALF_WIDTH    = 0.013    # |r - 0.5| < this → river isoline (~7 tile wide channel)
RIVER_MASK_SCALE    = 3000.0   # basin presence noise scale
RIVER_MASK_THRESH   = 0.57     # only ~43% of land has active river drainage

# ---------------------------------------------------------------------------
# Spline control points (piecewise-linear; must be float64 for numba)
# ---------------------------------------------------------------------------
# Continentalness → height offset  (c drives the base height level)
CONT_XS  = np.array([0.0,  0.20,  0.35,  0.45,  0.55,  0.70,  1.0 ], dtype=np.float64)
CONT_YS  = np.array([-0.48,-0.22, -0.06,  0.0,   0.07,  0.20,  0.38], dtype=np.float64)

# Erosion → PV amplitude scale  (high erosion = flat, no mountains)
EROSION_XS = np.array([0.0,  0.30,  0.55,  0.80,  1.0 ], dtype=np.float64)
EROSION_YS = np.array([2.0,  1.5,   0.8,   0.25,  0.08], dtype=np.float64)

# ---------------------------------------------------------------------------
# 4D biome profiles  [temperature, humidity, continentalness, erosion]
# Mountain is excluded — driven by ridge signal only.
# ---------------------------------------------------------------------------
biome_profiles = np.array([
    [0.75, 0.28, 0.60, 0.30],   # desert      — hot, dry, inland
    [0.85, 0.20, 0.50, 0.40],   # alt_desert  — very hot, very dry
    [0.88, 0.82, 0.50, 0.40],   # tropical    — very hot, very wet
    [0.55, 0.75, 0.42, 0.22],   # swamp       — warm, very wet, coastal
    [0.50, 0.55, 0.58, 0.45],   # forest      — warm temperate, moist
    [0.45, 0.38, 0.65, 0.30],   # plains      — warm, moderate humidity, inland
    [0.18, 0.30, 0.78, 0.22],   # tundra      — cold (unchanged)
], dtype=np.float64)

biome_id_lookup = np.array([6, 7, 8, 2, 5, 4, 9], dtype=np.uint8)

MOUNTAIN_BIOME_ID = BIOME_ID_MAP["mountain"]

GRADIENTS = np.array([
    [ 1,  1], [-1,  1], [ 1, -1], [-1, -1],
    [ 1,  0], [-1,  0], [ 0,  1], [ 0, -1],
], dtype=np.float64)

# ---------------------------------------------------------------------------
# Chunk storage  (CHUNK_DIR is defined in server.config)
# ---------------------------------------------------------------------------
os.makedirs(CHUNK_DIR, exist_ok=True)

# Cache of static node definitions per chunk — populated on generation/load.
# {(cx, cy): [{"id", "type", "lx", "ly"}, ...]}
chunk_nodes_cache: dict = {}
chunk_nodes_lock  = Lock()

# Bump this to force all existing chunks to regenerate their node lists
# (e.g. after changing densities or NODE_TYPES).
NODES_VERSION = 10


def load_chunk_from_disk(cx, cy):
    filename = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    if os.path.exists(filename):
        try:
            with open(filename, "rb") as f:
                raw_bytes = f.read()
            raw_data = _orjson.loads(raw_bytes) if _orjson else json.loads(raw_bytes)

            nodes = raw_data.get("_nodes")
            nodes_ver = raw_data.get("_nodes_version", 0)
            tiles = {
                tuple(map(int, k.split(","))): v
                for k, v in raw_data.items()
                if k not in ("_nodes", "_nodes_version")
            }

            if nodes is None or nodes_ver < NODES_VERSION:
                # Upgrade old chunk or version mismatch — regenerate nodes and re-save
                from server.world.resource_nodes import generate_resource_nodes
                biome_ids, _ = generate_chunk_arrays(cx, cy)
                nodes = generate_resource_nodes(cx, cy, biome_ids)
                save_data = {f"{x},{y}": v for (x, y), v in tiles.items()}
                save_data["_nodes"] = nodes
                save_data["_nodes_version"] = NODES_VERSION
                with open(filename, "wb" if _orjson else "w") as f:
                    f.write(_orjson.dumps(save_data) if _orjson else json.dumps(save_data).encode())

            with chunk_nodes_lock:
                chunk_nodes_cache[(cx, cy)] = nodes
            from server.world.resource_nodes import apply_depletions_to_cache
            apply_depletions_to_cache(cx, cy)
            return tiles
        except json.JSONDecodeError:
            print(f"[V3 LOAD ERROR] Corrupted chunk {filename}, deleting.")
            os.remove(filename)
    return None


# ---------------------------------------------------------------------------
# Numba noise kernels
# ---------------------------------------------------------------------------
@njit
def fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


@njit
def lerp(a, b, t):
    return a + t * (b - a)


@njit
def _hash(x, y, seed):
    return ((x * 1836311903) ^ (y * 2971215073) ^ seed) & 7


@njit
def grad(ix, iy, x, y, seed):
    g = GRADIENTS[_hash(ix, iy, seed)]
    return g[0] * (x - ix) + g[1] * (y - iy)


@njit
def perlin(x, y, seed):
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    sx, sy  = fade(x - x0), fade(y - y0)
    n00 = grad(x0,     y0,     x, y, seed)
    n10 = grad(x0 + 1, y0,     x, y, seed)
    n01 = grad(x0,     y0 + 1, x, y, seed)
    n11 = grad(x0 + 1, y0 + 1, x, y, seed)
    ix0 = lerp(n00, n10, sx)
    ix1 = lerp(n01, n11, sx)
    return lerp(ix0, ix1, sy)


@njit
def fbm(x, y, scale, octaves, seed):
    """Fractional Brownian Motion — returns [0, 1]."""
    nx, ny = x / scale, y / scale
    value, amp, freq, max_val = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        value   += perlin(nx * freq, ny * freq, seed + o * 100) * amp
        max_val += amp
        amp  *= 0.5
        freq *= 2.0
    return (value / max_val + 1.0) / 2.0


@njit
def ridge(x, y, scale, octaves, seed):
    """Ridged noise — returns [0, 1]; peaks cluster near 1.0 for sharp ridges."""
    nx, ny = x / scale, y / scale
    value, amp, freq, max_val = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        r = 1.0 - abs(perlin(nx * freq, ny * freq, seed + o * 100))
        value   += r * r * amp    # squared to sharpen peaks further
        max_val += amp
        amp  *= 0.5
        freq *= 2.0
    return value / max_val


@njit
def clamp(val, lo, hi):
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


@njit
def spline_eval(x, xs, ys):
    """Piecewise-linear spline — safe to call inside @njit."""
    n = len(xs)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[n - 1]:
        return ys[n - 1]
    for i in range(n - 1):
        if xs[i] <= x < xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[n - 1]


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------
@njit
def generate_chunk_arrays(cx, cy):
    """
    5-channel generation:
      c   — continentalness (large-scale land shape)
      e   — erosion (flatness; suppresses pv → no mountains on flat ground)
      pv  — peaks_valleys ridge noise (drives mountain chains)
      t/m — temperature / humidity (climate biome match)
      r   — rivers (independent noise channel)
      domain-warped h_detail — fine-grain height variation with organic edges
    """
    size = CHUNK_SIZE + 2 * PADDING
    biome_ids  = np.zeros((size, size), dtype=np.uint8)
    elevations = np.zeros((size, size), dtype=np.float32)
    STEP = 0.05

    for i in range(size):
        for j in range(size):
            x = float(cx * CHUNK_SIZE + (i - PADDING))
            y = float(cy * CHUNK_SIZE + (j - PADDING))

            # ---- Channel 1: Continentalness (large-scale, unwarped) ----
            c = fbm(x, y, CONTINENTAL_SCALE, CONTINENTAL_OCTAVES, SEED + 300)

            # ---- Channel 2: Erosion (unwarped) ----
            e = fbm(x, y, EROSION_SCALE, EROSION_OCTAVES, SEED + 400)

            # ---- Channel 3: Peaks & Valleys (ridge noise, unwarped) ----
            pv = ridge(x, y, PEAKS_SCALE, PEAKS_OCTAVES, SEED + 500)

            # ---- Domain warp vectors (offset coords for organic edges) ----
            wx = fbm(x, y, WARP_SCALE, WARP_OCTAVES, SEED + 700) * 2.0 - 1.0
            wy = fbm(x, y, WARP_SCALE, WARP_OCTAVES, SEED + 800) * 2.0 - 1.0
            x_w = x + wx * WARP_STRENGTH
            y_w = y + wy * WARP_STRENGTH

            # ---- Channel 4: Fine height detail (domain-warped) ----
            h_detail = fbm(x_w, y_w, HEIGHT_SCALE, HEIGHT_OCTAVES, SEED)

            # ---- Splines ----
            c_offset = spline_eval(c, CONT_XS, CONT_YS)    # continentalness → height offset
            e_scale  = spline_eval(e, EROSION_XS, EROSION_YS)  # erosion → pv amplitude

            # ---- Mountain signal (ridge × erosion resistance) ----
            mountain_signal = pv * e_scale

            # ---- Final height ----
            # Base: 0.5 shifted by continental offset
            # Detail: ±6% fine variation (domain-warped for organic shape)
            # Mountain uplift: ridge noise scaled by erosion resistance
            h = clamp(
                0.5 + c_offset + (h_detail - 0.5) * 0.12 + mountain_signal * 0.18,
                0.0, 1.0,
            )

            # ---- Channel 5: Climate ----
            # abs(y)/4096 maps the full hot→cold spectrum within ±4096 tiles (the 8K view),
            # so forest/plains/tundra appear in the temperate and polar bands.
            t = clamp(
                0.5 * fbm(x, y, CLIMATE_SCALE, CLIMATE_OCTAVES, SEED + 100)
                + 0.5 * (1.0 - abs(y) / 4096.0)
                + 0.03,
                0.0, 1.0,
            )
            m = clamp(
                fbm(x, y, HUMIDITY_SCALE, HUMIDITY_OCTAVES, SEED + 200) - 0.05,
                0.0, 1.0,
            )

            # ---- River channel (isoline inside drainage basin mask) ----
            r_raw       = fbm(x, y, RIVER_SCALE, 3, SEED + 600)
            river_basin = fbm(x, y, RIVER_MASK_SCALE, 2, SEED + 650)
            is_river    = abs(r_raw - 0.5) < RIVER_HALF_WIDTH and river_basin > RIVER_MASK_THRESH

            # ---- Biome assignment (priority order) ----
            # Beach threshold varies with detail noise so coast is ragged, not a uniform ring
            beach_thresh = OCEAN_C_THRESHOLD + 0.025 + (h_detail - 0.5) * 0.05
            if c < OCEAN_C_THRESHOLD:
                biome = 0                              # ocean
            elif c < OCEAN_C_THRESHOLD + LAKE_C_BAND and pv < LAKE_PV_MAX:
                biome = 0                              # inland lake (valley just inside coast)
            elif is_river:
                biome = 3                              # river cuts through coast/beach naturally
            elif c < beach_thresh and e < COASTAL_E_MAX:
                biome = 2 if m > 0.65 else 1           # swamp or beach (noise-varied width)
            elif mountain_signal > MOUNTAIN_SIGNAL:
                biome = 10                             # mountain (ridge-driven)
            else:
                # 4D climate profile match
                best_idx = 0
                min_dist = 999.0
                for k in range(biome_profiles.shape[0]):
                    profile = biome_profiles[k]
                    dist = (
                        (t - profile[0]) ** 2 +
                        (m - profile[1]) ** 2 +
                        (c - profile[2]) ** 2 +
                        (e - profile[3]) ** 2
                    )
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = k
                biome = int(biome_id_lookup[best_idx])

            biome_ids[i, j]  = biome
            elevations[i, j] = np.floor(h / STEP) * STEP

    return biome_ids, elevations


@njit(parallel=True)
def precompute_chunk_data(cx, cy, biome_ids, elevations):
    elevation_matrix = np.zeros((18, 18), dtype=np.float32)
    biome_matrix     = np.empty((18, 18), dtype=np.uint8)
    for dx in prange(18):
        for dy in range(18):
            elevation_matrix[dy, dx] = elevations[dx, dy]
            biome_matrix[dy, dx]     = biome_ids[dx, dy]
    return elevation_matrix, biome_matrix


def detect_cliffs(elevation_map: np.ndarray, biome_map: np.ndarray,
                  threshold=0.01, tall_threshold=0.03):
    size   = elevation_map.shape[0]
    biomes = np.full((size, size), "", dtype=object)

    center        = elevation_map[1:-1, 1:-1]
    center_biomes = biome_map[1:-1, 1:-1]

    mountain_mask = np.char.startswith(center_biomes.astype(np.str_), "mountain")

    n  = elevation_map[:-2, 1:-1]
    s  = elevation_map[2:,  1:-1]
    e  = elevation_map[1:-1, 2:]
    w  = elevation_map[1:-1, :-2]
    ne = elevation_map[:-2, 2:]
    nw = elevation_map[:-2, :-2]
    se = elevation_map[2:,  2:]
    sw = elevation_map[2:,  :-2]

    se_mask = mountain_mask & (center - s >= threshold) & (center - e >= threshold) & (center - se >= threshold)
    sw_mask = mountain_mask & (center - s >= threshold) & (center - w >= threshold) & (center - sw >= threshold)
    ne_mask = mountain_mask & (center - n >= threshold) & (center - e >= threshold) & (center - ne >= threshold)
    nw_mask = mountain_mask & (center - n >= threshold) & (center - w >= threshold) & (center - nw >= threshold)

    tall_se = se_mask & (center - se >= tall_threshold)
    tall_sw = sw_mask & (center - sw >= tall_threshold)

    output = biomes[1:-1, 1:-1]
    output[tall_se]            = "cliff_tall_southeast"
    output[se_mask & ~tall_se] = "cliff_southeast"
    output[tall_sw]            = "cliff_tall_southwest"
    output[sw_mask & ~tall_sw] = "cliff_southwest"
    output[ne_mask]            = "cliff_northeast"
    output[nw_mask]            = "cliff_northwest"

    base       = (output == "") & mountain_mask
    south_tall = base & (center - s >= tall_threshold)
    south      = base & ~south_tall & (center - s >= threshold)
    north      = base & (center - n >= threshold)
    east_      = base & (center - e >= threshold)
    west_      = base & (center - w >= threshold)

    output[south_tall] = "cliff_tall_south"
    output[south]      = "cliff_south"
    output[north]      = "cliff_north"
    output[east_]      = "cliff_east"
    output[west_]      = "cliff_west"

    return biomes[1:-1, 1:-1]


# ---------------------------------------------------------------------------
# Chunk queue
# ---------------------------------------------------------------------------
chunk_queue      = []
generated_chunks = set()
chunk_lock       = Lock()


def queue_chunks_near_players(player_data, radius):
    candidates: dict[tuple, int] = {}
    for pos in player_data.values():
        px, py  = map(float, pos["pos"])
        bcx, bcy = int(px) // CHUNK_SIZE, int(py) // CHUNK_SIZE
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                coord   = (bcx + dx, bcy + dy)
                dist_sq = dx * dx + dy * dy
                if coord not in candidates or dist_sq < candidates[coord]:
                    candidates[coord] = dist_sq

    with chunk_lock:
        for coord, dist_sq in candidates.items():
            if coord not in generated_chunks and coord not in queued_chunks:
                queued_chunks.add(coord)
                heapq.heappush(chunk_queue, (dist_sq, coord[0], coord[1]))


def get_cpu_percent():
    return psutil.cpu_percent(interval=0.05)


def process_chunk_queue(world_data):
    usage       = get_cpu_percent()
    chunk_limit = 8 if usage > 80 else 4
    new_tiles   = {}

    for _ in range(min(chunk_limit, len(chunk_queue))):
        _, cx, cy = heapq.heappop(chunk_queue)

        saved_chunk = load_chunk_from_disk(cx, cy)
        if saved_chunk:
            world_data.update(saved_chunk)
            new_tiles.update(saved_chunk)
            continue

        biome_ids, elevations = generate_chunk_arrays(cx, cy)
        elevation_matrix, biome_matrix = precompute_chunk_data(
            cx, cy, biome_ids, elevations
        )

        chunk_x0 = cx * CHUNK_SIZE - 1
        chunk_y0 = cy * CHUNK_SIZE - 1
        extended_chunk = {}

        for dx in range(18):
            for dy in range(18):
                x, y = chunk_x0 + dx, chunk_y0 + dy
                extended_chunk[(x, y)] = {
                    "biome":     int(biome_ids[dx, dy]),
                    "elevation": round(float(elevations[dx, dy]), 3),
                }

        biome_matrix_str = np.empty_like(biome_matrix, dtype=object)
        for i in range(18):
            for j in range(18):
                biome_matrix_str[i, j] = ID_TO_BIOME.get(
                    int(biome_matrix[i, j]), "plains"
                )

        cliff_biomes = detect_cliffs(elevation_matrix, biome_matrix_str)

        chunk = {}
        for dx in range(CHUNK_SIZE):
            for dy in range(CHUNK_SIZE):
                x, y     = cx * CHUNK_SIZE + dx, cy * CHUNK_SIZE + dy
                tile     = extended_chunk[(x, y)].copy()
                override = cliff_biomes[dy, dx]
                if override:
                    tile["biome"] = CLIFF_ID_MAP.get(override, tile["biome"])
                chunk[(x, y)] = tile

        world_data.update(chunk)
        new_tiles.update(chunk)
        generated_chunks.add((cx, cy))

        # Generate resource nodes and save alongside tile data
        from server.world.resource_nodes import generate_resource_nodes, apply_depletions_to_cache
        nodes = generate_resource_nodes(cx, cy, biome_ids)
        with chunk_nodes_lock:
            chunk_nodes_cache[(cx, cy)] = nodes
        apply_depletions_to_cache(cx, cy)

        filename = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
        save_data = {f"{x},{y}": v for (x, y), v in chunk.items()}
        save_data["_nodes"] = nodes
        save_data["_nodes_version"] = NODES_VERSION
        with open(filename, "wb" if _orjson else "w") as f:
            f.write(_orjson.dumps(save_data) if _orjson else json.dumps(save_data).encode())

    return new_tiles


# ---------------------------------------------------------------------------
# Utility: query a single tile's biome (used by spawn-safety check)
# ---------------------------------------------------------------------------
def get_tile_biome(tx: int, ty: int, cached_world: dict | None = None) -> int:
    """Return biome ID for a world tile.
    Checks cached_world first, then disk, then generates on-demand.
    Safe to call before world_data is populated.
    """
    if cached_world is not None:
        tile = cached_world.get((tx, ty))
        if tile is not None:
            return tile.get("biome") if isinstance(tile, dict) else int(tile)
    cx = tx // CHUNK_SIZE
    cy = ty // CHUNK_SIZE
    saved = load_chunk_from_disk(cx, cy)
    if saved:
        tile = saved.get((tx, ty))
        if tile is not None:
            return tile.get("biome") if isinstance(tile, dict) else int(tile)
    biome_ids, _ = generate_chunk_arrays(cx, cy)
    dx = tx - cx * CHUNK_SIZE + PADDING
    dy = ty - cy * CHUNK_SIZE + PADDING
    return int(biome_ids[dx, dy])

import numpy as np
from numba import njit, prange
from threading import Lock
import psutil
import os
import json
import heapq

queued_chunks = set()

CHUNK_SIZE = 16
PADDING = 1  
SEED = 42

# World scale factors
HEIGHT_SCALE = 3000.0
CLIMATE_SCALE = 1000.0
CONTINENTAL_SCALE = 12000.0
EROSION_SCALE = 1500.0
RIVER_SCALE = 1600.0
HEIGHT_OCTAVES = 4
CLIMATE_OCTAVES = 2

# Biome thresholds
OCEAN_THRESHOLD = 0.52
BEACH_THRESHOLD = 0.55
MIN_RIVER_HEIGHT = 0.56
MAX_RIVER_HEIGHT = 0.75

# Biome ID Mapping
BIOME_ID_MAP = {
    "ocean": 0, "beach": 1, "swamp": 2, "river": 3,
    "plains": 4, "forest": 5, "desert": 6, "alt_desert": 7,
    "tropical": 8, "tundra": 9, "mountain": 10
}

CLIFF_ID_MAP = {
    "cliff_north": 100,
    "cliff_south": 101,
    "cliff_east": 102,
    "cliff_west": 103,
    "cliff_northeast": 104,
    "cliff_northwest": 105,
    "cliff_southeast": 106,
    "cliff_southwest": 107,
    "cliff_tall_south": 108,
    "cliff_tall_southwest": 109,
    "cliff_tall_southeast": 110,
}

ID_TO_BIOME = {v: k for k, v in BIOME_ID_MAP.items()}
ID_TO_CLIFF = {v: k for k, v in CLIFF_ID_MAP.items()}

biome_profiles = np.array([
    [0.78, 0.32, 0.65, 0.28, 0.3],
    [0.85, 0.25, 0.5,  0.35, 0.4],
    [0.9,  0.9,  0.5,  0.3,  0.4],
    [0.5,  0.7,  0.4,  0.2,  0.2],
    [0.4,  0.5,  0.6,  0.5,  0.5],
    [0.3,  0.4,  0.7,  0.2,  0.3],
    [0.2,  0.3,  0.8,  0.2,  0.2],
    [0.5,  0.5,  0.6,  0.8,  0.6],
])

biome_elevation_min = np.array([
    0.0,   # ocean
    0.05,  # beach
    0.05,  # swamp
    0.1,   # river
    0.2,   # plains
    0.2,   # forest
    0.2,   # desert
    0.2,   # alt_desert
    0.2,   # tropical
    0.4,   # tundra
    0.6    # mountain
], dtype=np.float32)

biome_elevation_max = np.array([
    0.05,  # ocean
    0.1,   # beach
    0.2,   # swamp
    0.3,   # river
    0.6,   # plains
    0.6,   # forest
    0.6,   # desert
    0.6,   # alt_desert
    0.6,   # tropical
    0.75,  # tundra
    1.0    # mountain
], dtype=np.float32)


biome_id_lookup = np.array([6, 7, 8, 2, 5, 4, 9, 10], dtype=np.uint8)

GRADIENTS = np.array([
    [1, 1], [-1, 1], [1, -1], [-1, -1],
    [1, 0], [-1, 0], [0, 1], [0, -1]
])

CHUNK_DIR = "world_chunks"
os.makedirs(CHUNK_DIR, exist_ok=True)

def load_chunk_from_disk(cx, cy):
    filename = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                raw_data = json.load(f)
                return {
                    tuple(map(int, k.split(','))): v
                    for k, v in raw_data.items()
                }
        except json.JSONDecodeError:
            print(f"[LOAD ERROR] Corrupted or empty chunk file at {filename}, deleting it.")
            os.remove(filename)
    return None


@njit
def fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)

@njit
def lerp(a, b, t):
    return a + t * (b - a)

@njit
def hash(x, y, seed):
    return ((x * 1836311903) ^ (y * 2971215073) ^ seed) & 7

@njit
def grad(ix, iy, x, y, seed):
    g = GRADIENTS[hash(ix, iy, seed)]
    return g[0] * (x - ix) + g[1] * (y - iy)

@njit
def perlin(x, y, seed):
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    sx, sy = fade(x - x0), fade(y - y0)
    n00 = grad(x0, y0, x, y, seed)
    n10 = grad(x0 + 1, y0, x, y, seed)
    n01 = grad(x0, y0 + 1, x, y, seed)
    n11 = grad(x0 + 1, y0 + 1, x, y, seed)
    ix0 = lerp(n00, n10, sx)
    ix1 = lerp(n01, n11, sx)
    return lerp(ix0, ix1, sy)

@njit
def fbm(x, y, scale, octaves, seed):
    nx, ny = x / scale, y / scale
    value, amp, freq, max_val = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        value += perlin(nx * freq, ny * freq, seed + o * 100) * amp
        max_val += amp
        amp *= 0.5
        freq *= 2.0
    return (value / max_val + 1) / 2

@njit
def clamp(val, min_val, max_val):
    return min(max(val, min_val), max_val)

MOUNTAIN_BIOME_ID = BIOME_ID_MAP["mountain"]

@njit
def generate_chunk_arrays(cx, cy, min_elevs, max_elevs, mountain_id):
    size = CHUNK_SIZE + 2 * PADDING
    biome_ids = np.zeros((size, size), dtype=np.uint8)
    elevations = np.zeros((size, size), dtype=np.float32)
    STEP = 0.05

    for i in range(size):
        for j in range(size):
            x = cx * CHUNK_SIZE + (i - PADDING)
            y = cy * CHUNK_SIZE + (j - PADDING)

            h = fbm(x, y, HEIGHT_SCALE, HEIGHT_OCTAVES, SEED)
            t = clamp(0.5 * fbm(x, y, CLIMATE_SCALE, CLIMATE_OCTAVES, SEED + 100) + 0.5 * (1 - y / 16384) + 0.03, 0, 1)
            m = clamp((fbm(x, y, CLIMATE_SCALE, CLIMATE_OCTAVES, SEED + 200) - 0.5) * 1.6 + 0.5, 0, 1)
            c = fbm(x, y, CONTINENTAL_SCALE, 1, SEED + 300)
            e = fbm(x, y, EROSION_SCALE, 1, SEED + 400)
            r = fbm(x, y, RIVER_SCALE, 1, SEED + 600)

            if h < OCEAN_THRESHOLD:
                biome = 0
            elif h < BEACH_THRESHOLD:
                biome = 2 if m > 0.7 else 1
            elif MIN_RIVER_HEIGHT < h < MAX_RIVER_HEIGHT and r > 0.77:
                biome = 3
            else:
                best_idx = 0
                min_dist = 999.0
                for k in range(biome_profiles.shape[0]):
                    profile = biome_profiles[k]
                    dist = ((t - profile[0]) ** 2 +
                            (m - profile[1]) ** 2 +
                            (c - profile[2]) ** 2 +
                            (h - profile[3]) ** 2 +
                            (e - profile[4]) ** 2)
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = k
                biome = biome_id_lookup[best_idx]

            biome_ids[i, j] = biome
            min_elev = min_elevs[biome]
            max_elev = max_elevs[biome]

            if biome == mountain_id:
                raw = clamp((h - 0.6) / 0.1, 0.0, 1.0)
                norm_elev = clamp(raw ** 0.6, 0.0, 1.0)
            else:
                norm_elev = clamp((h - min_elev) / (max_elev - min_elev), 0.0, 1.0)

            # Apply same flooring for all
            norm_elev = np.floor(norm_elev / STEP) * STEP
            elevations[i, j] = norm_elev

    return biome_ids, elevations

@njit(parallel=True)
def precompute_chunk_data(cx, cy, biome_ids, elevations):
    elevation_matrix = np.zeros((18, 18), dtype=np.float32)
    biome_matrix = np.empty((18, 18), dtype=np.uint8)  # Store biome IDs only

    for dx in prange(18):
        for dy in range(18):
            i, j = dx, dy
            elevation_matrix[dy, dx] = elevations[i, j]
            biome_matrix[dy, dx] = biome_ids[i, j]

    return elevation_matrix, biome_matrix


def detect_cliffs(elevation_map: np.ndarray, biome_map: np.ndarray, threshold=0.01, tall_threshold=0.03):
    size = elevation_map.shape[0]
    biomes = np.full((size, size), '', dtype=object)

    center = elevation_map[1:-1, 1:-1]
    center_biomes = biome_map[1:-1, 1:-1]

    mountain_mask = np.char.startswith(center_biomes.astype(np.str_), "mountain")

    n = elevation_map[:-2, 1:-1]
    s = elevation_map[2:, 1:-1]
    e = elevation_map[1:-1, 2:]
    w = elevation_map[1:-1, :-2]
    ne = elevation_map[:-2, 2:]
    nw = elevation_map[:-2, :-2]
    se = elevation_map[2:, 2:]
    sw = elevation_map[2:, :-2]

    # Diagonal masks
    se_mask = mountain_mask & (center - s >= threshold) & (center - e >= threshold) & (center - se >= threshold)
    sw_mask = mountain_mask & (center - s >= threshold) & (center - w >= threshold) & (center - sw >= threshold)
    ne_mask = mountain_mask & (center - n >= threshold) & (center - e >= threshold) & (center - ne >= threshold)
    nw_mask = mountain_mask & (center - n >= threshold) & (center - w >= threshold) & (center - nw >= threshold)

    tall_se = se_mask & (center - se >= tall_threshold)
    tall_sw = sw_mask & (center - sw >= tall_threshold)

    output = biomes[1:-1, 1:-1]
    output[tall_se] = "cliff_tall_southeast"
    output[se_mask & ~tall_se] = "cliff_southeast"
    output[tall_sw] = "cliff_tall_southwest"
    output[sw_mask & ~tall_sw] = "cliff_southwest"
    output[ne_mask] = "cliff_northeast"
    output[nw_mask] = "cliff_northwest"

    base = (output == "") & mountain_mask
    south_tall = base & (center - s >= tall_threshold)
    south = base & ~south_tall & (center - s >= threshold)
    north = base & (center - n >= threshold)
    east = base & (center - e >= threshold)
    west = base & (center - w >= threshold)

    output[south_tall] = "cliff_tall_south"
    output[south] = "cliff_south"
    output[north] = "cliff_north"
    output[east] = "cliff_east"
    output[west] = "cliff_west"

    return biomes[1:-1, 1:-1]

chunk_queue = []
generated_chunks = set()
chunk_lock = Lock()

def queue_chunks_near_players(player_data, radius):
    all_new_coords = []

    for pos in player_data.values():
        px, py = map(float, pos)
        cx, cy = int(px) // CHUNK_SIZE, int(py) // CHUNK_SIZE

        # Generate a square grid of chunk coordinates around the player
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                coord = (cx + dx, cy + dy)

                if coord not in generated_chunks and coord not in queued_chunks:
                    queued_chunks.add(coord)
                    all_new_coords.append(coord)

    with chunk_lock:
        for coord in all_new_coords:
            heapq.heappush(chunk_queue, coord)

def get_cpu_percent():
    return psutil.cpu_percent(interval=0.05)

def process_chunk_queue(world_data, player_pos):
    player_center_x = player_pos[0]
    player_center_y = player_pos[1]

    def distance_to_player(chunk_coord):
        dx = chunk_coord[0] * CHUNK_SIZE + CHUNK_SIZE // 2 - player_center_x
        dy = chunk_coord[1] * CHUNK_SIZE + CHUNK_SIZE // 2 - player_center_y
        return dx * dx + dy * dy

    with chunk_lock:
        chunk_queue.sort(key=distance_to_player)
        heapq.heapify(chunk_queue)

    usage = get_cpu_percent()
    chunk_limit = 8 if usage > 80 else 4
    new_tiles = {}

    for _ in range(min(chunk_limit, len(chunk_queue))):
        cx, cy = heapq.heappop(chunk_queue)

        # Check for saved chunk first
        saved_chunk = load_chunk_from_disk(cx, cy)
        if saved_chunk:
            world_data.update(saved_chunk)
            new_tiles.update(saved_chunk)
            continue

        # Precompute elevations and biomes in one go
        biome_ids, elevations = generate_chunk_arrays(
            cx, cy, biome_elevation_min, biome_elevation_max, MOUNTAIN_BIOME_ID
        )

        elevation_matrix, biome_matrix = precompute_chunk_data(
            cx, cy, biome_ids, elevations
        )

        chunk_x0 = cx * CHUNK_SIZE - 1
        chunk_y0 = cy * CHUNK_SIZE - 1
        extended_chunk = {}

        for dx in range(18):
            for dy in range(18):
                x = chunk_x0 + dx
                y = chunk_y0 + dy
                key = (x, y)
                biome_id = int(biome_ids[dx, dy])
                elevation = float(elevations[dx, dy])

                extended_chunk[key] = {
                    "biome": biome_id,
                    "elevation": round(elevation, 3)
                }

        # Convert biome_matrix to string for cliff detection
        biome_matrix_str = np.empty_like(biome_matrix, dtype=object)
        for i in range(18):
            for j in range(18):
                biome_matrix_str[i, j] = ID_TO_BIOME.get(biome_matrix[i, j], "plains")

        cliff_biomes = detect_cliffs(elevation_matrix, biome_matrix_str)

        chunk = {}
        for dx in range(CHUNK_SIZE):
            for dy in range(CHUNK_SIZE):
                x = cx * CHUNK_SIZE + dx
                y = cy * CHUNK_SIZE + dy
                key = (x, y)
                base_tile = extended_chunk[key].copy()
                biome_override = cliff_biomes[dy, dx]
                if biome_override:
                    base_tile["biome"] = CLIFF_ID_MAP.get(biome_override, base_tile["biome"])
                chunk[key] = base_tile

        world_data.update(chunk)
        new_tiles.update(chunk)
        generated_chunks.add((cx, cy))

        filename = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
        with open(filename, "w") as f:
            json.dump({f"{x},{y}": v for (x, y), v in chunk.items()}, f)

    return new_tiles



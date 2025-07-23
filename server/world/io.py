import os
import json
from server.config import CHUNK_DIR

def load_chunk(cx, cy):
    """Load a single chunk from file and convert keys back to (x, y) tuples."""
    path = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            raw_data = json.load(f)
            return {
                tuple(map(int, key.split(','))): value
                for key, value in raw_data.items()
            }
    return {}

def save_chunk(cx, cy, chunk_data):
    """Save a single chunk to file."""
    os.makedirs(CHUNK_DIR, exist_ok=True)
    path = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    with open(path, "w") as f:
        json.dump({f"{x},{y}": v for (x, y), v in chunk_data.items()}, f)

def save_multiple_chunks(chunk_dict):
    """Save a dict of (cx, cy) -> tile_data."""
    os.makedirs(CHUNK_DIR, exist_ok=True)
    for (cx, cy), chunk_data in chunk_dict.items():
        save_chunk(cx, cy, chunk_data)

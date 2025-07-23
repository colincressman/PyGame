from server.config import CHUNK_SIZE

def split_tiles_by_chunk(tile_data):
    """
    Convert flat tile dictionary with (x, y) tuple keys into chunk-based groupings.
    """
    chunks = {}
    for (tx, ty), value in tile_data.items():
        cx, cy = tx // CHUNK_SIZE, ty // CHUNK_SIZE
        chunk_key = (cx, cy)
        if chunk_key not in chunks:
            chunks[chunk_key] = {}
        chunks[chunk_key][(tx, ty)] = value
    return chunks

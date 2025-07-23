from config import chunk_cache

def clear_distant_cache(center_chunk_x, center_chunk_y, radius_chunks=8):
    to_delete = []
    for key in list(chunk_cache.keys()):
        cx, cy = key
        if abs(cx - center_chunk_x) > radius_chunks or abs(cy - center_chunk_y) > radius_chunks:
            to_delete.append(key)
    for key in to_delete:
        del chunk_cache[key]
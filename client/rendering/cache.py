import os

import pygame

import config as _config
from config import CHUNK_SIZE, chunk_cache
from rendering.item_art import draw_item


_ITEM_SURFACE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_ITEMS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "data",
    "texturepack",
    "items",
)
_MAX_EVICT_CHUNKS_PER_PASS = 2


def get_item_surface(item_id: int, size: int) -> pygame.Surface:
    key = (item_id, size)
    surf = _ITEM_SURFACE_CACHE.get(key)
    if surf is None:
        path = os.path.join(_ITEMS_DIR, f"{item_id}.png")
        try:
            img = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.scale(img, (size, size))
        except Exception:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            draw_item(surf, 0, 0, size, item_id)
        _ITEM_SURFACE_CACHE[key] = surf
    return surf


def clear_distant_cache(center_chunk_x, center_chunk_y, radius_chunks=6):
    to_delete = [
        k for k in list(chunk_cache.keys())
        if abs(k[0] - center_chunk_x) > radius_chunks
        or abs(k[1] - center_chunk_y) > radius_chunks
    ]
    for key in to_delete:
        del chunk_cache[key]

    # Keep a larger radius than chunk_cache so re-renders always have source data.
    data_radius = radius_chunks + 4
    loaded = _config.world_data_loaded_chunks
    far_chunks = [
        k for k in list(loaded)
        if abs(k[0] - center_chunk_x) > data_radius
        or abs(k[1] - center_chunk_y) > data_radius
    ]
    if not far_chunks:
        return

    # Evict the farthest chunks first, but only a few per boundary crossing so
    # exploration does not stall on one large cleanup burst.
    far_chunks.sort(
        key=lambda k: abs(k[0] - center_chunk_x) + abs(k[1] - center_chunk_y),
        reverse=True,
    )
    far_chunks = far_chunks[:_MAX_EVICT_CHUNKS_PER_PASS]

    wd = _config.world_data
    for cx, cy in far_chunks:
        ox = cx * CHUNK_SIZE
        oy = cy * CHUNK_SIZE
        for i in range(CHUNK_SIZE):
            for j in range(CHUNK_SIZE):
                tile = (ox + i, oy + j)
                wd.pop(tile, None)
                node_ids = tuple(_config.node_by_tile.get(tile, ()))
                for node_id in node_ids:
                    _config.remove_world_node(node_id)
        loaded.discard((cx, cy))

    try:
        _config.state_outbox.put_nowait(
            {
                "type": "forget_chunks",
                "chunks": [[cx, cy] for cx, cy in far_chunks],
            }
        )
    except Exception:
        pass

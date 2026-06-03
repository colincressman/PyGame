import os

import pygame

import config as _config
from config import chunk_cache, CHUNK_SIZE
from rendering.item_art import draw_item


_ITEM_SURFACE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_ITEMS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "texturepack", "items")

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
    # ── Trim rendered-surface cache ───────────────────────────────────────────
    to_delete = [
        k for k in list(chunk_cache.keys())
        if abs(k[0] - center_chunk_x) > radius_chunks
        or abs(k[1] - center_chunk_y) > radius_chunks
    ]
    for key in to_delete:
        del chunk_cache[key]

    # ── Trim tile data from world_data ────────────────────────────────────────
    # Keep a larger radius than chunk_cache so re-renders always have source data.
    DATA_RADIUS = radius_chunks + 4
    loaded = _config.world_data_loaded_chunks
    far_chunks = [
        k for k in list(loaded)
        if abs(k[0] - center_chunk_x) > DATA_RADIUS
        or abs(k[1] - center_chunk_y) > DATA_RADIUS
    ]
    if far_chunks:
        wd = _config.world_data
        for cx, cy in far_chunks:
            ox = cx * CHUNK_SIZE
            oy = cy * CHUNK_SIZE
            for i in range(CHUNK_SIZE):
                for j in range(CHUNK_SIZE):
                    wd.pop((ox + i, oy + j), None)
            loaded.discard((cx, cy))

        # ── Evict nodes belonging to evicted chunks ───────────────────────────
        # world_nodes grows without bound as the player explores land; iterating
        # all of them every frame (get_node_drawables) is the primary land lag.
        far_set = set(far_chunks)
        old_nodes = _config.world_nodes
        new_nodes = {
            nid: node for nid, node in old_nodes.items()
            if (node["wx"] // CHUNK_SIZE, node["wy"] // CHUNK_SIZE) not in far_set
        }
        _config.world_nodes = new_nodes

        # ── Tell server to re-send those chunks when the player returns ────────
        # Without this the server's "already sent" set prevents re-delivery.
        try:
            _config.state_outbox.put_nowait({
                "type": "forget_chunks",
                "chunks": [[cx, cy] for cx, cy in far_chunks],
            })
        except Exception:
            pass
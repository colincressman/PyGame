import pygame


_node_surface_cache: dict[tuple[str, int], pygame.Surface] = {}
_NODE_FNS: dict[str, object] | None = None


def _get_node_fns() -> dict[str, object]:
    global _NODE_FNS
    if _NODE_FNS is None:
        from rendering import item_art as _legacy_item_art

        _NODE_FNS = {
            "tree": _legacy_item_art._node_tree,
            "pine_tree": _legacy_item_art._node_pine_tree,
            "jungle_tree": _legacy_item_art._node_jungle_tree,
            "palm_tree": _legacy_item_art._node_palm_tree,
            "stick_pile": _legacy_item_art._node_stick_pile,
            "bone_pile": _legacy_item_art._node_bone_pile,
            "stone_deposit": _legacy_item_art._node_stone,
            "iron_ore": _legacy_item_art._node_iron_ore,
            "coal_deposit": _legacy_item_art._node_coal,
            "herb_patch": _legacy_item_art._node_herb,
            "cactus": _legacy_item_art._node_cactus,
            "reed_cluster": _legacy_item_art._node_reed,
            "seashell_bed": _legacy_item_art._node_seashell,
            "mushroom": _legacy_item_art._node_mushroom,
            "snow_crystal": _legacy_item_art._node_snow,
            "clay_deposit": _legacy_item_art._node_clay,
            "copper_ore": _legacy_item_art._node_copper_ore,
            "tin_ore": _legacy_item_art._node_tin_ore,
            "silver_ore": _legacy_item_art._node_silver_ore,
            "gold_ore": _legacy_item_art._node_gold_ore,
            "crystal": _legacy_item_art._node_crystal,
            "obsidian": _legacy_item_art._node_obsidian,
        }
    return _NODE_FNS


def draw_node(screen, x: int, y: int, s: int, node_type: str) -> None:
    """Draw resource node art at top-left (x, y) in a square of size s pixels."""
    key = (node_type, s)
    surf = _node_surface_cache.get(key)
    if surf is None:
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        fn = _get_node_fns().get(node_type)
        if fn:
            fn(surf, 0, 0, s)
        else:
            pygame.draw.rect(surf, (160, 80, 160), (0, 0, s, s), border_radius=4)
            pygame.draw.rect(surf, (100, 40, 100), (0, 0, s, s), 2, border_radius=4)
        _node_surface_cache[key] = surf
    screen.blit(surf, (x, y))
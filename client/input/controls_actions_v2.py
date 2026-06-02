import time

import pygame
import config


# Wand item IDs — equipped in hotbar, fire a projectile instead of melee
_WAND_IDS = frozenset({1800, 1801, 1802, 1803, 1804, 1805})


def handle_smart_action(is_consumable_fn, has_tool_fn, best_tool_damage_fn, hotbar_offset: int) -> None:
    active_slot = hotbar_offset + config.hotbar_slot
    item = config.player_inventory[active_slot]
    item_id = item[0] if item is not None else None
    all_tools = {
        2000, 2050, 2051, 2100, 2150, 2200, 2250, 2300, 2350, 2400,
        2001, 2052, 2053, 2101, 2151, 2201, 2251, 2301, 2351, 2401,
    }

    if item_id is not None and item_id in all_tools:
        from state.player import player_data as _pd
        px, py = _pd["pos"]
        node_tool = {
            "tree": "axe",
            "pine_tree": "axe",
            "jungle_tree": "axe",
            "palm_tree": "axe",
            "stone_deposit": "pickaxe",
            "coal_deposit": "pickaxe",
            "iron_ore": "pickaxe_stone",
            "copper_ore": "pickaxe_stone",
            "tin_ore": "pickaxe_stone",
            "silver_ore": "pickaxe_iron",
            "gold_ore": "pickaxe_iron",
            "crystal": "pickaxe_steel",
            "obsidian": "pickaxe_steel",
        }
        best_id = None
        best_dist = 2.25
        for node_id, node in config.world_nodes.items():
            required = node_tool.get(node.get("type", ""))
            if required and not has_tool_fn(required):
                continue
            dx = (node["wx"] + 0.5) - px
            dy = (node["wy"] + 0.5) - py
            dsq = dx * dx + dy * dy
            if dsq < best_dist:
                best_dist = dsq
                best_id = node_id
        if best_id is not None:
            config.state_outbox.put({"type": "gather", "node_id": best_id})
            node = config.world_nodes.get(best_id)
            if node is not None:
                if node.get("type") == "item_drop":
                    uid = best_id[5:]
                    config.world_items = {k: v for k, v in config.world_items.items() if k != uid}
                required = node_tool.get(node.get("type", ""))
                dmg = best_tool_damage_fn(required) if required else 1
                node["hits"] = node.get("hits", 0) + dmg
                if node["hits"] >= node.get("max_hp", 1):
                    config.world_nodes.pop(best_id, None)
            config.is_attacking = True
        return

    if item_id is not None and is_consumable_fn(item_id):
        config.state_outbox.put({"type": "use_item", "slot": active_slot})
        return

    # ── Wand: fire a projectile towards the mouse cursor ────────────────────
    if item_id is not None and item_id in _WAND_IDS:
        if time.time() - config.last_attack_time >= 0.55:
            config.last_attack_time = time.time()
            from state.player import player_data as _pd
            mx, my = pygame.mouse.get_pos()
            # Direction in tile-space relative to the player centre
            dx = (mx - config.camera_offset_x) / config.TILE_SIZE - (_pd["pos"][0] + 0.5)
            dy = (my - config.camera_offset_y) / config.TILE_SIZE - (_pd["pos"][1] + 0.5)
            config.state_outbox.put({"type": "fire_spell", "dx": dx, "dy": dy})
        return

    if (not config.is_attacking
            and config.player_stamina >= 12.0
            and time.time() - config.last_attack_time >= 0.5):
        config.is_attacking = True
        config.player_stamina = max(0.0, config.player_stamina - 12.0)
        config.last_attack_time = time.time()
        from state.player import player_id_dict, player_data
        config.udp_outbox.put({
            "type": "attack",
            "player_id": player_id_dict["player_id"],
            "direction": config.player_facing,
            "pos": list(player_data["pos"]),
        })

import config
from input.controls_actions_v2 import handle_smart_action as _handle_smart_action_v2
from input.placeable_data import PLACEABLE_ITEMS as _PLACEABLE_ITEMS


def handle_world_left_click(is_consumable_fn, has_tool_fn, best_tool_damage_fn, hotbar_offset):
    if config.pickup_mode:
        tx, ty = config.mouse_tile
        target_uid, _target_obj = config.get_placed_object_at_tile((tx, ty))
        if target_uid is not None:
            if config.station_popup_uid == target_uid:
                config.show_station_popup = None
                config.station_popup_uid = None
                config.station_popup_scroll = 0
                config.station_popup_recipe = None
            config.state_outbox.put({"type": "remove_object", "uid": target_uid})
            config.remove_placed_object(target_uid)
        return

    active_slot = hotbar_offset + config.hotbar_slot
    item = config.player_inventory[active_slot]
    if item is not None and item[0] in _PLACEABLE_ITEMS and not config.placement_blocked:
        tx, ty = config.mouse_tile
        obj_type = _PLACEABLE_ITEMS[item[0]]
        config.state_outbox.put({"type": "place_object", "obj_type": obj_type, "pos": [tx, ty]})
        if item[1] > 1:
            config.player_inventory[active_slot] = [item[0], item[1] - 1]
        else:
            config.player_inventory[active_slot] = None
        opt_uid = f"_opt_{tx}_{ty}"
        config.upsert_placed_object(opt_uid, {
            "uid": opt_uid,
            "type": obj_type,
            "pos": [tx, ty],
            "placed_by": "",
        })
        return

    _handle_smart_action_v2(
        is_consumable_fn,
        has_tool_fn,
        best_tool_damage_fn,
        hotbar_offset,
    )

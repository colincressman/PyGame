import time

import pygame

import config


def cancel_active_drag():
    if config.chest_drag_slot is not None:
        from rendering.chest import _cancel_drag

        _cancel_drag()
        return
    if config.drag_item is not None and config.drag_slot is not None:
        config.player_inventory[config.drag_slot] = config.drag_item
        config.drag_slot = None
        config.drag_item = None


def handle_chest_mouse_down(event, state) -> bool:
    if not (
        event.button == 1
        and config.open_chest_uid is not None
        and not config.show_menu
        and not config.show_stats
        and config.show_station_popup is None
    ):
        return False

    mx, my = event.pos
    ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
    mods_chest = pygame.key.get_mods()
    from rendering.chest import chest_slot_at, chest_bag_slot_at

    cs = chest_slot_at(mx, my, ww, wh)
    if cs is not None:
        obj = config.placed_objects.get(config.open_chest_uid)
        if obj is not None:
            chest_inv = obj.setdefault("chest_inv", [None] * 27)
            while len(chest_inv) < 27:
                chest_inv.append(None)
            if chest_inv[cs] is not None:
                if mods_chest & pygame.KMOD_SHIFT:
                    target_bag = next(
                        (i for i in range(27) if config.player_inventory[i] is None), None
                    )
                    if target_bag is not None:
                        config.player_inventory[target_bag] = list(chest_inv[cs])
                        chest_inv[cs] = None
                        config.state_outbox.put(
                            {
                                "type": "chest_swap",
                                "uid": config.open_chest_uid,
                                "chest_slot": cs,
                                "player_slot": target_bag,
                            }
                        )
                        config.chest_ui_hold_until = time.time() + 0.3
                else:
                    config.chest_drag_slot = cs
                    config.drag_item = list(chest_inv[cs])
                    chest_inv[cs] = None
        return True

    bs = chest_bag_slot_at(mx, my, ww, wh)
    if bs is not None:
        if config.player_inventory[bs] is not None:
            if mods_chest & pygame.KMOD_SHIFT:
                obj = config.placed_objects.get(config.open_chest_uid)
                if obj is not None:
                    chest_inv = obj.setdefault("chest_inv", [None] * 27)
                    while len(chest_inv) < 27:
                        chest_inv.append(None)
                    target_cs = next((i for i in range(27) if chest_inv[i] is None), None)
                    if target_cs is not None:
                        chest_inv[target_cs] = list(config.player_inventory[bs])
                        config.player_inventory[bs] = None
                        config.state_outbox.put(
                            {
                                "type": "chest_swap",
                                "uid": config.open_chest_uid,
                                "chest_slot": target_cs,
                                "player_slot": bs,
                            }
                        )
                        config.chest_ui_hold_until = time.time() + 0.3
            else:
                config.drag_slot = bs
                config.drag_item = list(config.player_inventory[bs])
                config.player_inventory[bs] = None
        return True

    from rendering.chest import _cancel_drag

    _cancel_drag()
    config.open_chest_uid = None
    return True


def handle_inventory_mouse_down(event, state) -> bool:
    if not (event.button == 1 and config.show_inventory):
        return False

    mx, my = event.pos
    ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
    from rendering.inventory import inventory_tab_hit, slot_at

    inv_tab = inventory_tab_hit(mx, my, ww, wh)
    if inv_tab is not None:
        config.inventory_tab = inv_tab
        config.crafting_scroll = 0
        config.selected_recipe = None
        return True

    if config.inventory_tab == "creative":
        from rendering.inventory import creative_tab_click

        item_id = creative_tab_click(mx, my, ww, wh)
        if item_id is not None:
            config.state_outbox.put({"type": "give_item", "item_id": item_id, "qty": 1})
        return True

    if config.inventory_tab == "craft":
        from rendering.crafting import basic_crafting_inline_hit, inv_craft_area, _can_craft, _recipes

        ax, ay, aw, ah = inv_craft_area(ww, wh)
        result = basic_crafting_inline_hit(mx, my, ax, ay, aw, ah)
        if result is not None:
            kind, val = result
            if kind == "recipe":
                config.selected_recipe = val
            elif kind == "craft":
                sel = _recipes.get(config.selected_recipe)
                if sel and _can_craft(sel):
                    config.state_outbox.put(
                        {
                            "type": "craft",
                            "recipe_id": config.selected_recipe,
                            "nearby_stations": list(config.nearby_stations),
                        }
                    )
        return True

    idx = slot_at(mx, my, ww, wh)
    if idx is not None and config.player_inventory[idx] is not None:
        config.drag_slot = idx
        config.drag_item = list(config.player_inventory[idx])
        config.player_inventory[idx] = None
    return True


def handle_inventory_right_click(event, state) -> bool:
    if not (event.button == 3 and (config.show_inventory or config.open_chest_uid is not None)):
        return False

    if config.drag_item is not None:
        from rendering.chest import _cancel_drag as _cd

        _cd()
        if config.drag_item is not None and config.drag_slot is not None:
            config.player_inventory[config.drag_slot] = config.drag_item
            config.drag_slot = None
            config.drag_item = None
        return True

    if not config.show_inventory:
        return True

    from rendering.inventory import slot_at, _ITEM_SLOT_TYPES, _load_item_names

    _load_item_names()
    mx, my = event.pos
    idx = slot_at(mx, my, state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
    if idx is None or config.player_inventory[idx] is None:
        return True

    item = config.player_inventory[idx]
    item_id = item[0]
    equip_idx_by_type = {
        "head": 36,
        "chest": 37,
        "ring": 38,
        "pants": 40,
        "shoes": 41,
        "arms": 42,
        "necklace": 43,
        "back": 44,
        "shield": 45,
        "shoulders": 46,
        "hands": 47,
    }
    if idx >= 36:
        target = next((i for i in range(27) if config.player_inventory[i] is None), None)
        if target is not None:
            config.player_inventory[target] = item
            config.player_inventory[idx] = None
            config.state_outbox.put({"type": "inv_swap", "slot_a": idx, "slot_b": target})
        return True

    slot_type = _ITEM_SLOT_TYPES.get(item_id)
    equip_idx = equip_idx_by_type.get(slot_type) if slot_type else None
    if slot_type == "ring" and equip_idx is not None:
        if config.player_inventory[38] is not None and config.player_inventory[39] is None:
            equip_idx = 39
    if equip_idx is not None:
        existing = config.player_inventory[equip_idx]
        config.player_inventory[equip_idx] = item
        config.player_inventory[idx] = existing
        config.state_outbox.put({"type": "inv_swap", "slot_a": idx, "slot_b": equip_idx})
    return True


def handle_drag_mouse_up(event, state) -> bool:
    if not (event.button == 1 and config.drag_item is not None):
        return False

    from rendering.inventory import slot_at, can_drop_in_slot

    mx, my = event.pos
    ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]

    if config.chest_drag_slot is not None:
        from rendering.chest import chest_bag_slot_at as _cba, chest_slot_at as _csa
        from rendering.inventory import get_item_max_stack, is_item_stackable

        target = _cba(mx, my, ww, wh)
        if target is not None and can_drop_in_slot(config.drag_item[0], target):
            existing = config.player_inventory[target]
            drag_id = config.drag_item[0]
            obj = config.placed_objects.get(config.open_chest_uid)
            if obj is not None:
                ci = obj.setdefault("chest_inv", [None] * 27)
                while len(ci) < 27:
                    ci.append(None)
            merge_dest = None
            if existing is not None and existing[0] == drag_id and is_item_stackable(drag_id):
                max_stk = get_item_max_stack(drag_id)
                combined = existing[1] + config.drag_item[1]
                if combined <= max_stk:
                    config.player_inventory[target] = [drag_id, combined]
                    if obj is not None:
                        ci[config.chest_drag_slot] = None
                else:
                    config.player_inventory[target] = [drag_id, max_stk]
                    if obj is not None:
                        ci[config.chest_drag_slot] = [drag_id, combined - max_stk]
                merge_dest = "player"
            else:
                config.player_inventory[target] = config.drag_item
                if obj is not None:
                    ci[config.chest_drag_slot] = existing
            config.state_outbox.put(
                {
                    "type": "chest_swap",
                    "uid": config.open_chest_uid,
                    "chest_slot": config.chest_drag_slot,
                    "player_slot": target,
                    **({"merge_dest": merge_dest} if merge_dest else {}),
                }
            )
            config.chest_ui_hold_until = time.time() + 0.3
        else:
            cs2 = _csa(mx, my, ww, wh)
            if cs2 is not None and cs2 != config.chest_drag_slot:
                obj = config.placed_objects.get(config.open_chest_uid)
                if obj is not None:
                    ci = obj.setdefault("chest_inv", [None] * 27)
                    while len(ci) < 27:
                        ci.append(None)
                    ci[cs2], ci[config.chest_drag_slot] = config.drag_item, ci[cs2]
            else:
                obj = config.placed_objects.get(config.open_chest_uid)
                if obj is not None:
                    ci = obj.setdefault("chest_inv", [None] * 27)
                    while len(ci) < 27:
                        ci.append(None)
                    ci[config.chest_drag_slot] = config.drag_item
        config.chest_drag_slot = None
        config.drag_item = None

    elif config.open_chest_uid is not None:
        from rendering.chest import chest_slot_at as _csa2, chest_bag_slot_at as _cba2

        cs = _csa2(mx, my, ww, wh)
        if cs is not None:
            from rendering.inventory import get_item_max_stack, is_item_stackable

            obj = config.placed_objects.get(config.open_chest_uid)
            if obj is not None:
                ci = obj.setdefault("chest_inv", [None] * 27)
                while len(ci) < 27:
                    ci.append(None)
                existing = ci[cs]
                drag_id = config.drag_item[0]
                merge_dest = None
                if existing is not None and existing[0] == drag_id and is_item_stackable(drag_id):
                    max_stk = get_item_max_stack(drag_id)
                    combined = existing[1] + config.drag_item[1]
                    if combined <= max_stk:
                        ci[cs] = [drag_id, combined]
                        config.player_inventory[config.drag_slot] = None
                    else:
                        ci[cs] = [drag_id, max_stk]
                        config.player_inventory[config.drag_slot] = [drag_id, combined - max_stk]
                    merge_dest = "chest"
                else:
                    ci[cs] = config.drag_item
                    config.player_inventory[config.drag_slot] = existing
                config.state_outbox.put(
                    {
                        "type": "chest_swap",
                        "uid": config.open_chest_uid,
                        "chest_slot": cs,
                        "player_slot": config.drag_slot,
                        **({"merge_dest": merge_dest} if merge_dest else {}),
                    }
                )
                config.chest_ui_hold_until = time.time() + 0.3
            else:
                config.player_inventory[config.drag_slot] = config.drag_item
            config.drag_slot = None
            config.drag_item = None
        else:
            bs = _cba2(mx, my, ww, wh)
            if bs is None:
                config.player_inventory[config.drag_slot] = config.drag_item
                config.drag_slot = None
                config.drag_item = None

    if config.drag_item is not None:
        if config.open_chest_uid is not None:
            from rendering.chest import chest_bag_slot_at as _cba3

            target = _cba3(mx, my, ww, wh)
        else:
            target = slot_at(mx, my, ww, wh)
        if target is not None:
            drag_id = config.drag_item[0]
            existing = config.player_inventory[target]
            drag_ok = can_drop_in_slot(drag_id, target)
            swap_ok = existing is None or can_drop_in_slot(existing[0], config.drag_slot)
            if drag_ok and swap_ok:
                if existing is None:
                    config.player_inventory[target] = config.drag_item
                elif existing[0] == drag_id:
                    from rendering.inventory import get_item_max_stack, is_item_stackable

                    if is_item_stackable(drag_id):
                        max_stk = get_item_max_stack(drag_id)
                        combined = existing[1] + config.drag_item[1]
                        if combined <= max_stk:
                            config.player_inventory[target] = [drag_id, combined]
                            config.player_inventory[config.drag_slot] = None
                        else:
                            config.player_inventory[target] = [drag_id, max_stk]
                            config.player_inventory[config.drag_slot] = [drag_id, combined - max_stk]
                    else:
                        config.player_inventory[config.drag_slot] = existing
                        config.player_inventory[target] = config.drag_item
                else:
                    config.player_inventory[config.drag_slot] = existing
                    config.player_inventory[target] = config.drag_item
                config.state_outbox.put(
                    {"type": "inv_swap", "slot_a": config.drag_slot, "slot_b": target}
                )
            else:
                config.player_inventory[config.drag_slot] = config.drag_item
        else:
            config.player_inventory[config.drag_slot] = config.drag_item
        config.drag_slot = None
        config.drag_item = None
    return True

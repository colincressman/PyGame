import pygame

import config


def handle_shop_event(event, state) -> bool:
    if not config.show_shop:
        return False

    if event.type == pygame.MOUSEWHEEL:
        config.shop_scroll = max(0, config.shop_scroll - event.y)
        return True

    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
        if config.drag_item is not None:
            if config.drag_slot is not None:
                config.player_inventory[config.drag_slot] = config.drag_item
            config.drag_slot = None
            config.drag_item = None
        return True

    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        mx, my = event.pos
        sw, sh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
        from rendering.npc_shop import (
            merchant_slot_at as _msat,
            bag_slot_at as _bsat,
            close_shop as _close,
            panel_origin as _spo,
            PANEL_W as _SPW,
        )

        ppx, ppy = _spo(sw, sh)
        if ppx + _SPW - 24 <= mx <= ppx + _SPW - 6 and ppy + 6 <= my <= ppy + 24:
            _close()
            return True

        midx = _msat(mx, my, sw, sh)
        if midx is not None:
            config.state_outbox.put(
                {"type": "shop_buy", "npc_type": config.shop_npc_type, "shop_slot": midx}
            )
            return True

        bidx = _bsat(mx, my, sw, sh)
        if bidx is not None and bidx < len(config.player_inventory):
            item = config.player_inventory[bidx]
            if item is not None:
                config.drag_slot = bidx
                config.drag_item = list(item)
                config.player_inventory[bidx] = None
        return True

    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        if config.drag_item is None:
            return True
        mx, my = event.pos
        sw, sh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
        from rendering.npc_shop import bag_slot_at as _bsat2, merchant_section_rect as _msr

        if _msr(sw, sh).collidepoint(mx, my) and config.drag_slot is not None and config.drag_slot < 36:
            config.state_outbox.put(
                {"type": "shop_sell", "slot": config.drag_slot, "npc_type": config.shop_npc_type}
            )
            config.drag_slot = None
            config.drag_item = None
            return True

        bidx2 = _bsat2(mx, my, sw, sh)
        if bidx2 is not None:
            target_item = (
                config.player_inventory[bidx2] if bidx2 < len(config.player_inventory) else None
            )
            config.player_inventory[bidx2] = config.drag_item
            if config.drag_slot is not None:
                config.player_inventory[config.drag_slot] = target_item
                config.state_outbox.put(
                    {"type": "inv_swap", "slot_a": config.drag_slot, "slot_b": bidx2}
                )
            config.drag_slot = None
            config.drag_item = None
            return True

        if config.drag_slot is not None:
            config.player_inventory[config.drag_slot] = config.drag_item
        config.drag_slot = None
        config.drag_item = None
        return True

    return False

import pygame
import time
import config
from input.controls_actions_v2 import handle_smart_action as _handle_smart_action_v2
from input.controls_movement_v2 import handle_movement
from rendering.display import toggle_fullscreen
from rendering.inventory import _is_consumable
from config import TILE_SIZE, PLAYER_SPEED, SPRINT_SPEED, STEALTH_SPEED, WORLD_MAX_TILES

_door_last_toggle: float = 0.0   # time.time() of last door toggle; prevents key-repeat flicker
_DOOR_COOLDOWN: float   = 0.4    # seconds between allowed toggles

# Tool requirements per node type (mirrors server/world/resource_nodes.py NODE_TYPES)
_NODE_TOOL = {
    "tree":          "axe",
    "pine_tree":     "axe",
    "jungle_tree":   "axe",
    "palm_tree":     "axe",
    "stone_deposit": "pickaxe",
    "coal_deposit":  "pickaxe",
    "iron_ore":      "pickaxe_stone",
    "copper_ore":    "pickaxe_stone",
    "tin_ore":       "pickaxe_stone",
    "silver_ore":    "pickaxe_iron",
    "gold_ore":      "pickaxe_iron",
    "crystal":       "pickaxe_steel",
    "obsidian":      "pickaxe_steel",
}
# Item IDs that satisfy each tool tier
_TOOL_ITEMS = {
    "axe":            {2000, 2050, 2051, 2100, 2150, 2200, 2250, 2300, 2350, 2400},
    "pickaxe":        {2001, 2052, 2053, 2101, 2151, 2201, 2251, 2301, 2351, 2401},
    "pickaxe_stone":  {2053, 2101, 2151, 2201, 2251, 2301, 2351, 2401},
    "pickaxe_iron":   {2101, 2151, 2201, 2251, 2301, 2351, 2401},
    "pickaxe_steel":  {2251, 2301, 2351, 2401},
}
# Tier rank for combined picks (meta-based), mirrors server _PICK_TIER_RANK
_PICK_TIER_RANK: dict[str, int] = {
    "pickaxe":       0,
    "pickaxe_stone": 1,
    "pickaxe_iron":  2,
    "pickaxe_steel": 3,
}

# Damage per hit for optimistic progress bar (mirrors server TOOL_DAMAGE)
_TOOL_DAMAGE = {
    2000: 1,   # Scrap Axe
    2050: 2,   # Wooden Axe
    2051: 3,   # Stone Axe
    2100: 5,   # Iron Axe
    2150: 6,   # Copper Axe
    2200: 8,   # Bronze Axe
    2250: 10,  # Steel Axe
    2300: 12,  # Gold Axe
    2350: 14,  # Crystal Axe
    2400: 16,  # Obsidian Axe
    2001: 1,   # Scrap Pickaxe
    2052: 1,   # Wooden Pickaxe
    2053: 2,   # Stone Pickaxe
    2101: 4,   # Iron Pickaxe
    2151: 5,   # Copper Pickaxe
    2201: 7,   # Bronze Pickaxe
    2251: 8,   # Steel Pickaxe
    2301: 9,   # Gold Pickaxe
    2351: 12,  # Crystal Pick
    2401: 18,  # Obsidian Pickaxe
}


_HOTBAR_OFFSET = 27  # hotbar row starts at inventory slot 27

# Placeable item IDs → object type string (mirrors server/game_state/placed_objects.py)
_PLACEABLE_ITEMS = {
    207: "campfire",      200: "crafting_table", 201: "furnace",
    250: "wood_wall",     251: "stone_wall",     252: "door",    220: "bed",
    253: "stone_brick_wall", 254: "stone_brick_floor", 202: "alloy_forge",
    203: "chest",         204: "part_maker",
    205: "part_combiner", 206: "embedder",
    214: "torch",         215: "lantern",
    # Farming — saplings and ore seeds
    34:  "tree_sapling",  46: "pine_sapling",  47: "jungle_sapling", 48: "palm_sapling",
    35:  "iron_seed",     36: "coal_seed",     37: "copper_seed",    38: "tin_seed",
    39:  "silver_seed",   40: "gold_seed",     41: "crystal_seed",   42: "obsidian_seed",
}


def _hotbar_item():
    """Return the item in the currently selected hotbar slot, or None."""
    idx = _HOTBAR_OFFSET + config.hotbar_slot
    inv = config.player_inventory
    return inv[idx] if 0 <= idx < len(inv) else None


def _has_tool(tool_type: str) -> bool:
    """Return True if the active hotbar slot holds a tool satisfying tool_type."""
    item = _hotbar_item()
    if item is None:
        return False
    if item[0] in _TOOL_ITEMS.get(tool_type, set()):
        return True
    # Combined tool: check meta mining_tier
    if len(item) > 2 and isinstance(item[2], dict):
        req_rank  = _PICK_TIER_RANK.get(tool_type, -1)
        item_rank = _PICK_TIER_RANK.get(item[2].get("mining_tier", ""), -1)
        if req_rank >= 0 and item_rank >= req_rank:
            return True
    return False


def _best_tool_damage(tool_type: str) -> int:
    """Return the damage value of the tool currently in the hotbar slot."""
    item = _hotbar_item()
    if item is None:
        return 1
    # Combined tool: use meta mining_damage
    if len(item) > 2 and isinstance(item[2], dict):
        md = item[2].get("mining_damage")
        if md is not None:
            return int(md)
    if item[0] in _TOOL_ITEMS.get(tool_type, set()):
        return _TOOL_DAMAGE.get(item[0], 1)
    return 1


def handle_events(state):
    for event in pygame.event.get():
        # ── Shop UI: intercept mouse events when shop is open ───────────────
        if config.show_shop:
            if event.type == pygame.MOUSEWHEEL:
                config.shop_scroll = max(0, config.shop_scroll - event.y)
                continue

            # Right-click: cancel any active drag
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if config.drag_item is not None:
                    if config.drag_slot is not None:
                        config.player_inventory[config.drag_slot] = config.drag_item
                    config.drag_slot = None
                    config.drag_item = None
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                sw, sh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                from rendering.npc_shop import (
                    merchant_slot_at as _msat, bag_slot_at as _bsat,
                    close_shop as _close, panel_origin as _spo,
                    PANEL_W as _SPW,
                )
                ppx, ppy = _spo(sw, sh)
                # Close button [X] at panel-local (PANEL_W-24, 6), size (18, 18)
                if ppx + _SPW - 24 <= mx <= ppx + _SPW - 6 and ppy + 6 <= my <= ppy + 24:
                    _close()
                    continue
                # Click merchant slot → buy
                midx = _msat(mx, my, sw, sh)
                if midx is not None:
                    config.state_outbox.put({
                        "type":      "shop_buy",
                        "npc_type":  config.shop_npc_type,
                        "shop_slot": midx,
                    })
                    continue
                # Click bag slot → start drag
                bidx = _bsat(mx, my, sw, sh)
                if bidx is not None and bidx < len(config.player_inventory):
                    item = config.player_inventory[bidx]
                    if item is not None:
                        config.drag_slot = bidx
                        config.drag_item = list(item)
                        config.player_inventory[bidx] = None
                continue

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if config.drag_item is None:
                    continue
                mx, my = event.pos
                sw, sh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                from rendering.npc_shop import (
                    bag_slot_at as _bsat2, merchant_section_rect as _msr,
                )
                # Dropped on merchant grid → sell
                if (_msr(sw, sh).collidepoint(mx, my)
                        and config.drag_slot is not None and config.drag_slot < 36):
                    config.state_outbox.put({
                        "type":     "shop_sell",
                        "slot":     config.drag_slot,
                        "npc_type": config.shop_npc_type,
                    })
                    config.drag_slot = None
                    config.drag_item = None
                    continue
                # Dropped on bag slot → swap within bag
                bidx2 = _bsat2(mx, my, sw, sh)
                if bidx2 is not None:
                    target_item = (config.player_inventory[bidx2]
                                   if bidx2 < len(config.player_inventory) else None)
                    config.player_inventory[bidx2] = config.drag_item
                    if config.drag_slot is not None:
                        config.player_inventory[config.drag_slot] = target_item
                        config.state_outbox.put({
                            "type":   "inv_swap",
                            "slot_a": config.drag_slot,
                            "slot_b": bidx2,
                        })
                    config.drag_slot = None
                    config.drag_item = None
                    continue
                # Dropped outside → return to source
                if config.drag_slot is not None:
                    config.player_inventory[config.drag_slot] = config.drag_item
                config.drag_slot = None
                config.drag_item = None
                continue
        # ── Char creator: intercept mouse/scroll when creator is open ───────
        if config.show_char_creator:
            if event.type == pygame.MOUSEWHEEL:
                from rendering.char_creator import handle_scroll as _cc_scroll
                _cc_scroll(event.y)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                from rendering.char_creator import handle_click as _cc_click
                _cc_click(event.pos[0], event.pos[1], state["screen"])
                continue
        if event.type == pygame.QUIT:
            state["running"] = False
        elif event.type == pygame.KEYDOWN:
            # ── Chat input mode: intercept all keys while chat is open ──────────
            if config.chat_open:
                if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    text = config.chat_input.strip()
                    if text:
                        config.state_outbox.put({"type": "chat", "text": text})
                    config.chat_input = ""
                    config.chat_open  = False
                elif event.key == pygame.K_ESCAPE:
                    config.chat_input = ""
                    config.chat_open  = False
                elif event.key == pygame.K_BACKSPACE:
                    config.chat_input = config.chat_input[:-1]
                else:
                    if event.unicode and ord(event.unicode) >= 32:
                        config.chat_input += event.unicode
                continue  # eat all other events while chat is open
            # ── Open chat with T (when no other UI is blocking) ─────────────────
            if event.key == pygame.K_t:
                if (not config.show_inventory and not config.show_menu
                        and not config.show_stats
                        and config.show_station_popup is None
                        and config.open_chest_uid is None):
                    config.chat_open  = True
                    config.chat_input = ""
                continue
            # ── Keybind rebind: intercept next key while listening ───────────────
            if config.controls_listen is not None:
                if event.key != pygame.K_ESCAPE:
                    config.keybinds[config.controls_listen] = event.key
                    config.save_keybinds()
                config.controls_listen = None
                continue
            if event.key == config.keybinds["map"]:
                state["show_map"] = not state["show_map"]
                state["map_needs_redraw"] = state["show_map"]
            elif event.key == pygame.K_c and not config.chat_open:
                # C = toggle character creator
                if (not config.show_inventory and not config.show_menu
                        and not config.show_stats and not config.show_shop
                        and config.show_station_popup is None):
                    config.show_char_creator = not config.show_char_creator
            elif event.key == config.keybinds["roll"]:
                # Space → dodge roll in the direction currently held
                if (not config.show_inventory and not config.show_menu
                        and not config.show_stats
                        and config.show_station_popup is None
                        and config.open_chest_uid is None
                        and not config.rolling):
                    _keys = pygame.key.get_pressed()
                    _dx = float(_keys[config.keybinds["move_right"]]) - float(_keys[config.keybinds["move_left"]])
                    _dy = float(_keys[config.keybinds["move_down"]])  - float(_keys[config.keybinds["move_up"]])
                    if _dx != 0 or _dy != 0:
                        _length = (_dx * _dx + _dy * _dy) ** 0.5
                        from input.controls_movement_v2 import start_roll as _start_roll
                        _start_roll(_dx / _length, _dy / _length)
            elif event.key == config.keybinds["inventory"]:
                # Cancel any active drag before toggling inventory
                if config.drag_item is not None:
                    config.player_inventory[config.drag_slot] = config.drag_item
                    config.drag_slot = None
                    config.drag_item = None
                config.pickup_mode = False
                config.show_inventory = not config.show_inventory
            elif event.key == config.keybinds["interact"]:
                # F = close chest / close station popup / open chest or station / interact
                if config.open_chest_uid is not None:
                    from rendering.chest import _cancel_drag
                    _cancel_drag()
                    config.open_chest_uid = None
                elif config.show_station_popup is not None:
                    if config.show_station_popup == "part_combiner":
                        config.combiner_slots = [None, None, None, None]
                        config.combiner_selected_slot = -1
                    elif config.show_station_popup == "embedder":
                        config.embedder_slots = [None, None]
                        config.embedder_selected_slot = -1
                    config.show_station_popup = None
                    config.station_popup_uid   = None
                    config.station_popup_scroll = 0
                    config.station_popup_recipe = None
                elif (not config.show_inventory
                        and not config.show_menu and not config.show_stats):
                    config.pickup_mode = False
                    from state.player import player_data as _pd
                    px, py = _pd["pos"]
                    _STATION_TYPES = {"furnace", "campfire", "crafting_table", "alloy_forge", "part_maker", "part_combiner", "embedder"}
                    # 0. Open nearby chest
                    best_ch_uid, best_ch_dsq = None, 1.0
                    for uid, obj in config.placed_objects.items():
                        if obj.get("type") != "chest":
                            continue
                        dx = (obj["pos"][0] + 0.5) - px
                        dy = (obj["pos"][1] + 0.5) - py
                        dsq = dx * dx + dy * dy
                        if dsq < best_ch_dsq:
                            best_ch_dsq, best_ch_uid = dsq, uid
                    if best_ch_uid is not None:
                        config.open_chest_uid = best_ch_uid
                    else:
                        # 1. Open nearby crafting station
                        best_st_uid, best_st_dsq = None, 2.25
                        for uid, obj in config.placed_objects.items():
                            if obj.get("type") not in _STATION_TYPES:
                                continue
                            dx = (obj["pos"][0] + 0.5) - px
                            dy = (obj["pos"][1] + 0.5) - py
                            dsq = dx * dx + dy * dy
                            if dsq < best_st_dsq:
                                best_st_dsq, best_st_uid = dsq, uid
                        if best_st_uid is not None:
                            _st_type = config.placed_objects[best_st_uid]["type"]
                            config.show_station_popup = _st_type
                            config.station_popup_uid   = best_st_uid
                            config.station_popup_scroll = 0
                            config.station_popup_recipe = None
                            if _st_type == "part_maker":
                                config.station_popup_tab = "blade"
                            elif _st_type == "crafting_table":
                                config.station_popup_tab = "weapon"
                        else:
                            # 0b. NPC shop interaction
                            from rendering.npcs import try_open_npc_shop as _try_npc
                            if not _try_npc([px, py]):
                                # 2. Tool-less node gather (includes item_drop nodes)
                                best_id   = None
                                best_dist = 2.25
                                for nid, node in config.world_nodes.items():
                                    if node.get("type", "") in _NODE_TOOL:
                                        continue
                                    dx  = (node["wx"] + 0.5) - px
                                    dy  = (node["wy"] + 0.5) - py
                                    dsq = dx * dx + dy * dy
                                    if dsq < best_dist:
                                        best_dist = dsq
                                        best_id   = nid
                                if best_id is not None:
                                    config.state_outbox.put({"type": "gather", "node_id": best_id})
                                    node = config.world_nodes.get(best_id)
                                    if node is not None:
                                        if node.get("type") == "item_drop":
                                            # Optimistic removal of the item sprite too
                                            uid = best_id[5:]
                                            config.world_items = {k: v for k, v in config.world_items.items() if k != uid}
                                        node["hits"] = node.get("hits", 0) + 1
                                        if node["hits"] >= node.get("max_hp", 1):
                                            config.world_nodes.pop(best_id, None)
            elif event.key == pygame.K_z:
                # Z = toggle pickup mode (click placed objects to pick them up)
                if (not config.show_inventory
                        and not config.show_menu and not config.show_stats
                        and config.show_station_popup is None):
                    config.pickup_mode = not config.pickup_mode
            elif event.key == config.keybinds["stats"]:
                config.show_stats = not config.show_stats
            elif event.key == config.keybinds["door"]:
                # R = interact: toggle door / use bed (nearest interactive object within 1.5 tiles)
                if (not config.show_inventory
                        and not config.show_menu and not config.show_stats
                        and config.show_station_popup is None):
                    from state.player import player_data as _pd
                    px, py = _pd["pos"]
                    _INTERACTIVE = {"door", "bed"}
                    best_uid, best_dsq = None, 2.25  # 1.5 tiles squared
                    for uid, obj in config.placed_objects.items():
                        if obj.get("type") not in _INTERACTIVE:
                            continue
                        dx = (obj["pos"][0] + 0.5) - px
                        dy = (obj["pos"][1] + 0.5) - py
                        dsq = dx * dx + dy * dy
                        if dsq < best_dsq:
                            best_dsq, best_uid = dsq, uid
                    if best_uid is not None:
                        obj = config.placed_objects[best_uid]
                        if obj["type"] == "door":
                            global _door_last_toggle
                            now = time.time()
                            if now - _door_last_toggle >= _DOOR_COOLDOWN:
                                _door_last_toggle = now
                                config.state_outbox.put({"type": "toggle_door", "uid": best_uid})
                        elif obj["type"] == "bed":
                            config.state_outbox.put({"type": "use_bed", "uid": best_uid})
            elif pygame.K_1 <= event.key <= pygame.K_9:
                config.hotbar_slot = event.key - pygame.K_1
            elif event.key == pygame.K_F11:
                toggle_fullscreen(state)
            elif event.key == pygame.K_ESCAPE:
                # Cancel any active drag first
                if config.drag_item is not None:
                    config.player_inventory[config.drag_slot] = config.drag_item
                    config.drag_slot = None
                    config.drag_item = None
                if config.chest_drag_slot is not None:
                    from rendering.chest import _cancel_drag
                    _cancel_drag()
                if config.open_chest_uid is not None:
                    config.open_chest_uid = None
                if config.show_shop:
                    from rendering.npc_shop import close_shop as _close_shop
                    _close_shop()
                    return
                if config.show_char_creator:
                    config.show_char_creator = False
                    return
                if config.show_station_popup is not None:
                    if config.show_station_popup == "part_combiner":
                        config.combiner_slots = [None, None, None, None]
                        config.combiner_selected_slot = -1
                    elif config.show_station_popup == "embedder":
                        config.embedder_slots = [None, None]
                        config.embedder_selected_slot = -1
                    config.show_station_popup = None
                    config.station_popup_uid   = None
                    config.station_popup_scroll = 0
                    config.station_popup_recipe = None
                elif config.show_inventory:
                    config.show_inventory = False
                elif config.show_stats:
                    config.show_stats = False
                elif config.controls_listen is not None:
                    config.controls_listen = None
                elif config.show_controls:
                    config.show_controls = False
                else:
                    config.show_menu = not config.show_menu
        elif event.type == pygame.MOUSEWHEEL:
            if config.show_station_popup is not None:
                config.station_popup_scroll = max(0, config.station_popup_scroll - event.y * 24)
            elif config.show_inventory and config.inventory_tab == "craft":
                config.crafting_scroll = max(0, config.crafting_scroll - event.y * 24)
            elif config.show_inventory and config.inventory_tab == "creative":
                config.creative_scroll = max(0, config.creative_scroll - event.y)
            else:
                config.hotbar_slot = (config.hotbar_slot - event.y) % 9
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and config.show_menu:
                config.menu_click_pos = event.pos
            elif event.button == 1 and config.show_controls:
                config.controls_click_pos = event.pos
            elif event.button == 1 and config.show_station_popup == "part_combiner":
                from rendering.combiner import combiner_popup_hit, valid_for_slot, _compute_preview
                mx, my = event.pos
                ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                result = combiner_popup_hit(mx, my, ww, wh)
                if result is not None:
                    kind, val = result
                    if kind == "outside":
                        config.combiner_slots = [None, None, None, None]
                        config.combiner_selected_slot = -1
                        config.show_station_popup = None
                        config.station_popup_uid  = None
                    elif kind == "combiner_slot":
                        # Toggle selection: click selected slot to deselect it
                        if config.combiner_selected_slot == val:
                            config.combiner_selected_slot = -1
                        else:
                            config.combiner_selected_slot = val
                    elif kind == "inv_slot":
                        cs = config.combiner_selected_slot
                        if cs != -1:
                            slot = config.player_inventory[val]
                            # Determine current mold ID so slot-2 validation is armor-aware
                            _mold_ii = config.combiner_slots[0]
                            _mold_id = (
                                config.player_inventory[_mold_ii][0]
                                if _mold_ii is not None
                                and config.player_inventory[_mold_ii] is not None
                                else None
                            )
                            if slot is not None and valid_for_slot(slot[0], cs, _mold_id):
                                config.combiner_slots[cs] = val
                                # Auto-advance to next unfilled slot
                                for nxt in range(cs + 1, 4):
                                    if config.combiner_slots[nxt] is None:
                                        config.combiner_selected_slot = nxt
                                        break
                                else:
                                    config.combiner_selected_slot = -1
                    elif kind == "combine":
                        preview = _compute_preview(
                            config.player_inventory, config.combiner_slots
                        )
                        if preview is not None:
                            m, p, h, b = config.combiner_slots
                            config.state_outbox.put({
                                "type":            "combine_parts",
                                "mold_slot":       m,
                                "primary_slot":    p,
                                "handle_slot":     h,
                                "binding_slot":    b,
                                "nearby_stations": list(config.nearby_stations),
                            })
                            # Toast feedback
                            from rendering.hud import show_toast
                            trait_str = (", ".join(preview["traits"])
                                         if preview.get("traits") else "")
                            msg = f"Forged: {preview['name']}"
                            if trait_str:
                                msg += f"  [{trait_str}]"
                            show_toast(msg)
                            config.combiner_slots = [None, None, None, None]
                            config.combiner_selected_slot = -1
            elif event.button == 1 and config.show_station_popup == "embedder":
                from rendering.embedder import embedder_popup_hit, valid_for_embedder_slot, _can_embed
                mx, my = event.pos
                ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                result = embedder_popup_hit(mx, my, ww, wh)
                if result is not None:
                    kind, val = result
                    if kind == "outside":
                        config.embedder_slots = [None, None]
                        config.embedder_selected_slot = -1
                        config.show_station_popup = None
                        config.station_popup_uid  = None
                    elif kind == "embedder_slot":
                        config.embedder_selected_slot = (
                            -1 if config.embedder_selected_slot == val else val
                        )
                    elif kind == "inv_slot":
                        cs = config.embedder_selected_slot
                        if cs != -1:
                            slot = config.player_inventory[val]
                            if slot is not None and valid_for_embedder_slot(
                                slot[0], cs, slot
                            ):
                                config.embedder_slots[cs] = val
                                # Auto-advance to next unfilled slot
                                for nxt in range(cs + 1, 2):
                                    if config.embedder_slots[nxt] is None:
                                        config.embedder_selected_slot = nxt
                                        break
                                else:
                                    config.embedder_selected_slot = -1
                    elif kind == "embed":
                        if _can_embed(config.player_inventory, config.embedder_slots):
                            i_idx, g_idx = config.embedder_slots
                            config.state_outbox.put({
                                "type":            "embed_gem",
                                "item_slot":       i_idx,
                                "gem_slot":        g_idx,
                                "nearby_stations": list(config.nearby_stations),
                            })
                            # Toast
                            from rendering.hud import show_toast
                            inv = config.player_inventory
                            g_slot = inv[g_idx]
                            import json as _json, os as _os
                            try:
                                _ipath = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                                       "..", "..", "server", "items.json")
                                with open(_ipath) as _f:
                                    _idata = {int(k): v for k, v in _json.load(_f).items()}
                                gem_name = _idata.get(g_slot[0], {}).get("name", "Gem")
                            except Exception:
                                gem_name = "Gem"
                            show_toast(f"Embedded: {gem_name}")
                            config.embedder_slots = [None, None]
                            config.embedder_selected_slot = -1

            elif event.button == 1 and config.show_station_popup:
                from rendering.crafting import station_popup_hit, _can_craft, _recipes
                mx, my = event.pos
                result = station_popup_hit(mx, my, config.show_station_popup,
                                           state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
                if result is not None:
                    kind, val = result
                    if kind == "outside":
                        config.show_station_popup = None
                        config.station_popup_uid   = None
                        config.station_popup_scroll = 0
                        config.station_popup_recipe = None
                    elif kind == "tab":
                        config.station_popup_tab = val
                        config.station_popup_scroll = 0
                        config.station_popup_recipe = None
                        config.repair_selected_slot = None
                    elif kind == "recipe":
                        config.station_popup_recipe = val
                    elif kind == "craft":
                        sel = _recipes.get(config.station_popup_recipe)
                        if sel and _can_craft(sel):
                            _nearby = set(config.nearby_stations)
                            if config.show_station_popup:
                                _nearby.add(config.show_station_popup)
                            config.state_outbox.put({
                                "type":            "craft",
                                "recipe_id":       config.station_popup_recipe,
                                "nearby_stations": list(_nearby),
                            })
                    elif kind == "repair_slot":
                        config.repair_selected_slot = val
                    elif kind == "repair":
                        config.state_outbox.put({
                            "type":            "repair_item",
                            "item_slot":       config.repair_selected_slot,
                            "nearby_stations": list(config.nearby_stations),
                        })
            elif event.button == 1 and config.show_stats:
                config.stat_click_pos = event.pos
            elif event.button == 1 and config.open_chest_uid is not None \
                    and not config.show_menu and not config.show_stats \
                    and config.show_station_popup is None:
                # ── Unified chest panel click handler ────────────────────────
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
                                # Shift+click chest slot → auto-move to first free bag slot
                                target_bag = next(
                                    (i for i in range(27) if config.player_inventory[i] is None),
                                    None,
                                )
                                if target_bag is not None:
                                    config.player_inventory[target_bag] = list(chest_inv[cs])
                                    chest_inv[cs] = None
                                    config.state_outbox.put({
                                        "type":        "chest_swap",
                                        "uid":         config.open_chest_uid,
                                        "chest_slot":  cs,
                                        "player_slot": target_bag,
                                    })
                            else:
                                config.chest_drag_slot = cs
                                config.drag_item       = list(chest_inv[cs])
                                chest_inv[cs]          = None
                else:
                    bs = chest_bag_slot_at(mx, my, ww, wh)
                    if bs is not None:
                        if config.player_inventory[bs] is not None:
                            if mods_chest & pygame.KMOD_SHIFT:
                                # Shift+click bag slot → auto-move to first free chest slot
                                obj = config.placed_objects.get(config.open_chest_uid)
                                if obj is not None:
                                    chest_inv = obj.setdefault("chest_inv", [None] * 27)
                                    while len(chest_inv) < 27:
                                        chest_inv.append(None)
                                    target_cs = next(
                                        (i for i in range(27) if chest_inv[i] is None),
                                        None,
                                    )
                                    if target_cs is not None:
                                        chest_inv[target_cs] = list(config.player_inventory[bs])
                                        config.player_inventory[bs] = None
                                        config.state_outbox.put({
                                            "type":        "chest_swap",
                                            "uid":         config.open_chest_uid,
                                            "chest_slot":  target_cs,
                                            "player_slot": bs,
                                        })
                            else:
                                config.drag_slot = bs
                                config.drag_item = list(config.player_inventory[bs])
                                config.player_inventory[bs] = None
                    else:
                        # Click outside panel — close chest
                        from rendering.chest import _cancel_drag
                        _cancel_drag()
                        config.open_chest_uid = None
            elif event.button == 1 and config.show_inventory:
                mx, my = event.pos
                ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]
                # Check tab click first
                from rendering.inventory import inventory_tab_hit, slot_at
                inv_tab = inventory_tab_hit(mx, my, ww, wh)
                if inv_tab is not None:
                    config.inventory_tab = inv_tab
                    config.crafting_scroll = 0
                    config.selected_recipe = None
                elif config.inventory_tab == "creative":
                    from rendering.inventory import creative_tab_click
                    item_id = creative_tab_click(mx, my, ww, wh)
                    if item_id is not None:
                        config.state_outbox.put({
                            "type":    "give_item",
                            "item_id": item_id,
                            "qty":     1,
                        })
                elif config.inventory_tab == "craft":
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
                                config.state_outbox.put({
                                    "type":            "craft",
                                    "recipe_id":       config.selected_recipe,
                                    "nearby_stations": list(config.nearby_stations),
                                })
                else:
                    idx = slot_at(mx, my, ww, wh)
                    if idx is not None and config.player_inventory[idx] is not None:
                        config.drag_slot = idx
                        config.drag_item = list(config.player_inventory[idx])
                        config.player_inventory[idx] = None
            elif event.button == 1 and not (config.show_stats or config.show_menu):
                if config.pickup_mode:
                    # Pickup mode: click picks up whatever placed object is at the mouse tile
                    tx, ty = config.mouse_tile
                    target_uid = None
                    for uid, obj in list(config.placed_objects.items()):
                        if obj["pos"][0] == tx and obj["pos"][1] == ty:
                            target_uid = uid
                            break
                    if target_uid is not None:
                        if config.station_popup_uid == target_uid:
                            config.show_station_popup = None
                            config.station_popup_uid   = None
                            config.station_popup_scroll = 0
                            config.station_popup_recipe = None
                        config.state_outbox.put({"type": "remove_object", "uid": target_uid})
                        config.placed_objects.pop(target_uid, None)
                else:
                    # Left-click on world — place placeable item at mouse tile
                    active_slot = _HOTBAR_OFFSET + config.hotbar_slot
                    _item = config.player_inventory[active_slot]
                    if _item is not None and _item[0] in _PLACEABLE_ITEMS and not config.placement_blocked:
                        tx, ty = config.mouse_tile
                        obj_type = _PLACEABLE_ITEMS[_item[0]]
                        config.state_outbox.put({"type": "place_object", "obj_type": obj_type, "pos": [tx, ty]})
                        # Optimistic hotbar deduction
                        if _item[1] > 1:
                            config.player_inventory[active_slot] = [_item[0], _item[1] - 1]
                        else:
                            config.player_inventory[active_slot] = None
                        # Optimistic placed_objects update — prevents stacking before server confirms
                        _opt_uid = f"_opt_{tx}_{ty}"
                        config.placed_objects[_opt_uid] = {
                            "uid": _opt_uid, "type": obj_type, "pos": [tx, ty], "placed_by": "",
                        }
                    else:
                        # No placeable item held — smart action (attack / tool use / consume)
                        _handle_smart_action_v2(
                            _is_consumable,
                            _has_tool,
                            _best_tool_damage,
                            _HOTBAR_OFFSET,
                        )
            elif event.button == 3 and (config.show_inventory or config.open_chest_uid is not None):               
                if config.drag_item is not None:
                    # Cancel any active drag (chest-side or player-side)
                    from rendering.chest import _cancel_drag as _cd
                    _cd()
                    if config.drag_item is not None:
                        config.player_inventory[config.drag_slot] = config.drag_item
                        config.drag_slot = None
                        config.drag_item = None
                elif config.show_inventory:
                    from rendering.inventory import slot_at, _ITEM_SLOT_TYPES, _load_item_names
                    _load_item_names()
                    mx, my = event.pos
                    mods = pygame.key.get_mods()
                    idx = slot_at(mx, my, state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"])
                    if idx is not None and config.player_inventory[idx] is not None:
                        item    = config.player_inventory[idx]
                        item_id = item[0]
                        # Slot-type → equip inventory index (ring uses slot 38 primary, 39 fallback)
                        _EQUIP_IDX = {
                            "head": 36, "chest": 37, "ring": 38, "pants": 40,
                            "shoes": 41, "arms": 42, "necklace": 43, "back": 44,
                            "shield": 45, "shoulders": 46, "hands": 47
                        }
                        if idx >= 36:
                            # Already equipped → unequip to first free bag slot
                            target = next(
                                (i for i in range(27) if config.player_inventory[i] is None),
                                None,
                            )
                            if target is not None:
                                config.player_inventory[target] = item
                                config.player_inventory[idx]    = None
                                config.state_outbox.put({"type": "inv_swap",
                                                         "slot_a": idx, "slot_b": target})
                        else:
                            slot_type  = _ITEM_SLOT_TYPES.get(item_id)
                            equip_idx  = _EQUIP_IDX.get(slot_type) if slot_type else None
                            # For rings, prefer the empty ring slot (38→39 fallback)
                            if slot_type == "ring" and equip_idx is not None:
                                if (config.player_inventory[38] is not None
                                        and config.player_inventory[39] is None):
                                    equip_idx = 39
                            if equip_idx is not None:
                                # Quick-equip: swap bag slot ↔ equip slot
                                existing = config.player_inventory[equip_idx]
                                config.player_inventory[equip_idx] = item
                                config.player_inventory[idx]       = existing
                                config.state_outbox.put({"type": "inv_swap",
                                                         "slot_a": idx, "slot_b": equip_idx})
                            else:
                                pass  # not equippable and no shop sell
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and config.drag_item is not None:
                from rendering.inventory import slot_at, can_drop_in_slot
                mx, my = event.pos
                ww, wh = state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]

                # ── Chest-side drag released ──────────────────────────────
                if config.chest_drag_slot is not None:
                    # ── Chest-side drag released ─────────────────────────────
                    from rendering.chest import chest_bag_slot_at as _cba, chest_slot_at as _csa
                    from rendering.inventory import get_item_max_stack, is_item_stackable
                    target = _cba(mx, my, ww, wh)  # drop onto bag section
                    if target is not None and can_drop_in_slot(config.drag_item[0], target):
                        existing  = config.player_inventory[target]
                        drag_id   = config.drag_item[0]
                        obj = config.placed_objects.get(config.open_chest_uid)
                        if obj is not None:
                            ci = obj.setdefault("chest_inv", [None] * 27)
                            while len(ci) < 27:
                                ci.append(None)
                        merge_dest = None
                        if (existing is not None and existing[0] == drag_id
                                and is_item_stackable(drag_id)):
                            max_stk  = get_item_max_stack(drag_id)
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
                        config.state_outbox.put({
                            "type":        "chest_swap",
                            "uid":         config.open_chest_uid,
                            "chest_slot":  config.chest_drag_slot,
                            "player_slot": target,
                            **({"merge_dest": merge_dest} if merge_dest else {}),
                        })
                    else:
                        # Also try chest→chest slot swap
                        cs2 = _csa(mx, my, ww, wh)
                        if cs2 is not None and cs2 != config.chest_drag_slot:
                            obj = config.placed_objects.get(config.open_chest_uid)
                            if obj is not None:
                                ci = obj.setdefault("chest_inv", [None] * 27)
                                while len(ci) < 27:
                                    ci.append(None)
                                ci[cs2], ci[config.chest_drag_slot] = config.drag_item, ci[cs2]
                        else:
                            # No valid target — restore to chest
                            obj = config.placed_objects.get(config.open_chest_uid)
                            if obj is not None:
                                ci = obj.setdefault("chest_inv", [None] * 27)
                                while len(ci) < 27:
                                    ci.append(None)
                                ci[config.chest_drag_slot] = config.drag_item
                    config.chest_drag_slot = None
                    config.drag_item       = None

                # ── Player-side drag released while chest is open ─────────
                elif config.open_chest_uid is not None:
                    from rendering.chest import chest_slot_at as _csa2, chest_bag_slot_at as _cba2
                    cs = _csa2(mx, my, ww, wh)
                    if cs is not None:
                        # Drop onto chest slot
                        from rendering.inventory import get_item_max_stack, is_item_stackable
                        obj = config.placed_objects.get(config.open_chest_uid)
                        if obj is not None:
                            ci = obj.setdefault("chest_inv", [None] * 27)
                            while len(ci) < 27:
                                ci.append(None)
                            existing  = ci[cs]
                            drag_id   = config.drag_item[0]
                            merge_dest = None
                            if (existing is not None and existing[0] == drag_id
                                    and is_item_stackable(drag_id)):
                                max_stk  = get_item_max_stack(drag_id)
                                combined = existing[1] + config.drag_item[1]
                                if combined <= max_stk:
                                    ci[cs]                               = [drag_id, combined]
                                    config.player_inventory[config.drag_slot] = None
                                else:
                                    ci[cs]                               = [drag_id, max_stk]
                                    config.player_inventory[config.drag_slot] = [drag_id, combined - max_stk]
                                merge_dest = "chest"
                            else:
                                ci[cs] = config.drag_item
                                config.player_inventory[config.drag_slot] = existing
                            config.state_outbox.put({
                                "type":        "chest_swap",
                                "uid":         config.open_chest_uid,
                                "chest_slot":  cs,
                                "player_slot": config.drag_slot,
                                **({"merge_dest": merge_dest} if merge_dest else {}),
                            })
                        else:
                            config.player_inventory[config.drag_slot] = config.drag_item
                        config.drag_slot = None
                        config.drag_item = None
                    else:
                        # Check bag→bag swap within the panel
                        bs = _cba2(mx, my, ww, wh)
                        if bs is not None:
                            # Reuse normal inv swap — set target and fall through below
                            pass  # handled by the normal inv swap block below
                        else:
                            # Outside panel — return to source
                            config.player_inventory[config.drag_slot] = config.drag_item
                            config.drag_slot = None
                            config.drag_item = None

                # Normal player→player inventory swap (runs only if drag wasn't consumed above)
                if config.drag_item is not None:
                    if config.open_chest_uid is not None:
                        from rendering.chest import chest_bag_slot_at as _cba3
                        target = _cba3(mx, my, ww, wh)
                    else:
                        target = slot_at(mx, my, ww, wh)
                    if target is not None:
                        drag_id  = config.drag_item[0]
                        existing = config.player_inventory[target]
                        # Check dragged item fits in target slot
                        drag_ok = can_drop_in_slot(drag_id, target)
                        # If swapping, check existing item fits back in source slot
                        swap_ok = (existing is None or
                                   can_drop_in_slot(existing[0], config.drag_slot))
                        if drag_ok and swap_ok:
                            if existing is None:
                                config.player_inventory[target] = config.drag_item
                            elif existing[0] == drag_id:
                                # Same item — merge stacks up to max_stack
                                from rendering.inventory import get_item_max_stack, is_item_stackable
                                if is_item_stackable(drag_id):
                                    max_stk  = get_item_max_stack(drag_id)
                                    combined = existing[1] + config.drag_item[1]
                                    if combined <= max_stk:
                                        # Full merge — source slot becomes empty
                                        config.player_inventory[target]           = [drag_id, combined]
                                        config.player_inventory[config.drag_slot] = None
                                    else:
                                        # Partial merge — fill target, leave remainder in source
                                        config.player_inventory[target]           = [drag_id, max_stk]
                                        config.player_inventory[config.drag_slot] = [drag_id, combined - max_stk]
                                else:
                                    # Non-stackable same item type — swap
                                    config.player_inventory[config.drag_slot] = existing
                                    config.player_inventory[target]           = config.drag_item
                            else:
                                # Different items — swap
                                config.player_inventory[config.drag_slot] = existing
                                config.player_inventory[target]           = config.drag_item
                            # Tell the server about the new arrangement
                            config.state_outbox.put({"type": "inv_swap",
                                                     "slot_a": config.drag_slot,
                                                     "slot_b": target})
                        else:
                            # Invalid drop — return item to source
                            config.player_inventory[config.drag_slot] = config.drag_item
                    else:
                        # Dropped outside any slot – return to source
                        config.player_inventory[config.drag_slot] = config.drag_item
                    config.drag_slot = None
                    config.drag_item = None
        elif event.type == pygame.VIDEORESIZE:
            state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"] = event.w, event.h
            state["screen"] = pygame.display.set_mode((state["WINDOW_WIDTH"], state["WINDOW_HEIGHT"]), pygame.RESIZABLE | pygame.DOUBLEBUF)
            state["camera_x"] = state["player_data"]["pos"][0] * TILE_SIZE
            state["camera_y"] = state["player_data"]["pos"][1] * TILE_SIZE
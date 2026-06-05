from server.shared_lock import players_lock, world_items_lock, clients_lock
from server.game_state.progression_data import STAT_UPGRADES
from server.game_state.placed_objects import (
    place_object as _place_object,
    remove_object as _remove_object,
    toggle_door as _toggle_door,
    use_bed as _use_bed,
    chest_swap as _chest_swap,
)
from server.game_state.game_sync import mark_inventory_dirty, set_player_sleeping as _set_player_sleeping
from server.item_data import drain_durability, get_effective_health_max, get_item, get_sell_price, is_valid_equip_placement
from server.game_state.crafting import handle_craft

# Injected clients reference for chat broadcast
_clients: dict | None = None
_debug_last_log: dict[str, float] = {}


def _debug_log(key: str, message: str, interval: float = 1.0) -> None:
    import time as _time

    now = _time.time()
    last = _debug_last_log.get(key, 0.0)
    if now - last < interval:
        return
    _debug_last_log[key] = now
    print(message)


def _is_slot(value, limit: int = 48) -> bool:
    return isinstance(value, int) and 0 <= value < limit


def _is_vec2(value) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, (int, float)) for v in value)
    )


def _safe_stations(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value[:16] if isinstance(v, str) and 0 < len(v) <= 64]


def set_chat_refs(refs: dict) -> None:
    global _clients
    _clients = refs.get("clients")


def kick_player(player_id: str) -> None:
    """Close a player's TCP sockets to force them offline (e.g. after a ban)."""
    if _clients is None:
        return
    import socket as _socket
    with clients_lock:
        gs_sock = _clients.get("game_state", {}).get(player_id)
        w_sock  = _clients.get("world",      {}).get(player_id)
    for sock in filter(None, [gs_sock, w_sock]):
        try:
            sock.shutdown(_socket.SHUT_RDWR)
            sock.close()
        except Exception:
            pass


def dispatch_message(data, player_id: str, players: dict, give_item, world_items: dict) -> bool:
    if not isinstance(data, dict):
        print(f"[DISPATCH] non-dict message from {player_id}: {type(data).__name__}")
        return False
    msg_type = data.get("type")
    if not isinstance(msg_type, str):
        print(f"[DISPATCH] invalid type from {player_id}: {msg_type!r}")
        return False
    handler = _HANDLERS.get(msg_type)
    if handler is None:
        print(f"[DISPATCH] unknown type={msg_type!r} from {player_id}")
        return False
    print(f"[DISPATCH] {player_id} -> {msg_type}")
    handler(data, player_id, players, give_item, world_items)
    return True


def _handle_inv_swap(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    a, b = data.get("slot_a"), data.get("slot_b")
    if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < 48 and 0 <= b < 48 and a != b):
        return
    with players_lock:
        if player_id in players:
            inv = players[player_id]["inventory"]
            item_a = inv[a]
            item_b = inv[b]
            if (item_a is not None and item_b is not None
                    and item_a[0] == item_b[0]
                    and get_item(item_a[0]).get("stackable", False)):
                max_stk = get_item(item_a[0]).get("max_stack", 64)
                combined = item_a[1] + item_b[1]
                if combined <= max_stk:
                    inv[b] = [item_a[0], combined]
                    inv[a] = None
                else:
                    inv[b] = [item_a[0], max_stk]
                    inv[a] = [item_a[0], combined - max_stk]
            else:
                a_ok = item_b is None or is_valid_equip_placement(item_b[0], a)
                b_ok = item_a is None or is_valid_equip_placement(item_a[0], b)
                if a_ok and b_ok:
                    inv[a], inv[b] = inv[b], inv[a]
    mark_inventory_dirty(player_id)


def _handle_craft(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    recipe_id = data.get("recipe_id")
    if recipe_id is not None and not isinstance(recipe_id, (str, int)):
        return
    stations = _safe_stations(data.get("nearby_stations"))
    _debug_log(
        f"craft:{player_id}",
        f"[STATE DEBUG] craft pid={player_id} recipe={recipe_id} nearby_stations={stations}",
    )
    if handle_craft(player_id, recipe_id, players, stations):
        mark_inventory_dirty(player_id)


def _handle_sell(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    slot_idx = data.get("slot")
    if not (isinstance(slot_idx, int) and 0 <= slot_idx < 48):
        return
    with players_lock:
        if player_id in players:
            inv = players[player_id]["inventory"]
            if slot_idx < len(inv) and inv[slot_idx] is not None:
                price = get_sell_price(inv[slot_idx])
                inv[slot_idx] = None
                if price > 0:
                    players[player_id]["coins"] = players[player_id].get("coins", 0) + price
                    print(f"[SELL] {player_id} slot {slot_idx} -> {price}c")
    mark_inventory_dirty(player_id)


def _handle_spend_stat(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    stat = data.get("stat")
    upgrade = STAT_UPGRADES.get(stat)
    if upgrade is None:
        return
    with players_lock:
        if player_id in players:
            player = players[player_id]
            if player.get("stat_points", 0) > 0:
                key = upgrade["player_key"]
                amount = float(upgrade["amount"])
                player[key] = round(player.get(key, 0.0) + amount, 4)
                player["stat_points"] -= 1
                if stat == "health_max":
                    player["health"] = min(player.get("health", 0) + amount, player["health_max"])
                print(f"[STAT] {player_id} upgraded {stat} -> {player[key]} ({player['stat_points']} pts left)")


def _handle_cactus_hit(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    with players_lock:
        if player_id in players:
            players[player_id]["health"] = max(0.0, players[player_id]["health"] - 2.0)


def _handle_place_object(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    obj_type = data.get("obj_type", "")
    pos = data.get("pos", [0, 0])
    if not (isinstance(obj_type, str) and obj_type and _is_vec2(pos)):
        return
    with players_lock:
        if player_id in players:
            ok, _result = _place_object(player_id, obj_type, [int(pos[0]), int(pos[1])], players[player_id]["inventory"])
            print(
                f"[STATE DEBUG] place_object pid={player_id} type={obj_type} "
                f"pos=({int(pos[0])},{int(pos[1])}) ok={ok} result={_result}"
            )
            if ok:
                mark_inventory_dirty(player_id)


def _handle_remove_object(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    uid = data.get("uid", "")
    if not isinstance(uid, str):
        return
    with players_lock:
        if player_id in players:
            ok = _remove_object(uid, players[player_id]["inventory"], player_id)
            print(f"[STATE DEBUG] remove_object pid={player_id} uid={uid} ok={ok}")
            if ok:
                mark_inventory_dirty(player_id)


def _handle_toggle_door(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    uid = data.get("uid", "")
    if isinstance(uid, str) and uid:
        _toggle_door(uid)


def _handle_use_bed(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    uid = data.get("uid", "")
    if not (isinstance(uid, str) and uid):
        return
    with players_lock:
        ok = _use_bed(uid, player_id, players)
    if ok:
        mark_inventory_dirty(player_id)
        _set_player_sleeping(player_id, True)  # no-op during daytime


def _handle_wake_up(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    _set_player_sleeping(player_id, False)


def _handle_chest_swap(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    uid = data.get("uid", "")
    chest_slot = data.get("chest_slot")
    player_slot = data.get("player_slot")
    merge_dest = data.get("merge_dest")
    if not (isinstance(uid, str) and uid
            and isinstance(chest_slot, int) and 0 <= chest_slot < 27
            and _is_slot(player_slot, 48)):
        return
    if merge_dest is not None and merge_dest not in ("player", "chest"):
        return
    ok = False
    with players_lock:
        if player_id in players:
            player = players[player_id]
            player_pos = list(player.get("pos", [0, 0]))
            ok = _chest_swap(uid, chest_slot, player["inventory"], player_slot, player_pos, merge_dest)
    if ok:
        mark_inventory_dirty(player_id)


def _handle_combine_parts(data, player_id: str, players: dict, give_item, world_items: dict) -> None:
    mold_idx = data.get("mold_slot")
    primary_idx = data.get("primary_slot")
    handle_idx = data.get("handle_slot")
    binding_idx = data.get("binding_slot")
    nearby = _safe_stations(data.get("nearby_stations"))
    if all(_is_slot(x, 48) for x in (mold_idx, primary_idx, handle_idx, binding_idx)):
        from server.game_state.part_combiner import combine_parts as _combine
        ok, reason = _combine(player_id, mold_idx, primary_idx, handle_idx, binding_idx, players, nearby)
        if ok:
            mark_inventory_dirty(player_id)
        elif reason:
            print(f"[COMBINER] {player_id} failed: {reason}")
        return
    uid = data.get("uid")
    if not isinstance(uid, str):
        return
    with players_lock:
        player_pos = list(players.get(player_id, {}).get("pos", [0, 0]))
    with world_items_lock:
        world_item = world_items.get(uid)
        if world_item is None:
            return
        item_x, item_y = world_item["pos"]
        dx = player_pos[0] - item_x
        dy = player_pos[1] - item_y
        if dx * dx + dy * dy > 4.0:
            return
        world_items.pop(uid)
        with players_lock:
            if player_id in players:
                give_item(players[player_id], world_item["item_id"], world_item["qty"])
                mark_inventory_dirty(player_id)


def _handle_embed_gem(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    item_slot = data.get("item_slot")
    gem_slot = data.get("gem_slot")
    nearby = _safe_stations(data.get("nearby_stations"))
    if not (_is_slot(item_slot, 48) and _is_slot(gem_slot, 48)):
        return
    from server.game_state.embedder import embed_gem as _embed
    ok, reason = _embed(player_id, item_slot, gem_slot, players, nearby)
    if ok:
        mark_inventory_dirty(player_id)
    elif reason:
        print(f"[EMBEDDER] {player_id} failed: {reason}")


def _handle_repair_item(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    item_slot = data.get("item_slot")
    nearby = _safe_stations(data.get("nearby_stations"))
    if not _is_slot(item_slot, 48):
        return
    from server.game_state.repair import repair_item as _repair
    ok, reason = _repair(player_id, item_slot, players, nearby)
    if ok:
        mark_inventory_dirty(player_id)
    elif reason:
        print(f"[REPAIR] {player_id} failed: {reason}")


def _handle_use_item(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    slot_idx = data.get("slot")
    if not _is_slot(slot_idx, 48):
        return
    with players_lock:
        if player_id in players:
            player = players[player_id]
            inv = player["inventory"]
            slot = inv[slot_idx] if slot_idx < len(inv) else None
            if slot is not None:
                item_def = get_item(slot[0])
                if not item_def.get("consumable", False):
                    return
                heal = item_def.get("heal", 0)
                stamina_restore = item_def.get("stamina_restore", 0)
                if heal <= 0 and stamina_restore <= 0:
                    return
                if heal > 0:
                    player["health"] = min(player.get("health", 100) + heal, get_effective_health_max(player))
                if stamina_restore > 0:
                    player["stamina"] = min(player.get("stamina", 0) + stamina_restore, player.get("stamina_max", 100.0))
                if slot[1] > 1:
                    inv[slot_idx] = [slot[0], slot[1] - 1]
                else:
                    inv[slot_idx] = None
                mark_inventory_dirty(player_id)


def _handle_gather(data, player_id: str, players: dict, give_item, _world_items: dict) -> None:
    node_id = data.get("node_id")
    if not (isinstance(node_id, str) and node_id):
        return

    # World-item pickup routed through the gather message (avoids a separate broken path)
    if node_id.startswith("item:"):
        uid = node_id[5:]
        if uid:
            from server.game_state.world_items import handle_player_pickup
            handle_player_pickup(player_id, uid)
        return

    from server.world.resource_nodes import NODE_TYPES, damage_node, get_planted_node, tool_mining_damage, tool_satisfies

    if node_id.startswith("planted:"):
        pnode = get_planted_node(node_id)
        if pnode is None:
            return

        node_type = pnode["type"]
        node_def = NODE_TYPES.get(node_type)
        if node_def is None:
            return

        nx_world = pnode["wx"] + 0.5
        ny_world = pnode["wy"] + 0.5
        with players_lock:
            if player_id not in players:
                return
            ppos = players[player_id].get("pos", [0.0, 0.0])
        dist_sq = (ppos[0] - nx_world) ** 2 + (ppos[1] - ny_world) ** 2
        if dist_sq > 9.0:
            return

        with players_lock:
            if player_id not in players:
                return
            inv = list(players[player_id]["inventory"])
            hotbar_slot = players[player_id].get("hotbar_slot", 0)
        hotbar_idx = 27 + hotbar_slot
        hotbar_item = inv[hotbar_idx] if 0 <= hotbar_idx < len(inv) else None
        tool_type = node_def.get("tool")
        if tool_type is not None and not tool_satisfies(hotbar_item, tool_type):
            return

        tool_damage = tool_mining_damage(hotbar_item)
        loot = damage_node(node_id, node_def, tool_damage)
        if loot is None:
            return

        with players_lock:
            if player_id in players:
                if loot:
                    for item_id, qty in loot:
                        give_item(players[player_id], item_id, qty)
                drain_durability(players[player_id]["inventory"], hotbar_idx)
        mark_inventory_dirty(player_id)
        return

    from server.world.dyn_chunk_gen import CHUNK_SIZE, chunk_nodes_cache, chunk_nodes_lock

    try:
        parts = node_id.split(":")
        ncx, ncy, nidx = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return

    node_def_entry = None
    with chunk_nodes_lock:
        nodes_list = chunk_nodes_cache.get((ncx, ncy), [])
    if 0 <= nidx < len(nodes_list) and nodes_list[nidx] is not None and nodes_list[nidx]["id"] == node_id:
        node_def_entry = nodes_list[nidx]

    if node_def_entry is None:
        print(f"[GATHER] node_def_entry None for {node_id!r}  cache_len={len(nodes_list)}")
        return

    node_type = node_def_entry["type"]
    node_def = NODE_TYPES.get(node_type)
    if node_def is None:
        print(f"[GATHER] unknown node_type={node_type!r}")
        return

    nx_world = ncx * CHUNK_SIZE + node_def_entry["lx"] + 0.5
    ny_world = ncy * CHUNK_SIZE + node_def_entry["ly"] + 0.5
    with players_lock:
        if player_id not in players:
            return
        ppos = players[player_id].get("pos", [0.0, 0.0])
    dist_sq = (ppos[0] - nx_world) ** 2 + (ppos[1] - ny_world) ** 2
    if dist_sq > 9.0:
        print(f"[GATHER] too far: player={ppos} node=({nx_world},{ny_world}) dsq={dist_sq:.1f}")
        return

    with players_lock:
        if player_id not in players:
            return
        inv = list(players[player_id]["inventory"])
        hotbar_slot = players[player_id].get("hotbar_slot", 0)
    hotbar_idx = 27 + hotbar_slot
    hotbar_item = inv[hotbar_idx] if 0 <= hotbar_idx < len(inv) else None
    tool_type = node_def.get("tool")
    if tool_type is not None and not tool_satisfies(hotbar_item, tool_type):
        print(f"[GATHER] tool not satisfied: need={tool_type!r} hotbar={hotbar_item!r}")
        return

    tool_damage = tool_mining_damage(hotbar_item)
    loot = damage_node(node_id, node_def, tool_damage)
    if loot is None:
        print(f"[GATHER] loot=None for {node_id!r} (already depleted?)")
        # Re-broadcast depletion so any client still showing this node removes it
        from server.world.resource_nodes import _record_update as _rebroadcast_depletion
        _rebroadcast_depletion(node_id, depleted=True)
        return

    with players_lock:
        if player_id in players:
            if loot:
                print(f"[GATHER] giving loot={loot!r} to {player_id} from {node_id!r}")
                for item_id, qty in loot:
                    give_item(players[player_id], item_id, qty)
            drain_durability(players[player_id]["inventory"], hotbar_idx)
    mark_inventory_dirty(player_id)


def _broadcast_chat(packet: dict) -> None:
    """Send a chat packet to every connected game-state client."""
    if _clients is None:
        return
    from server.network.net_utils import send_json as _send_json
    with clients_lock:
        socks = list(_clients.get("game_state", {}).values())
    for sock in socks:
        try:
            _send_json(sock, packet)
        except Exception:
            pass


# Public alias so server.py can pass it to commands.set_server_refs
broadcast_chat = _broadcast_chat


def send_to_player(player_id: str, packet: dict) -> None:
    """Send a packet to a single connected game-state client."""
    if _clients is None:
        return
    from server.network.net_utils import send_json as _send_json
    with clients_lock:
        sock = _clients.get("game_state", {}).get(player_id)
    if sock:
        try:
            _send_json(sock, packet)
        except Exception:
            pass


def _handle_chat(data, player_id: str, players: dict, give_item, _world_items: dict) -> None:
    text = data.get("text", "").strip()
    if not text or len(text) > 256:
        return

    if text.startswith("/"):
        # Process command — replies go only to the sender
        from server.network.commands import process_command
        replies = process_command(text, player_id, players, give_item)
        if _clients is None:
            return
        from server.network.net_utils import send_json as _send_json
        with clients_lock:
            sock = _clients.get("game_state", {}).get(player_id)
        if sock:
            for pkt in replies:
                try:
                    _send_json(sock, pkt)
                except Exception:
                    pass
        # Also broadcast the command text so other players see what was typed
        _broadcast_chat({"type": "chat", "sender": player_id, "text": text})
        return

    # Normal message — broadcast to all
    print(f"[CHAT] {player_id}: {text}")
    _broadcast_chat({"type": "chat", "sender": player_id, "text": text})


def _handle_give_item(data, player_id: str, players: dict, give_item, _world_items: dict) -> None:
    """Creative-mode item give (called when player clicks an item in the creative tab)."""
    with players_lock:
        if player_id not in players:
            return
        if not players[player_id].get("creative", False):
            return
    item_id = data.get("item_id")
    qty     = data.get("qty", 1)
    if not (isinstance(item_id, int) and isinstance(qty, int) and qty > 0):
        return
    from server.item_data import get_item as _get_item
    if not _get_item(item_id):
        return
    with players_lock:
        if player_id in players:
            give_item(players[player_id], item_id, min(qty, 999))
    mark_inventory_dirty(player_id)


def _handle_shop_buy(data, player_id: str, players: dict, give_item, _world_items: dict) -> None:
    npc_type  = data.get("npc_type", "")
    shop_slot = data.get("shop_slot")
    if not (isinstance(npc_type, str) and 0 < len(npc_type) <= 64 and isinstance(shop_slot, int) and shop_slot >= 0):
        return
    from server.world.npc_shops import handle_shop_buy as _shop_buy, get_shop as _get_shop
    with players_lock:
        ok, _msg = _shop_buy(player_id, npc_type, shop_slot, players, give_item)
    if ok:
        mark_inventory_dirty(player_id)
        send_to_player(player_id, {"type": "shop_update", "items": _get_shop(npc_type)})


def _handle_shop_sell(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    inv_slot = data.get("slot")
    npc_type = data.get("npc_type", "merchant")
    if not _is_slot(inv_slot, 48):
        return
    if not isinstance(npc_type, str) or not npc_type:
        npc_type = "merchant"
    from server.world.npc_shops import handle_shop_sell as _shop_sell, get_shop as _get_shop
    with players_lock:
        ok, _msg = _shop_sell(player_id, inv_slot, npc_type, players)
    if ok:
        mark_inventory_dirty(player_id)
        send_to_player(player_id, {"type": "shop_update", "items": _get_shop(npc_type)})


def _handle_pickup(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    """Explicit item pickup triggered by the client (E key / click near item)."""
    uid = data.get("uid")
    if not isinstance(uid, str) or not uid:
        return
    from server.game_state.world_items import handle_player_pickup
    handle_player_pickup(player_id, uid)


def _handle_update_appearance(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    """Store cosmetic appearance chosen in the character creator."""
    appearance = data.get("appearance")
    if not isinstance(appearance, dict):
        return
    _ALLOWED_KEYS = {"body", "hair_style", "hair_color", "skin_tint",
                     "back_ext", "back_ext_color", "aura"}
    safe = {
        k: v
        for k, v in appearance.items()
        if k in _ALLOWED_KEYS and isinstance(v, (str, int, float, bool, type(None)))
    }
    with players_lock:
        if player_id in players:
            players[player_id]["appearance"] = safe
    mark_inventory_dirty(player_id)


def _handle_fire_spell(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    """Spawn a wand projectile in the direction (dx, dy) sent by the client.

    Validates that the player has a wand with a 'projectile' field equipped
    in their active hotbar slot before spawning anything.
    """
    dx = data.get("dx")
    dy = data.get("dy")
    if not (isinstance(dx, (int, float)) and isinstance(dy, (int, float))):
        return
    dx, dy = float(dx), float(dy)
    if dx * dx + dy * dy < 0.001:
        return

    from server.network.projectiles import fire_projectile, can_fire
    from server.item_data import (
        drain_active_hotbar_durability,
        get_equip_bonuses,
        get_hotbar_bonus,
        get_item as _get_item,
    )

    with players_lock:
        player = players.get(player_id)
        if player is None:
            return
        if not can_fire(player_id):
            return
        hotbar_slot = player.get("hotbar_slot", 0)
        if not isinstance(hotbar_slot, int) or not 0 <= hotbar_slot <= 8:
            return
        inv         = player.get("inventory", [])
        weapon_idx  = 27 + hotbar_slot
        weapon      = inv[weapon_idx] if weapon_idx < len(inv) else None
        if weapon is None:
            return
        item_def = _get_item(weapon[0])
        element  = item_def.get("projectile")
        if not element:
            return   # not a wand
        # Damage = base attack_power of wand + equipped bonuses
        atk = (float(player.get("attack_power", 10.0))
               + get_equip_bonuses(inv)["attack_power"]
               + get_hotbar_bonus(inv, hotbar_slot)["attack_power"])
        pos = player.get("pos", [0.0, 0.0])
        if not _is_vec2(pos):
            return
        mag = (dx * dx + dy * dy) ** 0.5
        if mag < 0.001:
            return
        nx = dx / mag
        ny = dy / mag
        # Spawn slightly in front of the caster's centre so the projectile reads from the hand.
        ox  = float(pos[0]) + 0.5 + nx * 0.22
        oy  = float(pos[1]) + 0.5 + ny * 0.22

    if fire_projectile(player_id, ox, oy, dx, dy, element, atk):
        with players_lock:
            player = players.get(player_id)
            if player is not None:
                drain_active_hotbar_durability(player)
        mark_inventory_dirty(player_id)


def _handle_forget_chunks(data, player_id: str, players: dict, _give_item, _world_items: dict) -> None:
    """Client is evicting distant chunk data; allow those chunks to be re-sent on next visit."""
    chunks = data.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        return
    # Clamp to a reasonable maximum to prevent abuse
    if len(chunks) > 512:
        return
    from server.game_state.sync import forget_player_chunks as _forget
    safe_chunks = [
        [int(c[0]), int(c[1])]
        for c in chunks
        if isinstance(c, (list, tuple)) and len(c) == 2
        and isinstance(c[0], int) and isinstance(c[1], int)
    ]
    if safe_chunks:
        _forget(player_id, safe_chunks)


_HANDLERS = {
    "inv_swap": _handle_inv_swap,
    "craft": _handle_craft,
    "sell": _handle_sell,
    "spend_stat": _handle_spend_stat,
    "gather": _handle_gather,
    "cactus_hit": _handle_cactus_hit,
    "place_object": _handle_place_object,
    "remove_object": _handle_remove_object,
    "toggle_door": _handle_toggle_door,
    "use_bed": _handle_use_bed,
    "wake_up": _handle_wake_up,
    "chest_swap": _handle_chest_swap,
    "combine_parts": _handle_combine_parts,
    "embed_gem": _handle_embed_gem,
    "repair_item": _handle_repair_item,
    "use_item": _handle_use_item,
    "chat": _handle_chat,
    "give_item": _handle_give_item,
    "shop_buy": _handle_shop_buy,
    "shop_sell": _handle_shop_sell,
    "update_appearance": _handle_update_appearance,
    "fire_spell": _handle_fire_spell,
    "forget_chunks": _handle_forget_chunks,
    "pickup": _handle_pickup,
}

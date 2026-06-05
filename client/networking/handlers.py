import time, struct
import socket
import threading, orjson
import config
from input.resource_node_data import NODE_MAX_HP
from utils.logging import log_error, log_info
from .sockets import connect_with_retry
from .protocols import identify_socket, recv_json, send_json
from state.player import player_data
from state.remote_mob import RemoteMob
from state.remote_player import RemotePlayer

# Registry of every node's base data, used to re-add nodes when they respawn.
# Never shrinks; depleted nodes are removed from config.world_nodes but stay here.
_node_base_cache: dict = {}
_debug_last_log: dict[str, float] = {}


def _debug_log(key: str, message: str, interval: float = 2.0) -> None:
    if not getattr(config, "DEBUG_MODE", False):
        return
    now = time.time()
    last = _debug_last_log.get(key, 0.0)
    if now - last < interval:
        return
    _debug_last_log[key] = now
    log_info(message)

def handle_world(HOST, PORT_WORLD, chunk_queue, player_id):
    _my_session = config.session_id
    sock = connect_with_retry(HOST, PORT_WORLD)
    if not sock:
        return
    identify_socket(sock, "world", player_id, config.session_token)
    sock.settimeout(0.1)  # avoid blocking forever
    print("[WORLD] Connected and handshake sent.")

    try:
        while config.session_id == _my_session:
            try:
                data = recv_json(sock)
                if data and data.get("type") == "world_chunks":
                    chunks    = data.get("data", {})
                    node_data = data.get("node_data", {})
                    for chunk_key_str, tiles in chunks.items():
                        cx, cy = map(int, chunk_key_str.strip("()").split(","))
                        converted_tiles = {
                            tuple(map(int, key.split(","))): val
                            for key, val in tiles.items()
                        }
                        chunk_queue.put(((cx, cy), converted_tiles))
                    # Populate world_nodes with static node definitions
                    for chunk_key_str, nodes_list in node_data.items():
                        cx, cy = map(int, chunk_key_str.strip("()").split(","))
                        _new_nodes = dict(config.world_nodes)
                        for node in nodes_list:
                            nid = node["id"]
                            ntype = node["type"]
                            wx = cx * 16 + node["lx"]
                            wy = cy * 16 + node["ly"]
                            max_hp = node.get("max_hp") or NODE_MAX_HP.get(ntype, 1)
                            if nid not in _new_nodes:
                                _node_base_cache[nid] = {"type": ntype, "wx": wx, "wy": wy, "max_hp": max_hp}
                                _new_nodes[nid] = {
                                    "type": ntype, "wx": wx, "wy": wy,
                                    "max_hp": max_hp, "hits": 0,
                                }
                        config.set_world_nodes(_new_nodes)

            except socket.timeout:
                continue  # allow frequent checks
            except Exception as e:
                log_error(f"[WORLD RECV ERROR] {e}")
                break

            time.sleep(1 / 60)
    finally:
        try:
            sock.close()
        except Exception:
            pass

def handle_state(HOST, PORT_STATE, player_id):
    _my_session = config.session_id
    sock = connect_with_retry(HOST, PORT_STATE)
    if not sock:
        return
    identify_socket(sock, "game_state", player_id, config.session_token)
    log_info("[STATE] Connected and handshake sent.")
    sock.settimeout(0.1)

    try:
        while config.session_id == _my_session:
            try:
                data = recv_json(sock)
                if data and data.get("type") == "game_state":
                    _debug_log(
                        "state_recv",
                        (
                            f"[CLIENT STATE DEBUG] recv "
                            f"players={len(data.get('players', {}))} "
                            f"placed={len(data.get('placed_objects', []))} "
                            f"items={len(data.get('world_items', []))} "
                            f"mobs={len(config.mob_entities)} "
                            f"npcs={len(data.get('npcs', []))} "
                            f"time={data.get('world_time', config.world_time):.2f} "
                            f"weather={data.get('weather', config.weather)}"
                        ),
                    )
                    self_data = data.get("self", {})
                    # Store velocity knockback — applied smoothly in the game loop over 0.25 s
                    kb = self_data.get("knockback_vel")
                    if kb:
                        player_data["knockback_vel"] = list(kb)
                        config.hit_flash_timer = 0.2
                        _kbpos = player_data.get("pos", [0.0, 0.0])
                        from rendering.particles import emit_hit
                        emit_hit(_kbpos[0], _kbpos[1])
                    _old_level = config.player_level
                    config.player_health          = self_data.get("health",          config.player_health)
                    config.player_health_max      = self_data.get("health_max",      config.player_health_max)
                    config.player_stamina_max     = self_data.get("stamina_max",     config.player_stamina_max)
                    config.player_attack_power    = self_data.get("attack_power",    config.player_attack_power)
                    config.player_speed_bonus     = self_data.get("speed_bonus",     config.player_speed_bonus)
                    config.player_level           = self_data.get("level",           config.player_level)
                    config.player_exp             = self_data.get("exp",             config.player_exp)
                    config.player_exp_next        = self_data.get("exp_next",        config.player_exp_next)
                    config.player_stat_points     = self_data.get("stat_points",     config.player_stat_points)
                    config.player_coins           = self_data.get("coins",           config.player_coins)
                    config.player_hp_regen        = self_data.get("hp_regen",        config.player_hp_regen)
                    config.player_sp_regen_bonus  = self_data.get("sp_regen_bonus",  config.player_sp_regen_bonus)
                    config.player_slow_timer      = self_data.get("slow_timer",      0.0)
                    config.player_dead            = self_data.get("dead",            False)
                    config.player_respawn_in      = self_data.get("respawn_in",      0.0)
                    config.player_defense         = self_data.get("defense",         0)
                    config.world_time             = data.get("world_time",           config.world_time)
                    config.sleeping               = self_data.get("sleeping",          False)
                    config.weather                = data.get("weather",               "clear")
                    config.poison_timer           = self_data.get("poison_timer",      0.0)
                    config.burn_timer             = self_data.get("burn_timer",        0.0)
                    config.player_creative        = self_data.get("creative",        False)
                    # Sync appearance from server (e.g. after server restarts and reloads save)
                    _srv_appearance = self_data.get("appearance")
                    if isinstance(_srv_appearance, dict) and _srv_appearance:
                        config.player_appearance.update(_srv_appearance)
                    # If creative was revoked and creative tab is open, fall back to bag
                    if not config.player_creative and config.inventory_tab == "creative":
                        config.inventory_tab = "bag"
                    # Level-up particle burst
                    if config.player_level > _old_level:
                        _lupos = player_data.get("pos", [0.0, 0.0])
                        from rendering.particles import emit_levelup
                        emit_levelup(_lupos[0], _lupos[1])
                    if "inventory" in self_data:
                        config.player_inventory = self_data["inventory"]
                    players_payload = data.get("players")
                    if players_payload is not None:
                        current_remote_ids = set()
                        for pid, pdata in players_payload.items():
                            current_remote_ids.add(pid)
                            if pid not in config.players_data:
                                config.players_data[pid] = RemotePlayer(list(pdata.get("pos", [0.0, 0.0])))
                            config.players_data[pid].health = pdata.get("health", 100)
                            equip = pdata.get("equip")
                            if equip is not None:
                                config.players_data[pid].equip_ids = {int(k): v for k, v in equip.items()}
                            config.players_data[pid].held_item_id = pdata.get("held_item")
                            appearance = pdata.get("appearance")
                            if isinstance(appearance, dict):
                                config.players_data[pid].appearance = appearance
                        for pid in [pid for pid in config.players_data if pid not in current_remote_ids]:
                            config.players_data.pop(pid, None)
                        if config.players_data:
                            _sample_pid, _sample_player = next(iter(config.players_data.items()))
                            _debug_log(
                                "state_remote_sample",
                                (
                                    f"[CLIENT STATE DEBUG] remote sample={_sample_pid} "
                                    f"body={_sample_player.appearance.get('body', 'missing')} "
                                    f"equip_slots={sorted(_sample_player.equip_ids.keys())}"
                                ),
                            )
                    wi_list = data.get("world_items")
                    if wi_list is not None:
                        new_wi = {item["uid"]: item for item in wi_list}
                        _ppos = player_data.get("pos", [0.0, 0.0])
                        for uid, item in config.world_items.items():
                            if uid not in new_wi:
                                ix, iy = item["pos"]
                                if (ix - _ppos[0]) ** 2 + (iy - _ppos[1]) ** 2 < 16.0:
                                    from rendering.particles import emit_pickup
                                    emit_pickup(ix, iy)
                        config.world_items = new_wi
                        # Mirror item drops as tool-less gather nodes so both the
                        # F-key and left-click paths pick them up via the proven
                        # gather message route ("item:<uid>" prefix).
                        _item_nodes = {
                            f"item:{uid}": {
                                "type": "item_drop",
                                # Store at item centre minus 0.5 so wx+0.5 == item centre
                                "wx": item["pos"][0] - 0.5,
                                "wy": item["pos"][1] - 0.5,
                                "hits": 0,
                                "max_hp": 1,
                            }
                            for uid, item in new_wi.items()
                        }
                        config.set_world_nodes({
                            k: v for k, v in config.world_nodes.items()
                            if not k.startswith("item:")
                        })
                        for node_id, node in _item_nodes.items():
                            config.upsert_world_node(node_id, node)
                    npcs_list = data.get("npcs")
                    if npcs_list is not None:
                        config.npcs = npcs_list
                    dungeons_list = data.get("dungeons")
                    if dungeons_list is not None:
                        config.dungeons = dungeons_list
                    placed_list = data.get("placed_objects")
                    if placed_list is not None:
                        new_placed = {obj["uid"]: obj for obj in placed_list}
                        if (config.open_chest_uid is not None
                                and time.time() < getattr(config, "chest_ui_hold_until", 0.0)):
                            current_open = config.placed_objects.get(config.open_chest_uid)
                            if current_open is not None and config.open_chest_uid in new_placed:
                                merged_open = dict(new_placed[config.open_chest_uid])
                                if "chest_inv" in current_open:
                                    merged_open["chest_inv"] = current_open["chest_inv"]
                                new_placed[config.open_chest_uid] = merged_open
                        config.set_placed_objects(new_placed)
                        _debug_log(
                            "state_placed_apply",
                            (
                                f"[CLIENT STATE DEBUG] applied placed={len(config.placed_objects)} "
                                f"solid_tiles={len(config.object_by_tile)} floor_tiles={len(config.floor_by_tile)}"
                            ),
                        )
                    proj_list = data.get("projectiles")
                    if proj_list is not None:
                        config.projectiles = proj_list
                    node_updates = data.get("node_updates")
                    if node_updates:
                        _new_nodes = dict(config.world_nodes)
                        for u in node_updates:
                            nid = u.get("node_id")
                            if not nid:
                                continue
                            if u.get("depleted", False):
                                # Node destroyed — remove it entirely
                                _new_nodes.pop(nid, None)
                            else:
                                # Node respawned — re-add from base cache
                                if nid not in _new_nodes and nid in _node_base_cache:
                                    _new_nodes[nid] = dict(_node_base_cache[nid], hits=0)
                        config.set_world_nodes(_new_nodes)
                    depleted_snapshot = data.get("depleted_snapshot")
                    if depleted_snapshot:
                        _new_nodes = dict(config.world_nodes)
                        for nid in depleted_snapshot:
                            _new_nodes.pop(nid, None)
                        config.set_world_nodes(_new_nodes)
                    planted_list = data.get("planted_nodes")
                    if planted_list is not None:
                        _new_nodes = dict(config.world_nodes)
                        reported_ids = {pn["node_id"] for pn in planted_list}
                        for pn in planted_list:
                            nid = pn["node_id"]
                            if nid not in _new_nodes:
                                ntype = pn["node_type"]
                                _new_nodes[nid] = {
                                    "type":    ntype,
                                    "wx":      pn["wx"],
                                    "wy":      pn["wy"],
                                    "max_hp":  pn.get("max_hp") or NODE_MAX_HP.get(ntype, 1),
                                    "depleted": False,
                                    "hits":    0,
                                }
                        # Remove planted nodes that are no longer active on the server
                        for nid in [k for k in _new_nodes if k.startswith("planted:") and k not in reported_ids]:
                            del _new_nodes[nid]
                        config.set_world_nodes(_new_nodes)
                elif data and data.get("type") == "shop_update":
                    config.shop_items = data.get("items", [])
                elif data and data.get("type") == "mob_sync":
                    if data.get("reset", False):
                        config.mob_entities.clear()
                    for mob in data.get("spawns", []):
                        mob_id = mob.get("id")
                        if mob_id is None:
                            continue
                        config.mob_entities[mob_id] = RemoteMob(mob)
                    for mob in data.get("updates", []):
                        mob_id = mob.get("id")
                        if mob_id is None:
                            continue
                        if mob_id not in config.mob_entities:
                            config.mob_entities[mob_id] = RemoteMob(mob)
                        else:
                            config.mob_entities[mob_id].apply_snapshot(mob)
                    for mob_id in data.get("despawns", []):
                        config.mob_entities.pop(mob_id, None)
                    config.mobs = [mob.to_snapshot() for mob in config.mob_entities.values()]
                elif data and data.get("type") == "teleport":
                    pos = data.get("pos")
                    if isinstance(pos, list) and len(pos) == 2:
                        player_data["pos"] = [float(pos[0]), float(pos[1])]
                        player_data.pop("knockback_vel", None)
                        log_info(f"[CLIENT STATE DEBUG] teleport pos=({pos[0]}, {pos[1]})")
                elif data and data.get("type") == "chat":
                    import time as _time
                    _msgs = config.chat_messages
                    _msgs.append({
                        "sender": data.get("sender", ""),
                        "text":   data.get("text",   ""),
                        "ts":     _time.time(),
                    })
                    # Trim history
                    if len(_msgs) > config.CHAT_MAX_MESSAGES:
                        del _msgs[:-config.CHAT_MAX_MESSAGES]
            except socket.timeout:
                pass
            except Exception as e:
                log_error(f"[STATE RECV ERROR] {e}")
                break

            # Forward any queued client→server messages (inv_swap, etc.)
            while not config.state_outbox.empty():
                try:
                    send_json(sock, config.state_outbox.get_nowait())
                except Exception:
                    break
    finally:
        try:
            sock.close()
        except Exception:
            pass

def send_and_receive_udp():
    _my_session = config.session_id
    from config import HOST, PORT_UDP, BUFFER_SIZE, PLAYER_START_X, PLAYER_START_Y
    from state.player import player_id_dict, player_data

    player_id = player_id_dict["player_id"]

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('0.0.0.0', 0))

    # Send the player's desired username so the server can use it as their ID.
    # If we have a last_player_id (from a previous session), also send it as a
    # rejoin hint so the server can restore that slot (e.g. after a disconnect).
    desired = getattr(config, "DEFAULT_PLAYER_ID", "Player") or "Player"
    rejoin_hint: dict = {"desired_name": desired}
    if config.last_player_id:
        rejoin_hint["rejoin_id"] = config.last_player_id
    initial_payload = orjson.dumps(rejoin_hint)
    size = struct.pack("!I", len(initial_payload))
    udp_sock.sendto(size + initial_payload, (HOST, PORT_UDP))

    try:
        data, _ = udp_sock.recvfrom(BUFFER_SIZE)
        size = struct.unpack("!I", data[:4])[0]
        payload = orjson.loads(data[4:4+size])
        player_id = payload["player_id"]
        player_id_dict["player_id"] = player_id
        config.last_player_id = player_id
        config.session_token = payload.get("session_token")
        if not config.session_token:
            print("[UDP INIT ERROR] Server did not provide a session token")
            return
        # Use server-provided spawn position (may be saved location on rejoin)
        assigned_pos = payload.get("pos", [PLAYER_START_X, PLAYER_START_Y])
        player_data["pos"] = [assigned_pos[0], assigned_pos[1]]
        print(f"[UDP ASSIGNED ID] {player_id}")
    except Exception as e:
        print(f"[UDP INIT ERROR] {e}")
        return

    threading.Thread(target=udp_receive_loop, args=(udp_sock,), daemon=True).start()

    while config.session_id == _my_session:
        config.last_ping_sent = time.time()
        pos_payload = orjson.dumps({
            "player_id": player_id,
            "session_token": config.session_token,
            "pos": player_data["pos"],
            "stealthy": config.is_stealthy,
            "hotbar_slot": config.hotbar_slot,
            "rolling": config.rolling,
            "blocking": config.is_blocking,
        })
        udp_sock.sendto(struct.pack("!I", len(pos_payload)) + pos_payload, (HOST, PORT_UDP))

        # Drain any queued UDP messages (attack events etc.)
        while not config.udp_outbox.empty():
            try:
                msg = config.udp_outbox.get_nowait()
                if isinstance(msg, dict):
                    msg.setdefault("player_id", player_id)
                    msg.setdefault("session_token", config.session_token)
                raw = orjson.dumps(msg)
                udp_sock.sendto(struct.pack("!I", len(raw)) + raw, (HOST, PORT_UDP))
            except Exception:
                break

        time.sleep(1 / 120)

def udp_receive_loop(sock):
    _my_session = config.session_id
    from config import BUFFER_SIZE
    from state.player import player_id_dict
    from config import players_data
    from shared_lock import data_lock

    sock.setblocking(False)

    while config.session_id == _my_session:
        try:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            size = struct.unpack("!I", data[:4])[0]
            payload = orjson.loads(data[4:4+size])

            if payload.get("type") == "positions":
                if config.last_ping_sent > 0:
                    rtt_ms = int((time.time() - config.last_ping_sent) * 1000)
                    config.ping = int(config.ping * 0.8 + rtt_ms * 0.2)  # smoothed EMA
                with data_lock:
                    raw_positions = payload.get("players", {})
                    for pid, update in raw_positions.items():
                        if pid == player_id_dict["player_id"]:
                            continue  # Local handled separately
                        if pid not in players_data:
                            players_data[pid] = RemotePlayer(update['pos'])
                        players_data[pid].add_update(update)
            elif payload.get("type") == "attack_event":
                pid       = payload.get("player_id")
                direction = payload.get("direction", "down")
                with data_lock:
                    if pid and pid in players_data:
                        players_data[pid].start_attack(direction)
            if payload.get("type") == "assign_id":
                player_id_dict["player_id"] = payload.get("player_id")
                player_id = player_id_dict["player_id"]
                print(f"[CLIENT] Assigned player_id: {player_id}")
            elif payload.get("type") == "banned":
                reason = payload.get("reason", "You are banned from this server.")
                config.connection_error = reason
                print(f"[CLIENT] Banned: {reason}")
        except BlockingIOError:
            pass
        except Exception as e:
            print(f"[UDP RECV ERROR] {e}")

        time.sleep(1 / 120)

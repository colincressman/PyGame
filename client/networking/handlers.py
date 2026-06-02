import time, struct
import socket
import threading, orjson
from collections import deque
import config
from .sockets import connect_with_retry
from .protocols import identify_socket, recv_json, send_json
from state.player import player_data

# Registry of every node's base data, used to re-add nodes when they respawn.
# Never shrinks; depleted nodes are removed from config.world_nodes but stay here.
_node_base_cache: dict = {}

# Fallback max-HP values for node types, used only when the server hasn't yet
# sent max_hp in the node packet (e.g. old cached chunks or race conditions).
_NODE_MAX_HP_FALLBACK: dict[str, int] = {
    "tree":          6,
    "pine_tree":     6,
    "jungle_tree":   8,
    "palm_tree":     5,
    "stone_deposit": 20,
    "iron_ore":      20,
    "coal_deposit":  20,
    "herb_patch":    1,
    "cactus":        2,
    "reed_cluster":  1,
    "seashell_bed":  1,
    "mushroom":      1,
    "snow_crystal":  1,
    "stick_pile":    1,
    "bone_pile":     1,
    "clay_deposit":  2,
    "copper_ore":    25,
    "tin_ore":       25,
    "silver_ore":    30,
    "gold_ore":      35,
    "crystal":       40,
    "obsidian":      50,
}

class RemotePlayer:
    _WALK_FPS    = 10.0
    _WALK_FRAMES = 9   # walk animation (9 frames)
    _ATK_FPS     = 14.0
    _ATK_FRAMES  = 6   # LPC slash animation has 6 frames

    def __init__(self, pos):
        self.pos_buffer = deque(maxlen=3)
        self.pos_buffer.append({'pos': pos, 'vel': [0, 0], 'ts': time.time(), 'seq': 0})
        self.last_seq       = 0
        self.health         = 100
        self.facing         = "down"
        self.is_moving      = False
        self.walk_frame     = 0
        self.walk_timer     = 0.0
        self.last_move_time = 0.0
        self.is_attacking   = False
        self.atk_frame      = 0
        self.atk_timer      = 0.0
        self.equip_ids: dict = {}   # {slot_index: item_id} for visual rendering
        self.appearance: dict = {}  # cosmetic appearance from server

    def start_attack(self, direction: str):
        self.is_attacking = True
        self.atk_frame    = 0
        self.atk_timer    = 0.0
        if direction:
            self.facing = direction

    def add_update(self, update):
        seq = update.get('seq', 0)
        if seq > self.last_seq:  # Ignore old/out-of-order
            self.last_seq = seq
            self.pos_buffer.append({
                'pos': update['pos'],
                'vel': update.get('vel', [0, 0]),
                'ts': update.get('timestamp', time.time()),
                'seq': seq
            })
            vx, vy = update.get('vel', [0, 0])
            speed_sq = vx * vx + vy * vy
            if speed_sq > 1e-8:
                self.last_move_time = time.time()
                if abs(vy) >= abs(vx):
                    self.facing = "down" if vy > 0 else "up"
                else:
                    self.facing = "right" if vx > 0 else "left"

    _MOVE_DECAY = 0.15   # seconds after last non-zero vel before animation stops

    def update_anim(self, dt):
        if self.is_attacking:
            self.atk_timer += dt
            frame = int(self.atk_timer * self._ATK_FPS)
            if frame >= self._ATK_FRAMES:
                self.is_attacking = False
                self.atk_frame    = 0
                self.atk_timer    = 0.0
            else:
                self.atk_frame = frame
            return   # don't update walk anim while attacking

        # is_moving stays True for _MOVE_DECAY seconds after the last non-zero vel packet.
        self.is_moving = (time.time() - self.last_move_time) < self._MOVE_DECAY
        if self.is_moving:
            self.walk_timer += dt
            self.walk_frame = int(self.walk_timer * self._WALK_FPS) % self._WALK_FRAMES
        else:
            self.walk_frame = 0
            self.walk_timer = 0.0

    # Maximum time (seconds) to extrapolate when the server goes silent.
    # Beyond this the player stays frozen at the last known position.
    _MAX_EXTRAP_TIME = 0.3

    def get_render_pos(self, current_time, interp_delay=0.1):
        if len(self.pos_buffer) < 2:
            return self.pos_buffer[0]['pos']
        target_time = current_time - interp_delay
        for i in range(len(self.pos_buffer) - 1):
            prev, next = self.pos_buffer[i], self.pos_buffer[i+1]
            if prev['ts'] <= target_time <= next['ts']:
                alpha = (target_time - prev['ts']) / (next['ts'] - prev['ts'])
                return [
                    prev['pos'][0] + alpha * (next['pos'][0] - prev['pos'][0]),
                    prev['pos'][1] + alpha * (next['pos'][1] - prev['pos'][1])
                ]
        # Extrapolate — capped to _MAX_EXTRAP_TIME so a silent server doesn't slide players away
        last = self.pos_buffer[-1]
        time_diff = min(current_time - last['ts'], self._MAX_EXTRAP_TIME)
        return [
            last['pos'][0] + last['vel'][0] * time_diff,
            last['pos'][1] + last['vel'][1] * time_diff
        ]

def handle_world(HOST, PORT_WORLD, chunk_queue, player_id):
    _my_session = config.session_id
    sock = connect_with_retry(HOST, PORT_WORLD)
    if not sock:
        return
    identify_socket(sock, "world", player_id)
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
                            max_hp = node.get("max_hp") or _NODE_MAX_HP_FALLBACK.get(ntype, 1)
                            if nid not in _new_nodes:
                                _node_base_cache[nid] = {"type": ntype, "wx": wx, "wy": wy, "max_hp": max_hp}
                                _new_nodes[nid] = {
                                    "type": ntype, "wx": wx, "wy": wy,
                                    "max_hp": max_hp, "hits": 0,
                                }
                        config.world_nodes = _new_nodes

            except socket.timeout:
                continue  # allow frequent checks
            except Exception as e:
                print(f"[WORLD RECV ERROR] {e}")
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
    identify_socket(sock, "game_state", player_id)
    print("[STATE] Connected and handshake sent.")
    sock.settimeout(0.1)

    try:
        while config.session_id == _my_session:
            try:
                data = recv_json(sock)
                if data and data.get("type") == "game_state":
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
                    for pid, pdata in data.get("players", {}).items():
                        if pid in config.players_data:
                            config.players_data[pid].health = pdata.get("health", 100)
                            equip = pdata.get("equip")
                            if equip is not None:
                                config.players_data[pid].equip_ids = {int(k): v for k, v in equip.items()}
                            appearance = pdata.get("appearance")
                            if isinstance(appearance, dict):
                                config.players_data[pid].appearance = appearance
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
                        config.world_nodes = {
                            k: v for k, v in config.world_nodes.items()
                            if not k.startswith("item:")
                        }
                        config.world_nodes.update(_item_nodes)
                    mob_list = data.get("mobs")
                    if mob_list is not None:
                        config.mobs = mob_list
                    npcs_list = data.get("npcs")
                    if npcs_list is not None:
                        config.npcs = npcs_list
                    dungeons_list = data.get("dungeons")
                    if dungeons_list is not None:
                        config.dungeons = dungeons_list
                    placed_list = data.get("placed_objects")
                    if placed_list is not None:
                        config.placed_objects = {obj["uid"]: obj for obj in placed_list}
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
                        config.world_nodes = _new_nodes
                    depleted_snapshot = data.get("depleted_snapshot")
                    if depleted_snapshot:
                        _new_nodes = dict(config.world_nodes)
                        for nid in depleted_snapshot:
                            _new_nodes.pop(nid, None)
                        config.world_nodes = _new_nodes
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
                                    "max_hp":  pn.get("max_hp") or _NODE_MAX_HP_FALLBACK.get(ntype, 1),
                                    "depleted": False,
                                    "hits":    0,
                                }
                        # Remove planted nodes that are no longer active on the server
                        for nid in [k for k in _new_nodes if k.startswith("planted:") and k not in reported_ids]:
                            del _new_nodes[nid]
                        config.world_nodes = _new_nodes
                elif data and data.get("type") == "shop_update":
                    config.shop_items = data.get("items", [])
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
                print(f"[STATE RECV ERROR] {e}")
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
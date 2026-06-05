# server/network/udp_routes.py

import socket
import struct
import time
import orjson
from server.shared_lock import clients_lock, players_lock
from server.config import HOST, PORT_UDP, BUFFER_SIZE, TICK_RATE, WORLD_RADIUS
from server.world.visible import get_visible_chunks_for_player
from server.cleanup import last_positions
from server.player_save import load_player, default_player_stats, _SAFE_ID
from server.network.combat import handle_attack
from server.ops import is_banned
from server.session_auth import issue_token, verify_token
from server.world.world_types import WATER_BIOMES

# Minimum interval between accepted movement packets per client (half the server tick period)
_UDP_MIN_INTERVAL = 1.0 / (TICK_RATE * 2)
# Per-player timestamp of last accepted movement packet
_last_udp_time: dict[str, float] = {}

# Shared game_state references to be injected
clients = None
players = None
player_positions = None
pending_udp_assignments = None
client_id_counter = None
_world_data = None

def _is_safe_player_id(player_id) -> bool:
    return isinstance(player_id, str) and bool(_SAFE_ID.match(player_id))


def _safe_spawn_pos(raw_pos):
    """Return raw_pos if it's on dry land; otherwise spiral outward until dry land is found.
    Uses get_tile_biome() which loads/generates chunks on-demand, so this works even
    before world_data is populated by the game loop.
    """
    from server.world.dyn_chunk_gen import get_tile_biome
    tx, ty = int(raw_pos[0]), int(raw_pos[1])
    if get_tile_biome(tx, ty, _world_data) not in WATER_BIOMES:
        return raw_pos
    # Scan outward from the requested position for the nearest dry tile
    for r in range(1, 100):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue  # only check perimeter of expanding square
                nx, ny = tx + dx, ty + dy
                if get_tile_biome(nx, ny, _world_data) not in WATER_BIOMES:
                    return [float(nx), float(ny)]
    return [0.0, 0.0]  # fallback (shouldn't happen with radius 100)


def set_udp_state_refs(refs):
    global clients, players, player_positions, pending_udp_assignments, client_id_counter, _world_data
    clients = refs["clients"]
    players = refs["players"]
    player_positions = refs["player_positions"]
    pending_udp_assignments = refs["pending_udp_assignments"]
    client_id_counter = refs["client_id_counter"]
    _world_data = refs.get("world_data")


def udp_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT_UDP))
    print(f"[UDP LISTENING] on {PORT_UDP}")

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            size = struct.unpack("!I", data[:4])[0]
            payload = orjson.loads(data[4:4+size])

            player_id = payload.get("player_id")
            pos = payload.get("pos")
            session_token = payload.get("session_token")

            if player_id is not None and not _is_safe_player_id(player_id):
                continue

            if not player_id:
                rejoin_id    = payload.get("rejoin_id")
                desired_name = payload.get("desired_name")
                if rejoin_id is not None and not _is_safe_player_id(rejoin_id):
                    rejoin_id = None
                if desired_name is not None and not _is_safe_player_id(desired_name):
                    desired_name = None

                # Reject banned players before doing any work
                candidate_name = rejoin_id or desired_name
                if candidate_name and is_banned(candidate_name):
                    import struct as _struct
                    import orjson as _orj
                    ban_resp = _orj.dumps({"type": "banned", "reason": "You are banned from this server."})
                    sock.sendto(_struct.pack("!I", len(ban_resp)) + ban_resp, addr)
                    print(f"[UDP] Rejected banned player '{candidate_name}' from {addr}")
                    continue

                # Determine the candidate name to try:
                #   1. rejoin_id wins if the slot is free (returning player reconnecting)
                #   2. desired_name is used for new connections with a chosen username
                #   3. fallback: Player{counter}
                candidate = rejoin_id or desired_name or None

                # Pre-load save data outside lock to avoid I/O under contention
                saved = load_player(candidate) if candidate else None

                with players_lock:
                    if candidate and candidate not in players:
                        # Slot is free — use the candidate directly
                        new_id = candidate
                    elif desired_name:
                        # Desired name is taken — find first free suffix (Bob_2, Bob_3 …)
                        suffix = 2
                        while True:
                            attempt = f"{desired_name}_{suffix}"
                            if attempt not in players:
                                new_id = attempt
                                saved  = load_player(new_id)
                                break
                            suffix += 1
                    else:
                        new_id = f"Player{client_id_counter[0]}"
                        client_id_counter[0] += 1
                        saved = load_player(new_id)  # fast: None for truly new players

                    raw_pos   = (saved or {}).get("pos", last_positions.pop(new_id, [0, 0]))
                    spawn_pos = _safe_spawn_pos(raw_pos)
                    stats = {**default_player_stats(), **(saved or {})}
                    # Pad inventory to 48 slots (old saves may have fewer slots)
                    _inv = list(stats.get("inventory", []))
                    if len(_inv) < 48:
                        _inv += [None] * (48 - len(_inv))
                    stats["inventory"] = _inv
                    player_id = new_id
                    players[player_id] = {
                        "pos":            spawn_pos,
                        "health":         stats["health"],
                        "health_max":     stats["health_max"],
                        "stamina":        stats["stamina"],
                        "stamina_max":    stats["stamina_max"],
                        "attack_power":   stats["attack_power"],
                        "speed_bonus":    stats.get("speed_bonus",    0.0),
                        "hp_regen":       stats.get("hp_regen",       0.0),
                        "sp_regen_bonus": stats.get("sp_regen_bonus", 0.0),
                        "level":          stats["level"],
                        "exp":            stats.get("exp",            0),
                        "exp_next":       stats.get("exp_next",       100),
                        "stat_points":    stats.get("stat_points",    0),
                        "coins":          stats.get("coins",          0),
                        "inventory":      stats["inventory"],
                        "last_seen":      time.time()
                    }
                    if "bed_spawn" in stats:
                        players[player_id]["bed_spawn"] = stats["bed_spawn"]
                    if "home_pos" in stats:
                        players[player_id]["home_pos"] = stats["home_pos"]
                    if "appearance" in stats:
                        players[player_id]["appearance"] = stats["appearance"]
                    player_positions[player_id] = {
                        'pos': spawn_pos, 'vel': [0, 0], 'timestamp': time.time(), 'seq': 0
                    }
                    pending_udp_assignments.add(player_id)
                    assigned_token = issue_token(player_id)
                with clients_lock:
                    clients["udp"][player_id] = addr

                response = orjson.dumps({
                    "type": "assign_id",
                    "player_id": player_id,
                    "pos": spawn_pos,
                    "session_token": assigned_token,
                })
                sock.sendto(struct.pack("!I", len(response)) + response, addr)
                print(f"[UDP ASSIGN] {player_id} assigned to {addr}")

                # ID sent immediately — remove from pending so broadcast loop doesn't resend
                with players_lock:
                    pending_udp_assignments.discard(player_id)

            elif payload.get("type") == "attack":
                if not verify_token(player_id, session_token):
                    continue
                # Must be checked BEFORE `elif pos` — attack packets also carry a pos field.
                from server.mobs.mob_manager import mobs
                direction = payload.get("direction", "down")
                atk_pos   = payload.get("pos", [0, 0])
                handle_attack(
                    attacker_id = player_id,
                    direction   = direction,
                    pos         = atk_pos,
                    players     = players,
                    mobs        = mobs,
                )
                # Broadcast attack animation event to nearby players
                with clients_lock:
                    udp_snap = dict(clients["udp"])
                with players_lock:
                    pos_snap = dict(player_positions)
                evt = orjson.dumps({
                    "type":      "attack_event",
                    "player_id": player_id,
                    "direction": direction,
                })
                evt_msg = struct.pack("!I", len(evt)) + evt
                RANGE_SQ = 100 * 100
                for pid, pdata in pos_snap.items():
                    if pid == player_id:
                        continue
                    op = pdata.get("pos", [0, 0])
                    ddx = op[0] - atk_pos[0]
                    ddy = op[1] - atk_pos[1]
                    if ddx * ddx + ddy * ddy <= RANGE_SQ:
                        dest = udp_snap.get(pid)
                        if dest:
                            try:
                                sock.sendto(evt_msg, dest)
                            except Exception:
                                pass

            elif pos:
                if not verify_token(player_id, session_token):
                    continue
                # --- Rate limiting: drop packets arriving too fast ---
                now_t = time.time()
                if now_t - _last_udp_time.get(player_id, 0.0) < _UDP_MIN_INTERVAL:
                    continue  # silently drop; client is sending faster than allowed
                _last_udp_time[player_id] = now_t

                # --- World bounds validation ---
                if not (-WORLD_RADIUS <= pos[0] <= WORLD_RADIUS and
                        -WORLD_RADIUS <= pos[1] <= WORLD_RADIUS):
                    continue  # reject out-of-bounds teleport

                with players_lock:
                    if player_id not in players:
                        continue  # stale update from a disconnected client
                    old_pos = players[player_id].get("old_pos", pos)
                    dx = pos[0] - old_pos[0]
                    dy = pos[1] - old_pos[1]
                    seq = players[player_id].get("seq", 0) + 1
                    players[player_id]["pos"] = pos
                    players[player_id]["stealthy"]      = payload.get("stealthy",    False)
                    players[player_id]["hotbar_slot"]   = payload.get("hotbar_slot", 0)
                    players[player_id]["invulnerable"]  = payload.get("rolling",     False)
                    _was_blocking = players[player_id].get("blocking", False)
                    _now_blocking = payload.get("blocking", False)
                    players[player_id]["blocking"] = _now_blocking
                    if _now_blocking and not _was_blocking:
                        players[player_id]["block_start"] = time.time()
                    players[player_id]["last_seen"] = time.time()
                    players[player_id]["old_pos"] = pos
                    players[player_id]["seq"] = seq
                    player_positions[player_id] = {
                        'pos': pos,
                        'vel': [dx, dy],
                        'timestamp': time.time(),
                        'seq': seq
                    }
                with clients_lock:
                    clients["udp"][player_id] = addr

        except Exception as e:
            print(f"[UDP ERROR] {e}")

def udp_broadcast_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    BROADCAST_RANGE_SQ = 100 * 100  # tiles² — ~3200 px, well beyond any render distance

    while True:
        with clients_lock:
            udp_clients_snapshot = dict(clients["udp"])

        with players_lock:
            pos_snapshot = dict(player_positions)
            active_ids = set(player_positions.keys())
            pending_snap = set(pending_udp_assignments)

        if pos_snapshot:
            udp_clients = {
                pid: addr for pid, addr in udp_clients_snapshot.items()
                if pid in active_ids and pid not in pending_snap
            }

            for player_id, addr in udp_clients.items():
                my_pos = pos_snapshot.get(player_id, {}).get("pos", [0, 0])
                nearby_player_positions = {}
                for pid, pdata in pos_snapshot.items():
                    if pid == player_id:
                        continue
                    op = pdata.get("pos", [0, 0])
                    dx = op[0] - my_pos[0]
                    dy = op[1] - my_pos[1]
                    if dx * dx + dy * dy <= BROADCAST_RANGE_SQ:
                        nearby_player_positions[pid] = pdata

                payload = {
                    "type": "positions",
                    "players": nearby_player_positions
                }
                encoded = orjson.dumps(payload)
                message = struct.pack("!I", len(encoded)) + encoded

                try:
                    sock.sendto(message, addr)
                except Exception as e:
                    print(f"[UDP POS SEND ERROR] {e}")

        time.sleep(1 / 120.0)

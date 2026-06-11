import time
from collections import deque
from state.replication_config import REMOTE_PLAYER_CFG


class RemotePlayer:
    _WALK_FPS = 10.0
    _WALK_FRAMES = 9
    _ATK_FPS = 14.0
    _ATK_FRAMES = 6
    _MOVE_DECAY = float(REMOTE_PLAYER_CFG.get("move_decay", 0.15))
    _MAX_EXTRAP_TIME = float(REMOTE_PLAYER_CFG.get("max_extrap_time", 0.03))
    _INTERP_NEAR_DELAY = float(REMOTE_PLAYER_CFG.get("interp_near_delay", 0.11))
    _INTERP_MID_DELAY = float(REMOTE_PLAYER_CFG.get("interp_mid_delay", 0.14))
    _INTERP_FAR_DELAY = float(REMOTE_PLAYER_CFG.get("interp_far_delay", 0.17))
    _COMBAT_NEAR_DELAY = float(REMOTE_PLAYER_CFG.get("combat_near_delay", 0.08))
    _COMBAT_MID_DELAY = float(REMOTE_PLAYER_CFG.get("combat_mid_delay", 0.10))
    _COMBAT_NEAR_DIST_SQ = float(REMOTE_PLAYER_CFG.get("combat_near_dist_sq", 16.0))
    _COMBAT_MID_DIST_SQ = float(REMOTE_PLAYER_CFG.get("combat_mid_dist_sq", 64.0))
    _NEAR_DIST_SQ = float(REMOTE_PLAYER_CFG.get("near_dist_sq", 36.0))
    _MID_DIST_SQ = float(REMOTE_PLAYER_CFG.get("mid_dist_sq", 144.0))

    def __init__(self, pos):
        self._time_offset = 0.0
        self.pos_buffer = deque(maxlen=16)
        self.pos_buffer.append({"pos": pos, "vel": [0.0, 0.0], "ts": time.time(), "seq": 0})
        self.last_seq = 0
        self.health = 100
        self.facing = "down"
        self.is_moving = False
        self.walk_frame = 0
        self.walk_timer = 0.0
        self.last_move_time = 0.0
        self.is_attacking = False
        self.atk_frame = 0
        self.atk_timer = 0.0
        self.equip_ids: dict = {}
        self.held_item_id: int | None = None
        self.appearance: dict = {}

    def _resolved_ts(self, update, recv_now: float, prev_ts: float | None) -> float:
        server_ts = update.get("timestamp")
        if not isinstance(server_ts, (int, float)):
            if prev_ts is None:
                return recv_now
            return max(recv_now, prev_ts + 1e-4)
        target_offset = recv_now - float(server_ts)
        if self._time_offset == 0.0:
            self._time_offset = target_offset
        else:
            self._time_offset = self._time_offset * 0.9 + target_offset * 0.1
        resolved = float(server_ts) + self._time_offset
        if prev_ts is None:
            return min(resolved, recv_now)
        return max(resolved, prev_ts + 1e-4)

    def start_attack(self, direction: str):
        self.is_attacking = True
        self.atk_frame = 0
        self.atk_timer = 0.0
        if direction:
            self.facing = direction

    def add_update(self, update):
        seq = update.get("seq", 0)
        if seq > self.last_seq:
            self.last_seq = seq
            recv_now = time.time()
            prev = self.pos_buffer[-1]
            vel = update.get("vel", [0.0, 0.0])
            if not (isinstance(vel, (list, tuple)) and len(vel) == 2):
                vel = [0.0, 0.0]
            sample_ts = self._resolved_ts(update, recv_now, prev["ts"])
            self.pos_buffer.append({
                "pos": update["pos"],
                "vel": [float(vel[0]), float(vel[1])],
                "ts": sample_ts,
                "seq": seq,
            })
            vx, vy = vel
            speed_sq = vx * vx + vy * vy
            if speed_sq > 1e-8:
                self.last_move_time = recv_now
                if abs(vy) >= abs(vx):
                    self.facing = "down" if vy > 0 else "up"
                else:
                    self.facing = "right" if vx > 0 else "left"

    def update_anim(self, dt):
        if self.is_attacking:
            self.atk_timer += dt
            frame = int(self.atk_timer * self._ATK_FPS)
            if frame >= self._ATK_FRAMES:
                self.is_attacking = False
                self.atk_frame = 0
                self.atk_timer = 0.0
            else:
                self.atk_frame = frame
            return

        self.is_moving = (time.time() - self.last_move_time) < self._MOVE_DECAY
        if self.is_moving:
            self.walk_timer += dt
            self.walk_frame = int(self.walk_timer * self._WALK_FPS) % self._WALK_FRAMES
        else:
            self.walk_frame = 0
            self.walk_timer = 0.0

    def get_render_pos(self, current_time, interp_delay=None):
        if interp_delay is None:
            interp_delay = self._INTERP_FAR_DELAY
        if len(self.pos_buffer) < 2:
            return self.pos_buffer[0]["pos"]
        target_time = current_time - interp_delay
        for i in range(len(self.pos_buffer) - 1):
            prev, nxt = self.pos_buffer[i], self.pos_buffer[i + 1]
            if prev["ts"] <= target_time <= nxt["ts"]:
                alpha = (target_time - prev["ts"]) / (nxt["ts"] - prev["ts"])
                return [
                    prev["pos"][0] + alpha * (nxt["pos"][0] - prev["pos"][0]),
                    prev["pos"][1] + alpha * (nxt["pos"][1] - prev["pos"][1]),
                ]
        last = self.pos_buffer[-1]
        time_diff = min(current_time - last["ts"], self._MAX_EXTRAP_TIME)
        return [
            last["pos"][0] + last["vel"][0] * time_diff,
            last["pos"][1] + last["vel"][1] * time_diff,
        ]

    def get_interp_delay(self, local_pos, combat_active: bool = False) -> float:
        latest = self.pos_buffer[-1]["pos"]
        dx = latest[0] - float(local_pos[0])
        dy = latest[1] - float(local_pos[1])
        dist_sq = dx * dx + dy * dy

        if combat_active or self.is_attacking:
            if dist_sq <= self._COMBAT_NEAR_DIST_SQ:
                return self._COMBAT_NEAR_DELAY
            if dist_sq <= self._COMBAT_MID_DIST_SQ:
                return self._COMBAT_MID_DELAY

        if dist_sq <= self._NEAR_DIST_SQ:
            return self._INTERP_NEAR_DELAY
        if dist_sq <= self._MID_DIST_SQ:
            return self._INTERP_MID_DELAY
        return self._INTERP_FAR_DELAY

import time
from collections import deque


class RemotePlayer:
    _WALK_FPS = 10.0
    _WALK_FRAMES = 9
    _ATK_FPS = 14.0
    _ATK_FRAMES = 6
    _MOVE_DECAY = 0.15
    _MAX_EXTRAP_TIME = 0.3

    def __init__(self, pos):
        self.pos_buffer = deque(maxlen=3)
        self.pos_buffer.append({"pos": pos, "vel": [0, 0], "ts": time.time(), "seq": 0})
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
        self.appearance: dict = {}

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
            self.pos_buffer.append({
                "pos": update["pos"],
                "vel": update.get("vel", [0, 0]),
                "ts": update.get("timestamp", time.time()),
                "seq": seq,
            })
            vx, vy = update.get("vel", [0, 0])
            speed_sq = vx * vx + vy * vy
            if speed_sq > 1e-8:
                self.last_move_time = time.time()
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

    def get_render_pos(self, current_time, interp_delay=0.1):
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

import time
from collections import deque


class RemoteMob:
    _MAX_EXTRAP_TIME = 0.03

    def __init__(self, snapshot: dict):
        now = time.time()
        self._time_offset = 0.0
        pos = list(snapshot.get("pos", [0.0, 0.0]))
        incoming_vel = snapshot.get("vel")
        vel = [0.0, 0.0]
        if isinstance(incoming_vel, (list, tuple)) and len(incoming_vel) == 2:
            vel = [float(incoming_vel[0]), float(incoming_vel[1])]
        self.mob_id = snapshot.get("id", "")
        self.mob_type = snapshot.get("type", "slime")
        self.health = snapshot.get("health", 100)
        self.health_max = snapshot.get("health_max", 100)
        self.level = snapshot.get("level", 1)
        self.hit_flash = snapshot.get("hit_flash", 0.0)
        self.state = snapshot.get("state", "wander")
        self.facing = snapshot.get("facing", "down")
        self.pos_buffer = deque(maxlen=16)
        sample_ts = self._resolved_ts(snapshot, now, None)
        self.pos_buffer.append({"pos": pos, "vel": vel, "ts": sample_ts})

    def _resolved_ts(self, snapshot: dict, recv_now: float, prev_ts: float | None) -> float:
        server_ts = snapshot.get("ts")
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

    def apply_snapshot(self, snapshot: dict) -> None:
        recv_now = time.time()
        prev = self.pos_buffer[-1]
        new_pos = list(snapshot.get("pos", prev["pos"]))
        incoming_vel = snapshot.get("vel")
        if isinstance(incoming_vel, (list, tuple)) and len(incoming_vel) == 2:
            vel = [float(incoming_vel[0]), float(incoming_vel[1])]
        else:
            dt = max(recv_now - prev["ts"], 1e-6)
            vel = [
                (new_pos[0] - prev["pos"][0]) / dt,
                (new_pos[1] - prev["pos"][1]) / dt,
            ]
        sample_ts = self._resolved_ts(snapshot, recv_now, prev["ts"])
        if (abs(new_pos[0] - prev["pos"][0]) > 1e-4
                or abs(new_pos[1] - prev["pos"][1]) > 1e-4
                or sample_ts - prev["ts"] > 0.10):
            self.pos_buffer.append({"pos": new_pos, "vel": vel, "ts": sample_ts})
        self.mob_type = snapshot.get("type", self.mob_type)
        self.health = snapshot.get("health", self.health)
        self.health_max = snapshot.get("health_max", self.health_max)
        self.level = snapshot.get("level", self.level)
        self.hit_flash = snapshot.get("hit_flash", self.hit_flash)
        self.state = snapshot.get("state", self.state)
        self.facing = snapshot.get("facing", self.facing)

    def get_render_pos(self, current_time: float, interp_delay: float = 0.17) -> list[float]:
        if len(self.pos_buffer) < 2:
            return list(self.pos_buffer[0]["pos"])
        target_time = current_time - interp_delay
        for i in range(len(self.pos_buffer) - 1):
            prev, nxt = self.pos_buffer[i], self.pos_buffer[i + 1]
            if prev["ts"] <= target_time <= nxt["ts"]:
                alpha = (target_time - prev["ts"]) / max(nxt["ts"] - prev["ts"], 1e-6)
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

    def to_snapshot(self) -> dict:
        return {
            "id": self.mob_id,
            "type": self.mob_type,
            "pos": list(self.pos_buffer[-1]["pos"]),
            "health": self.health,
            "health_max": self.health_max,
            "level": self.level,
            "hit_flash": self.hit_flash,
            "state": self.state,
            "facing": self.facing,
        }

# server/game_state/weather.py
"""Server-side global weather state machine.

One weather value is shared across the entire world.  get_weather() is called
by game_sync.build_game_state() and its return value is included in every
player's state packet.

States: clear, cloudy, rain, snow, fog
"""
import random
import time

# Weighted transition table: current_state → {next_state: relative_weight}
_TRANSITIONS: dict[str, dict[str, int]] = {
    "clear":  {"clear": 55, "cloudy": 35, "fog":   10},
    "cloudy": {"clear": 30, "cloudy": 30, "rain":  30, "fog": 10},
    "rain":   {"clear": 20, "cloudy": 30, "rain":  50},
    "snow":   {"snow":  60, "cloudy": 30, "clear": 10},
    "fog":    {"clear": 40, "cloudy": 40, "fog":   20},
}

_MIN_DURATION: float = 180.0   # minimum seconds a state lasts before a new roll
_MAX_DURATION: float = 600.0   # maximum seconds

_current: str = "clear"
_next_transition: float = 0.0   # Unix timestamp of the next state roll


def get_weather() -> str:
    """Return the current weather string; advances the state machine when due."""
    global _current, _next_transition
    now = time.time()
    if now >= _next_transition:
        weights_map = _TRANSITIONS.get(_current, {"clear": 100})
        states  = list(weights_map.keys())
        weights = list(weights_map.values())
        _current = random.choices(states, weights=weights, k=1)[0]
        _next_transition = now + random.uniform(_MIN_DURATION, _MAX_DURATION)
        if _current != "clear":
            print(f"[WEATHER] → {_current}")
    return _current

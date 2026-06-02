# server/game_state/status_effects.py
"""Server-side status effect management: poison (future: burn, freeze).

apply_poison() is called by mob_manager when a scorpion scores a lunge hit.
tick_status_effects() is called once per server tick from server.py.
"""
from server.shared_lock import players_lock
from server.config import DEFAULT_BURN_DPS as _DEFAULT_BURN_DPS, DEFAULT_POISON_DPS as _DEFAULT_POISON_DPS


def tick_status_effects(players: dict, dt: float) -> None:
    """Tick all active status effects on every connected player."""
    with players_lock:
        for pdata in players.values():
            pt = pdata.get("poison_timer", 0.0)
            if pt > 0.0:
                dps = pdata.get("poison_dps", _DEFAULT_POISON_DPS)
                pdata["health"]       = max(0.0, pdata.get("health", 0.0) - dps * dt)
                pdata["poison_timer"] = max(0.0, pt - dt)
            bt = pdata.get("burn_timer", 0.0)
            if bt > 0.0:
                dps = pdata.get("burn_dps", _DEFAULT_BURN_DPS)
                pdata["health"]     = max(0.0, pdata.get("health", 0.0) - dps * dt)
                pdata["burn_timer"] = max(0.0, bt - dt)


def apply_poison(
    pid: str,
    players: dict,
    duration: float = 5.0,
    dps: float = 2.0,
) -> None:
    """Apply (or refresh) a poison effect on a player.

    Creative-mode players are immune.  If the player is already poisoned,
    the longer of the two durations wins.
    """
    with players_lock:
        if pid not in players:
            return
        pdata = players[pid]
        if pdata.get("creative", False):
            return
        pdata["poison_timer"] = max(pdata.get("poison_timer", 0.0), duration)
        pdata["poison_dps"]   = dps

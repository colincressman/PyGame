"""Server-side status effect management."""

from server.shared_lock import players_lock
from server.game_state.status_effect_data import STATUS_EFFECTS


def _get_effect_cfg(effect_name: str) -> dict:
    return STATUS_EFFECTS.get(effect_name, {})


def apply_status_effect(
    entity: dict,
    effect_name: str,
    duration: float | None = None,
    potency: float | None = None,
) -> None:
    """Apply or refresh a configured status effect on an entity dict."""
    cfg = _get_effect_cfg(effect_name)
    timer_key = cfg.get("timer_key")
    if not timer_key:
        return
    duration = float(duration if duration is not None else cfg.get("default_duration", 0.0))
    entity[timer_key] = max(entity.get(timer_key, 0.0), duration)

    potency_key = cfg.get("potency_key")
    if potency_key:
        if potency is None:
            potency = cfg.get("default_dps")
        if potency is not None:
            entity[potency_key] = float(potency)


def tick_effects_on_entity(
    entity: dict,
    dt: float,
    death_credit: str | None = None,
    flash_on_tick: bool = False,
) -> None:
    """Advance all known timed effects on a single entity."""
    for cfg in STATUS_EFFECTS.values():
        timer_key = cfg.get("timer_key")
        if not timer_key:
            continue
        remaining = entity.get(timer_key, 0.0)
        if remaining <= 0.0:
            continue

        entity[timer_key] = max(0.0, remaining - dt)

        if not cfg.get("deals_damage", False):
            continue

        potency_key = cfg.get("potency_key")
        default_dps = float(cfg.get("default_dps", 0.0))
        dps = float(entity.get(potency_key, default_dps)) if potency_key else default_dps
        if dps <= 0.0:
            continue

        entity["health"] = max(0.0, entity.get("health", 0.0) - dps * dt)
        if flash_on_tick and cfg.get("hit_flash"):
            entity["hit_flash"] = max(entity.get("hit_flash", 0.0), float(cfg["hit_flash"]))
        if entity["health"] <= 0 and death_credit and not entity.get("killed_by"):
            entity["killed_by"] = death_credit


def tick_status_effects(players: dict, dt: float) -> None:
    """Tick all active status effects on every connected player."""
    with players_lock:
        for pdata in players.values():
            tick_effects_on_entity(pdata, dt)


def apply_poison(
    pid: str,
    players: dict,
    duration: float = 5.0,
    dps: float = 2.0,
) -> None:
    """Apply (or refresh) a poison effect on a player."""
    with players_lock:
        if pid not in players:
            return
        pdata = players[pid]
        if pdata.get("creative", False):
            return
        apply_status_effect(pdata, "poison", duration=duration, potency=dps)

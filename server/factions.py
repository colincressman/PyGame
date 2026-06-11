"""Persistent faction registry and player-power helpers."""

from __future__ import annotations

import json
import os
import threading
import time

from server.config import CHUNK_SIZE
from server.player_save import load_player, save_player

_DATA_PATH = os.path.join(os.path.dirname(__file__), "factions.json")
_LOCK = threading.RLock()

DEFAULT_PLAYER_POWER = 0.0
MAX_PLAYER_POWER = 10.0
MIN_PLAYER_POWER = 0.0
DEATH_POWER_LOSS = 2.0
POWER_REGEN_PER_HOUR = 1.0
OFFLINE_POWER_GRACE = 60.0 * 60.0 * 24.0
OFFLINE_POWER_FLOOR_FACTOR = 0.5
MAX_TAG_LEN = 6

_factions: dict[str, dict] = {}
_invites: dict[str, str] = {}


def _load() -> None:
    global _factions
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            _factions = payload
        else:
            _factions = {}
    except FileNotFoundError:
        _factions = {}
    except Exception as exc:
        print(f"[FACTIONS] Load error: {exc}")
        _factions = {}


def _save() -> None:
    try:
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(_factions, f, indent=2)
    except Exception as exc:
        print(f"[FACTIONS] Save error: {exc}")


def _now() -> float:
    return time.time()


def _normalize_name(name: str) -> str:
    return (name or "").strip()


def _normalize_tag(tag: str) -> str:
    return (tag or "").strip().upper()[:MAX_TAG_LEN]


def _player_snapshot(player_id: str, players: dict) -> dict | None:
    player = players.get(player_id)
    if player is not None:
        return dict(player)
    return load_player(player_id)


def _player_current_power(player_id: str, players: dict | None = None) -> float:
    snapshot = _player_snapshot(player_id, players or {})
    if snapshot is None:
        return DEFAULT_PLAYER_POWER
    raw = float(snapshot.get("faction_power", DEFAULT_PLAYER_POWER))
    return max(MIN_PLAYER_POWER, min(MAX_PLAYER_POWER, raw))


def _player_effective_power(player_id: str, players: dict | None = None, now: float | None = None) -> float:
    snapshot = _player_snapshot(player_id, players or {})
    if snapshot is None:
        return DEFAULT_PLAYER_POWER
    if now is None:
        now = _now()
    current = _player_current_power(player_id, players or {})
    last_seen = float(snapshot.get("last_seen", now))
    if now - last_seen <= OFFLINE_POWER_GRACE:
        return current
    return round(current * OFFLINE_POWER_FLOOR_FACTOR, 2)


def get_player_faction(player_id: str, players: dict | None = None) -> str | None:
    snapshot = _player_snapshot(player_id, players or {})
    if snapshot is None:
        return None
    faction = snapshot.get("faction")
    if isinstance(faction, str) and faction:
        return faction
    return None


def get_player_faction_tag(player_id: str, players: dict | None = None) -> str | None:
    faction_name = get_player_faction(player_id, players)
    if not faction_name:
        return None
    with _LOCK:
        faction = _factions.get(faction_name)
        if faction is None:
            return None
        tag = faction.get("tag")
        return tag if isinstance(tag, str) and tag else None


def player_chat_label(player_id: str, players: dict | None = None) -> str:
    tag = get_player_faction_tag(player_id, players)
    if tag:
        return f"[{tag}] {player_id}"
    return player_id


def create_faction(leader_id: str, name: str, tag: str, players: dict) -> tuple[bool, str]:
    name = _normalize_name(name)
    tag = _normalize_tag(tag)
    if len(name) < 3:
        return False, "Faction name must be at least 3 characters."
    if len(tag) < 2:
        return False, "Faction tag must be at least 2 characters."
    with _LOCK:
        if name in _factions:
            return False, "That faction name is already taken."
        if any(f.get("tag") == tag for f in _factions.values()):
            return False, "That faction tag is already taken."
    if get_player_faction(leader_id, players):
        return False, "You are already in a faction."
    snapshot = _player_snapshot(leader_id, players)
    if snapshot is None:
        return False, "Player not found."
    snapshot["faction"] = name
    snapshot.setdefault("faction_power", DEFAULT_PLAYER_POWER)
    snapshot["last_seen"] = _now()
    save_player(leader_id, snapshot)
    if leader_id in players:
        players[leader_id]["faction"] = name
        players[leader_id]["faction_power"] = snapshot["faction_power"]
    with _LOCK:
        _factions[name] = {
            "tag": tag,
            "leader": leader_id,
            "officers": [],
            "members": [leader_id],
            "claimed_chunks": [],
            "created_at": _now(),
        }
        _save()
    return True, f"Faction {name} [{tag}] created."


def invite_player(inviter_id: str, target_id: str, players: dict) -> tuple[bool, str]:
    inviter_faction = get_player_faction(inviter_id, players)
    if not inviter_faction:
        return False, "You are not in a faction."
    with _LOCK:
        faction = _factions.get(inviter_faction)
        if faction is None:
            return False, "Your faction data is missing."
        if inviter_id != faction.get("leader") and inviter_id not in faction.get("officers", []):
            return False, "Only the leader or officers can invite players."
        if target_id not in players:
            return False, f"Player '{target_id}' is not online."
        if get_player_faction(target_id, players):
            return False, f"{target_id} is already in a faction."
        _invites[target_id] = inviter_faction
        tag = faction.get("tag", "")
    return True, f"Invited {target_id} to [{tag}] {inviter_faction}."


def get_pending_invite(player_id: str) -> str | None:
    with _LOCK:
        return _invites.get(player_id)


def accept_invite(player_id: str, players: dict) -> tuple[bool, str]:
    if get_player_faction(player_id, players):
        return False, "You are already in a faction."
    with _LOCK:
        faction_name = _invites.pop(player_id, None)
        faction = _factions.get(faction_name) if faction_name else None
        if faction is None:
            return False, "You do not have a pending faction invite."
        if player_id not in faction["members"]:
            faction["members"].append(player_id)
        _save()
        tag = faction.get("tag", "")
    snapshot = _player_snapshot(player_id, players)
    if snapshot is None:
        return False, "Player not found."
    snapshot["faction"] = faction_name
    snapshot.setdefault("faction_power", DEFAULT_PLAYER_POWER)
    snapshot["last_seen"] = _now()
    save_player(player_id, snapshot)
    if player_id in players:
        players[player_id]["faction"] = faction_name
        players[player_id]["faction_power"] = snapshot["faction_power"]
    return True, f"You joined [{tag}] {faction_name}."


def leave_faction(player_id: str, players: dict) -> tuple[bool, str]:
    faction_name = get_player_faction(player_id, players)
    if not faction_name:
        return False, "You are not in a faction."
    with _LOCK:
        faction = _factions.get(faction_name)
        if faction is None:
            return False, "Your faction data is missing."
        if faction.get("leader") == player_id:
            del _factions[faction_name]
            _save()
            msg = f"Faction {faction_name} was disbanded."
            affected_members = list(faction.get("members", []))
        else:
            affected_members = [player_id]
            if player_id in faction.get("members", []):
                faction["members"].remove(player_id)
            if player_id in faction.get("officers", []):
                faction["officers"].remove(player_id)
            _save()
            msg = f"You left {faction_name}."
    for member_id in affected_members:
        snapshot = _player_snapshot(member_id, players)
        if snapshot is None:
            continue
        snapshot.pop("faction", None)
        snapshot["last_seen"] = _now()
        save_player(member_id, snapshot)
        if member_id in players:
            players[member_id].pop("faction", None)
    return True, msg


def get_faction_info(faction_name: str, players: dict) -> dict | None:
    with _LOCK:
        faction = _factions.get(faction_name)
        if faction is None:
            return None
        out = dict(faction)
    members = list(out.get("members", []))
    now = _now()
    current_power = sum(_player_current_power(pid, players) for pid in members)
    effective_power = sum(_player_effective_power(pid, players, now) for pid in members)
    out["current_power"] = round(current_power, 2)
    out["effective_power"] = round(effective_power, 2)
    out["claim_capacity"] = int(effective_power)
    out["overclaimed_by"] = max(0, len(out.get("claimed_chunks", [])) - int(effective_power))
    return out


def get_player_power(player_id: str, players: dict, now: float | None = None) -> tuple[float, float]:
    if now is None:
        now = _now()
    return (
        round(_player_current_power(player_id, players), 2),
        round(_player_effective_power(player_id, players, now), 2),
    )


def _chunk_key_from_tile(tile_x: int, tile_y: int) -> tuple[int, int]:
    return tile_x // CHUNK_SIZE, tile_y // CHUNK_SIZE


def _claim_list_to_set(claims: list) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for claim in claims or []:
        if isinstance(claim, (list, tuple)) and len(claim) == 2:
            out.add((int(claim[0]), int(claim[1])))
    return out


def get_chunk_owner(cx: int, cy: int) -> str | None:
    with _LOCK:
        for faction_name, faction in _factions.items():
            if (cx, cy) in _claim_list_to_set(faction.get("claimed_chunks", [])):
                return faction_name
    return None


def get_chunk_owner_for_tile(tile_x: int, tile_y: int) -> str | None:
    cx, cy = _chunk_key_from_tile(tile_x, tile_y)
    return get_chunk_owner(cx, cy)


def get_claim_overlays(players: dict | None = None) -> list[dict]:
    overlays: list[dict] = []
    with _LOCK:
        for faction_name, faction in _factions.items():
            tag = faction.get("tag")
            for cx, cy in _claim_list_to_set(faction.get("claimed_chunks", [])):
                overlays.append({
                    "owner": faction_name,
                    "tag": tag if isinstance(tag, str) else None,
                    "chunk": [cx, cy],
                })
    overlays.sort(key=lambda entry: (entry["owner"], entry["chunk"][1], entry["chunk"][0]))
    return overlays


def can_build_at(player_id: str, tile_x: int, tile_y: int, players: dict | None = None) -> bool:
    owner = get_chunk_owner_for_tile(tile_x, tile_y)
    if owner is None:
        return True
    return get_player_faction(player_id, players or {}) == owner


def faction_can_claim_more(faction_name: str, players: dict) -> tuple[bool, str]:
    info = get_faction_info(faction_name, players)
    if info is None:
        return False, "Faction not found."
    claim_capacity = int(info.get("claim_capacity", 0))
    claimed = len(info.get("claimed_chunks", []))
    if claimed >= claim_capacity:
        return False, f"Your faction can only support {claim_capacity} claimed chunks right now."
    return True, ""


def claim_chunk_for_player(player_id: str, tile_x: int, tile_y: int, players: dict) -> tuple[bool, str]:
    faction_name = get_player_faction(player_id, players)
    if not faction_name:
        return False, "You are not in a faction."
    cx, cy = _chunk_key_from_tile(tile_x, tile_y)
    with _LOCK:
        faction = _factions.get(faction_name)
        if faction is None:
            return False, "Your faction data is missing."
        my_claims = _claim_list_to_set(faction.get("claimed_chunks", []))
        if (cx, cy) in my_claims:
            return False, "Your faction already owns this chunk."
        owner = None
        owner_info = None
        for other_name, other_faction in _factions.items():
            other_claims = _claim_list_to_set(other_faction.get("claimed_chunks", []))
            if (cx, cy) in other_claims:
                owner = other_name
                owner_info = other_faction
                break
        ok, reason = faction_can_claim_more(faction_name, players)
        if not ok:
            return False, reason
        if owner is None:
            my_claims.add((cx, cy))
            faction["claimed_chunks"] = [list(c) for c in sorted(my_claims)]
            _save()
            return True, f"Claimed chunk ({cx}, {cy}) for {faction_name}."
        info = get_faction_info(owner, players)
        if info is None or info.get("overclaimed_by", 0) <= 0:
            return False, f"Chunk ({cx}, {cy}) belongs to {owner}."
        owner_claims = _claim_list_to_set(owner_info.get("claimed_chunks", []))
        owner_claims.discard((cx, cy))
        owner_info["claimed_chunks"] = [list(c) for c in sorted(owner_claims)]
        my_claims.add((cx, cy))
        faction["claimed_chunks"] = [list(c) for c in sorted(my_claims)]
        _save()
        return True, f"Captured overclaimed chunk ({cx}, {cy}) from {owner}."


def unclaim_chunk_for_player(player_id: str, tile_x: int, tile_y: int, players: dict) -> tuple[bool, str]:
    faction_name = get_player_faction(player_id, players)
    if not faction_name:
        return False, "You are not in a faction."
    cx, cy = _chunk_key_from_tile(tile_x, tile_y)
    with _LOCK:
        faction = _factions.get(faction_name)
        if faction is None:
            return False, "Your faction data is missing."
        claims = _claim_list_to_set(faction.get("claimed_chunks", []))
        if (cx, cy) not in claims:
            return False, "Your faction does not own this chunk."
        claims.discard((cx, cy))
        faction["claimed_chunks"] = [list(c) for c in sorted(claims)]
        _save()
    return True, f"Unclaimed chunk ({cx}, {cy})."


def apply_death_penalty(player_id: str, players: dict, now: float | None = None) -> tuple[float, float]:
    if now is None:
        now = _now()
    snapshot = _player_snapshot(player_id, players)
    if snapshot is None:
        return DEFAULT_PLAYER_POWER, DEFAULT_PLAYER_POWER
    current = float(snapshot.get("faction_power", DEFAULT_PLAYER_POWER))
    new_power = max(MIN_PLAYER_POWER, current - DEATH_POWER_LOSS)
    snapshot["faction_power"] = round(new_power, 2)
    snapshot["last_seen"] = now
    save_player(player_id, snapshot)
    if player_id in players:
        players[player_id]["faction_power"] = snapshot["faction_power"]
        players[player_id]["last_seen"] = now
    return get_player_power(player_id, players, now=now)


def refresh_online_player_power(player_id: str, players: dict) -> float:
    snapshot = _player_snapshot(player_id, players)
    if snapshot is None:
        return DEFAULT_PLAYER_POWER
    current = float(snapshot.get("faction_power", DEFAULT_PLAYER_POWER))
    last_seen = float(snapshot.get("last_seen", _now()))
    now = _now()
    delta_hours = max(0.0, now - last_seen) / 3600.0
    if delta_hours > 0:
        current = min(MAX_PLAYER_POWER, current + delta_hours * POWER_REGEN_PER_HOUR)
    snapshot["faction_power"] = round(current, 2)
    snapshot["last_seen"] = now
    save_player(player_id, snapshot)
    if player_id in players:
        players[player_id]["faction_power"] = snapshot["faction_power"]
        players[player_id]["last_seen"] = now
    return snapshot["faction_power"]


def touch_player_seen(player_id: str, players: dict) -> None:
    if player_id in players:
        players[player_id]["last_seen"] = _now()


_load()

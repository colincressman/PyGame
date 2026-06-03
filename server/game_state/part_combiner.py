"""server/game_state/part_combiner.py

Validates and executes Part Combiner requests.

Takes 4 inventory slot indices (mold, primary, handle, binding),
validates part compatibility, computes final stats, and produces
a meta_dict item in the player's inventory.

The output meta dict follows the standard format read by _get_slot_stats():
  {"stats": {...}, "dur": N, "dur_max": N, "traits": [...], "parts": [...], "gem_slots": N}
"""

import random
from server.item_data import get_item
from server.shared_lock import players_lock
from server.game_state.crafting import _roll_quality
from server.game_state.mold_data import MOLD_DATA

# Primary slot type → suffix to strip from the item name to get the material
_SLOT_NAME_SUFFIX: dict[str, str] = {
    "blade":    " Blade",
    "pick_head": " Pick Head",
    "axe_head":  " Axe Head",
    "plate":    " Plate",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _part_stats(inv: list, idx: int) -> dict | None:
    """Return part_stats dict for the item at inventory index idx, or None."""
    slot = inv[idx] if 0 <= idx < len(inv) else None
    if slot is None:
        return None
    return get_item(slot[0]).get("part_stats")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def combine_parts(
    player_id: str,
    mold_idx: int,
    primary_idx: int,
    handle_idx: int,
    binding_idx: int,
    players: dict,
    nearby_stations: list | None = None,
) -> tuple[bool, str]:
    """
    Validate the four inventory slots, consume one of each, and place the
    combined item into the first free bag slot.

    Returns (True, '') on success or (False, reason_string) on failure.
    """
    if nearby_stations is not None and "part_combiner" not in nearby_stations:
        return False, "not near part_combiner"

    with players_lock:
        player = players.get(player_id)
        if not player:
            return False, "player not found"
        inv = player["inventory"]

        # All indices must be in bag range (0-35)
        for idx in (mold_idx, primary_idx, handle_idx, binding_idx):
            if not (isinstance(idx, int) and 0 <= idx < 36):
                return False, f"invalid slot index {idx}"

        mold_slot    = inv[mold_idx]
        primary_slot = inv[primary_idx]
        handle_slot  = inv[handle_idx]
        binding_slot = inv[binding_idx]

        if any(s is None for s in (mold_slot, primary_slot, handle_slot, binding_slot)):
            return False, "empty slot"

        # ── Validate mold ─────────────────────────────────────────────────
        mold_id = mold_slot[0]
        mold_entry = MOLD_DATA.get(mold_id)
        if mold_entry is None:
            return False, "not a mold"
        base_item_id = mold_entry["base_item_id"]
        is_armor = mold_entry["is_armor"]
        required_p2_slot = mold_entry["primary_slot"]

        # ── Validate primary (slot 2) ──────────────────────────────────────
        p2 = _part_stats(inv, primary_idx)
        if p2 is None or p2.get("slot") != required_p2_slot:
            return False, f"primary must be a {required_p2_slot}"

        # ── Validate handle / core / lining (slot 3) ─────────────────────
        # Armor molds use a lining here; weapon/tool molds use a handle or core.
        p3 = _part_stats(inv, handle_idx)
        _valid_p3 = ("lining",) if is_armor else ("handle", "core")
        if p3 is None or p3.get("slot") not in _valid_p3:
            label = "lining" if is_armor else "handle or core"
            return False, f"slot 3 must be a {label}"

        # ── Validate binding (slot 4) ──────────────────────────────────────
        p4 = _part_stats(inv, binding_idx)
        if p4 is None or p4.get("slot") != "binding":
            return False, "slot 4 must be a binding"

        # ── Stat formula ───────────────────────────────────────────────────
        dur = (
            p2.get("base_dur", 100)
            + p3.get("dur_bonus", 0)
            + p4.get("dur_bonus", 0)
        )
        speed_bonus = round(p3.get("speed_mult", 1.0) - 1.0, 4)

        _pick_mining_damage: int | None = None
        _pick_mining_tier:   str | None = None

        if is_armor:
            stats: dict = {
                "defense":    p2.get("base_def", 0),
                "health_max": p2.get("base_hp", 0),
            }
        elif required_p2_slot == "pick_head":
            # Pickaxes: no combat ATK — mining_damage comes from head only (not handle)
            _pick_mining_damage = max(1, p2.get("base_mining", 0))
            _pick_mining_tier   = p2.get("mining_tier", "pickaxe")
            stats = {}  # no attack_power
        else:
            atk = p2.get("base_atk", 0) + p3.get("atk_bonus", 0)
            stats = {"attack_power": atk}

        if speed_bonus != 0.0:
            stats["speed_bonus"] = speed_bonus

        traits: list[str] = list(dict.fromkeys(
            t for t in (p2.get("trait"), p3.get("trait"), p4.get("trait")) if t
        ))

        gem_slots = (
            p2.get("gem_slots", 0)
            + p3.get("gem_slots", 0)
            + p4.get("gem_slots", 0)
        )

        meta: dict = {
            "stats":   stats,
            "dur":     dur,
            "dur_max": dur,
            "traits":  traits,
            "parts":   [mold_id, primary_slot[0], handle_slot[0], binding_slot[0]],
        }

        # ── Quality roll ───────────────────────────────────────────────────
        quality, lo, hi = _roll_quality()
        # Scale all numeric stats by a random mult in [lo, hi]
        for k, v in list(meta["stats"].items()):
            if isinstance(v, (int, float)) and k not in ("speed_bonus",):
                mult = random.uniform(lo, hi)
                meta["stats"][k] = max(1, round(v * mult)) if isinstance(v, int) else round(v * mult, 4)
        # Scale durability
        dur_mult = random.uniform(lo, hi)
        meta["dur"] = meta["dur_max"] = max(10, round(dur * dur_mult))
        meta["quality"] = quality
        if gem_slots > 0:
            meta["gem_slots"] = gem_slots
        if _pick_mining_damage is not None:
            # Apply the same quality mult to mining damage
            mine_mult = random.uniform(lo, hi)
            meta["mining_damage"] = max(1, round(_pick_mining_damage * mine_mult))
        if _pick_mining_tier is not None:
            meta["mining_tier"] = _pick_mining_tier

        # ── Derive material-based item name ────────────────────────────────
        # Strip the slot-type suffix from the primary part's name to get the
        # material prefix (e.g. "Steel Pick Head" → "Steel"; "Obsidian Blade" → "Obsidian").
        primary_item_name = get_item(primary_slot[0]).get("name", "")
        suffix = _SLOT_NAME_SUFFIX.get(required_p2_slot, "")
        if suffix and primary_item_name.endswith(suffix):
            material = primary_item_name[: -len(suffix)]
        else:
            material = primary_item_name.split()[0] if primary_item_name else ""
        weapon_type = mold_entry.get("output_name", get_item(base_item_id).get("name", ""))
        if material:
            meta["name"]     = f"{material} {weapon_type}"
            meta["material"] = material

        # ── Inventory space check ──────────────────────────────────────────
        # Mold is permanent — only primary/handle/binding are consumed
        input_idxs = {primary_idx, handle_idx, binding_idx}
        will_free  = sum(1 for i in input_idxs if inv[i] is not None and inv[i][1] == 1)
        free_now   = sum(1 for i in range(36) if inv[i] is None and i not in input_idxs)
        if free_now + will_free < 1:
            return False, "no inventory space"

        # ── Consume 1 of each input (mold is NOT consumed) ────────────────
        for idx in (primary_idx, handle_idx, binding_idx):
            s = inv[idx]
            inv[idx] = [s[0], s[1] - 1] if s[1] > 1 else None

        # ── Place result in first free bag slot ────────────────────────────
        result = [base_item_id, 1, meta]
        for i in range(36):
            if inv[i] is None:
                inv[i] = result
                break

        base_name  = get_item(base_item_id).get("name", f"Item {base_item_id}")
        trait_str  = ", ".join(traits) if traits else "—"
        print(
            f"[COMBINER] {player_id} forged {base_name} | "
            f"traits=[{trait_str}] | dur={dur} | stats={stats}"
        )
        return True, ""

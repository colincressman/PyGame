"""Shared loader for repair material rules."""

import json
import os

_DATA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "repair.json")
)

_RANGE_REPAIR: list[tuple[tuple[int, int], int, int]] = []
_PART_TO_MAT: dict[int, tuple[int, int]] = {}
_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(f"[REPAIR] Failed to load repair data from {_DATA_PATH}: {e}") from e

    for entry in raw.get("range_rules", []):
        if not isinstance(entry, dict):
            continue
        lo = entry.get("min_id")
        hi = entry.get("max_id")
        mat_id = entry.get("material_id")
        qty = entry.get("qty")
        if not all(isinstance(v, int) for v in (lo, hi, mat_id, qty)):
            continue
        _RANGE_REPAIR.append(((lo, hi), mat_id, qty))

    for part_id, entry in raw.get("part_rules", {}).items():
        if not isinstance(entry, dict):
            continue
        try:
            pid = int(part_id)
        except (TypeError, ValueError):
            continue
        mat_id = entry.get("material_id")
        qty = entry.get("qty")
        if not isinstance(mat_id, int) or not isinstance(qty, int):
            continue
        _PART_TO_MAT[pid] = (mat_id, qty)


def get_repair_cost(slot: list) -> tuple[int, int] | None:
    """Return (material_item_id, qty) or None if item is not repairable."""
    _load()
    item_id = slot[0]
    meta = slot[2] if len(slot) > 2 and isinstance(slot[2], dict) else {}

    parts = meta.get("parts")
    if parts and len(parts) >= 2:
        result = _PART_TO_MAT.get(parts[1])
        if result:
            return result

    for (lo, hi), mat_id, qty in _RANGE_REPAIR:
        if lo <= item_id < hi:
            return mat_id, qty

    return None

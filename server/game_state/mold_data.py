"""Shared loader for Part Combiner mold metadata."""

import json
import os

_DATA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "molds.json")
)

MOLD_DATA: dict[int, dict] = {}


def _load() -> None:
    global MOLD_DATA
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(f"[MOLDS] Failed to load mold data from {_DATA_PATH}: {e}") from e

    data: dict[int, dict] = {}
    for mold_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            mid = int(mold_id)
        except (TypeError, ValueError):
            continue
        base_item_id = entry.get("base_item_id")
        output_name = entry.get("output_name")
        primary_slot = entry.get("primary_slot")
        is_armor = bool(entry.get("is_armor", False))
        if not isinstance(base_item_id, int):
            continue
        if not isinstance(output_name, str) or not output_name:
            continue
        if not isinstance(primary_slot, str) or not primary_slot:
            continue
        data[mid] = {
            "base_item_id": base_item_id,
            "is_armor": is_armor,
            "output_name": output_name,
            "primary_slot": primary_slot,
        }
    MOLD_DATA = data


_load()


def get_mold_entry(mold_id: int) -> dict | None:
    return MOLD_DATA.get(mold_id)

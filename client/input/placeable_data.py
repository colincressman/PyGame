import json
import os


def _load() -> tuple[dict[int, str], frozenset[str], frozenset[str]]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "placeables.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    placeable_items: dict[int, str] = {}
    floor_types: set[str] = set()
    walkable_types: set[str] = set()
    for entry in raw.get("placeables", []):
        item_id = int(entry["item_id"])
        obj_type = str(entry["type"])
        placeable_items[item_id] = obj_type
        if entry.get("floor"):
            floor_types.add(obj_type)
        if entry.get("walkable", not entry.get("solid")):
            walkable_types.add(obj_type)
    return placeable_items, frozenset(floor_types), frozenset(walkable_types)


PLACEABLE_ITEMS, FLOOR_TYPES, WALKABLE_TYPES = _load()

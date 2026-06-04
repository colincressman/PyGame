import json
import os


def _load() -> tuple[dict[int, str], frozenset[str], frozenset[str], dict[str, int], dict[str, str], frozenset[str]]:
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
    solid_types: set[str] = set()
    grow_times: dict[str, int] = {}
    grows_into: dict[str, str] = {}
    nonsolid_types: set[str] = set()

    for entry in raw.get("placeables", []):
        item_id = int(entry["item_id"])
        obj_type = str(entry["type"])
        placeable_items[item_id] = obj_type
        if entry.get("floor"):
            floor_types.add(obj_type)
        if entry.get("solid"):
            solid_types.add(obj_type)
        else:
            nonsolid_types.add(obj_type)
        if "grow_time" in entry:
            grow_times[obj_type] = int(entry["grow_time"])
        if "grows_into" in entry:
            grows_into[obj_type] = str(entry["grows_into"])

    return (
        placeable_items,
        frozenset(floor_types),
        frozenset(solid_types),
        grow_times,
        grows_into,
        frozenset(nonsolid_types),
    )


(
    PLACEABLE_ITEMS,
    FLOOR_TYPES,
    SOLID_TYPES,
    GROW_TIMES,
    GROWS_INTO,
    NONSOLID_TYPES,
) = _load()
ITEM_FOR_TYPE = {v: k for k, v in PLACEABLE_ITEMS.items()}


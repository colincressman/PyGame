import json
import os


def _load() -> dict[int, dict]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "gems.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {int(item_id): entry for item_id, entry in raw.items()}


GEM_DATA = _load()
GEM_IDS = frozenset(GEM_DATA)
GEM_COLORS = {
    entry.get("trait"): tuple(entry.get("color", [200, 200, 200]))
    for entry in GEM_DATA.values()
    if entry.get("trait")
}


def get_gem_entry(item_id: int) -> dict | None:
    return GEM_DATA.get(int(item_id))

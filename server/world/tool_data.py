import json
import os


def _load() -> tuple[dict[str, set[int]], dict[int, int], dict[str, int]]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "tools.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    tool_items = {
        tool_type: {int(item_id) for item_id in item_ids}
        for tool_type, item_ids in raw.get("tool_items", {}).items()
    }
    tool_damage = {
        int(item_id): int(damage)
        for item_id, damage in raw.get("tool_damage", {}).items()
    }
    pick_tier_rank = {
        str(tool_type): int(rank)
        for tool_type, rank in raw.get("pick_tier_rank", {}).items()
    }
    return tool_items, tool_damage, pick_tier_rank


TOOL_ITEMS, TOOL_DAMAGE, PICK_TIER_RANK = _load()

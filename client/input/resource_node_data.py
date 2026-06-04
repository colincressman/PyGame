import json
import os


def _load() -> tuple[dict[str, int], dict[str, str], dict[str, float], set[str], dict[str, float], dict[str, float]]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "resource_nodes.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    max_hp = {
        str(node_type): int(entry.get("hp", 1))
        for node_type, entry in raw.items()
    }
    node_tool = {
        str(node_type): str(entry["tool"])
        for node_type, entry in raw.items()
        if entry.get("tool") is not None
    }
    render_scale = {
        str(node_type): float(entry["render_scale"])
        for node_type, entry in raw.items()
        if "render_scale" in entry
    }
    y_sorted = {
        str(node_type)
        for node_type, entry in raw.items()
        if entry.get("y_sorted")
    }
    collision_r = {
        str(node_type): float(entry["collision_radius"])
        for node_type, entry in raw.items()
        if "collision_radius" in entry
    }
    collision_cy = {
        str(node_type): float(entry["collision_center_y"])
        for node_type, entry in raw.items()
        if "collision_center_y" in entry
    }
    return max_hp, node_tool, render_scale, y_sorted, collision_r, collision_cy


(
    NODE_MAX_HP,
    NODE_TOOL_REQUIREMENTS,
    NODE_RENDER_SCALE,
    Y_SORTED_NODES,
    NODE_COLLISION_R,
    NODE_COLLISION_CY,
) = _load()

NODE_SIZE_DEFAULT = 0.65
BLOCKING_NODES = {
    node_type
    for node_type, radius in NODE_COLLISION_R.items()
    if radius > 0.0
}


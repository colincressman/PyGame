import json
import os

from server.world.world_types import BIOME_ID_MAP


def _load() -> dict[str, dict]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "resource_nodes.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    node_types: dict[str, dict] = {}
    for node_type, entry in raw.items():
        node_def = dict(entry)
        node_def["hp"] = int(node_def.get("hp", 1))
        node_def["respawn"] = int(node_def.get("respawn", 0))
        node_def["density"] = float(node_def.get("density", 0.0))
        if "min_dist" in node_def:
            node_def["min_dist"] = float(node_def["min_dist"])
        if "tool" in node_def:
            node_def["tool"] = node_def["tool"]
        node_def["yields"] = [
            (int(yield_def["item_id"]), int(yield_def["min"]), int(yield_def["max"]))
            for yield_def in node_def.get("yields", [])
        ]
        spawn_biomes = [str(name) for name in node_def.get("spawn_biomes", [])]
        node_def["spawn_biomes"] = spawn_biomes
        node_def["biomes"] = frozenset(
            BIOME_ID_MAP[name]
            for name in spawn_biomes
            if name in BIOME_ID_MAP
        )
        seed_drop = node_def.get("seed_drop")
        if isinstance(seed_drop, dict):
            node_def["seed_drop"] = (
                int(seed_drop["item_id"]),
                float(seed_drop["chance"]),
            )
        node_types[str(node_type)] = node_def
    return node_types


NODE_TYPES = _load()


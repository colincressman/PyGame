import json
import os


def _load() -> tuple[dict[str, int], dict[str, int], frozenset[int]]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "world_types.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    biome_id_map = {
        str(name): int(biome_id)
        for name, biome_id in raw.get("biomes", {}).items()
    }
    cliff_id_map = {
        str(name): int(cliff_id)
        for name, cliff_id in raw.get("cliffs", {}).items()
    }
    water_biomes = frozenset(
        biome_id_map[name]
        for name in raw.get("water_biomes", [])
        if name in biome_id_map
    )
    return biome_id_map, cliff_id_map, water_biomes


BIOME_ID_MAP, CLIFF_ID_MAP, WATER_BIOMES = _load()
ID_TO_BIOME = {v: k for k, v in BIOME_ID_MAP.items()}
ID_TO_CLIFF = {v: k for k, v in CLIFF_ID_MAP.items()}


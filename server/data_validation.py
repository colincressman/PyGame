"""Lightweight validation for gameplay data registries.

These checks focus on the cross-file references that can break core loops:
crafting, shops, placeables, resource gathering, tool gating, and mob drops.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_items(root: Path) -> dict[int, dict]:
    raw = _load_json(root / "server" / "items.json")
    return {int(item_id): entry for item_id, entry in raw.items()}


def validate_game_data(root: Path | None = None) -> list[str]:
    root = Path(root) if root is not None else ROOT
    errors: list[str] = []

    items = _load_items(root)
    item_ids = set(items)

    recipes = _load_json(root / "server" / "recipes.json")
    world_types = _load_json(root / "data" / "world_types.json")
    tools = _load_json(root / "data" / "tools.json")
    placeables = _load_json(root / "data" / "placeables.json")
    resource_nodes = _load_json(root / "data" / "resource_nodes.json")
    repair = _load_json(root / "data" / "repair.json")

    biome_names = set(world_types.get("biomes", {}))
    tool_types = set(tools.get("tool_items", {}))
    node_types = set(resource_nodes)

    for recipe_id, recipe in recipes.items():
        result = recipe.get("result", [])
        if len(result) >= 1 and result[0] not in item_ids:
            errors.append(f"recipe {recipe_id} result item {result[0]} missing from items.json")
        for ingredient in recipe.get("ingredients", []):
            if len(ingredient) >= 1 and ingredient[0] not in item_ids:
                errors.append(
                    f"recipe {recipe_id} ingredient item {ingredient[0]} missing from items.json"
                )

    shops_dir = root / "data" / "shops"
    for shop_path in sorted(shops_dir.glob("*.json")):
        entries = _load_json(shop_path)
        for index, entry in enumerate(entries):
            item_id = entry.get("id")
            if item_id not in item_ids:
                errors.append(
                    f"shop {shop_path.stem} entry {index} item {item_id} missing from items.json"
                )

    for index, entry in enumerate(placeables.get("placeables", [])):
        item_id = entry.get("item_id")
        placeable_type = entry.get("type")
        if item_id not in item_ids:
            errors.append(f"placeable {placeable_type} item {item_id} missing from items.json")
        grows_into = entry.get("grows_into")
        if grows_into is not None and grows_into not in node_types:
            errors.append(
                f"placeable {placeable_type} grows_into {grows_into} missing from resource_nodes.json"
            )
        if "grow_time" in entry and not isinstance(entry["grow_time"], int):
            errors.append(f"placeable {placeable_type} has non-integer grow_time")

    for node_name, node in resource_nodes.items():
        for yield_def in node.get("yields", []):
            item_id = yield_def.get("item_id")
            if item_id not in item_ids:
                errors.append(
                    f"resource node {node_name} yield item {item_id} missing from items.json"
                )
        seed_drop = node.get("seed_drop")
        if isinstance(seed_drop, dict) and seed_drop.get("item_id") not in item_ids:
            errors.append(
                f"resource node {node_name} seed item {seed_drop.get('item_id')} missing from items.json"
            )
        for biome_name in node.get("spawn_biomes", []):
            if biome_name not in biome_names:
                errors.append(
                    f"resource node {node_name} spawn biome {biome_name} missing from world_types.json"
                )
        tool_name = node.get("tool")
        if tool_name is not None and tool_name not in tool_types:
            errors.append(f"resource node {node_name} tool {tool_name} missing from tools.json")

    for tool_name, ids in tools.get("tool_items", {}).items():
        for item_id in ids:
            if item_id not in item_ids:
                errors.append(f"tool group {tool_name} item {item_id} missing from items.json")
    for item_id in tools.get("tool_damage", {}):
        parsed_id = int(item_id)
        if parsed_id not in item_ids:
            errors.append(f"tool damage item {parsed_id} missing from items.json")

    for part_id, entry in repair.get("part_rules", {}).items():
        if int(part_id) not in item_ids:
            errors.append(f"repair part item {part_id} missing from items.json")
        material_id = entry.get("material_id")
        if material_id not in item_ids:
            errors.append(
                f"repair part item {part_id} material {material_id} missing from items.json"
            )
    for index, entry in enumerate(repair.get("range_rules", [])):
        material_id = entry.get("material_id")
        if material_id not in item_ids:
            errors.append(
                f"repair range rule {index} material {material_id} missing from items.json"
            )

    mobs_dir = root / "data" / "mobs"
    for mob_path in sorted(mobs_dir.glob("*.json")):
        mob = _load_json(mob_path)
        mob_name = mob_path.stem
        drop_id = mob.get("drop_id")
        if drop_id is not None and drop_id not in item_ids:
            errors.append(f"mob {mob_name} drop item {drop_id} missing from items.json")
        for biome_name in mob.get("spawn_biomes", []):
            if biome_name not in biome_names:
                errors.append(
                    f"mob {mob_name} spawn biome {biome_name} missing from world_types.json"
                )
        sprite = mob.get("sprite")
        if not isinstance(sprite, dict):
            errors.append(f"mob {mob_name} missing sprite config")
            continue
        sprite_type = sprite.get("type")
        if not sprite_type:
            errors.append(f"mob {mob_name} sprite missing type")
            continue
        if sprite_type == "procedural":
            if not sprite.get("key"):
                errors.append(f"mob {mob_name} sprite missing key")
        elif not sprite.get("path"):
            errors.append(f"mob {mob_name} sprite missing path")

    return errors

import json
import os


def _load() -> tuple[dict, dict[str, dict]]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "projectiles.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("globals", {}), raw.get("elements", {})


PROJECTILE_GLOBALS, PROJECTILE_ELEMENTS = _load()

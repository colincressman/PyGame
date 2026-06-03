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
PROJECTILE_COLORS = {
    element: (
        tuple(entry.get("core_color", [200, 200, 200])),
        tuple(entry.get("glow_color", [140, 140, 140])),
    )
    for element, entry in PROJECTILE_ELEMENTS.items()
}

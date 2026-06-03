import json
import os


def _load() -> dict[str, dict]:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "status_effects.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


STATUS_EFFECTS = _load()

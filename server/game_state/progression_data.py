import json
import os


def _load() -> dict:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "data",
        "progression.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_DATA = _load()
CRAFT_QUALITY_TIERS = _DATA.get("craft_quality_tiers", [])
LOOT_QUALITY_TIERS = _DATA.get("loot_quality_tiers", [])
QUALITY_SELL_MULT = _DATA.get("quality_sell_mult", {})
STAT_UPGRADES = _DATA.get("stat_upgrades", {})

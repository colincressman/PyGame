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
QUALITY_SELL_MULT = _DATA.get("quality_sell_mult", {})
QUALITY_COLORS = {
    key: tuple(value)
    for key, value in {
        tier["name"]: tier.get("color", [200, 200, 200])
        for tier in CRAFT_QUALITY_TIERS
    }.items()
}
QUALITY_BORDERS = {
    key: tuple(value)
    for key, value in {
        tier["name"]: tier.get("border", [120, 120, 120])
        for tier in CRAFT_QUALITY_TIERS
    }.items()
}
QUALITY_ABBR = {
    tier["name"]: tier.get("abbr", tier["name"])
    for tier in CRAFT_QUALITY_TIERS
}
STAT_LABELS = _DATA.get("stat_labels", {})
STAT_ABBR = _DATA.get("stat_abbr", {})
STAT_NAMES = _DATA.get("stat_names", {})
STAT_UPGRADES = _DATA.get("stat_upgrades", {})

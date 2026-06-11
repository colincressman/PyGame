import json
import os


def _load_replication_config() -> dict:
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "replication.json",
    )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


_CFG = _load_replication_config()
REMOTE_PLAYER_CFG = dict(_CFG.get("remote_player", {}))
REMOTE_MOB_CFG = dict(_CFG.get("remote_mob", {}))

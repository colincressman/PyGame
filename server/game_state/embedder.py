"""server/game_state/embedder.py

Embed-gem logic: consumes one gem from the player's inventory and adds
meta["gem"] / meta["gem_trait"] to the target item in-place.

Rules:
  - The target item must have at least one gem_slot in its meta (set by Part Combiner).
  - Each item may only hold one gem (one slot used at a time).
  - The gem is consumed; the target item gains meta["gem"] = gem_name and
    meta["gem_trait"] = trait_str (e.g. "Fire").
  - A gem can be removed by a Gem Extractor (future feature) - not implemented here.
"""

from server.game_state.gem_data import get_gem_entry
from server.item_data import get_item
from server.shared_lock import players_lock


def embed_gem(
    player_id: str,
    item_slot: int,
    gem_slot: int,
    players: dict,
    nearby_stations: list | None = None,
) -> tuple[bool, str]:
    """
    Embed the gem at `gem_slot` into the item at `item_slot`.

    Returns (True, '') on success or (False, reason) on failure.
    """
    if nearby_stations is not None and "embedder" not in nearby_stations:
        return False, "not near embedder"

    with players_lock:
        player = players.get(player_id)
        if not player:
            return False, "player not found"
        inv = player["inventory"]

        for idx in (item_slot, gem_slot):
            if not (isinstance(idx, int) and 0 <= idx < 36):
                return False, f"invalid slot index {idx}"
        if item_slot == gem_slot:
            return False, "item and gem must be different slots"

        target = inv[item_slot]
        gem = inv[gem_slot]

        if target is None:
            return False, "no item in target slot"
        if gem is None:
            return False, "no gem in gem slot"

        gem_id = gem[0]
        gem_entry = get_gem_entry(gem_id)
        if gem_entry is None:
            return False, "not a gem"

        # Target must have meta with gem_slots > 0.
        meta = target[2] if len(target) >= 3 and isinstance(target[2], dict) else None
        if meta is None:
            return False, "target item has no gem slots (not a combined item)"
        if meta.get("gem_slots", 0) < 1:
            return False, "target item has no gem slots"
        if meta.get("gem"):
            return False, "item already has a gem embedded"

        trait = gem_entry["trait"]
        gem_name = get_item(gem_id).get("name", f"Gem {gem_id}")

        meta["gem"] = gem_name
        meta["gem_trait"] = trait
        traits = meta.get("traits", [])
        if trait not in traits:
            traits.append(trait)
            meta["traits"] = traits

        if gem[1] > 1:
            inv[gem_slot] = [gem_id, gem[1] - 1]
        else:
            inv[gem_slot] = None

        print(
            f"[EMBEDDER] {player_id} embedded {gem_name} ({trait}) "
            f"into slot {item_slot} ({meta.get('name', target[0])})"
        )
        return True, ""

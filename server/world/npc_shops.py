"""server/world/npc_shops.py

Defines per-NPC-type shop inventories and handles server-side buy/sell logic.

Shop item format:
    {"id": item_id, "name": str, "price": int, "qty": int}

Buy price is charged to the player; sell price (via item_data.get_sell_price)
is paid to the player when selling back.
"""

import json
import os
import copy

from server.config import NPC_BUY_PRICE_FLOOR as _BUY_PRICE_FLOOR
from server.config import NPC_BUY_PRICE_MULT as _BUY_PRICE_MULT
from server.item_data import get_item, get_sell_price

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "shops")
)


def _load_shops() -> dict[str, list[dict[str, int]]]:
    shops: dict[str, list[dict[str, int]]] = {}
    try:
        filenames = sorted(os.listdir(_DATA_DIR))
    except OSError as e:
        print(f"[SHOPS] Could not list shop data at {_DATA_DIR}: {e}")
        return shops

    for fname in filenames:
        if not fname.endswith(".json"):
            continue
        npc_type = fname[:-5]
        path = os.path.join(_DATA_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                raw_entries = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[SHOPS] Could not load {path}: {e}")
            continue

        if not isinstance(raw_entries, list):
            print(f"[SHOPS] Ignoring {path}: expected a JSON array.")
            continue

        entries: list[dict[str, int]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("id")
            qty = entry.get("qty", 1)
            if not isinstance(item_id, int) or not isinstance(qty, int) or qty <= 0:
                continue
            entries.append({"id": item_id, "qty": qty})
        shops[npc_type] = entries

    return shops


# Buy price is roughly 2-3x sell_price to maintain a coin sink.
_SHOPS: dict[str, list[dict[str, int]]] = _load_shops()

# Dynamic per-NPC-type inventory; items sold back by players appear here.
_dynamic_inv: dict[str, list] = {}


def _add_exact_slot(player: dict, slot: list) -> bool:
    """Add an exact inventory slot back into a player's bag, preserving metadata."""
    if slot is None or len(slot) < 2:
        return False
    item_id = slot[0]
    qty = slot[1]
    meta = slot[2] if len(slot) >= 3 and isinstance(slot[2], dict) else None
    item_def = get_item(item_id)
    if not item_def:
        return False
    stackable = item_def.get("stackable", False)
    max_stack = item_def.get("max_stack", 1)
    inv = player["inventory"]

    # Only merge plain stackables. Meta-bearing slots must stay distinct.
    if stackable and meta is None:
        remaining = qty
        for i in range(36):
            existing = inv[i]
            if existing is not None and len(existing) < 3 and existing[0] == item_id:
                space = max_stack - existing[1]
                if space > 0:
                    add = min(space, remaining)
                    existing[1] += add
                    remaining -= add
                if remaining == 0:
                    return True
        qty = remaining

    for i in range(36):
        if inv[i] is None:
            restored = [item_id, qty]
            if meta is not None:
                restored.append(copy.deepcopy(meta))
            inv[i] = restored
            return True
    return False


def _static_shop_len(npc_type: str) -> int:
    """Count of resolvable static items for *npc_type*."""
    return sum(1 for e in _SHOPS.get(npc_type, []) if get_item(e["id"]) is not None)


def get_shop(npc_type: str) -> list:
    """Return annotated shop list for *npc_type*, with resolved names and prices.

    Returns [{"id", "name", "price", "qty"}, ...] or [] if unknown type.
    Static items appear first; player-sold buyback items follow.
    """
    raw = _SHOPS.get(npc_type, [])
    result = []
    for entry in raw:
        iid = entry["id"]
        idef = get_item(iid)
        if idef is None:
            continue
        sell_p = get_sell_price([iid, 1])
        price = max(_BUY_PRICE_FLOOR, int(sell_p * _BUY_PRICE_MULT))
        result.append({
            "id": iid,
            "name": idef.get("name", f"Item {iid}"),
            "price": price,
            "qty": entry["qty"],
        })

    for dyn in _dynamic_inv.get(npc_type, []):
        result.append(dict(dyn))
    return result


def handle_shop_buy(
    player_id: str,
    npc_type: str,
    shop_slot: int,
    players: dict,
    give_item_fn,
) -> tuple[bool, str]:
    """Attempt to buy slot *shop_slot* from the NPC's shop."""
    shop = get_shop(npc_type)
    if not (0 <= shop_slot < len(shop)):
        return False, "Invalid shop slot."
    entry = shop[shop_slot]
    price = entry["price"]
    item_id = entry["id"]
    qty = 1

    player = players.get(player_id)
    if player is None:
        return False, "Player not found."
    if player.get("coins", 0) < price:
        return False, f"Not enough coins (need {price})."

    player["coins"] -= price
    if shop_slot >= _static_shop_len(npc_type):
        dyn_idx = shop_slot - _static_shop_len(npc_type)
        dyn = _dynamic_inv.get(npc_type, [])
        if not (0 <= dyn_idx < len(dyn)):
            player["coins"] += price
            return False, "Buyback item no longer exists."
        dyn_entry = dyn[dyn_idx]
        slot_payload = dyn_entry.get("slot")
        ok = _add_exact_slot(player, slot_payload) if slot_payload is not None else give_item_fn(player, item_id, qty)
        if not ok:
            player["coins"] += price
            return False, "No inventory space."
        dyn.pop(dyn_idx)
    else:
        give_item_fn(player, item_id, qty)
    print(f"[SHOP] {player_id} bought item {item_id} from {npc_type} for {price}c")
    return True, "ok"


def handle_shop_sell(
    player_id: str,
    inv_slot: int,
    npc_type: str,
    players: dict,
) -> tuple[bool, str]:
    """Sell an inventory slot to the NPC shop and add it to buyback stock."""
    player = players.get(player_id)
    if player is None:
        return False, "Player not found."
    inv = player.get("inventory", [])
    if not (0 <= inv_slot < len(inv)) or inv[inv_slot] is None:
        return False, "No item in that slot."

    item = inv[inv_slot]
    price = get_sell_price(item)
    if price <= 0:
        return False, "That item cannot be sold."

    item_id = item[0]
    qty = item[1] if len(item) > 1 else 1
    idef = get_item(item_id)
    meta = item[2] if len(item) >= 3 and isinstance(item[2], dict) else None

    inv[inv_slot] = None
    player["coins"] = player.get("coins", 0) + price
    print(f"[SHOP] {player_id} sold slot {inv_slot} (item {item_id} x{qty}) to {npc_type} for {price}c")

    buyback_price = max(_BUY_PRICE_FLOOR, int(price * _BUY_PRICE_MULT))
    dyn = _dynamic_inv.setdefault(npc_type, [])
    name = idef.get("name", f"Item {item_id}") if idef else f"Item {item_id}"
    if meta is None and idef and idef.get("stackable", False):
        for entry in dyn:
            if entry["id"] == item_id and entry.get("slot") is None:
                entry["qty"] += qty
                break
        else:
            dyn.append({"id": item_id, "name": name, "price": buyback_price, "qty": qty})
    else:
        dyn.append({
            "id": item_id,
            "name": name,
            "price": buyback_price,
            "qty": 1,
            "slot": copy.deepcopy(item),
        })

    return True, "ok"

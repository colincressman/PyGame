"""server/world/npc_shops.py

Defines per-NPC-type shop inventories and handles server-side buy/sell logic.

Shop item format:
    {"id": item_id, "name": str, "price": int, "qty": int}

Buy price is charged to the player; sell price (via item_data.get_sell_price)
is paid to the player when selling back.
"""
from server.item_data import get_item, get_sell_price
from server.config import NPC_BUY_PRICE_MULT as _BUY_PRICE_MULT, NPC_BUY_PRICE_FLOOR as _BUY_PRICE_FLOOR

# ---------------------------------------------------------------------------
# Shop catalogue (item_id → buy price, capped qty per purchase)
# ---------------------------------------------------------------------------
# Buy price is roughly 2-3× sell_price to maintain a coin sink.
_MERCHANT_SHOP = [
    {"id": 4000, "qty": 64},   # Herb Tea (Heals 25 HP)
    {"id": 4001, "qty": 32},   # Mushroom Stew (Heals 40 HP)
    {"id": 100,  "qty": 64},   # Iron Bar
    {"id": 101,  "qty": 64},   # Copper Bar
    {"id": 120,  "qty": 64},   # Stone Brick
    {"id": 10,   "qty": 64},   # Wood
    {"id": 12,   "qty": 64},   # Stick
]

_BLACKSMITH_SHOP = [
    {"id": 1100, "qty": 1},    # Iron Dagger
    {"id": 1101, "qty": 1},    # Iron Sword
    {"id": 1102, "qty": 1},    # Iron Mace
    {"id": 3002, "qty": 1},    # Iron Helm
    {"id": 3103, "qty": 1},    # Iron Chestplate
    {"id": 3401, "qty": 1},    # Iron Boots
    {"id": 3278, "qty": 1},    # Iron Gloves
    {"id": 100,  "qty": 64},   # Iron Bar (repairs / crafting)
    {"id": 101,  "qty": 64},   # Copper Bar
    {"id": 102,  "qty": 64},   # Tin Bar
]

_HEALER_SHOP = [
    {"id": 4000, "qty": 64},   # Herb Tea
    {"id": 4001, "qty": 32},   # Mushroom Stew
    {"id": 4002, "qty": 16},   # Healing Potion
]

_INNKEEPER_SHOP = [
    {"id": 4000, "qty": 32},   # Herb Tea
    {"id": 4001, "qty": 16},   # Mushroom Stew
]

_SHOPS: dict[str, list] = {
    "merchant":   _MERCHANT_SHOP,
    "blacksmith": _BLACKSMITH_SHOP,
    "healer":     _HEALER_SHOP,
    "innkeeper":  _INNKEEPER_SHOP,
}

# Dynamic per-NPC-type inventory — items sold back by players appear here
_dynamic_inv: dict[str, list] = {}


def _static_shop_len(npc_type: str) -> int:
    """Count of resolvable static items for *npc_type*."""
    return sum(1 for e in _SHOPS.get(npc_type, []) if get_item(e["id"]) is not None)


def get_shop(npc_type: str) -> list:
    """Return annotated shop list for *npc_type*, with resolved names and prices.

    Returns [{"id", "name", "price", "qty"}, …] or [] if unknown type.
    Static items appear first; player-sold (buyback) items follow.
    """
    raw = _SHOPS.get(npc_type, [])
    result = []
    for entry in raw:
        iid  = entry["id"]
        idef = get_item(iid)
        if idef is None:
            continue
        sell_p = get_sell_price([iid, 1])
        price  = max(_BUY_PRICE_FLOOR, int(sell_p * _BUY_PRICE_MULT))
        result.append({
            "id":    iid,
            "name":  idef.get("name", f"Item {iid}"),
            "price": price,
            "qty":   entry["qty"],
        })
    # Append player-sold buyback items
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
    """Attempt to buy slot *shop_slot* from the NPC's shop.

    Parameters
    ----------
    player_id : str
    npc_type : str           — "merchant" | "blacksmith" | "healer" | "innkeeper"
    shop_slot : int          — index into get_shop(npc_type)
    players : dict           — shared players dict (caller holds players_lock)
    give_item_fn             — give_item(player_data, item_id, qty)

    Returns (success, message).
    """
    shop = get_shop(npc_type)
    if not (0 <= shop_slot < len(shop)):
        return False, "Invalid shop slot."
    entry  = shop[shop_slot]
    price  = entry["price"]
    item_id = entry["id"]
    qty    = 1

    player = players.get(player_id)
    if player is None:
        return False, "Player not found."
    if player.get("coins", 0) < price:
        return False, f"Not enough coins (need {price})."

    player["coins"] -= price
    give_item_fn(player, item_id, qty)
    print(f"[SHOP] {player_id} bought item {item_id} from {npc_type} for {price}c")
    # Reduce dynamic-inventory qty when buying back a player-sold item
    static_len = _static_shop_len(npc_type)
    if shop_slot >= static_len:
        dyn_idx = shop_slot - static_len
        dyn = _dynamic_inv.get(npc_type, [])
        if 0 <= dyn_idx < len(dyn):
            dyn[dyn_idx]["qty"] -= 1
            if dyn[dyn_idx]["qty"] <= 0:
                dyn.pop(dyn_idx)
    return True, "ok"


def handle_shop_sell(
    player_id: str,
    inv_slot: int,
    npc_type: str,
    players: dict,
) -> tuple[bool, str]:
    """Sell item in *inv_slot* to the NPC shop — player gets sell price,
    item moves into the merchant's dynamic buyback stock.

    Parameters
    ----------
    player_id : str
    inv_slot : int           — inventory slot index (0-44)
    npc_type : str           — which NPC's stock to add the item to
    players : dict           — shared players dict (caller holds players_lock)

    Returns (success, message).
    """
    player = players.get(player_id)
    if player is None:
        return False, "Player not found."
    inv = player.get("inventory", [])
    if not (0 <= inv_slot < len(inv)) or inv[inv_slot] is None:
        return False, "No item in that slot."

    item  = inv[inv_slot]
    price = get_sell_price(item)
    if price <= 0:
        return False, "That item cannot be sold."

    item_id = item[0]
    qty     = item[1] if len(item) > 1 else 1
    idef    = get_item(item_id)

    inv[inv_slot] = None
    player["coins"] = player.get("coins", 0) + price
    print(f"[SHOP] {player_id} sold slot {inv_slot} (item {item_id} ×{qty}) to {npc_type} for {price}c")

    # Add to merchant's dynamic buyback stock at a higher price
    buyback_price = max(_BUY_PRICE_FLOOR, int(price * _BUY_PRICE_MULT))
    dyn = _dynamic_inv.setdefault(npc_type, [])
    for entry in dyn:
        if entry["id"] == item_id:
            entry["qty"] += qty
            break
    else:
        name = idef.get("name", f"Item {item_id}") if idef else f"Item {item_id}"
        dyn.append({"id": item_id, "name": name, "price": buyback_price, "qty": qty})

    return True, "ok"

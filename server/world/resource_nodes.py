"""server/world/resource_nodes.py

Resource node system: definitions, deterministic placement, runtime state (HP, respawn).

Node IDs use the format "{cx}:{cy}:{idx}" — colons handle negative coordinates safely.

Biome IDs match dyn_chunk_gen.py:
  0=ocean  1=beach  2=swamp  3=river  4=plains  5=forest
  6=desert 7=alt_desert 8=tropical 9=tundra 10=mountain
"""

import random
import math
import os
import json
import uuid
import time
import threading
import atexit

# ---- Biome ID constants (match dyn_chunk_gen.py) ----
OCEAN, BEACH, SWAMP, RIVER, PLAINS, FOREST = 0, 1, 2, 3, 4, 5
DESERT, ALT_DESERT, TROPICAL, TUNDRA, MOUNTAIN = 6, 7, 8, 9, 10

# _CHUNK_SIZE and _CHUNK_DIR come from server config; _PADDING is local world-gen detail
from server.config import CHUNK_SIZE as _CHUNK_SIZE, CHUNK_DIR as _CHUNK_DIR, WORLD_SEED as _WORLD_SEED
_PADDING    = 1

# ---- Node type definitions ----
# yields: [(item_id, min_qty, max_qty)]
# tool:   None | "axe" | "pickaxe" | "pickaxe_stone"
# density: per-tile spawn probability in allowed biomes
NODE_TYPES: dict[str, dict] = {
    "tree":          {"hp": 6, "yields": [(10, 2, 4), (12, 1, 2)],  "tool": "axe",           "respawn": 120,  "density": 0.045, "biomes": {FOREST, PLAINS},                           "permanent": True, "seed_drop": (34, 0.20)},
    "pine_tree":     {"hp": 6, "yields": [(43, 2, 4), (12, 1, 2)], "tool": "axe",           "respawn": 120,  "density": 0.040, "biomes": {TUNDRA, MOUNTAIN},                          "permanent": True, "seed_drop": (46, 0.20)},
    "jungle_tree":   {"hp": 8, "yields": [(44, 2, 5), (12, 1, 2)], "tool": "axe",           "respawn": 150,  "density": 0.050, "biomes": {TROPICAL},                                  "permanent": True, "seed_drop": (47, 0.20)},
    "palm_tree":     {"hp": 5, "yields": [(45, 2, 4), (12, 1, 1)], "tool": "axe",           "respawn": 100,  "density": 0.035, "biomes": {BEACH},                                    "permanent": True, "seed_drop": (48, 0.20)},
    "stick_pile":    {"hp": 1, "yields": [(12, 2, 4)],              "tool": None,            "respawn": 45,   "density": 0.022, "biomes": {FOREST, PLAINS, TROPICAL}},
    "stone_deposit": {"hp": 20, "yields": [(11, 1, 3)],              "tool": "pickaxe",       "respawn": 180,  "density": 0.028, "biomes": {MOUNTAIN, TUNDRA, PLAINS}},
    "iron_ore":      {"hp": 20, "yields": [(21, 1, 2)],             "tool": "pickaxe_stone", "respawn": 300,  "density": 0.003, "biomes": {MOUNTAIN},                "min_dist": 3,   "permanent": True, "seed_drop": (35, 0.04)},
    "coal_deposit":  {"hp": 20, "yields": [(20, 1, 2)],             "tool": "pickaxe",       "respawn": 240,  "density": 0.008, "biomes": {MOUNTAIN, TUNDRA},        "min_dist": 2,   "permanent": True, "seed_drop": (36, 0.04)},
    "herb_patch":    {"hp": 1, "yields": [(13,  1, 2)],             "tool": None,           "respawn": 60,   "density": 0.018, "biomes": {PLAINS, FOREST, SWAMP}},
    "cactus":        {"hp": 2, "yields": [(15,  1, 3)],             "tool": None,           "respawn": 90,   "density": 0.012, "biomes": {DESERT, ALT_DESERT}},
    "reed_cluster":  {"hp": 1, "yields": [(18, 2, 4)],             "tool": None,           "respawn": 60,   "density": 0.014, "biomes": {SWAMP, RIVER}},
    "seashell_bed":  {"hp": 1, "yields": [(17,  1, 3)],             "tool": None,           "respawn": 60,   "density": 0.012, "biomes": {BEACH}},
    "mushroom":      {"hp": 1, "yields": [(14,  1, 2)],             "tool": None,           "respawn": 60,   "density": 0.012, "biomes": {SWAMP, FOREST}},
    "snow_crystal":  {"hp": 1, "yields": [(16,  1, 2)],             "tool": None,           "respawn": 60,   "density": 0.016, "biomes": {TUNDRA}},
    "bone_pile":     {"hp": 1, "yields": [(19, 2, 4)],             "tool": None,           "respawn": 120,  "density": 0.012, "biomes": {DESERT, ALT_DESERT}},
    "clay_deposit":  {"hp": 2, "yields": [(30, 2, 4)],             "tool": None,           "respawn": 90,   "density": 0.018, "biomes": {RIVER, SWAMP, PLAINS, BEACH}},
    # --- Distance-gated ores (min_dist = chunk distance from origin) ---
    "copper_ore":   {"hp": 25, "yields": [(22, 1, 2)], "tool": "pickaxe_stone", "respawn": 240, "density": 0.004, "biomes": {MOUNTAIN, PLAINS},         "min_dist": 15, "permanent": True, "seed_drop": (37, 0.025)},
    "tin_ore":      {"hp": 25, "yields": [(23, 1, 2)], "tool": "pickaxe_stone", "respawn": 240, "density": 0.003, "biomes": {MOUNTAIN, DESERT},         "min_dist": 15, "permanent": True, "seed_drop": (38, 0.025)},
    "silver_ore":   {"hp": 30, "yields": [(24, 1, 2)], "tool": "pickaxe_iron",  "respawn": 360, "density": 0.003, "biomes": {MOUNTAIN, TUNDRA},         "min_dist": 50, "permanent": True, "seed_drop": (39, 0.015)},
    "gold_ore":     {"hp": 35, "yields": [(25, 1, 2)], "tool": "pickaxe_iron",  "respawn": 420, "density": 0.002, "biomes": {MOUNTAIN, DESERT},         "min_dist": 75, "permanent": True, "seed_drop": (40, 0.010)},
    "crystal":      {"hp": 40, "yields": [(26, 1, 1)], "tool": "pickaxe_steel", "respawn": 600, "density": 0.001, "biomes": {MOUNTAIN},                 "min_dist": 100, "permanent": True, "seed_drop": (41, 0.008)},
    "obsidian":     {"hp": 50, "yields": [(27, 1, 1)], "tool": "pickaxe_steel", "respawn": 720, "density": 0.001, "biomes": {MOUNTAIN},                 "min_dist": 130, "permanent": True, "seed_drop": (42, 0.005)},
}

# Item IDs satisfying each tool tier (higher tiers also satisfy lower ones)
TOOL_ITEMS: dict[str, set[int]] = {
    "axe":            {2000, 2050, 2051, 2100, 2150, 2200, 2250, 2300, 2350, 2400},
    "pickaxe":        {2001, 2052, 2053, 2101, 2151, 2201, 2251, 2301, 2351, 2401},
    "pickaxe_stone":  {2053, 2101, 2151, 2201, 2251, 2301, 2351, 2401},  # stone+ (incl. copper/bronze — better than iron)
    "pickaxe_iron":   {2101, 2151, 2201, 2251, 2301, 2351, 2401},       # iron+ (incl. copper/bronze/steel/gold/crystal)
    "pickaxe_steel":  {2251, 2301, 2351, 2401},                          # steel/gold/crystal/obsidian only
}

# Damage per hit for each tool item (higher tier = more damage per F press)
TOOL_DAMAGE: dict[int, int] = {
    # Axes — tree HP = 6
    2000: 1,  # Scrap Axe    (6 hits)
    2050: 2,  # Wooden Axe   (3 hits)
    2051: 3,  # Stone Axe    (2 hits)
    2100: 5,  # Iron Axe     (2 hits)
    2150: 6,  # Copper Axe   (1 hit)
    2200: 8,  # Bronze Axe
    2250: 10, # Steel Axe
    2300: 12, # Gold Axe
    2350: 14, # Crystal Axe
    2400: 16, # Obsidian Axe
    # Pickaxes
    2001: 1,  # Scrap Pickaxe
    2052: 1,  # Wooden Pickaxe
    2053: 2,  # Stone Pickaxe  (stone/coal hp=20 → 10 hits)
    2101: 4,  # Iron Pickaxe   (iron hp=20 → 5 hits)
    2151: 5,  # Copper Pickaxe (copper/tin hp=25 → 5 hits)
    2201: 7,  # Bronze Pickaxe (silver hp=30 → 5 hits)
    2251: 8,  # Steel Pickaxe  (crystal hp=40 → 5 hits; obsidian hp=50 → 7 hits)
    2301: 9,  # Gold Pickaxe   (crystal hp=40 → 5 hits; obsidian hp=50 → 6 hits)
    2351: 12, # Crystal Pick   (crystal hp=40 → 4 hits; obsidian hp=50 → 5 hits)
    2401: 18, # Obsidian Pickaxe (crystal hp=40 → 3 hits; obsidian hp=50 → 3 hits)
}

# Tier rank for combined-tool (meta-based) tier checks. Higher = better.
_PICK_TIER_RANK: dict[str, int] = {
    "pickaxe":       0,
    "pickaxe_stone": 1,
    "pickaxe_iron":  2,
    "pickaxe_steel": 3,
}

# ---- Runtime node state (in-memory; resets on server restart) ----
_state_lock    = threading.Lock()
_node_hp:               dict[str, int]   = {}  # node_id → current HP (absent = full HP)
_node_respawn:          dict[str, float] = {}  # node_id → Unix timestamp when respawn finishes
_node_restore_data:     dict[str, dict]  = {}  # node_id → original node dict for cache restoration
_permanently_depleted:  set[str]         = set()  # node IDs that never auto-respawn
_planted_nodes:         dict[str, dict]  = {}     # planted_id → {type, wx, wy}

_PERM_PATH     = os.path.join(_CHUNK_DIR, "perm_depleted.json")
_PLANTED_PATH  = os.path.join(_CHUNK_DIR, "planted_nodes.json")
_RESPAWN_PATH  = os.path.join(_CHUNK_DIR, "node_respawn.json")


def _load_persistence() -> None:
    global _permanently_depleted, _planted_nodes, _node_respawn
    try:
        with open(_PERM_PATH) as f:
            _permanently_depleted = set(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[NODES] perm_depleted load error: {e}")
    try:
        with open(_PLANTED_PATH) as f:
            _planted_nodes = json.load(f)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[NODES] planted_nodes load error: {e}")
    try:
        now = time.time()
        with open(_RESPAWN_PATH) as f:
            raw = json.load(f)
        # Only keep entries whose respawn time is still in the future
        _node_respawn = {k: v for k, v in raw.items() if v > now}
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[NODES] node_respawn load error: {e}")


def _save_persistence_sync() -> None:
    """Write all persistence files synchronously (used by atexit)."""
    with _state_lock:
        perm_snap     = list(_permanently_depleted)
        planted_snap  = dict(_planted_nodes)
        respawn_snap  = dict(_node_respawn)
    try:
        os.makedirs(_CHUNK_DIR, exist_ok=True)
        with open(_PERM_PATH,    "w") as f:
            json.dump(perm_snap,    f)
        with open(_PLANTED_PATH, "w") as f:
            json.dump(planted_snap, f)
        with open(_RESPAWN_PATH, "w") as f:
            json.dump(respawn_snap, f)
    except Exception as e:
        print(f"[NODES] persistence save error: {e}")


def _save_persistence_async() -> None:
    """Write all persistence files on a background thread."""
    with _state_lock:
        perm_snap     = list(_permanently_depleted)
        planted_snap  = dict(_planted_nodes)
        respawn_snap  = dict(_node_respawn)
    def _write():
        try:
            os.makedirs(_CHUNK_DIR, exist_ok=True)
            with open(_PERM_PATH,    "w") as f:
                json.dump(perm_snap,    f)
            with open(_PLANTED_PATH, "w") as f:
                json.dump(planted_snap, f)
            with open(_RESPAWN_PATH, "w") as f:
                json.dump(respawn_snap, f)
        except Exception as e:
            print(f"[NODES] persistence save error: {e}")
    threading.Thread(target=_write, daemon=False, name="nodes-persist").start()


_load_persistence()
atexit.register(_save_persistence_sync)

# ---- Broadcast queue: recent state changes sent to all clients ----
_bcast_lock   = threading.Lock()
_bcast_log:   list[dict] = []  # [{node_id, depleted, ts}, ...]
_BCAST_WINDOW = 8.0            # seconds to retain entries


# ---------------------------------------------------------------------------
# Node generation
# ---------------------------------------------------------------------------

def generate_resource_nodes(cx: int, cy: int, biome_ids) -> list[dict]:
    """Deterministically generate resource nodes for a 16×16 chunk.

    biome_ids: 2D array shape (CHUNK_SIZE+2, CHUNK_SIZE+2) with PADDING=1.
               Index as [lx + PADDING, ly + PADDING] for core tile (lx, ly).
    Returns list of {"id": str, "type": str, "lx": int, "ly": int}.
    """
    rng = random.Random((cx * 73856093) ^ (cy * 19349663) ^ _WORLD_SEED)
    nodes: list[dict] = []
    occupied: set[tuple] = set()
    chunk_dist = math.sqrt(cx * cx + cy * cy)  # Euclidean distance from origin in chunks

    for node_type, defn in NODE_TYPES.items():
        if chunk_dist < defn.get("min_dist", 0):
            continue
        allowed = defn["biomes"]
        density = defn["density"]
        for lx in range(_CHUNK_SIZE):
            for ly in range(_CHUNK_SIZE):
                biome = int(biome_ids[lx + _PADDING, ly + _PADDING])
                if biome not in allowed or (lx, ly) in occupied:
                    continue
                if rng.random() < density:
                    idx = len(nodes)
                    node_id = f"{cx}:{cy}:{idx}"
                    nodes.append({"id": node_id, "type": node_type, "lx": lx, "ly": ly})
                    # Enforce minimum 1-tile spacing
                    for ddx in (-1, 0, 1):
                        for ddy in (-1, 0, 1):
                            occupied.add((lx + ddx, ly + ddy))
    return nodes


# ---------------------------------------------------------------------------
# Node state queries
# ---------------------------------------------------------------------------

def is_depleted(node_id: str) -> bool:
    if node_id.startswith("planted:"):
        with _state_lock:
            return node_id not in _planted_nodes
    with _state_lock:
        rt = _node_respawn.get(node_id)
        if rt is not None:
            return time.time() < rt
        if node_id in _permanently_depleted:
            return True
    return False


def damage_node(node_id: str, node_def: dict, damage: int = 1) -> list[tuple] | None:
    """Deal `damage` points of damage to a node.

    Returns:
        None               — node is currently depleted (can't interact)
        []                 — damaged but not yet destroyed
        [(item_id, qty)]   — destroyed; loot list
    """
    is_planted = node_id.startswith("planted:")
    null_cache_slot = False   # set True when we need to zero the chunk cache entry
    restore_data    = None    # original node dict to save for timed-respawn restoration

    with _state_lock:
        if is_planted:
            if node_id not in _planted_nodes:
                return None   # already harvested
        else:
            if node_id in _permanently_depleted:
                return None
            if node_id in _node_respawn and time.time() < _node_respawn[node_id]:
                return None
        max_hp  = node_def["hp"]
        current = _node_hp.get(node_id, max_hp) - damage
        if current <= 0:
            _node_hp[node_id] = 0
            destroyed = True
            if is_planted:
                del _planted_nodes[node_id]
            elif node_def.get("permanent"):
                # Permanent nodes (trees, ores with seeds) don't auto-respawn.
                # Players can regrow them by planting the seed/sapling drop.
                _permanently_depleted.add(node_id)
                null_cache_slot = True
            else:
                _node_respawn[node_id] = time.time() + node_def["respawn"]
                null_cache_slot = True
        else:
            _node_hp[node_id] = current
            destroyed = False

    # Null out the chunk_nodes_cache slot OUTSIDE the state lock to avoid
    # nested lock acquisition (_state_lock → chunk_nodes_lock is fine, but
    # doing it separately is simpler and safe).
    if null_cache_slot and not is_planted:
        try:
            parts = node_id.split(":")
            cx, cy, idx = int(parts[0]), int(parts[1]), int(parts[2])
            from server.world.dyn_chunk_gen import chunk_nodes_cache, chunk_nodes_lock
            with chunk_nodes_lock:
                nodes = chunk_nodes_cache.get((cx, cy))
                if nodes and 0 <= idx < len(nodes) and nodes[idx] is not None:
                    if not node_def.get("permanent"):
                        # Save for restoration when respawn fires
                        restore_data = nodes[idx]
                    nodes[idx] = None
        except (ValueError, IndexError):
            pass
        if restore_data is not None:
            with _state_lock:
                _node_restore_data[node_id] = restore_data

    _record_update(node_id, depleted=destroyed)
    if destroyed:
        _save_persistence_async()

    if destroyed:
        rng  = random.Random(hash(node_id) ^ (int(time.time() * 1000) & 0xFFFF))
        loot = [(iid, rng.randint(mn, mx)) for iid, mn, mx in node_def["yields"]]
        seed_info = node_def.get("seed_drop")
        if seed_info:
            seed_id, seed_chance = seed_info
            if rng.random() < seed_chance:
                loot.append((seed_id, 1))
        return loot
    return []


def _get_node_world_pos(node_id: str):
    """Return (wx, wy) for a node_id, or None if not found."""
    try:
        parts = node_id.split(":")
        cx, cy, idx = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return None
    from server.world.dyn_chunk_gen import chunk_nodes_cache, chunk_nodes_lock
    with chunk_nodes_lock:
        nodes = chunk_nodes_cache.get((cx, cy), [])
        if idx >= len(nodes):
            return None
        node = nodes[idx]
    if node is None:
        return None
    return cx * _CHUNK_SIZE + node["lx"], cy * _CHUNK_SIZE + node["ly"]


def _get_floor_positions() -> frozenset:
    """Return a frozenset of (wx, wy) covered by stone_brick_floor tiles."""
    try:
        from server.game_state.placed_objects import (
            placed_objects as _po_dict, placed_objects_lock as _po_lock
        )
        with _po_lock:
            return frozenset(
                (o["pos"][0], o["pos"][1])
                for o in _po_dict.values()
                if o["type"] == "stone_brick_floor"
            )
    except Exception:
        return frozenset()


def tick_respawns() -> list[str]:
    """Expire finished respawns.  Returns list of node_ids that just came back."""
    now = time.time()
    respawned = []
    to_restore = []  # (nid, node_dict) pairs for cache restoration
    # Snapshot floor positions once for O(1) lookup across all respawn candidates
    floor_positions = _get_floor_positions()
    with _state_lock:
        for nid, rt in list(_node_respawn.items()):
            if nid in _permanently_depleted:  # belt-and-suspenders: skip permanent
                del _node_respawn[nid]
                continue
            if now >= rt:
                del _node_respawn[nid]
                _node_hp.pop(nid, None)
                # Skip respawn if a floor tile covers this node's position
                wp = _get_node_world_pos(nid)
                if wp is not None and (wp[0], wp[1]) in floor_positions:
                    _node_restore_data.pop(nid, None)
                    continue
                respawned.append(nid)
                node_data = _node_restore_data.pop(nid, None)
                if node_data is not None:
                    to_restore.append((nid, node_data))

    # Restore nodes into chunk_nodes_cache (outside state lock)
    if to_restore:
        from server.world.dyn_chunk_gen import chunk_nodes_cache, chunk_nodes_lock
        with chunk_nodes_lock:
            for nid, node_data in to_restore:
                try:
                    parts = nid.split(":")
                    cx, cy, idx = int(parts[0]), int(parts[1]), int(parts[2])
                    nodes = chunk_nodes_cache.get((cx, cy))
                    if nodes and 0 <= idx < len(nodes):
                        nodes[idx] = node_data
                except (ValueError, IndexError):
                    pass

    for nid in respawned:
        _record_update(nid, depleted=False)
    return respawned


# ---------------------------------------------------------------------------
# Cache depletion helper (called on chunk load to re-apply persisted state)
# ---------------------------------------------------------------------------

def apply_depletions_to_cache(cx: int, cy: int) -> None:
    """Null out cache slots for nodes that are still depleted after a server restart.

    Must be called after chunk_nodes_cache[(cx, cy)] has been populated so that
    persisted _permanently_depleted and _node_respawn state is reflected in the cache.
    """
    now = time.time()
    # Snapshot depletion state without holding chunk_nodes_lock
    with _state_lock:
        perm_snap      = frozenset(_permanently_depleted)
        respawning_ids = frozenset(nid for nid, rt in _node_respawn.items() if rt > now)

    from server.world.dyn_chunk_gen import chunk_nodes_cache, chunk_nodes_lock
    to_save: dict[str, dict] = {}
    with chunk_nodes_lock:
        nodes = chunk_nodes_cache.get((cx, cy))
        if not nodes:
            return
        for i, node in enumerate(nodes):
            if node is None:
                continue
            nid = node["id"]
            if nid in perm_snap:
                nodes[i] = None
            elif nid in respawning_ids:
                to_save[nid] = node  # collect, don't lock-nest
                nodes[i] = None

    # Save restore data outside chunk_nodes_lock to avoid nested lock acquisition
    if to_save:
        with _state_lock:
            for nid, node_data in to_save.items():
                if nid not in _node_restore_data:
                    _node_restore_data[nid] = node_data


# ---------------------------------------------------------------------------
# Planted node API
# ---------------------------------------------------------------------------

def register_planted_node(node_type: str, wx: int, wy: int) -> str:
    """Create a new active planted node at world tile (wx, wy). Returns its ID."""
    planted_id = f"planted:{uuid.uuid4().hex[:8]}"
    with _state_lock:
        _planted_nodes[planted_id] = {"type": node_type, "wx": wx, "wy": wy}
    _save_persistence_async()
    _record_update(planted_id, depleted=False)
    return planted_id


def get_planted_node(planted_id: str) -> dict | None:
    """Return the planted node dict (type, wx, wy) or None if harvested."""
    with _state_lock:
        return dict(_planted_nodes[planted_id]) if planted_id in _planted_nodes else None


def get_planted_snapshot() -> list[dict]:
    """Return all active planted nodes for inclusion in game_state payloads."""
    with _state_lock:
        return [
            {"node_id": nid, "node_type": info["type"],
             "wx": info["wx"], "wy": info["wy"],
             "max_hp": NODE_TYPES[info["type"]]["hp"] if info["type"] in NODE_TYPES else 1}
            for nid, info in _planted_nodes.items()
        ]


# ---------------------------------------------------------------------------
# Tool check
# ---------------------------------------------------------------------------

def has_required_tool(inventory: list, tool_type: str | None) -> bool:
    """True if any inventory slot contains a tool satisfying tool_type."""
    if tool_type is None:
        return True
    required = TOOL_ITEMS.get(tool_type, set())
    req_rank = _PICK_TIER_RANK.get(tool_type, -1)
    for slot in inventory:
        if slot is None:
            continue
        if slot[0] in required:
            return True
        # Check combined tool via meta mining_tier
        if len(slot) > 2 and isinstance(slot[2], dict):
            tier = slot[2].get("mining_tier", "")
            if req_rank >= 0 and _PICK_TIER_RANK.get(tier, -1) >= req_rank:
                return True
    return False


def tool_satisfies(hotbar_item: list | None, tool_type: str | None) -> bool:
    """True if the hotbar item meets the required tool tier (ID-based or meta-based)."""
    if tool_type is None:
        return True
    if hotbar_item is None:
        return False
    if hotbar_item[0] in TOOL_ITEMS.get(tool_type, set()):
        return True
    if len(hotbar_item) > 2 and isinstance(hotbar_item[2], dict):
        req_rank  = _PICK_TIER_RANK.get(tool_type, -1)
        item_rank = _PICK_TIER_RANK.get(hotbar_item[2].get("mining_tier", ""), -1)
        if req_rank >= 0 and item_rank >= req_rank:
            return True
    return False


def tool_mining_damage(hotbar_item: list | None) -> int:
    """Return the mining damage for a hotbar item (handles combined picks via meta)."""
    if hotbar_item is None:
        return 1
    if len(hotbar_item) > 2 and isinstance(hotbar_item[2], dict):
        md = hotbar_item[2].get("mining_damage")
        if md is not None:
            return int(md)
    return TOOL_DAMAGE.get(hotbar_item[0], 1)


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------

def get_recent_updates() -> list[dict]:
    """Return recent node state changes for inclusion in game_state payloads."""
    cutoff = time.time() - _BCAST_WINDOW
    with _bcast_lock:
        _bcast_log[:] = [u for u in _bcast_log if u["ts"] >= cutoff]
        return [{"node_id": u["node_id"], "depleted": u["depleted"]} for u in _bcast_log]


def get_depleted_snapshot() -> list[str]:
    """Return all currently-depleted node IDs (permanent + respawning).

    Used for initial sync when a client first connects so they receive the full
    depleted state rather than relying solely on delta updates (which are lost
    across server restarts).
    """
    now = time.time()
    with _state_lock:
        result = list(_permanently_depleted)
        result.extend(nid for nid, rt in _node_respawn.items() if rt > now)
    return result


def _record_update(node_id: str, depleted: bool) -> None:
    with _bcast_lock:
        _bcast_log.append({"node_id": node_id, "depleted": depleted, "ts": time.time()})

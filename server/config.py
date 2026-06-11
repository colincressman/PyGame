# === Server Settings ===
HOST = '0.0.0.0'

# Port assignments
PORT_WORLD = 6000
PORT_STATE = 6001
PORT_UDP = 6002

# Networking
BUFFER_SIZE = 4096  # Adjust if needed for large world updates
TICK_RATE = 120     # Main game loop update frequency (Hz)
PLAYER_STALE_TIMEOUT = 15.0  # seconds without movement/keepalive before forced cleanup
WORLD_ITEM_DESPAWN_SECONDS = 300.0  # runtime lifetime for dropped world items before auto-unload

# World Generation / Chunking
CHUNK_DIR    = "world_chunks_v3"  # active chunk storage directory (bump version to force regen)
CHUNK_SIZE   = 16       # tiles per chunk (16×16)
CHUNK_RADIUS = 5        # radius of chunks around player to load/generate
WORLD_SEED   = 42       # change to generate a completely different world

# Autosave Settings
SAVE_INTERVAL = 300   # seconds between autosaves (5 minutes)

# Game Limits
MAX_PLAYERS  = 100    # optional player cap
WORLD_RADIUS = 2000   # max tile coordinate from origin (world spans [-2000, 2000])

# ---------------------------------------------------------------------------
# Day / Night cycle
# ---------------------------------------------------------------------------
WORLD_DAY_SECONDS = 600.0   # real seconds per full game day (10 min)
WORLD_START_HOUR  = 12.0    # game-hour (0-24) the server starts at (noon)
DAY_START_HOUR    = 6.0     # dawn — daytime begins
DAY_END_HOUR      = 18.0    # dusk — night begins

# ---------------------------------------------------------------------------
# Respawn
# ---------------------------------------------------------------------------
RESPAWN_DELAY       = 3.0   # seconds between death and respawn
RESPAWN_HP_FRACTION = 0.3   # fraction of max HP restored on respawn
RESPAWN_HP_MIN      = 20.0  # absolute minimum HP on respawn
DEATH_DROP_SLOT_CHANCE = 0.35  # chance an occupied backpack slot drops some contents on death
DEATH_DROP_STACK_FRACTION = 0.5  # fraction of a stack dropped from a chosen slot on death

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
INVENTORY_SIZE = 48   # total slot count including all equipment slots

# ---------------------------------------------------------------------------
# Rendering / Visibility (server-side culling)
# ---------------------------------------------------------------------------
RENDER_DIST_TILES = 50   # tile radius for state sync and placed-object queries

# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------
KNOCKBACK_DECAY     = 12.0  # exponential decay rate applied to knockback velocity
PARRY_WINDOW        = 0.15  # seconds after block-start that counts as a perfect parry
PARRY_STAGGER_DUR   = 0.5   # seconds a mob is staggered after a perfect parry
BLOCK_DAMAGE_MULT   = 0.4   # damage fraction that passes through a normal block
MIN_DAMAGE          = 1.0   # damage floor — no hit deals less than this
BASE_SP_REGEN       = 10.0  # base stamina regen rate (SP per second)
COIN_DROP_MIN_MULT  = 1     # coin drop minimum = mob_level × this
COIN_DROP_MAX_MULT  = 3     # coin drop maximum = mob_level × this
DEFAULT_BURN_DPS    = 5.0   # burn damage per second (fallback when not set per-mob)
DEFAULT_POISON_DPS  = 2.0   # poison damage per second (fallback when not set per-mob)

# ---------------------------------------------------------------------------
# Mob spawning / AI
# ---------------------------------------------------------------------------
SPAWN_RATE_COEFF   = 0.01   # base spawn cadence: SPAWN_INTERVAL = 1/(coeff×TICK_RATE)
MOB_SPAWN_RADIUS   = 30     # tiles from player where mobs may appear
MOB_SPAWN_MIN_DIST = 12     # minimum distance mobs spawn from player
MOB_KNOCKBACK      = 1.5    # tiles player is pushed on mob melee hit
MAX_MOB_LEVEL      = 10     # global mob level cap
MOB_SEP_DIST       = 0.8    # tile distance at which mob-mob separation push begins
MOB_SEP_FORCE      = 3.0    # separation push strength (tiles/sec at full overlap)
STEALTH_AGGRO_MULT = 0.4    # aggro range multiplier when player is sneaking
LEVEL_DIST_SCALE   = 100    # 100 tiles from origin = +1 mob level
EXP_CURVE_BASE     = 50     # EXP curve coefficient: exp_next = base × level × (level+1)

# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------
NPC_BUY_PRICE_MULT  = 2.5   # NPC sell-to-player price = sell_value × this
NPC_BUY_PRICE_FLOOR = 5     # minimum NPC sell-to-player price (coins)

# ---------------------------------------------------------------------------
# World structure spacing
# ---------------------------------------------------------------------------
TOWN_GRID            = 30    # one town per N×N chunk grid cell
NPC_RENDER_DIST      = 80.0  # tile radius for NPC visibility and town build trigger
DUNGEON_GRID         = 25    # one dungeon per N×N chunk grid cell
DUNGEON_TRIGGER_DIST = 8.0   # tiles from dungeon centre that wake the boss
BOSS_RESPAWN_DELAY   = 300.0 # seconds after boss defeat before the dungeon resets

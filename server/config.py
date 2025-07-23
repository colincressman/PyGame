# === Server Settings ===
HOST = '0.0.0.0'

# Port assignments
PORT_WORLD = 6000
PORT_STATE = 6001
PORT_UDP = 6002

# Networking
BUFFER_SIZE = 4096  # Adjust if needed for large world updates
TICK_RATE = 120     # Main game loop update frequency (Hz)

# World Generation / Chunking
CHUNK_DIR = "world_chunks"
CHUNK_SIZE = 16       # Number of tiles per chunk (16x16)
CHUNK_RADIUS = 5      # Radius of chunks around player to load/generate

# Autosave Settings
SAVE_INTERVAL = 300   # In seconds (5 minutes)

# Game Limits
MAX_PLAYERS = 100  # Optional limit

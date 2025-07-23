import time
from server.world.chunk_utils import split_tiles_by_chunk
from server.world.io import save_multiple_chunks
from server.config import SAVE_INTERVAL
from server.shared_lock import world_data_lock

# This reference will be injected
world_data = {}

def autosave_world():
    global world_data
    while True:
        time.sleep(SAVE_INTERVAL)

        with world_data_lock:
            if not world_data:
                continue
            world_snapshot = dict(world_data)

        chunks = split_tiles_by_chunk(world_snapshot)

        if chunks:
            save_multiple_chunks(chunks)
            print(f"[AUTOSAVE] Saved {len(chunks)} chunks.")

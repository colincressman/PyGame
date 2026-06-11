import os
import json
import queue
import threading
from server.config import CHUNK_DIR

try:
    import orjson as _orjson
except ImportError:
    _orjson = None

_save_queue: "queue.Queue[tuple[int, int, dict]]" = queue.Queue()
_save_worker_started = False
_save_worker_lock = threading.Lock()


def _decode_chunk_bytes(raw_bytes: bytes) -> dict:
    payload = _orjson.loads(raw_bytes) if _orjson else json.loads(raw_bytes)
    return payload if isinstance(payload, dict) else {}


def _encode_chunk_bytes(chunk_data: dict) -> bytes:
    serializable = {f"{x},{y}": v for (x, y), v in chunk_data.items()}
    if _orjson is not None:
        return _orjson.dumps(serializable)
    return json.dumps(serializable).encode("utf-8")

def load_chunk(cx, cy):
    """Load a single chunk from file and convert keys back to (x, y) tuples."""
    path = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                raw_data = _decode_chunk_bytes(f.read())
                return {
                    tuple(map(int, key.split(','))): value
                    for key, value in raw_data.items()
                }
        except (ValueError, json.JSONDecodeError, OSError) as e:
            print(f"[IO ERROR] Failed to load chunk ({cx},{cy}): {e}")
    return {}

def save_chunk(cx, cy, chunk_data):
    """Save a single chunk to file using an atomic write (write temp, then rename)."""
    os.makedirs(CHUNK_DIR, exist_ok=True)
    path = os.path.join(CHUNK_DIR, f"chunk_{cx}_{cy}.json")
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(_encode_chunk_bytes(chunk_data))
        os.replace(tmp_path, path)
    except OSError as e:
        print(f"[IO ERROR] Failed to save chunk ({cx},{cy}): {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def save_multiple_chunks(chunk_dict):
    """Queue chunk saves so world generation never blocks on filesystem writes."""
    _ensure_save_worker()
    for (cx, cy), chunk_data in chunk_dict.items():
        snapshot = {
            (x, y): dict(tile) if isinstance(tile, dict) else tile
            for (x, y), tile in chunk_data.items()
        }
        _save_queue.put((cx, cy, snapshot))


def _save_worker() -> None:
    while True:
        cx, cy, chunk_data = _save_queue.get()
        try:
            save_chunk(cx, cy, chunk_data)
        finally:
            _save_queue.task_done()


def _ensure_save_worker() -> None:
    global _save_worker_started
    if _save_worker_started:
        return
    with _save_worker_lock:
        if _save_worker_started:
            return
        threading.Thread(target=_save_worker, daemon=True).start()
        _save_worker_started = True

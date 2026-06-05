import os
from config import LOG_FILE

_CONSOLE_VERBOSE = os.environ.get("PYGAME_M_CONSOLE_LOGS", "").lower() in {"1", "true", "yes", "on"}

def log(level, message):
    entry = f"[{level.upper()}] {message}"
    with open(LOG_FILE, "a") as log_file:
        log_file.write(entry + "\n")
    if _CONSOLE_VERBOSE or level.lower() == "error":
        print(entry)

def log_error(msg): log("error", msg)
def log_info(msg): log("info", msg)

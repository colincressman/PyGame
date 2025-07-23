import os
from config import LOG_FILE

def log(level, message):
    entry = f"[{level.upper()}] {message}"
    with open(LOG_FILE, "a") as log_file:
        log_file.write(entry + "\n")
    print(entry)

def log_error(msg): log("error", msg)
def log_info(msg): log("info", msg)

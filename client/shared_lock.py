import threading

data_lock = threading.Lock()
players_lock = threading.Lock()
queue_lock = threading.Lock()
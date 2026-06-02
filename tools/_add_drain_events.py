"""Add drain_events() to mob_manager.py"""
import os
os.chdir(r"c:\Users\colin\OneDrive\Desktop\Projects\PyGame_Working\PyGame_M")

with open('server/mobs/mob_manager.py', encoding='utf-8') as f:
    content = f.read()

drain_fn = '''

def drain_events() -> list:
    """Return and clear all pending mob events (boss_spawned, boss_defeated, etc.).
    Thread-safe — call from the server game-loop after update_mobs().
    """
    with mobs_lock:
        evts = list(_pending_events)
        _pending_events.clear()
    return evts
'''

with open('server/mobs/mob_manager.py', 'w', encoding='utf-8') as f:
    f.write(content.rstrip() + drain_fn)
print('drain_events added')

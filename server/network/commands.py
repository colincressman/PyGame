"""
server/network/commands.py

Server-side chat command processor.
All commands start with '/'.

== Any player ==
  /help                         list available commands
  /tprequest <player>           request to teleport to a player
  /tpaccept                     accept an incoming tp request
  /tpdeny                       deny an incoming tp request

== Operator only ==
  /heal [player]                restore HP to full
  /repair [player]              repair all inventory items
  /tp <player>                  teleport to a player (instant)
  /op [player]                  grant op (op-only; edit ops.json to set first op)
  /deop <player>                remove op
  /creative [player]            toggle creative mode
  /give <player> <id> [qty]     give item to any player
  /ban <player>                 ban and kick a player
  /unban <player>               remove a ban
  /restart                      restart the server
  /shutdown                     shut down the server
"""

import os
import sys

from server.shared_lock import players_lock
from server.item_data import get_item
from server.ops import (
    is_op, add_op, remove_op,
    ban_player, unban_player,
    op_count, list_ops, list_bans,
)

# Max item ID guard for /give
_MAX_ITEM_ID = 9999

# Pending tp requests: target_player_id -> requester_player_id
_pending_tp: dict[str, str] = {}

# Runtime references injected by server.py at startup
_server_refs: dict = {}


def set_server_refs(refs: dict) -> None:
    """Inject kick_player, broadcast_chat, and save_all_players callables."""
    global _server_refs
    _server_refs = refs


def _reply(text: str) -> dict:
    return {"type": "chat", "sender": "SYSTEM", "text": text}


def _need_op(player_id: str) -> list | None:
    """Return an error reply list if player is not op, else None."""
    if not is_op(player_id):
        return [_reply("Permission denied — you are not an operator.")]
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_command(
    text: str,
    player_id: str,
    players: dict,
    give_item,
) -> list[dict]:
    """Parse and execute a slash command.

    Returns a list of chat packets sent only to the issuing player.
    """
    parts = text.strip().split()
    if not parts:
        return []
    cmd  = parts[0].lower()
    args = parts[1:]

    # ── /help ──────────────────────────────────────────────────────────────
    if cmd == "/help":
        lines = [
            "== General ==",
            "  /tprequest <player> — request to teleport to a player",
            "  /tpaccept          — accept an incoming tp request",
            "  /tpdeny            — deny an incoming tp request",
        ]
        if is_op(player_id):
            lines += [
                "== Operator ==",
                "  /heal [player]           — restore HP to full",
                "  /repair [player]         — repair all items",
                "  /tp <player>             — instant teleport",
                "  /op [player]             — grant op (edit ops.json for first op)",
                "  /deop <player>           — remove op",
                "  /creative [player]       — toggle creative mode",
                "  /give <player> <id> [qty]— give item to player",
                "  /ban <player>            — ban and kick player",
                "  /unban <player>          — remove ban",
                "  /restart                 — restart server",
                "  /shutdown                — shutdown server",
                "  /time set [day, night]   - Set server time",
            ]
        return [_reply(l) for l in lines]

    # ── /tprequest ─────────────────────────────────────────────────────────
    elif cmd == "/tprequest":
        if not args:
            return [_reply("Usage: /tprequest <player>")]
        target = args[0]
        if target == player_id:
            return [_reply("You cannot request a tp to yourself.")]
        with players_lock:
            if target not in players:
                return [_reply(f"Player '{target}' is not online.")]
        _pending_tp[target] = player_id
        stp = _server_refs.get("send_to_player")
        if stp:
            stp(target, _reply(
                f"{player_id} wants to teleport to you. "
                f"Type /tpaccept to allow or /tpdeny to deny."
            ))
        return [_reply(f"Teleport request sent to {target}.")]

    # ── /tpaccept ──────────────────────────────────────────────────────────
    elif cmd == "/tpaccept":
        requester = _pending_tp.pop(player_id, None)
        if requester is None:
            return [_reply("No pending teleport request.")]
        with players_lock:
            if requester not in players:
                return [_reply(f"{requester} is no longer online.")]
            if player_id not in players:
                return []
            players[requester]["pos"] = list(players[player_id].get("pos", [0, 0]))
        stp = _server_refs.get("send_to_player")
        if stp:
            stp(requester, _reply(f"{player_id} accepted your tp request."))
        return [_reply(f"Teleported {requester} to you.")]

    # ── /tpdeny ────────────────────────────────────────────────────────────
    elif cmd == "/tpdeny":
        requester = _pending_tp.pop(player_id, None)
        if requester is None:
            return [_reply("No pending teleport request.")]
        stp = _server_refs.get("send_to_player")
        if stp:
            stp(requester, _reply(f"{player_id} denied your tp request."))
        return [_reply(f"Denied tp request from {requester}.")]

    # ── /heal ──────────────────────────────────────────────────────────────
    elif cmd == "/heal":
        err = _need_op(player_id)
        if err:
            return err
        target = args[0] if args else player_id
        with players_lock:
            if target not in players:
                return [_reply(f"Player '{target}' is not online.")]
            p = players[target]
            p["health"] = p.get("health_max", 100)
        if target == player_id:
            return [_reply("You have been healed.")]
        stp = _server_refs.get("send_to_player")
        if stp:
            stp(target, _reply("You have been healed by an operator."))
        return [_reply(f"Healed {target}.")]

    # ── /repair ────────────────────────────────────────────────────────────
    elif cmd == "/repair":
        err = _need_op(player_id)
        if err:
            return err
        target = args[0] if args else player_id
        _repair_all(target, players)
        if target == player_id:
            return [_reply("All items repaired.")]
        stp = _server_refs.get("send_to_player")
        if stp:
            stp(target, _reply("Your items have been repaired by an operator."))
        return [_reply(f"Repaired {target}'s items.")]

    # ── /tp ────────────────────────────────────────────────────────────────
    elif cmd == "/tp":
        err = _need_op(player_id)
        if err:
            return err
        if not args:
            return [_reply("Usage: /tp <player>")]
        target = args[0]
        with players_lock:
            if player_id not in players:
                return []
            if target not in players:
                return [_reply(f"Player '{target}' is not online.")]
            players[player_id]["pos"] = list(players[target].get("pos", [0, 0]))
        return [_reply(f"Teleported to {target}.")]

    # ── /op ────────────────────────────────────────────────────────────────
    elif cmd == "/op":
        target = args[0] if args else player_id
        if not is_op(player_id):
            return [_reply("Permission denied — you are not an operator.")]
        with players_lock:
            if target not in players and target != player_id:
                return [_reply(f"Player '{target}' is not online.")]
        add_op(target)
        if target == player_id:
            return [_reply("You are now an operator.")]
        return [_reply(f"Granted op to {target}.")]

    # ── /deop ──────────────────────────────────────────────────────────────
    elif cmd == "/deop":
        err = _need_op(player_id)
        if err:
            return err
        if not args:
            return [_reply("Usage: /deop <player>")]
        remove_op(args[0])
        return [_reply(f"Removed op from {args[0]}.")]

    # ── /creative ──────────────────────────────────────────────────────────
    elif cmd == "/creative":
        err = _need_op(player_id)
        if err:
            return err
        target = args[0] if args else player_id
        with players_lock:
            if target not in players:
                return [_reply(f"Player '{target}' is not online.")]
            p       = players[target]
            new_val = not p.get("creative", False)
            p["creative"] = new_val
        state = "ON" if new_val else "OFF"
        if target == player_id:
            return [_reply(f"Creative mode {state}.")]
        return [_reply(f"Creative mode {state} for {target}.")]

    # ── /give ──────────────────────────────────────────────────────────────
    elif cmd == "/give":
        err = _need_op(player_id)
        if err:
            return err
        if len(args) < 2:
            return [_reply("Usage: /give <player> <item_id> [qty]")]
        target = args[0]
        try:
            item_id = int(args[1])
            qty     = max(1, int(args[2])) if len(args) > 2 else 1
        except ValueError:
            return [_reply("Usage: /give <player> <item_id> [qty]  — IDs must be integers.")]
        if not (0 < item_id <= _MAX_ITEM_ID):
            return [_reply(f"Unknown item ID {item_id}.")]
        item_def = get_item(item_id)
        if not item_def:
            return [_reply(f"Unknown item ID {item_id}.")]
        with players_lock:
            if target not in players:
                return [_reply(f"Player '{target}' is not online.")]
            ok = give_item(players[target], item_id, qty)
        name = item_def.get("name", str(item_id))
        if ok:
            return [_reply(f"Gave {qty}\u00d7 {name} to {target}.")]
        return [_reply(f"Inventory full — could not give {name} to {target}.")]

    # ── /ban ───────────────────────────────────────────────────────────────
    elif cmd == "/ban":
        err = _need_op(player_id)
        if err:
            return err
        if not args:
            return [_reply("Usage: /ban <player>")]
        target = args[0]
        if target == player_id:
            return [_reply("You cannot ban yourself.")]
        ban_player(target)
        kick = _server_refs.get("kick_player")
        if kick:
            kick(target)
        return [_reply(f"Banned and kicked {target}.")]

    # ── /unban ─────────────────────────────────────────────────────────────
    elif cmd == "/unban":
        err = _need_op(player_id)
        if err:
            return err
        if not args:
            return [_reply("Usage: /unban <player>")]
        unban_player(args[0])
        return [_reply(f"Unbanned {args[0]}.")]

    # ── /restart ───────────────────────────────────────────────────────────
    elif cmd == "/restart":
        err = _need_op(player_id)
        if err:
            return err
        bc = _server_refs.get("broadcast_chat")
        if bc:
            bc({"type": "chat", "sender": "SYSTEM", "text": "Server is restarting..."})
        sa = _server_refs.get("save_all_players")
        if sa:
            sa()
        import threading
        threading.Thread(target=_do_restart, daemon=True).start()
        return [_reply("Restarting server...")]

    # ── /shutdown ──────────────────────────────────────────────────────────
    elif cmd == "/shutdown":
        err = _need_op(player_id)
        if err:
            return err
        bc = _server_refs.get("broadcast_chat")
        if bc:
            bc({"type": "chat", "sender": "SYSTEM", "text": "Server is shutting down..."})
        sa = _server_refs.get("save_all_players")
        if sa:
            sa()
        import threading
        threading.Thread(target=_do_shutdown, daemon=True).start()
        return [_reply("Shutting down server...")]
    
    elif cmd == "/time":
        err = _need_op(player_id)
        if err:
            return err
        if len(args) < 2 or args[0] != "set":
            return [_reply("Usage: /time set <day|night|dawn|dusk|<hour>>  (hour = 0–24)")]
        val = args[1].lower()
        _PRESETS = {"day": 12.0, "noon": 12.0, "night": 22.0,
                    "midnight": 0.0, "dawn": 6.0, "dusk": 18.0}
        if val in _PRESETS:
            hour = _PRESETS[val]
        else:
            try:
                hour = float(val)
            except ValueError:
                return [_reply("Usage: /time set <day|night|dawn|dusk|<hour>>")]
        from server.game_state.game_sync import set_world_time
        set_world_time(hour)
        bc = _server_refs.get("broadcast_chat")
        if bc:
            bc({"type": "chat", "sender": "SYSTEM",
                "text": f"Time set to {val} ({hour:.1f})."})
        return [_reply(f"Time set to {hour:.1f}.")]

    else:
        return [_reply(f"Unknown command '{cmd}'. Try /help.")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repair_all(player_id: str, players: dict) -> None:
    """Restore durability on every item in the player's inventory."""
    with players_lock:
        if player_id not in players:
            return
        for slot in players[player_id].get("inventory", []):
            if not isinstance(slot, (list, tuple)) or len(slot) < 1:
                continue
            item_def = get_item(slot[0])
            if item_def is None:
                continue
            max_dur = item_def.get("durability")
            if max_dur and len(slot) >= 3 and isinstance(slot[2], dict):
                slot[2]["dur"]     = int(max_dur)
                slot[2]["dur_max"] = int(max_dur)


def _do_restart() -> None:
    """Spawn a fresh server process then hard-exit (Windows-compatible)."""
    import time
    import subprocess
    time.sleep(0.5)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    subprocess.Popen([sys.executable, "-m", "server.server"], cwd=root)
    os._exit(0)


def _do_shutdown() -> None:
    import time
    time.sleep(0.5)
    os._exit(0)

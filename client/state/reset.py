import config
import state.player as _player_module
from client_constants import DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH

def reset_client_state():
    # Persist the player's map exploration before any resets
    config.save_visited_chunks()
    config.save_map_memory(force=True)

    # Mutate dicts/lists in-place so all modules holding a reference see the reset
    _player_module.player_data.clear()
    _player_module.player_data.update({"pos": [config.PLAYER_START_X, config.PLAYER_START_Y], "health": 100, "level": 1})
    _player_module.player_id_dict["player_id"] = None

    config.players_data.clear()
    config.mob_entities.clear()
    config.world_data.clear()
    # full_world_data intentionally kept — it's the player's map exploration history
    config.faction_claims = []
    config.chunk_cache.clear()

    # Drain stale chunks so the next session's loading screen starts from 0%
    while not config.chunk_queue.empty():
        try:
            config.chunk_queue.get_nowait()
            config.chunk_queue.task_done()
        except Exception:
            pass

    # Clear scheduled render set so chunks can be re-submitted to render_queue
    config.scheduled_chunk_renders.clear()

    config.map_surface_cache = None
    config.last_player_chunk = None
    config.is_fullscreen = False
    config.screen = None
    config.WINDOW_WIDTH = DEFAULT_WINDOW_WIDTH
    config.WINDOW_HEIGHT = DEFAULT_WINDOW_HEIGHT

    config.ping = 0
    config.session_token = None
    config.last_ping_sent = 0.0
    config.awaiting_ping = False
    config.client_running = True
    config.hit_flash_timer = 0.0
    config.show_menu = False
    config.menu_click_pos = None
    config.show_stats = False
    config.stat_click_pos = None
    config.show_char_creator = False
    config.first_join_setup_required = False
    config.player_coins = 0
    config.player_exp = 0
    config.player_exp_next = 100
    config.player_stat_points = 0
    config.player_speed_bonus = 0.0
    config.player_hp_regen = 0.0
    config.player_sp_regen_bonus = 0.0
    config.player_slow_timer = 0.0
    config.current_territory_owner = None
    config.current_territory_tag = None
    config.territory_state_ready = False
    config.territory_banner_text = ""
    config.territory_banner_started_at = 0.0
    config.territory_banner_until = 0.0
    config.debug_overlay_mode = 1 if config.DEBUG_MODE else 0

    # Clear world items so session 2 doesn't start with stale data
    config.world_items = {}
    config.mobs = []

    # Cancel any in-progress inventory drag
    config.drag_slot        = None
    config.drag_item        = None
    config.open_chest_uid   = None
    config.chest_drag_slot  = None
    config.chest_ui_hold_until = 0.0
    config.pending_private_chest = False

    # Reset animation / combat state
    config.player_facing    = "down"
    config.is_moving        = False
    config.is_attacking     = False
    config.last_attack_time = 0.0

    # Discard any unsent outbox messages from the previous session
    while not config.state_outbox.empty():
        try:
            config.state_outbox.get_nowait()
        except Exception:
            break

    while not config.udp_outbox.empty():
        try:
            config.udp_outbox.get_nowait()
        except Exception:
            break

    # Clear module-level pygame caches that become invalid after pygame.quit().
    # These are lazily re-created on first use in the new session.
    import rendering.hud as _hud
    import rendering.inventory as _inv
    import rendering.cache as _cache
    import rendering.display as _disp
    import rendering.mobs as _mobs
    import rendering.stat_screen as _ss
    _hud._font = None
    _inv._font = None
    _cache._ITEM_SURFACE_CACHE.clear()
    _disp._MISSING_TILE_SURFACE = None
    _mobs._mob_timers.clear()
    _mobs._mob_buf.clear()
    if hasattr(_mobs, "_mob_sprites"):
        _mobs._mob_sprites.clear()
    _mobs._loaded = False
    for attr in ("_scorpion_surf", "_yeti_surf", "_deer_surf", "_slime_king_surf"):
        if hasattr(_mobs, attr):
            setattr(_mobs, attr, None)
    _mobs._level_font = None
    _ss._font_title = None
    _ss._font_body = None
    _ss._font_small = None

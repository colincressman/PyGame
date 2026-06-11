# client/rendering/mobs.py
"""Renders server-provided mob entities."""
import json
import os
import time
from collections import deque
import pygame
import config

# ---------------------------------------------------------------------------
# Load sprite config from data/mobs/*.json (same files the server uses)
# ---------------------------------------------------------------------------
_CLIENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOB_DATA_DIR = os.path.normpath(os.path.join(_CLIENT_DIR, "..", "data", "mobs"))
_MOB_SPRITE_CFG: dict = {}
for _fname in os.listdir(_MOB_DATA_DIR):
    if _fname.endswith(".json"):
        _t = _fname[:-5]
        with open(os.path.join(_MOB_DATA_DIR, _fname), encoding="utf-8") as _f:
            _MOB_SPRITE_CFG[_t] = json.load(_f).get("sprite", {})

_DIRS          = ("down", "up", "left", "right")
# LPC walk row order: down=0, left=1, right=2, up=3
_LPC_WALK_ROWS = {"down": 2, "left": 1, "right": 3, "up": 0}
_LPC_WALK_ROWS_SWEN = {"down": 0, "left": 1, "right": 2, "up": 3}

# Render mobs 2 server frames behind real-time (33 ms).
# This guarantees we always interpolate between two *known* positions
# rather than extrapolating/guessing, giving smooth motion at any speed.
_INTERP_DELAY  = 3.0 / 60   # seconds
_BUFFER_MAXLEN = 12          # ~200 ms of history at 60 Hz

_mob_sprites: dict = {}  # {mob_type: {dir: [Surface, ...]}}
_MOB_MOVING_STATES = frozenset({
    "wander",
    "aggro",
    "chase",
    "flee",
    "lunge",
    "return_to_origin",
    "patrol",
    "follow",
})

_scorpion_surf: pygame.Surface | None = None   # procedural, direction-agnostic
_yeti_surf:     pygame.Surface | None = None
_deer_surf:     pygame.Surface | None = None
_slime_king_surf: pygame.Surface | None = None
_loaded          = False
_level_font      = None  # lazy-init for mob level labels

def _get_level_font():
    global _level_font
    if _level_font is None:
        _level_font = pygame.font.SysFont("Arial", 11, bold=True)
    return _level_font

# Per-mob state keyed by mob_id
_mob_timers: dict = {}   # {mob_id: float}           — animation clock
_mob_buf:    dict = {}   # {mob_id: deque[(t, x, y)]} — interpolation buffer


def _clamp_int(value, minimum, maximum):
    return max(minimum, min(int(round(value)), maximum))


def _get_mob_layout(mob_type: str, img: pygame.Surface) -> dict:
    """Return anchor and visible-body layout for oversized mob sprites."""
    cfg = _MOB_SPRITE_CFG.get(mob_type, {})
    w, h = img.get_width(), img.get_height()
    anchor_x = _clamp_int(cfg.get("anchor_x", w / 2), 0, w)
    anchor_y = _clamp_int(cfg.get("anchor_y", h / 2), 0, h)

    bounds_cfg = cfg.get("visual_bounds")
    if isinstance(bounds_cfg, dict):
        bx = _clamp_int(bounds_cfg.get("x", 0), 0, w)
        by = _clamp_int(bounds_cfg.get("y", 0), 0, h)
        bw = _clamp_int(bounds_cfg.get("w", w - bx), 1, max(1, w - bx))
        bh = _clamp_int(bounds_cfg.get("h", h - by), 1, max(1, h - by))
    else:
        bx, by, bw, bh = 0, 0, w, h

    bar_cfg = cfg.get("health_bar")
    if isinstance(bar_cfg, dict):
        bar_w = _clamp_int(bar_cfg.get("w", bw), 8, bw)
        bar_x = bx + _clamp_int(bar_cfg.get("x", (bw - bar_w) / 2), 0, max(0, bw - bar_w))
        bar_y = by + int(round(bar_cfg.get("y", -6)))
    else:
        bar_w = bw
        bar_x = bx
        bar_y = by - 6

    sort_anchor_y = _clamp_int(cfg.get("sort_anchor_y", by + bh), 0, h)
    return {
        "anchor_x": anchor_x,
        "anchor_y": anchor_y,
        "bar_x": bar_x,
        "bar_y": bar_y,
        "bar_w": bar_w,
        "sort_anchor_y": sort_anchor_y,
    }


def _load_mob_sprite(mob_type: str, cfg: dict) -> dict:
    """Load all directional frames for one mob from its sprite config.

    Supported sprite types:
      "frames"     — per-direction individual files; path uses {dir} and {frame}
      "lpc_walk"   — LPC spritesheet (rows = directions) with optional head overlay
      "walk_strip" — generic spritesheet strip (rows = directions, cols = frames)

    Returns {direction: [Surface, ...]} for each direction in row_order.
    """
    stype = cfg.get("type", "")
    result: dict = {}

    if stype == "frames":
        path_tmpl = cfg["path"]
        frame_count = cfg.get("frames", 3)
        for d in _DIRS:
            result[d] = [
                pygame.image.load(
                    os.path.join(_CLIENT_DIR, path_tmpl.format(dir=d, frame=i))
                ).convert_alpha()
                for i in range(frame_count)
            ]

    elif stype == "lpc_walk":
        fw = cfg.get("frame_w", 64)
        fh = cfg.get("frame_h", 64)
        frame_count = cfg.get("frames", 9)
        row_order = cfg.get("row_order", _LPC_WALK_ROWS)
        body_sheet = pygame.image.load(
            os.path.join(_CLIENT_DIR, cfg["path"])
        ).convert_alpha()
        head_sheet = None
        head_path = cfg.get("head_path")
        if head_path:
            full = os.path.join(_CLIENT_DIR, head_path)
            if os.path.exists(full):
                head_sheet = pygame.image.load(full).convert_alpha()
            else:
                print(f"[MOBS] {mob_type} head sheet not found: {full}")
        for direction, row in row_order.items():
            frames = []
            for col in range(frame_count):
                rect = pygame.Rect(col * fw, row * fh, fw, fh)
                frame = body_sheet.subsurface(rect).copy()
                if head_sheet is not None:
                    frame.blit(head_sheet.subsurface(rect), (0, 0))
                frames.append(frame)
            result[direction] = frames

    elif stype == "walk_strip":
        fw = cfg.get("frame_w", 64)
        fh = cfg.get("frame_h", 64)
        frame_count = cfg.get("walk_frames", cfg.get("frames", 4))
        start_col = cfg.get("walk_start_col", 0)
        row_order = cfg.get("row_order", _LPC_WALK_ROWS)
        sheet = pygame.image.load(
            os.path.join(_CLIENT_DIR, cfg["path"])
        ).convert_alpha()
        for direction, row in row_order.items():
            frames = []
            for col in range(start_col, start_col + frame_count):
                rect = pygame.Rect(col * fw, row * fh, fw, fh)
                frames.append(sheet.subsurface(rect).copy())
            result[direction] = frames

    return result


def _ensure_loaded():
    import math as _m
    global _loaded, _scorpion_surf
    global _yeti_surf, _deer_surf, _slime_king_surf
    if _loaded:
        return
    _loaded = True

    for mob_type, cfg in _MOB_SPRITE_CFG.items():
        if cfg.get("type") == "procedural":
            continue
        try:
            _mob_sprites[mob_type] = _load_mob_sprite(mob_type, cfg)
        except Exception as e:
            print(f"[MOBS] Failed to load {mob_type} sprite: {e}")

    # --- Procedural scorpion sprite (40×40) ---
    _scorpion_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
    scx, scy = 20, 22
    pygame.draw.ellipse(_scorpion_surf, (160, 90, 30), (scx - 8, scy - 5, 16, 10))  # body
    pygame.draw.ellipse(_scorpion_surf, (140, 75, 20), (scx - 5, scy - 8, 10, 6))   # head
    # Tail segments
    for seg in range(4):
        tx = scx + 8 + seg * 5
        ty = scy - seg * 2
        pygame.draw.circle(_scorpion_surf, (150, 80, 25), (tx, ty), 3)
    pygame.draw.circle(_scorpion_surf, (40, 160, 40), (scx + 26, scy - 8), 3)       # stinger
    # Claws
    pygame.draw.arc(_scorpion_surf, (130, 70, 20),
                    pygame.Rect(scx - 16, scy - 10, 12, 8), 0, _m.pi, 2)
    pygame.draw.arc(_scorpion_surf, (130, 70, 20),
                    pygame.Rect(scx - 16, scy + 2, 12, 8), -_m.pi, 0, 2)

    
    # --- Procedural yeti sprite (44×52) ---
    _yeti_surf = pygame.Surface((44, 52), pygame.SRCALPHA)
    yx, yy = 22, 28
    pygame.draw.ellipse(_yeti_surf, (210, 220, 230), (yx - 12, yy - 12, 24, 20))  # body
    pygame.draw.circle(_yeti_surf, (220, 225, 235), (yx, yy - 18), 10)             # head
    pygame.draw.circle(_yeti_surf, (30, 30, 80),    (yx - 3, yy - 20), 2)          # eye L
    pygame.draw.circle(_yeti_surf, (30, 30, 80),    (yx + 3, yy - 20), 2)          # eye R
    # Arms
    pygame.draw.line(_yeti_surf, (190, 200, 210), (yx - 12, yy - 6), (yx - 20, yy + 4), 5)
    pygame.draw.line(_yeti_surf, (190, 200, 210), (yx + 12, yy - 6), (yx + 20, yy + 4), 5)
    # Legs
    pygame.draw.line(_yeti_surf, (190, 200, 210), (yx - 6, yy + 8),  (yx - 8, yy + 20), 5)
    pygame.draw.line(_yeti_surf, (190, 200, 210), (yx + 6, yy + 8),  (yx + 8, yy + 20), 5)
    # Claws
    pygame.draw.line(_yeti_surf, (160, 170, 180), (yx - 20, yy + 4), (yx - 24, yy + 2), 2)
    pygame.draw.line(_yeti_surf, (160, 170, 180), (yx - 20, yy + 4), (yx - 24, yy + 6), 2)
    pygame.draw.line(_yeti_surf, (160, 170, 180), (yx + 20, yy + 4), (yx + 24, yy + 2), 2)
    pygame.draw.line(_yeti_surf, (160, 170, 180), (yx + 20, yy + 4), (yx + 24, yy + 6), 2)

    # --- Procedural deer sprite (24×34) ---
    _deer_surf = pygame.Surface((24, 34), pygame.SRCALPHA)
    drx, dry = 12, 22
    pygame.draw.ellipse(_deer_surf, (170, 120, 70), (drx - 6, dry - 8, 12, 12))  # body
    pygame.draw.circle(_deer_surf, (180, 130, 80),  (drx, dry - 14), 5)           # head
    pygame.draw.circle(_deer_surf, (30, 20, 10),    (drx - 1, dry - 15), 1)       # eye L
    pygame.draw.circle(_deer_surf, (30, 20, 10),    (drx + 1, dry - 15), 1)       # eye R
    # Antlers
    pygame.draw.line(_deer_surf, (120, 80, 40), (drx - 2, dry - 18), (drx - 5, dry - 26), 2)
    pygame.draw.line(_deer_surf, (120, 80, 40), (drx - 5, dry - 26), (drx - 8, dry - 23), 1)
    pygame.draw.line(_deer_surf, (120, 80, 40), (drx + 2, dry - 18), (drx + 5, dry - 26), 2)
    pygame.draw.line(_deer_surf, (120, 80, 40), (drx + 5, dry - 26), (drx + 8, dry - 23), 1)
    # Legs (4)
    for lx_off in (-4, -1, 2, 5):
        pygame.draw.line(_deer_surf, (150, 100, 55),
                         (drx + lx_off, dry + 4), (drx + lx_off, dry + 12), 2)

    # --- Procedural Slime King sprite (52×52) ---
    _slime_king_surf = pygame.Surface((52, 52), pygame.SRCALPHA)
    kx, ky = 26, 32
    # Crown jewel glow
    pygame.draw.circle(_slime_king_surf, (180, 255, 100, 60), (kx, ky), 26)
    # Large body
    pygame.draw.ellipse(_slime_king_surf, (80, 200, 60), (kx - 20, ky - 14, 40, 26))
    # Gooey drips
    for dx_off, dy_off in [(-12, 12), (-4, 14), (4, 14), (12, 12)]:
        pygame.draw.circle(_slime_king_surf, (70, 180, 50), (kx + dx_off, ky + dy_off), 4)
    # Eyes (large, menacing)
    pygame.draw.circle(_slime_king_surf, (255, 50, 50), (kx - 7, ky - 8), 5)
    pygame.draw.circle(_slime_king_surf, (255, 50, 50), (kx + 7, ky - 8), 5)
    pygame.draw.circle(_slime_king_surf, (20, 0, 0),    (kx - 7, ky - 8), 2)
    pygame.draw.circle(_slime_king_surf, (20, 0, 0),    (kx + 7, ky - 8), 2)
    # Crown
    crown_pts = [(kx - 14, ky - 14), (kx - 14, ky - 22), (kx - 8, ky - 18),
                 (kx, ky - 26), (kx + 8, ky - 18), (kx + 14, ky - 22), (kx + 14, ky - 14)]
    pygame.draw.polygon(_slime_king_surf, (220, 200, 30), crown_pts)
    pygame.draw.lines(_slime_king_surf, (255, 240, 60), False, crown_pts, 2)
    # Crown gems
    for gx_off, gy_off, gc in [(-10, -22, (255, 80, 80)), (0, -26, (80, 150, 255)),
                                (10, -22, (80, 255, 100))]:
        pygame.draw.circle(_slime_king_surf, gc, (kx + gx_off, ky + gy_off), 2)


def _make_mob_draw(screen, img, sx, sy, bar_x, bar_y, bar_w, hit_flash, mob_state, hp_pct, mob_level):
    """Return a zero-argument callable that blits one mob entry onto screen."""
    def _draw():
        bar_h = 4
        screen.blit(img, (sx, sy))
        if hit_flash > 0.0:
            tinted = img.copy()
            tinted.fill((255, 80, 80, 255), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(tinted, (sx, sy))
        elif mob_state in ("windup", "lunge"):
            tinted = img.copy()
            tinted.fill((255, 220, 50, 255), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(tinted, (sx, sy))
        elif mob_state == "landing":
            tinted = img.copy()
            tinted.fill((100, 255, 100, 255), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(tinted, (sx, sy))
        draw_bar_x = sx + bar_x
        draw_bar_y = sy + bar_y
        pygame.draw.rect(screen, (60, 0, 0),    (draw_bar_x, draw_bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (200, 40, 40), (draw_bar_x, draw_bar_y, int(bar_w * hp_pct), bar_h))
        lv_surf = _get_level_font().render(f"Lv{mob_level}", True, (255, 220, 50))
        lv_x = draw_bar_x + bar_w // 2 - lv_surf.get_width() // 2
        lv_y = draw_bar_y - lv_surf.get_height()
        pad = 1
        bg = pygame.Surface((lv_surf.get_width() + pad * 2, lv_surf.get_height()), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, (lv_x - pad, lv_y))
        screen.blit(lv_surf, (lv_x, lv_y))
    return _draw


def get_mob_drawables(screen: pygame.Surface, mobs: list, player_pos: list,
                      window_width: int, window_height: int, dt: float):
    """
    Process mob interpolation / animation and return [(world_y, draw_fn)] so the
    caller can merge with player drawables and sort by Y before blitting.
    """
    active_ids = {m.get("id") for m in mobs}
    for k in [k for k in _mob_timers if k not in active_ids]:
        del _mob_timers[k]
    for k in [k for k in _mob_buf if k not in active_ids]:
        del _mob_buf[k]

    if not mobs:
        return []
    _ensure_loaded()

    px, py = player_pos
    now = time.time()
    result = []

    for mob in mobs:
        mid        = mob.get("id", "")
        server_pos = mob.get("pos", [0, 0])
        facing     = mob.get("facing", "down")
        mob_state  = mob.get("state", "idle")
        pre_smoothed = bool(mob.get("_pre_smoothed"))

        if pre_smoothed:
            mx, my = server_pos[0], server_pos[1]
        else:
            buf = _mob_buf.get(mid)
            if buf is None:
                _mob_buf[mid] = buf = deque(maxlen=_BUFFER_MAXLEN)
                buf.append((now, server_pos[0], server_pos[1]))
            else:
                lx, ly = buf[-1][1], buf[-1][2]
                pos_changed = abs(server_pos[0] - lx) > 0.0001 or abs(server_pos[1] - ly) > 0.0001
                buf_stale   = (now - buf[-1][0]) > _INTERP_DELAY
                if pos_changed or buf_stale:
                    buf.append((now, server_pos[0], server_pos[1]))

            render_t = now - _INTERP_DELAY
            if len(buf) == 1 or render_t <= buf[0][0]:
                mx, my = buf[0][1], buf[0][2]
            elif render_t >= buf[-1][0]:
                mx, my = buf[-1][1], buf[-1][2]
            else:
                for i in range(len(buf) - 1):
                    if buf[i][0] <= render_t < buf[i + 1][0]:
                        t0, x0, y0 = buf[i]
                        t1, x1, y1 = buf[i + 1]
                        alpha = (render_t - t0) / (t1 - t0)
                        mx = x0 + (x1 - x0) * alpha
                        my = y0 + (y1 - y0) * alpha
                        break
                else:
                    mx, my = buf[-1][1], buf[-1][2]

        _mob_timers[mid] = _mob_timers.get(mid, 0.0) + dt

        mob_type = mob.get("type", "slime")
        sprite_data = _mob_sprites.get(mob_type)
        if sprite_data:
            cfg = _MOB_SPRITE_CFG.get(mob_type, {})
            fps = cfg.get("fps", 8.0)
            frames_list = sprite_data.get(facing) or sprite_data.get("down", [])
            if mob_state in _MOB_MOVING_STATES:
                frame_idx = int(_mob_timers[mid] * fps) % max(len(frames_list), 1)
            else:
                frame_idx = 0
            img = frames_list[frame_idx]
        elif mob_type == "scorpion" and _scorpion_surf is not None:
            img = _scorpion_surf
        elif mob_type == "yeti" and _yeti_surf is not None:
            img = _yeti_surf
        elif mob_type == "deer" and _deer_surf is not None:
            img = _deer_surf
        elif mob_type == "slime_king" and _slime_king_surf is not None:
            img = _slime_king_surf
        else:
            # Unknown type — use first available sprite as fallback
            fallback = next(iter(_mob_sprites.values()), None)
            frames_list = (fallback or {}).get("down", [])
            img = frames_list[0] if frames_list else pygame.Surface((32, 32))
        layout = _get_mob_layout(mob_type, img)
        sx = round((mx - px) * 32 + window_width  // 2 - layout["anchor_x"])
        sy = round((my - py) * 32 + window_height // 2 - layout["anchor_y"])

        hit_flash = mob.get("hit_flash", 0.0)
        hp_pct    = mob.get("health", 100) / max(mob.get("health_max", 100), 1)
        mob_level = mob.get("level", 1)

        sort_y = my + (layout["sort_anchor_y"] - layout["anchor_y"]) / 32.0
        result.append((
            sort_y,
            _make_mob_draw(
                screen,
                img,
                sx,
                sy,
                layout["bar_x"],
                layout["bar_y"],
                layout["bar_w"],
                hit_flash,
                mob_state,
                hp_pct,
                mob_level,
            ),
        ))

    return result


def draw_mobs(screen: pygame.Surface, mobs: list, player_pos: list,
              window_width: int, window_height: int, dt: float):
    """Compatibility wrapper — draws all mobs unsorted. Use get_mob_drawables for Y-sorting."""
    for _, fn in get_mob_drawables(screen, mobs, player_pos, window_width, window_height, dt):
        fn()

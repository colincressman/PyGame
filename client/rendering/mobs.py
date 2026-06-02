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

_SLIME_CFG    = _MOB_SPRITE_CFG.get("slime", {})
_SKELETON_CFG = _MOB_SPRITE_CFG.get("skeleton", {})
_SPIDER_CFG = _MOB_SPRITE_CFG.get("spider", {})
_BAT_CFG = _MOB_SPRITE_CFG.get("bat", {})
_RABBIT_CFG = _MOB_SPRITE_CFG.get("rabbit", {})

_SLIME_FRAMES    = _SLIME_CFG.get("frames", 3)
_SLIME_FPS       = _SLIME_CFG.get("fps", 6.0)
_SKELETON_FRAMES = _SKELETON_CFG.get("frames", 9)
_SKELETON_FPS    = _SKELETON_CFG.get("fps", 8.0)
_SPIDER_FRAMES   = _SPIDER_CFG.get("walk_frames", 6)
_SPIDER_FPS      = _SPIDER_CFG.get("fps", 8.0)
_BAT_FRAMES   = _BAT_CFG.get("walk_frames", 8)
_BAT_FPS      = _BAT_CFG.get("fps", 8.0)
_RABBIT_FRAMES   = _RABBIT_CFG.get("walk_frames", 8)
_RABBIT_FPS      = _RABBIT_CFG.get("fps", 8.0)
_LPC_FRAME_W     = _SKELETON_CFG.get("frame_w", 64)
_LPC_FRAME_H     = _SKELETON_CFG.get("frame_h", 64)

_DIRS          = ("down", "up", "left", "right")
# LPC walk row order: down=0, left=1, right=2, up=3
_LPC_WALK_ROWS = {"down": 2, "left": 1, "right": 3, "up": 0}
_LPC_WALK_ROWS_SWEN = {"down": 0, "left": 1, "right": 2, "up": 3}

# Render mobs 2 server frames behind real-time (33 ms).
# This guarantees we always interpolate between two *known* positions
# rather than extrapolating/guessing, giving smooth motion at any speed.
_INTERP_DELAY  = 3.0 / 60   # seconds
_BUFFER_MAXLEN = 12          # ~200 ms of history at 60 Hz

_slime: dict    = {}   # {dir: [Surface, ...]}
_skeleton: dict  = {}   # {dir: [Surface, ...]}  — loaded from LPC walk sheet
_spider: dict   = {}
_bat: dict   = {}
_rabbit: dict   = {}

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

_ASSETS_DIR   = os.path.join(_CLIENT_DIR, "assets", "mobs", "slime")

_SKELETON_WALK_PATH = os.path.join(
    _CLIENT_DIR,
    _SKELETON_CFG.get(
        "path",
        "Universal-LPC-Spritesheet-Character-Generator/spritesheets/body/bodies/skeleton/walk/skeleton.png",
    ),
)

_SPIDER_WALK_PATH = os.path.join(
    _CLIENT_DIR,
    _SPIDER_CFG.get(
        "path",
        "Universal-LPC-Spritesheet-Character-Generator/spritesheets/mobs/spider/spider05.png",
    ),
)

_BAT_WALK_PATH = os.path.join(
    _CLIENT_DIR,
    _BAT_CFG.get(
        "path",
        "Universal-LPC-Spritesheet-Character-Generator/spritesheets/mobs/bat/bat-SWEN.png",
    ),
)

_RABBIT_WALK_PATH = os.path.join(
    _CLIENT_DIR,
    _RABBIT_CFG.get(
        "path",
        "Universal-LPC-Spritesheet-Character-Generator/spritesheets/mobs/bunny/rabbit.png",
    ),
)

# Per-mob state keyed by mob_id
_mob_timers: dict = {}   # {mob_id: float}           — animation clock
_mob_buf:    dict = {}   # {mob_id: deque[(t, x, y)]} — interpolation buffer


def _ensure_loaded():
    import math as _m
    global _loaded, _scorpion_surf
    global _yeti_surf, _deer_surf, _slime_king_surf
    if _loaded:
        return
    _loaded = True
    for d in _DIRS:
        _slime_path_tmpl = _SLIME_CFG.get("path", "assets/mobs/slime/slime{dir}{frame}.png")
        _slime[d] = [
            pygame.image.load(
                os.path.join(_CLIENT_DIR, _slime_path_tmpl.format(dir=d, frame=i))
            ).convert_alpha()
            for i in range(_SLIME_FRAMES)
        ]
    # Load skeleton walk animation from LPC spritesheet (body + head overlay)
    try:
        body_sheet = pygame.image.load(_SKELETON_WALK_PATH).convert_alpha()
        _head_path = _SKELETON_CFG.get("head_path")
        head_sheet = None
        if _head_path:
            _head_full = os.path.join(_CLIENT_DIR, _head_path)
            if os.path.exists(_head_full):
                head_sheet = pygame.image.load(_head_full).convert_alpha()
            else:
                print(f"[MOBS] Skeleton head sheet not found: {_head_full}")
        for direction, row in _LPC_WALK_ROWS.items():
            frames = []
            for col in range(_SKELETON_FRAMES):
                rect = pygame.Rect(col * _LPC_FRAME_W, row * _LPC_FRAME_H,
                                   _LPC_FRAME_W, _LPC_FRAME_H)
                frame = body_sheet.subsurface(rect).copy()
                if head_sheet is not None:
                    frame.blit(head_sheet.subsurface(rect), (0, 0))
                frames.append(frame)
            _skeleton[direction] = frames
    except Exception as e:
        print(f"[MOBS] Failed to load skeleton walk sheet: {e}")

    # --- Spider sprite (walk strip: row 0, cols walk_start_col .. walk_start_col+walk_frames) ---
    try:
        body_sheet = pygame.image.load(_SPIDER_WALK_PATH).convert_alpha()
        _walk_start = _SPIDER_CFG.get("walk_start_col", 5)
        for direction, row in _LPC_WALK_ROWS.items():
            frames = []
            for col in range(_walk_start, _walk_start + _SPIDER_FRAMES):
                rect = pygame.Rect(col * _LPC_FRAME_W, row * _LPC_FRAME_H,
                                   _LPC_FRAME_W, _LPC_FRAME_H)
                frame = body_sheet.subsurface(rect).copy()
                frames.append(frame)
            _spider[direction] = frames
    except Exception as e:
        print(f"[MOBS] Failed to load spider walk sheet: {e}")

    # --- Bat sprite (SWEN sheet: 3 cols × 4 rows, frame 48×64) ---
    try:
        body_sheet = pygame.image.load(_BAT_WALK_PATH).convert_alpha()
        _bat_fw = _BAT_CFG.get("frame_w", 48)
        _bat_fh = _BAT_CFG.get("frame_h", 64)
        _bat_start = _BAT_CFG.get("walk_start_col", 0)
        for direction, row in _LPC_WALK_ROWS_SWEN.items():
            frames = []
            for col in range(_bat_start, _bat_start + _BAT_FRAMES):
                rect = pygame.Rect(col * _bat_fw, row * _bat_fh, _bat_fw, _bat_fh)
                frame = body_sheet.subsurface(rect).copy()
                frames.append(frame)
            _bat[direction] = frames
    except Exception as e:
        print(f"[MOBS] Failed to load bat walk sheet: {e}")

    # --- Rabbit sprite (SWEN sheet: 3 cols × 6 rows, frame 53×54) ---
    try:
        body_sheet = pygame.image.load(_RABBIT_WALK_PATH).convert_alpha()
        _rab_fw = _RABBIT_CFG.get("frame_w", 40)
        _rab_fh = _RABBIT_CFG.get("frame_h", 40)
        _rab_start = _RABBIT_CFG.get("walk_start_col", 0)
        for direction, row in _LPC_WALK_ROWS.items():
            frames = []
            for col in range(_rab_start, _rab_start + _RABBIT_FRAMES):
                rect = pygame.Rect(col * _rab_fw, row * _rab_fh, _rab_fw, _rab_fh)
                frame = body_sheet.subsurface(rect).copy()
                frames.append(frame)
            _rabbit[direction] = frames
    except Exception as e:
        print(f"[MOBS] Failed to load rabbit walk sheet: {e}")


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


def _make_mob_draw(screen, img, sx, sy, w, hit_flash, mob_state, hp_pct, mob_level):
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
        bar_w = w
        bar_x, bar_y = sx, sy - bar_h - 2
        pygame.draw.rect(screen, (60, 0, 0),    (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (200, 40, 40), (bar_x, bar_y, int(bar_w * hp_pct), bar_h))
        lv_surf = _get_level_font().render(f"Lv{mob_level}", True, (255, 220, 50))
        lv_x = bar_x + bar_w // 2 - lv_surf.get_width() // 2
        lv_y = bar_y - lv_surf.get_height()
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
        frame = int(_mob_timers[mid] * _SLIME_FPS) % _SLIME_FRAMES

        mob_type = mob.get("type", "slime")
        if mob_type == "skeleton" and _skeleton:
            frame_sk = int(_mob_timers[mid] * _SKELETON_FPS) % _SKELETON_FRAMES
            img = _skeleton[facing][frame_sk]
        elif mob_type == "spider" and _spider:
            frame_sk = int(_mob_timers[mid] * _SPIDER_FPS) % _SPIDER_FRAMES
            img = _spider[facing][frame_sk]
        elif mob_type == "scorpion" and _scorpion_surf is not None:
            img = _scorpion_surf
        elif mob_type == "bat" and _bat:
            frame_sk = int(_mob_timers[mid] * _BAT_FPS) % _BAT_FRAMES
            img = _bat[facing][frame_sk]
        elif mob_type == "yeti" and _yeti_surf is not None:
            img = _yeti_surf
        elif mob_type == "rabbit" and _rabbit:
            frame_sk = int(_mob_timers[mid] * _RABBIT_FPS) % _RABBIT_FRAMES
            img = _rabbit[facing][frame_sk]
        elif mob_type == "deer" and _deer_surf is not None:
            img = _deer_surf
        elif mob_type == "slime_king" and _slime_king_surf is not None:
            img = _slime_king_surf
        else:
            img = _slime[facing][frame]
        w, h = img.get_width(), img.get_height()
        sx = round((mx - px) * 32 + window_width  // 2 - w // 2)
        sy = round((my - py) * 32 + window_height // 2 - h // 2)

        hit_flash = mob.get("hit_flash", 0.0)
        hp_pct    = mob.get("health", 100) / max(mob.get("health_max", 100), 1)
        mob_level = mob.get("level", 1)

        result.append((my + h / 64.0, _make_mob_draw(screen, img, sx, sy, w, hit_flash, mob_state, hp_pct, mob_level)))

    return result


def draw_mobs(screen: pygame.Surface, mobs: list, player_pos: list,
              window_width: int, window_height: int, dt: float):
    """Compatibility wrapper — draws all mobs unsorted. Use get_mob_drawables for Y-sorting."""
    for _, fn in get_mob_drawables(screen, mobs, player_pos, window_width, window_height, dt):
        fn()

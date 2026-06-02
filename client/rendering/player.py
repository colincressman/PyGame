"""
player.py — LPC-based layered player renderer.

Animation states:
  idle  (2 frames, ~1.5 fps) — standing still
  run   (8 frames,  14 fps)  — moving
  slash (6 frames,  14 fps)  — attacking

Layers (bottom → top):  body → head → legs → torso → arms → feet → helmet

LPC row/direction order:  Row 0=up, Row 1=left, Row 2=down, Row 3=right
"""

import pygame
import config
from rendering.lpc import get_frames, get_frames_128, get_attack_frames, get_attack_behind_frames, ANIM_FRAMES, DIR_ROW, CELL, _ATTACK_CELL, LPC_DIR
from rendering.equipment_layers import (
    get_layers, get_layers_from_equip_ids,
    get_weapon_layer, get_weapon_attack_anim,
    get_back_layer, get_back_layer_from_equip_ids,
    get_wing_item, get_wing_item_from_equip_ids,
    _LEGS_DEFAULT, LayerSpec,
)

# ---------------------------------------------------------------------------
# Animation constants
# ---------------------------------------------------------------------------
_WALK_FPS  = 10.0
_RUN_FPS   = 14.0
_ATK_FPS   = 14.0
_IDLE_FPS  =  1.5   # subtle 2-frame breath cycle

_ATK_FRAMES    = ANIM_FRAMES["slash"]   # 6
_THRUST_FRAMES = ANIM_FRAMES["thrust"]  # 8
_WALK_FRAMES   = ANIM_FRAMES["walk"]    # 9
_RUN_FRAMES    = ANIM_FRAMES["run"]     # 8
_IDLE_FRAMES   = ANIM_FRAMES["idle"]    # 2

_SMASH_CELL = 128   # smash tool sheets use 128×128 px cells (6 frames × 4 dirs)

# Permanent base layers — computed dynamically from player_appearance at draw time.
# These constants are kept as fallbacks.
_BODY_FOLDER = "body/bodies/male"
_HEAD_FOLDER = "head/heads/human/male"

# Wing colour options that map to LPC colour variant filenames
_WING_COLOURS = (
    "ash", "black", "blonde", "blue", "brown", "carrot", "chestnut",
    "dark_brown", "dark_gray", "gold", "gray", "green", "orange",
    "pink", "purple", "red", "white",
)

# ---------------------------------------------------------------------------
# Animation state (local player only)
# ---------------------------------------------------------------------------
_anim:       str   = "idle"
_frame:      int   = 0
_anim_timer: float = 0.0

# ---------------------------------------------------------------------------
# Layer frame cache: (folder, colour, anim) -> list[list[Surface]] | False
# ---------------------------------------------------------------------------
_frame_cache: dict = {}

# Dodge-roll squish animation
_roll_surf:   pygame.Surface | None = None   # reusable off-screen canvas
_roll_squish: float = 1.0                    # vertical scale factor (1.0 = normal)


def _get_cached(folder: str, anim: str, colour: str | None):
    """Return frames list for a layer/anim combo, caching misses as False."""
    key = (folder, colour, anim)
    if key not in _frame_cache:
        result = get_frames(folder, anim, colour)
        _frame_cache[key] = result if result is not None else False
    return _frame_cache[key] or None


def _get_attack_cached(folder: str, colour: str | None) -> list | None:
    """Return 192-px attack_slash frames, caching misses as False."""
    key = ("attack_slash", folder, colour)
    if key not in _frame_cache:
        result = get_attack_frames(folder, colour)
        _frame_cache[key] = result if result is not None else False
    return _frame_cache[key] or None


def _get_cached_128(folder: str, anim: str, colour: str | None):
    """Return frames from a 128px-cell sheet, center-cropped to 64×64 per cell."""
    key = (folder, colour, anim, 128)
    if key not in _frame_cache:
        result = get_frames_128(folder, anim, colour)
        _frame_cache[key] = result if result is not None else False
    return _frame_cache[key] or None


def _get_attack_behind_cached(folder: str, colour: str | None) -> list | None:
    """Return 192-px attack_slash/behind frames, caching misses as False."""
    key = ("attack_slash_behind", folder, colour)
    if key not in _frame_cache:
        result = get_attack_behind_frames(folder, colour)
        _frame_cache[key] = result if result is not None else False
    return _frame_cache[key] or None


def _get_smash_frames(colour: str, layer: str = "foreground") -> list | None:
    """Load a smash tool overlay sheet (128×128 px cells, 6 frames × 4 dirs).
    layer: 'foreground' (in front of body) or 'background' (behind body)."""
    import os
    key = ("smash", layer, colour)
    cached = _frame_cache.get(key)
    if cached is not None:
        return cached or None
    path = os.path.join(LPC_DIR, "tools", "smash", layer, colour + ".png")
    if not os.path.exists(path):
        _frame_cache[key] = False
        return None
    sheet = pygame.image.load(path).convert_alpha()
    n_dirs   = sheet.get_height() // _SMASH_CELL   # 4
    n_frames = sheet.get_width()  // _SMASH_CELL   # 6
    all_dirs = [
        [sheet.subsurface(c * _SMASH_CELL, r * _SMASH_CELL, _SMASH_CELL, _SMASH_CELL)
         for c in range(n_frames)]
        for r in range(n_dirs)
    ]
    _frame_cache[key] = all_dirs
    return all_dirs


def _blit_layer(
    screen: pygame.Surface,
    spec: LayerSpec,
    anim: str,
    dir_row: int,
    frame_idx: int,
    x: int,
    y: int,
    tint_override: tuple | None = None,
) -> None:
    """Blit one equipment layer at (x, y), applying spec.tint if set.
    Falls back through slash → walk if the layer lacks the requested anim sheet."""
    frames = _get_cached(spec.folder, anim, spec.colour)
    if frames is None and anim == "thrust":
        frames = _get_cached(spec.folder, "slash", spec.colour)
    if frames is None and anim in ("slash", "thrust"):
        frames = _get_cached(spec.folder, "walk", spec.colour)
    if frames is None and anim == "idle":
        frames = _get_cached(spec.folder, "walk", spec.colour)
    if frames is None and anim == "run":
        frames = _get_cached(spec.folder, "walk", spec.colour)
    actual_row = dir_row + spec.row_offset
    if frames is None or actual_row >= len(frames) or frame_idx >= len(frames[actual_row]):
        return
    surf = frames[actual_row][frame_idx]
    tint = tint_override if tint_override is not None else spec.tint
    if tint:
        surf = surf.copy()
        surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(surf, (x, y))


def _weapon_carry_surf(
    weapon_spec: LayerSpec,
    which: str,
    dir_row: int,
    frame: int,
    anim: str,
) -> pygame.Surface | None:
    """Return the Surface for a weapon carry layer (walk/run/idle only), or None.
    which: 'behind' — rendered before the body (uses behind/universal_behind sheet)
           'front'  — rendered after equipment (uses main walk sheet)
    """
    use_128 = weapon_spec.col_stride > 1
    load    = _get_cached_128 if use_128 else _get_cached
    name    = weapon_spec.folder.rsplit("/", 1)[-1]

    if which == "behind":
        row = dir_row  # both 64px and 128px behind sheets use standard 4-row indexing
        if weapon_spec.behind == "universal_behind":
            frames = load(f"{weapon_spec.folder}/universal_behind/walk", name, None)
        elif weapon_spec.behind == "behind":
            frames = load(f"{weapon_spec.folder}/walk/behind", name, None)
        else:
            return None
    else:  # "front"
        row    = dir_row if use_128 else dir_row * weapon_spec.row_stride + weapon_spec.row_offset
        w_anim = "walk" if anim == "run" else anim
        frames = load(weapon_spec.folder, w_anim, weapon_spec.colour)
        if frames is None and w_anim != "walk":
            frames = load(weapon_spec.folder, "walk", weapon_spec.colour)
        if frames is None:
            frames = load(weapon_spec.folder, "slash", weapon_spec.colour)

    if frames is None or row >= len(frames) or not frames[row]:
        return None
    if use_128:
        col = 0 if anim == "idle" else min(frame, len(frames[row]) - 1)
    else:
        col = (0 if anim == "idle" else frame) * weapon_spec.col_stride + weapon_spec.x_offset
        col = min(col, len(frames[row]) - 1)
    return frames[row][col]


# ---------------------------------------------------------------------------
# Public: animation update (local player)
# ---------------------------------------------------------------------------
def update(dt: float) -> None:
    """Advance animation state. Call once per tick before draw_player."""
    global _anim, _frame, _anim_timer, _roll_squish

    if config.is_attacking:
        # slash for weapons, thrust for tools (axe/pickaxe) and unarmed
        target_anim  = get_weapon_attack_anim(config.player_inventory)
        atk_n_frames = _ATK_FRAMES if target_anim == "slash" else _THRUST_FRAMES
        if _anim != target_anim:
            _anim       = target_anim
            _frame      = 0
            _anim_timer = 0.0
        _anim_timer += dt
        frame = int(_anim_timer * _ATK_FPS)
        if frame >= atk_n_frames:
            config.is_attacking = False
            _anim       = "idle"
            _frame      = 0
            _anim_timer = 0.0
        else:
            _frame = frame
    elif config.is_moving:
        target_anim = "run" if config.is_running else "walk"
        if _anim != target_anim:
            _anim       = target_anim
            _anim_timer = 0.0
        fps    = _RUN_FPS if _anim == "run" else _WALK_FPS
        frames = _RUN_FRAMES if _anim == "run" else _WALK_FRAMES
        _anim_timer += dt
        if _anim == "walk":
            # LPC walk sheet: col 0 = standing pose (used for idle only).
            # Actual walk cycle is cols 1-8, so cycle 8 frames starting at 1.
            _frame = int(_anim_timer * fps) % 8 + 1
        else:
            _frame = int(_anim_timer * fps) % frames
    else:
        if _anim != "idle":
            _anim       = "idle"
            _frame      = 0
            _anim_timer = 0.0
        _anim_timer += dt
        _frame = int(_anim_timer * _IDLE_FPS) % _IDLE_FRAMES

    # Squish scale — ramp toward 0.55 while rolling, snap back to 1.0 after
    if config.rolling:
        _roll_squish = max(0.55, _roll_squish - dt * 5.0)
    else:
        _roll_squish = min(1.0, _roll_squish + dt * 10.0)


def get_sprite_feet_offset() -> float:
    """Return Y offset in world tiles from entity's world pos to sprite feet.
    Used as Y-depth sort key for layered rendering."""
    return CELL / 2.0 / 32.0


# ---------------------------------------------------------------------------
# Public: local player draw
# ---------------------------------------------------------------------------
def draw_player(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    """Draw the local player sprite centred on screen."""
    d       = config.player_facing
    anim    = _anim
    frame   = _frame
    dir_row = DIR_ROW.get(d, 0)

    # Centre the 64×64 cell on screen
    x = window_width  // 2 - CELL // 2
    y = window_height // 2 - CELL // 2

    # Dodge-roll squish: render all layers to an off-screen CELL×CELL surface,
    # then scale it vertically and blit to screen (feet-anchored).
    global _roll_surf
    _squish = _roll_squish < 1.0
    if _squish:
        if _roll_surf is None or _roll_surf.get_size() != (CELL, CELL):
            _roll_surf = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        _roll_surf.fill((0, 0, 0, 0))
        target, lx, ly = _roll_surf, 0, 0
    else:
        target, lx, ly = screen, x, y

    # Appearance-based folders (dynamic)
    _app        = config.player_appearance
    _sex        = _app.get("body", "male")
    _body_fld   = f"body/bodies/{_sex}"
    _head_fld   = f"head/heads/human/{_sex}"
    _hair_style = _app.get("hair_style", "plain")
    _hair_fld   = f"hair/{_hair_style}/adult"
    _wing_type  = _app.get("back_ext")            # None or e.g. "feathered"
    _wing_col   = _app.get("back_ext_color", "white")
    _wing_bg_fld: str | None = None
    _wing_fg_fld: str | None = None
    # Equipped wing item in back slot overrides appearance wings
    _wing_item = get_wing_item(config.player_inventory)
    if _wing_item is not None:
        _wing_bg_fld, _wing_fg_fld, _wing_col = _wing_item
        _wing_type = None  # suppress appearance-based wing path
    elif _wing_type is not None:
        _wing_bg_fld = f"body/wings/{_wing_type}/adult/bg"
        _wing_fg_fld = f"body/wings/{_wing_type}/adult/fg"
    _skin_tint  = _app.get("skin_tint")           # None or (r,g,b,a) tuple

    # Effect tint (overrides per-item tints while active)
    effect_tint: tuple | None = None
    if config.hit_flash_timer > 0.0:
        effect_tint = (255, 80, 80, 255)
    elif config.player_slow_timer > 0.0:
        effect_tint = (80, 220, 100, 255)

    # Determine weapon/tool held — needed before body draw for smash background pass
    weapon_spec = get_weapon_layer(config.player_inventory)
    _is_smash = (
        anim == "slash"
        and weapon_spec is not None
        and weapon_spec.folder == "tools/smash/universal/male"
        and weapon_spec.colour is not None
    )
    _smash_tint = (effect_tint if effect_tint is not None else
                   (weapon_spec.tint if weapon_spec is not None else None))

    # Smash background layer (rendered BEFORE body so it appears behind character)
    smash_frame = _ATK_FRAMES - 1 - frame   # smash sheets store frames end→start
    body_frame  = smash_frame if _is_smash else frame
    if _is_smash:
        bg_frames = _get_smash_frames(weapon_spec.colour, "background")
        if bg_frames and dir_row < len(bg_frames) and smash_frame < len(bg_frames[dir_row]):
            surf = bg_frames[dir_row][smash_frame]
            if _smash_tint:
                surf = surf.copy()
                surf.fill(_smash_tint, special_flags=pygame.BLEND_RGBA_MULT)
            target.blit(surf, (lx - CELL // 2, ly - CELL // 2))

    # Cape / cloak layer (rendered BEFORE body so it drapes behind the character)
    cape_spec = get_back_layer(config.player_inventory)
    if cape_spec is not None:
        tint = effect_tint if effect_tint is not None else cape_spec.tint
        _blit_layer(target, cape_spec, anim, dir_row, body_frame, lx, ly, tint_override=tint)

    # Weapon behind layer (rendered BEFORE body) — all non-thrust anims
    if weapon_spec is not None and weapon_spec.behind != "none" and anim != "thrust":
        if anim == "slash":
            # Slash attack: render the dedicated behind-body attack frame
            if weapon_spec.col_stride > 1:
                # 128px-cell slash/behind sheet (katana)
                _sb = _get_cached_128(weapon_spec.folder, "slash/behind", weapon_spec.colour)
                _sb_blit = (lx - CELL // 2, ly - CELL // 2)
                _sb_col  = frame
            else:
                # 192px attack_slash/behind sheet (longsword, etc.)
                _sb = _get_attack_behind_cached(weapon_spec.folder, weapon_spec.colour)
                _sb_blit = (lx - CELL, ly - CELL)
                _sb_col  = frame
            if _sb and dir_row < len(_sb) and _sb_col < len(_sb[dir_row]):
                surf = _sb[dir_row][_sb_col]
                tint = effect_tint if effect_tint is not None else weapon_spec.tint
                if tint:
                    surf = surf.copy()
                    surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
                target.blit(surf, _sb_blit)
        else:
            # Walk / run / idle: use carry behind frame
            surf = _weapon_carry_surf(weapon_spec, "behind", dir_row, body_frame, anim)
            if surf is not None:
                tint = effect_tint if effect_tint is not None else weapon_spec.tint
                if tint:
                    surf = surf.copy()
                    surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
                _wp = (lx - CELL // 2, ly - CELL // 2) if weapon_spec.col_stride > 1 else (lx, ly + weapon_spec.y_offset)
                target.blit(surf, _wp)

    # Wing background layer (behind body)
    if _wing_bg_fld:
        _wing_bg = LayerSpec(_wing_bg_fld, colour=_wing_col)
        _blit_layer(target, _wing_bg, anim, dir_row, body_frame, lx, ly,
                    tint_override=effect_tint)

    # Body + head (permanent base layers, sex-aware)
    for base_folder in (_body_fld, _head_fld):
        base_frames = _get_cached(base_folder, anim, None)
        if base_frames and dir_row < len(base_frames) and body_frame < len(base_frames[dir_row]):
            surf = base_frames[dir_row][body_frame]
            _btint = effect_tint if effect_tint is not None else (_skin_tint if _skin_tint else None)
            if _btint:
                surf = surf.copy()
                surf.fill(_btint, special_flags=pygame.BLEND_RGBA_MULT)
            target.blit(surf, (lx, ly))

    # Hair layer (rendered on top of body/head)
    _hair_frames = _get_cached(_hair_fld, anim, None)
    if _hair_frames and dir_row < len(_hair_frames) and body_frame < len(_hair_frames[dir_row]):
        _hsurf = _hair_frames[dir_row][body_frame]
        if effect_tint:
            _hsurf = _hsurf.copy()
            _hsurf.fill(effect_tint, special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(_hsurf, (lx, ly))

    # Equipment layers (bottom → top)
    layers = get_layers(config.player_inventory)
    for spec in layers:
        tint = effect_tint if effect_tint is not None else spec.tint
        _blit_layer(target, spec, anim, dir_row, body_frame, lx, ly, tint_override=tint)

    # Smash foreground layer (rendered AFTER body so it appears in front of character)
    # or weapon carry frame during walk/run/idle
    if _is_smash:
        fg_frames = _get_smash_frames(weapon_spec.colour, "foreground")
        if fg_frames and dir_row < len(fg_frames) and smash_frame < len(fg_frames[dir_row]):
            surf = fg_frames[dir_row][smash_frame]
            if _smash_tint:
                surf = surf.copy()
                surf.fill(_smash_tint, special_flags=pygame.BLEND_RGBA_MULT)
            target.blit(surf, (lx - CELL // 2, ly - CELL // 2))
    elif weapon_spec is not None and anim == "slash":
        # Attack: try 192-px attack_slash overlay (longsword, mace, waraxe, …)
        # then fall back to 64-px slash sheet (dagger and other weapons)
        atk = _get_attack_cached(weapon_spec.folder, weapon_spec.colour)
        if atk and dir_row < len(atk) and frame < len(atk[dir_row]):
            surf = atk[dir_row][frame]
            tint = effect_tint if effect_tint is not None else weapon_spec.tint
            if tint:
                surf = surf.copy()
                surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
            # Centre the 192-px frame on the player cell
            target.blit(surf, (lx - CELL, ly - CELL))
        else:
            _load_fn   = _get_cached_128 if weapon_spec.col_stride > 1 else _get_cached
            slash_f    = _load_fn(weapon_spec.folder, "slash", weapon_spec.colour)
            if weapon_spec.col_stride > 1:
                _slash_row = dir_row
                _slash_col = frame
            else:
                _slash_row = dir_row * weapon_spec.row_stride + weapon_spec.row_offset
                _slash_col = frame * weapon_spec.col_stride + weapon_spec.x_offset
            if slash_f and _slash_row < len(slash_f) and _slash_col < len(slash_f[_slash_row]):
                surf = slash_f[_slash_row][_slash_col]
                tint = effect_tint if effect_tint is not None else weapon_spec.tint
                if tint:
                    surf = surf.copy()
                    surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
                _wp = (lx - CELL // 2, ly - CELL // 2) if weapon_spec.col_stride > 1 else (lx, ly + weapon_spec.y_offset)
                target.blit(surf, _wp)
    elif weapon_spec is not None and anim not in ("slash", "thrust"):
        # Walk / run / idle: show weapon front carry frame
        surf = _weapon_carry_surf(weapon_spec, "front", dir_row, frame, anim)
        if surf is not None:
            tint = effect_tint if effect_tint is not None else weapon_spec.tint
            if tint:
                surf = surf.copy()
                surf.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
            _wp = (lx - CELL // 2, ly - CELL // 2) if weapon_spec.col_stride > 1 else (lx, ly + weapon_spec.y_offset)
            target.blit(surf, _wp)
    # anim == "thrust" (unarmed punch) → no weapon visible

    # Wing foreground layer (in front of body and equipment)
    if _wing_fg_fld:
        _wing_fg = LayerSpec(_wing_fg_fld, colour=_wing_col)
        _blit_layer(target, _wing_fg, anim, dir_row, body_frame, lx, ly,
                    tint_override=effect_tint)

    # Flush squish surface to screen (feet-anchored)
    if _squish:
        sq_h = max(1, int(CELL * _roll_squish))
        squished = pygame.transform.scale(_roll_surf, (CELL, sq_h))
        screen.blit(squished, (x, y + CELL - sq_h))

    # Hitbox outline (white, 32×32 centred)
    pygame.draw.rect(
        screen, (255, 255, 255),
        (window_width // 2 - 16, window_height // 2 - 16, 32, 32), 1
    )


# ---------------------------------------------------------------------------
# Public: remote player draw
# ---------------------------------------------------------------------------
def draw_remote_player(
    screen: pygame.Surface,
    pos: list,
    facing: str,
    walk_frame: int,
    player_x: float,
    player_y: float,
    window_width: int,
    window_height: int,
    is_attacking: bool = False,
    atk_frame: int = 0,
    equip_ids: dict | None = None,
    name: str | None = None,
    appearance: dict | None = None,
) -> None:
    """Draw a remote player sprite at their world position."""
    d       = facing if facing in DIR_ROW else "down"
    dir_row = DIR_ROW[d]

    if is_attacking:
        anim  = "slash"
        frame = min(atk_frame, _ATK_FRAMES - 1)
    elif walk_frame > 0:
        anim  = "walk"
        frame = walk_frame % _WALK_FRAMES
    else:
        anim  = "idle"
        frame = 0

    # World → screen
    sx = int((pos[0] - player_x) * 32 + window_width  // 2 - CELL // 2)
    sy = int((pos[1] - player_y) * 32 + window_height // 2 - CELL // 2)

    # Resolve appearance
    _app       = appearance or {}
    _sex       = _app.get("body", "male")
    _body_fld  = f"body/bodies/{_sex}"
    _head_fld  = f"head/heads/human/{_sex}"
    _hair_fld  = f"hair/{_app.get('hair_style', 'plain')}/adult"
    _wing_type = _app.get("back_ext")
    _wing_col  = _app.get("back_ext_color", "white")
    _wing_bg_fld_r: str | None = None
    _wing_fg_fld_r: str | None = None
    # Equipped wing item overrides appearance wings for remote players too
    if equip_ids:
        _wing_item_r = get_wing_item_from_equip_ids(equip_ids)
        if _wing_item_r is not None:
            _wing_bg_fld_r, _wing_fg_fld_r, _wing_col = _wing_item_r
            _wing_type = None
    if _wing_type is not None:
        _wing_bg_fld_r = f"body/wings/{_wing_type}/adult/bg"
        _wing_fg_fld_r = f"body/wings/{_wing_type}/adult/fg"
    _skin_tint = _app.get("skin_tint")

    # Cape layer (rendered BEFORE body so it drapes behind the character)
    if equip_ids:
        remote_cape = get_back_layer_from_equip_ids(equip_ids)
        if remote_cape is not None:
            _blit_layer(screen, remote_cape, anim, dir_row, frame, sx, sy)

    # Wing background layer (behind body)
    if _wing_bg_fld_r:
        _blit_layer(screen, LayerSpec(_wing_bg_fld_r, colour=_wing_col),
                    anim, dir_row, frame, sx, sy)

    # Body + head (sex-aware)
    for base_folder in (_body_fld, _head_fld):
        base_frames = _get_cached(base_folder, anim, None)
        if base_frames and dir_row < len(base_frames) and frame < len(base_frames[dir_row]):
            surf = base_frames[dir_row][frame]
            if _skin_tint:
                surf = surf.copy()
                surf.fill(_skin_tint, special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(surf, (sx, sy))

    # Hair layer
    _hair_frames = _get_cached(_hair_fld, anim, None)
    if _hair_frames and dir_row < len(_hair_frames) and frame < len(_hair_frames[dir_row]):
        screen.blit(_hair_frames[dir_row][frame], (sx, sy))

    # Equipment layers
    if equip_ids:
        layers = get_layers_from_equip_ids(equip_ids)
    else:
        layers = [_LEGS_DEFAULT]

    for spec in layers:
        _blit_layer(screen, spec, anim, dir_row, frame, sx, sy)

    # Wing foreground layer (in front of equipment)
    if _wing_fg_fld_r:
        _blit_layer(screen, LayerSpec(_wing_fg_fld_r, colour=_wing_col),
                    anim, dir_row, frame, sx, sy)

    # Hitbox outline (yellow, 32×32 centred)
    pygame.draw.rect(
        screen, (255, 220, 0),
        (sx + CELL // 2 - 16, sy + CELL // 2 - 16, 32, 32), 1
    )

    # Player name above sprite
    if name:
        if not hasattr(draw_remote_player, "_name_font"):
            draw_remote_player._name_font = pygame.font.SysFont("Arial", 11, bold=True)
        nf = draw_remote_player._name_font
        ns = nf.render(name, True, (255, 255, 255))
        nx = sx + CELL // 2 - ns.get_width() // 2
        ny = sy - ns.get_height() - 2
        # Drop-shadow for readability
        shadow = nf.render(name, True, (0, 0, 0))
        screen.blit(shadow, (nx + 1, ny + 1))
        screen.blit(ns, (nx, ny))

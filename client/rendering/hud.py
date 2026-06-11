import pygame
import time
import config

BAR_HEIGHT  = 18
BAR_PAD     = 6

# Hotbar geometry — must match inventory.py
_SLOT_SIZE  = 40
_SLOT_PAD   = 4
_GRID_COLS  = 9
_HB_W       = _GRID_COLS * (_SLOT_SIZE + _SLOT_PAD) - _SLOT_PAD  # 392 px

_EXP_BAR_H   = 12
_EXP_BTM_PAD = 5
_GAP         = 4   # vertical gap between HUD rows
_PANEL_PAD_V = 4   # extra padding above topmost element

# ---------------------------------------------------------------------------
# Toast / notification banner
# ---------------------------------------------------------------------------
_toasts: list[tuple[str, float]] = []   # (text, expiry_unix_time)
_TOAST_DURATION = 3.5
_TOAST_FADE     = 0.6   # seconds before expiry to start fading
_MAX_TOASTS     = 5
_TERRITORY_BANNER_DURATION = 3.0


def show_toast(text: str, duration: float = _TOAST_DURATION) -> None:
    """Queue a toast message to be displayed on screen."""
    now = time.time()
    _toasts[:] = [(msg, exp) for msg, exp in _toasts if now < exp]
    _toasts.append((text, time.time() + duration))
    if len(_toasts) > _MAX_TOASTS:
        del _toasts[:-_MAX_TOASTS]


def draw_toasts(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    """Draw all active toasts, centred near the top of the screen."""
    now = time.time()
    # Prune expired
    active = [(t, exp) for t, exp in _toasts if now < exp]
    _toasts.clear()
    _toasts.extend(active)

    font = _get_font()
    fh   = font.get_height()
    y    = 20   # near top of screen (no top-right panel any more)
    for text, exp in active:
        remaining = exp - now
        alpha = min(1.0, remaining / _TOAST_FADE)
        a = int(alpha * 220)
        surf = pygame.Surface((window_width, fh + 10), pygame.SRCALPHA)
        # Dark background strip
        bg = pygame.Surface((window_width, fh + 10), pygame.SRCALPHA)
        bg.fill((0, 0, 0, min(a, 140)))
        surf.blit(bg, (0, 0))
        txt = font.render(text, True, (255, 230, 100))
        txt.set_alpha(a)
        tx = (window_width - txt.get_width()) // 2
        surf.blit(txt, (tx, 5))
        screen.blit(surf, (0, y))
        y += fh + 12


def show_territory_banner(text: str, duration: float = _TERRITORY_BANNER_DURATION) -> None:
    """Display a location-style banner when crossing faction territory boundaries."""
    now = time.time()
    config.territory_banner_text = text
    config.territory_banner_started_at = now
    config.territory_banner_until = now + max(0.5, duration)


def draw_territory_banner(screen: pygame.Surface, window_width: int, window_height: int) -> None:
    """Draw a clean territory banner across the top of the screen."""
    text = getattr(config, "territory_banner_text", "")
    started_at = float(getattr(config, "territory_banner_started_at", 0.0))
    until = float(getattr(config, "territory_banner_until", 0.0))
    if not text or started_at <= 0.0 or until <= 0.0:
        return

    now = time.time()
    if now >= until:
        config.territory_banner_text = ""
        config.territory_banner_started_at = 0.0
        config.territory_banner_until = 0.0
        return

    total = max(0.001, until - started_at)
    progress = max(0.0, min(1.0, (now - started_at) / total))
    fade = 1.0
    if progress < 0.16:
        fade = progress / 0.16
    elif progress > 0.82:
        fade = max(0.0, (1.0 - progress) / 0.18)

    font = _get_font()
    txt = font.render(text, True, (255, 245, 210))
    txt_alpha = int(255 * fade)
    txt.set_alpha(txt_alpha)

    bar_h = txt.get_height() + 14
    y = 18
    base = pygame.Surface((window_width, bar_h), pygame.SRCALPHA)
    base.fill((18, 22, 30, int(120 * fade)))
    screen.blit(base, (0, y))

    edge = pygame.Surface((window_width, 2), pygame.SRCALPHA)
    edge.fill((255, 225, 150, int(160 * fade)))
    screen.blit(edge, (0, y + bar_h - 2))

    tx = (window_width - txt.get_width()) // 2
    screen.blit(txt, (tx, y + (bar_h - txt.get_height()) // 2))

_font = None


def _get_font():
    global _font
    if _font is None:
        _font = pygame.font.SysFont("Arial", 13)
    return _font


def _draw_bar_w(screen, x, y, w, ratio, fill_color, label):
    """Draw a bar of explicit pixel width *w*."""
    pygame.draw.rect(screen, (60, 60, 60),    (x, y, w, BAR_HEIGHT), border_radius=4)
    fill_w = int(w * max(0.0, min(1.0, ratio)))
    if fill_w > 0:
        pygame.draw.rect(screen, fill_color,  (x, y, fill_w, BAR_HEIGHT), border_radius=4)
    pygame.draw.rect(screen, (180, 180, 180), (x, y, w, BAR_HEIGHT), 1, border_radius=4)
    text = _get_font().render(label, True, (255, 255, 255))
    screen.blit(text, (x + 5, y + 2))


def draw_hud(screen, window_width, window_height):
    """Compact bottom HUD.

    Layout (upward from the slot row):
        [ HP bar (left half) | SP bar (right half) ]   ← 16 px
        [ EXP bar — thin full-width                ]   ←  8 px
        ── separator ──
        [ hotbar slots                             ]   ← 40 px
    Right of hotbar : Coins (+ Creative badge above)
    Left of hotbar  : BLOCK indicator when blocking
    """
    font = _get_font()
    fh   = font.get_height()

    # ── Hotbar reference geometry ────────────────────────────────────────
    hb_w       = _HB_W
    hb_x       = (window_width - hb_w) // 2
    hb_y       = window_height - _SLOT_SIZE - 10   # top of slot icons
    label_h    = fh + 2                             # hotbar number labels
    hotbar_top = hb_y - _SLOT_PAD - label_h         # top edge of hotbar backdrop

    # ── Compact stats layout (2 rows above hotbar) ───────────────────────
    _BAR_H = 16    # HP / SP bar height
    _EXP_H =  8    # thin EXP bar height
    _GAP   =  3    # spacing between rows

    exp_y  = hotbar_top - _GAP - _EXP_H
    bars_y = exp_y - _GAP - _BAR_H
    half_w = (hb_w - _GAP) // 2

    panel_top = bars_y - _PANEL_PAD_V
    panel_h   = (window_height - 6) - panel_top

    # ── Unified backdrop ─────────────────────────────────────────────────
    backdrop = pygame.Surface((hb_w + BAR_PAD * 2, panel_h), pygame.SRCALPHA)
    backdrop.fill((0, 0, 0, 165))
    screen.blit(backdrop, (hb_x - BAR_PAD, panel_top))
    pygame.draw.rect(screen, (55, 80, 115),
                     (hb_x - BAR_PAD, panel_top, hb_w + BAR_PAD * 2, panel_h),
                     1, border_radius=4)
    # Separator between stats and hotbar slot row
    pygame.draw.line(screen, (70, 70, 70),
                     (hb_x - BAR_PAD + 4, hotbar_top),
                     (hb_x + hb_w + BAR_PAD - 4, hotbar_top))

    # ── HP bar (left half) — includes DEF in the label ───────────────────
    hp     = config.player_health
    hp_max = max(1, config.player_health_max)
    hp_col = (255, 215, 0) if hp / hp_max < 0.3 else (50, 200, 50)
    hp_lbl = f"HP {int(hp)}/{int(hp_max)}  DEF:{int(config.player_defense)}"
    pygame.draw.rect(screen, (60, 60, 60),    (hb_x, bars_y, half_w, _BAR_H), border_radius=3)
    fw = int(half_w * max(0.0, min(1.0, hp / hp_max)))
    if fw > 0:
        pygame.draw.rect(screen, hp_col,      (hb_x, bars_y, fw, _BAR_H), border_radius=3)
    pygame.draw.rect(screen, (180, 180, 180), (hb_x, bars_y, half_w, _BAR_H), 1, border_radius=3)
    hs = font.render(hp_lbl, True, (255, 255, 255))
    screen.blit(hs, (hb_x + 4, bars_y + (_BAR_H - hs.get_height()) // 2))

    # ── SP bar (right half) ───────────────────────────────────────────────
    sp     = config.player_stamina
    sp_max = max(1, config.player_stamina_max)
    sp_col = (255, 215, 0) if sp / sp_max < 0.3 else (60, 120, 220)
    sp_lbl = f"SP {int(sp)}/{int(sp_max)}"
    sp_x   = hb_x + half_w + _GAP
    sp_w   = hb_w - half_w - _GAP
    pygame.draw.rect(screen, (60, 60, 60),    (sp_x, bars_y, sp_w, _BAR_H), border_radius=3)
    fw = int(sp_w * max(0.0, min(1.0, sp / sp_max)))
    if fw > 0:
        pygame.draw.rect(screen, sp_col,      (sp_x, bars_y, fw, _BAR_H), border_radius=3)
    pygame.draw.rect(screen, (180, 180, 180), (sp_x, bars_y, sp_w, _BAR_H), 1, border_radius=3)
    ss = font.render(sp_lbl, True, (255, 255, 255))
    screen.blit(ss, (sp_x + 4, bars_y + (_BAR_H - ss.get_height()) // 2))

    # ── EXP bar (thin) — level label left, bar fills remaining width ─────
    exp      = config.player_exp
    exp_next = max(1, config.player_exp_next)
    lv_surf  = font.render(f"Lv.{config.player_level}", True, (220, 220, 100))
    lv_w     = lv_surf.get_width() + 4
    bar_x    = hb_x + lv_w
    bar_w    = hb_w - lv_w
    fill_w   = int(bar_w * min(1.0, exp / exp_next))
    pygame.draw.rect(screen, (30, 30, 30),    (bar_x, exp_y, bar_w, _EXP_H), border_radius=3)
    if fill_w > 0:
        pygame.draw.rect(screen, (40, 180, 70), (bar_x, exp_y, fill_w, _EXP_H), border_radius=3)
    pygame.draw.rect(screen, (70, 120, 70),   (bar_x, exp_y, bar_w, _EXP_H), 1, border_radius=3)
    screen.blit(lv_surf, (hb_x, exp_y + (_EXP_H - lv_surf.get_height()) // 2))

    # ── Unspent stat points indicator — above EXP bar ────────────────────
    if config.player_stat_points > 0:
        pts_surf = font.render(f"+ {config.player_stat_points} stat point(s) — press P", True, (80, 255, 180))
        pts_x = hb_x
        pts_y = exp_y - pts_surf.get_height() - 4
        pts_bg = pygame.Surface((pts_surf.get_width() + 10, pts_surf.get_height() + 4), pygame.SRCALPHA)
        pts_bg.fill((0, 0, 0, 150))
        screen.blit(pts_bg, (pts_x - 5, pts_y - 2))
        screen.blit(pts_surf, (pts_x, pts_y))

    # ── Coins — right of hotbar, vertically centred on slot row ─────────
    coin_x    = hb_x + hb_w + 12
    coin_y    = hb_y + (_SLOT_SIZE - fh) // 2
    coin_surf = font.render(f"\u25cf  {config.player_coins}", True, (255, 215, 0))
    coin_bg   = pygame.Surface((coin_surf.get_width() + 10, coin_surf.get_height() + 6), pygame.SRCALPHA)
    coin_bg.fill((0, 0, 0, 140))
    screen.blit(coin_bg,   (coin_x - 5, coin_y - 3))
    screen.blit(coin_surf, (coin_x, coin_y))

    # ── Creative badge — above coins ─────────────────────────────────────
    if config.player_creative:
        badge_surf = font.render("CREATIVE", True, (255, 255, 100))
        bx2 = coin_x - 5
        by2 = coin_y - badge_surf.get_height() - 8
        bg  = pygame.Surface((badge_surf.get_width() + 10, badge_surf.get_height() + 6), pygame.SRCALPHA)
        bg.fill((80, 60, 0, 180))
        screen.blit(bg, (bx2, by2))
        pygame.draw.rect(screen, (200, 160, 0), (bx2, by2, bg.get_width(), bg.get_height()), 1, border_radius=3)
        screen.blit(badge_surf, (bx2 + 5, by2 + 3))

    # ── Block indicator — left of hotbar when blocking ────────────────────
    if config.is_blocking:
        _parry_window = time.time() - config.block_start_time < config.PARRY_WINDOW
        _blk_col  = (255, 220, 60) if _parry_window else (100, 160, 255)
        blk_surf  = font.render("\u25a0 BLOCK", True, _blk_col)
        blk_x     = hb_x - blk_surf.get_width() - 14
        blk_bg    = pygame.Surface((blk_surf.get_width() + 10, fh + 6), pygame.SRCALPHA)
        blk_bg.fill((0, 20, 70, 200))
        screen.blit(blk_bg, (blk_x - 5, coin_y - 3))
        pygame.draw.rect(screen, (80, 130, 220),
                         (blk_x - 5, coin_y - 3, blk_bg.get_width(), blk_bg.get_height()),
                         1, border_radius=3)
        screen.blit(blk_surf, (blk_x, coin_y))


# ---------------------------------------------------------------------------
# Level / EXP bar — now drawn inside draw_hud; kept as no-op for compat
# ---------------------------------------------------------------------------


def draw_level_bar(screen, window_width, window_height):
    """No-op — level/EXP bar is rendered inside draw_hud."""
    return


# ---------------------------------------------------------------------------
# Death overlay — drawn on top of everything when the player is dead
# ---------------------------------------------------------------------------
_big_font = None
_small_font = None

def _get_big_font():
    global _big_font
    if _big_font is None:
        _big_font = pygame.font.SysFont("Arial", 64, bold=True)
    return _big_font

def _get_small_font():
    global _small_font
    if _small_font is None:
        _small_font = pygame.font.SysFont("Arial", 22)
    return _small_font


def draw_death_overlay(screen, window_width, window_height):
    """Full-screen dark overlay shown while the player is dead."""
    if not config.player_dead:
        return

    overlay = pygame.Surface((window_width, window_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    cx = window_width  // 2
    cy = window_height // 2

    title = _get_big_font().render("YOU DIED", True, (200, 30, 30))
    screen.blit(title, (cx - title.get_width() // 2, cy - 60))

    secs = config.player_respawn_in
    sub_str = f"Respawning in {secs:.1f}s..." if secs > 0 else "Respawning..."
    sub = _get_small_font().render(sub_str, True, (220, 180, 180))
    screen.blit(sub, (cx - sub.get_width() // 2, cy + 20))

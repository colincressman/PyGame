"""client/rendering/ui_theme.py

Shared UI palette for all popups and panels in the game.
All rendering files should derive their chrome colours from these constants
so that a single edit here propagates everywhere.
"""

# ── Panel chrome ──────────────────────────────────────────────────────────────
OVERLAY_ALPHA = 172              # full-screen backdrop alpha behind menus/panels
BG_FILL   = (18, 18, 24)        # SRCALPHA surface .fill() colour (pair with BG_ALPHA)
BG_ALPHA  = 230                 # alpha for semi-transparent panel backgrounds
BORDER    = (88, 88, 108)       # 2-px panel border
RADIUS    = 6                   # border_radius for panels
TITLE_BAR = (28, 28, 42)        # solid rect drawn across the top of each panel
TITLE_H   = 28                  # standard title-bar height in pixels
TITLE_TXT = (220, 215, 195)     # warm off-white title text
HINT_TXT  = (108, 108, 128)     # "[F / ESC to close]" muted helper text
DIVIDER   = (62, 62, 80)        # horizontal divider lines
LABEL_TXT = (155, 150, 175)     # secondary label text (slot labels, section headers)

# ── Item slots ────────────────────────────────────────────────────────────────
SLOT_BG   = (32, 32, 42)        # empty slot fill
SLOT_BD   = (78, 78, 98)        # slot border (normal)
SLOT_SEL  = (255, 215,  0)      # selected / active slot border  (gold — universal)
SLOT_HOV  = (185, 185, 255)     # hovered slot border
SLOT_FILL = (44, 40, 58)        # slot that contains an item  (station UIs)
SLOT_FILL_BD = (98, 88, 128)    # border for a filled station slot

# ── Primary action button (CRAFT / COMBINE / REPAIR / EMBED) ─────────────────
BTN_BG    = (45, 110, 55)
BTN_BD    = (78, 185, 90)
BTN_TXT   = (255, 255, 255)
BTN_HOV   = (58, 140, 68)
BTN_DIS_BG = (38, 38, 46)
BTN_DIS_BD = (60, 60, 76)
BTN_DIS_TX = (84, 84, 100)

# ── Navigation / menu button (pause menu, etc.) ───────────────────────────────
NAV_BG    = (38, 58, 78)
NAV_HOV   = (55, 80, 108)
NAV_BD    = (88, 88, 108)

# ── Sub-panel / detail column inside a popup ─────────────────────────────────
SUB_BG    = (24, 24, 32)
SUB_BD    = (55, 55, 72)

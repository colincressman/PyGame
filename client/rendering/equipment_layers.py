"""
equipment_layers.py — Maps equipped item IDs to LPC layer specifications.

Layer render order (bottom → top):
  1. body      (always — body/bodies/male)
  2. legs      (always — default pants or equipped leggings/plate)
  3. torso     (when chest slot filled)
  4. arms      (when arms slot filled)
  5. feet      (when feet slot filled)
  6. head      (when head slot filled)

Each LayerSpec carries:
  folder : str            path relative to LPC spritesheets root
  colour : str | None     colour-subdir variant (None → use direct .png)
  tint   : tuple | None   RGBA multiplier applied via BLEND_RGBA_MULT (None = no tint)
"""

from typing import NamedTuple


class LayerSpec(NamedTuple):
    folder: str
    colour: str | None = None
    tint:   tuple | None = None
    row_offset: int = 0   # row offset for non-standard sheets (e.g. katana 8-row)
    behind: str = "none"  # "universal_behind", "behind", or "none"
    row_stride: int = 1   # multiplier for dir_row: actual_row = dir_row * row_stride + row_offset
    col_stride: int = 1
    y_offset:   int = 0   # pixel shift applied to the blit y-position (positive = shift down)
    x_offset:   int = 0


# ---------------------------------------------------------------------------
# Tint palettes (RGBA, used with pygame.BLEND_RGBA_MULT)
# ---------------------------------------------------------------------------
_TINT = {
    "iron":     None,                       # default — no modification
    "copper":   (220, 160, 100, 255),
    "bronze":   (210, 140,  60, 255),
    "steel":    (170, 185, 200, 255),
    "gold":     (255, 195,  40, 255),
    "silver":   (200, 210, 225, 255),
    "crystal":  (130, 200, 255, 255),
    "obsidian": ( 70,  70,  90, 255),
    "bone":     (225, 215, 185, 255),
    "scrap":    (170, 160, 145, 255),
    "reed":     (200, 190, 130, 255),
    "leaf":     (130, 200, 110, 255),
    "stone":    (160, 165, 170, 255),
    "tin":      (185, 195, 200, 255),
    "wood":     (180, 140,  90, 255),
}

# ---------------------------------------------------------------------------
# Head slot (inventory index 36)
# item_id -> LayerSpec
# ---------------------------------------------------------------------------
_HEAD: dict[int, LayerSpec] = {
    3000: LayerSpec("equipment/hat/cloth/leather_cap/adult"),                                # Scrap Cap
    3001: LayerSpec("equipment/hat/helmet/spangenhelm/adult", tint=_TINT["stone"]),         # Stone Helm
    3002: LayerSpec("equipment/hat/helmet/armet/adult"),                                    # Iron Helm
    3003: LayerSpec("equipment/hat/helmet/kettle/adult",       tint=_TINT["copper"]),       # Copper Helm
    3004: LayerSpec("equipment/hat/helmet/barbuta/male",        tint=_TINT["bronze"]),      # Bronze Helm
    3005: LayerSpec("equipment/hat/helmet/close/male",          tint=_TINT["steel"]),       # Steel Helm
    3006: LayerSpec("equipment/hat/formal/crown/adult",         tint=_TINT["gold"]),        # Gold Crown
    3007: LayerSpec("equipment/hat/helmet/armet/adult",         tint=_TINT["crystal"]),     # Crystal Helm
    3008: LayerSpec("equipment/hat/helmet/greathelm/male",      tint=_TINT["obsidian"]),    # Obsidian Helm
}

# ---------------------------------------------------------------------------
# Chest slot (inventory index 37)
# ---------------------------------------------------------------------------
_TORSO: dict[int, LayerSpec] = {
    3100: LayerSpec("equipment/torso/clothes/vest/male",  "leather"),                       # Scrap Vest
    3101: LayerSpec("equipment/torso/clothes/vest/male",  "tan",    tint=_TINT["reed"]),    # Reed Tunic
    3102: LayerSpec("equipment/torso/clothes/vest/male",  "white",  tint=_TINT["bone"]),    # Bone Vest
    3103: LayerSpec("equipment/torso/armour/plate/male"),                                   # Iron Chestplate
    3104: LayerSpec("equipment/torso/armour/leather/male",          tint=_TINT["copper"]),  # Copper Vest
    3105: LayerSpec("equipment/torso/armour/leather/male",          tint=_TINT["bronze"]),  # Bronze Vest
    3106: LayerSpec("equipment/torso/armour/plate/male",            tint=_TINT["steel"]),   # Steel Chestplate
    3107: LayerSpec("equipment/torso/armour/plate/male",            tint=_TINT["gold"]),    # Gold Chestplate
    3108: LayerSpec("equipment/torso/armour/plate/male",            tint=_TINT["crystal"]), # Crystal Chestplate
    3109: LayerSpec("equipment/torso/armour/plate/male",            tint=_TINT["obsidian"]),# Obsidian Chestplate
}

# ---------------------------------------------------------------------------
# Arms slot (inventory index 42)
# ---------------------------------------------------------------------------
_ARMS: dict[int, LayerSpec] = {
    3200: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["bone"]),              # Bone Bracers
    3201: LayerSpec("equipment/arms/bracers/male"),                                         # Iron Bracers
    3202: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["copper"]),            # Copper Bracers
    3203: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["bronze"]),            # Bronze Bracers
    3204: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["steel"]),             # Steel Bracers
    3205: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["gold"]),              # Gold Bracers
    3206: LayerSpec("equipment/arms/bracers/male",       tint=_TINT["crystal"]),           # Crystal Bracers
    3207: LayerSpec("equipment/arms/armour/plate/male",  tint=_TINT["obsidian"]),          # Obsidian Bracers
}

# ---------------------------------------------------------------------------
# Legs slot (inventory index 40)
# None entry = default bare pants (always shown when slot is empty)
# ---------------------------------------------------------------------------
_LEGS_DEFAULT = LayerSpec("legs/pants/male")

_LEGS: dict[int, LayerSpec] = {
    3300: LayerSpec("equipment/legs/leggings/male",       tint=_TINT["scrap"]),            # Scrap Leggings
    3301: LayerSpec("equipment/legs/leggings/male",       tint=_TINT["reed"]),             # Reed Leggings
    3302: LayerSpec("equipment/legs/leggings/male",       tint=_TINT["bone"]),             # Bone Leggings
    3303: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["copper"]),           # Copper Leggings
    3304: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["bronze"]),           # Bronze Leggings
    3305: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["steel"]),            # Steel Leggings
    3306: LayerSpec("equipment/legs/armour/plate/male"),                                   # Iron Leggings
    3307: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["gold"]),             # Gold Leggings
    3308: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["crystal"]),          # Crystal Leggings
    3309: LayerSpec("equipment/legs/armour/plate/male",   tint=_TINT["obsidian"]),         # Obsidian Leggings
}

# ---------------------------------------------------------------------------
# Feet slot (inventory index 41)
# ---------------------------------------------------------------------------
_FEET: dict[int, LayerSpec] = {
    3400: LayerSpec("equipment/feet/sandals/male",          tint=_TINT["leaf"]),           # Leaf Sandals
    3401: LayerSpec("equipment/feet/boots/basic/male"),                                    # Iron Boots
    3402: LayerSpec("equipment/feet/boots/revised/male",    tint=_TINT["bronze"]),         # Bronze Boots
    3403: LayerSpec("equipment/feet/boots/revised/male",    tint=_TINT["steel"]),          # Steel Boots
    3404: LayerSpec("equipment/feet/boots/basic/male",      tint=_TINT["copper"]),         # Copper Boots
    3405: LayerSpec("equipment/feet/armour/plate/male",     "gold"),                       # Gold Boots
    3406: LayerSpec("equipment/feet/armour/plate/male",     "ceramic", tint=_TINT["crystal"]), # Crystal Boots
    3407: LayerSpec("equipment/feet/armour/plate/male",     "iron",    tint=_TINT["obsidian"]), # Obsidian Boots
}

# ---------------------------------------------------------------------------
# Shield slot (inventory index 45)
# Rendered as a standard layer on top of body.
# ---------------------------------------------------------------------------
_SHIELD: dict[int, LayerSpec] = {
    3550: LayerSpec("equipment/shield/round",  tint=_TINT["wood"]),      # Wooden Shield
    3551: LayerSpec("equipment/shield/round",  tint=_TINT["bone"]),      # Bone Shield
    3552: LayerSpec("equipment/shield/round"),                            # Iron Shield
    3553: LayerSpec("equipment/shield/round",  tint=_TINT["copper"]),    # Copper Shield
    3554: LayerSpec("equipment/shield/round",  tint=_TINT["bronze"]),    # Bronze Shield
    3555: LayerSpec("equipment/shield/round",  tint=_TINT["steel"]),     # Steel Shield
    3556: LayerSpec("equipment/shield/round",  tint=_TINT["gold"]),      # Gold Shield
    3557: LayerSpec("equipment/shield/round",  tint=_TINT["crystal"]),   # Crystal Shield
    3558: LayerSpec("equipment/shield/round",  tint=_TINT["obsidian"]),  # Obsidian Shield
}

# ---------------------------------------------------------------------------
# Shoulders slot (inventory index 46)
# ---------------------------------------------------------------------------
_SHOULDERS: dict[int, LayerSpec] = {
    3560: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["bone"]),      # Bone Pauldrons
    3561: LayerSpec("equipment/shoulders/pauldrons/male"),                           # Iron Pauldrons
    3562: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["copper"]),    # Copper Pauldrons
    3563: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["bronze"]),    # Bronze Pauldrons
    3564: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["steel"]),     # Steel Pauldrons
    3565: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["gold"]),      # Gold Pauldrons
    3566: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["crystal"]),   # Crystal Pauldrons
    3567: LayerSpec("equipment/shoulders/pauldrons/male", tint=_TINT["obsidian"]),  # Obsidian Pauldrons
}

# ---------------------------------------------------------------------------
# Gloves (also use arms slot index 42, same slot as bracers)
# Players equip either bracers or gloves in the arms slot.
# ---------------------------------------------------------------------------
_GLOVES: dict[int, LayerSpec] = {
    3570: LayerSpec("equipment/arms/hands/gloves/male"),                             # Cloth Gloves
    3571: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["bone"]),        # Bone Gloves
    3572: LayerSpec("equipment/arms/hands/gloves/male"),                             # Iron Gloves
    3573: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["copper"]),      # Copper Gloves
    3574: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["bronze"]),      # Bronze Gloves
    3575: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["steel"]),       # Steel Gloves
    3576: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["gold"]),        # Gold Gloves
    3577: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["crystal"]),     # Crystal Gloves
    3578: LayerSpec("equipment/arms/hands/gloves/male", tint=_TINT["obsidian"]),    # Obsidian Gloves
}

# ---------------------------------------------------------------------------
# Weapon / tool held in hotbar (weapon layer rendered on top of equipment)
# Walk sheets are 576×256 (9 frames × 4 dirs × 64px) — standard LPC.
# Wands have only a slash sheet; walk/idle fall back to slash frame 0.
# Longsword/mace/rapier/saber attack_slash sheets use 192px cells.
# ---------------------------------------------------------------------------
_WEAPON: dict[int, LayerSpec] = {
    # ---- Swords (longsword sprite, 192px attack_slash) ----
    1000: LayerSpec("equipment/weapon/sword/dagger"),                                     # Scrap Knife
    1050: LayerSpec("equipment/weapon/sword/longsword", behind="universal_behind"),                                   # Wooden Sword
    1101: LayerSpec("equipment/weapon/sword/longsword", behind="universal_behind"),                                   # Iron Sword
    1150: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["copper"], behind="universal_behind"),            # Copper Sword
    1200: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["bronze"], behind="universal_behind"),            # Bronze Sword
    1250: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["steel"],  behind="universal_behind"),            # Steel Sword
    1300: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["gold"],   behind="universal_behind"),            # Gold Sword
    1350: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["crystal"], behind="universal_behind"),           # Crystal Sword
    1400: LayerSpec("equipment/weapon/sword/longsword", tint=_TINT["obsidian"], behind="universal_behind"),          # Obsidian Sword
    # ---- Daggers ----
    1052: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["bone"]),                 # Bone Dagger
    1100: LayerSpec("equipment/weapon/sword/dagger"),                                      # Iron Dagger
    1151: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["copper"]),               # Copper Dagger
    1201: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["bronze"]),               # Bronze Dagger
    1251: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["steel"]),                # Steel Dagger
    1301: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["gold"]),                 # Gold Dagger
    1351: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["crystal"]),              # Crystal Dagger
    1401: LayerSpec("equipment/weapon/sword/dagger", tint=_TINT["obsidian"]),             # Obsidian Dagger
    # ---- Maces / Clubs ----
    1001: LayerSpec("equipment/weapon/blunt/mace", behind="universal_behind"),                                        # Scrap Club
    1051: LayerSpec("equipment/weapon/blunt/mace", behind="universal_behind"),                                        # Wooden Mace
    1053: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["stone"],    behind="universal_behind"),                # Stone Mace
    1102: LayerSpec("equipment/weapon/blunt/mace", behind="universal_behind"),                                        # Iron Mace
    1152: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["copper"],   behind="universal_behind"),                # Copper Mace
    1202: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["bronze"],   behind="universal_behind"),                # Bronze Mace
    1252: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["steel"],    behind="universal_behind"),                # Steel Mace
    1302: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["gold"],     behind="universal_behind"),                # Gold Mace
    1352: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["crystal"],  behind="universal_behind"),                # Crystal Mace
    1402: LayerSpec("equipment/weapon/blunt/mace", tint=_TINT["obsidian"], behind="universal_behind"),                # Obsidian Mace
    # ---- Rapiers (192px attack_slash) ----
    1500: LayerSpec("equipment/weapon/sword/rapier", behind="universal_behind"),                                      # Iron Rapier
    1550: LayerSpec("equipment/weapon/sword/rapier", tint=_TINT["copper"],  behind="universal_behind"),               # Copper Rapier
    1600: LayerSpec("equipment/weapon/sword/rapier", tint=_TINT["bronze"],  behind="universal_behind"),               # Bronze Rapier
    1650: LayerSpec("equipment/weapon/sword/rapier", tint=_TINT["steel"],   behind="universal_behind"),               # Steel Rapier
    1700: LayerSpec("equipment/weapon/sword/rapier", tint=_TINT["gold"],    behind="universal_behind"),               # Gold Rapier
    1750: LayerSpec("equipment/weapon/sword/rapier", tint=_TINT["crystal"], behind="universal_behind"),               # Crystal Rapier
    # ---- Katanas (slash animation, unique sprite) ----
    # weapon/sword/katana has slash/katana.png + walk/katana.png (no 192px overlay)
    # Katana sheets use 128-px cells (8 rows × 2 = 4 LPC directions).  Use row_stride=2 so
    # actual_row = dir_row * 2 + 1 → lower-half rows 1/3/5/7 which have the most content.
    # y_offset=32 shifts the sprite down half a cell to sit at character waist height.
    1850: LayerSpec("equipment/weapon/sword/katana", behind="behind", col_stride=2),                        # Iron Katana
    1851: LayerSpec("equipment/weapon/sword/katana", tint=_TINT["copper"],  behind="behind", col_stride=2), # Copper Katana
    1852: LayerSpec("equipment/weapon/sword/katana", tint=_TINT["bronze"],  behind="behind", col_stride=2), # Bronze Katana
    1853: LayerSpec("equipment/weapon/sword/katana", tint=_TINT["steel"],   behind="behind", col_stride=2), # Steel Katana
    1854: LayerSpec("equipment/weapon/sword/katana", tint=_TINT["gold"],    behind="behind", col_stride=2), # Gold Katana
    1855: LayerSpec("equipment/weapon/sword/katana", tint=_TINT["crystal"], behind="behind", col_stride=2), # Crystal Katana
    # ---- Sabers (192px attack_slash, unique sprite) ----
    1860: LayerSpec("equipment/weapon/sword/saber", behind="universal_behind"),                                       # Iron Saber
    1861: LayerSpec("equipment/weapon/sword/saber", tint=_TINT["copper"],  behind="universal_behind"),                # Copper Saber
    1862: LayerSpec("equipment/weapon/sword/saber", tint=_TINT["bronze"],  behind="universal_behind"),                # Bronze Saber
    1863: LayerSpec("equipment/weapon/sword/saber", tint=_TINT["steel"],   behind="universal_behind"),                # Steel Saber
    1864: LayerSpec("equipment/weapon/sword/saber", tint=_TINT["gold"],    behind="universal_behind"),                # Gold Saber
    1865: LayerSpec("equipment/weapon/sword/saber", tint=_TINT["crystal"], behind="universal_behind"),                # Crystal Saber
    # ---- Scimitars (slash animation, unique curved sprite) ----
    1870: LayerSpec("equipment/weapon/sword/scimitar"),                                    # Iron Scimitar
    1871: LayerSpec("equipment/weapon/sword/scimitar", tint=_TINT["copper"], behind="behind", col_stride=2),             # Copper Scimitar
    1872: LayerSpec("equipment/weapon/sword/scimitar", tint=_TINT["bronze"], behind="behind", col_stride=2),             # Bronze Scimitar
    1873: LayerSpec("equipment/weapon/sword/scimitar", tint=_TINT["steel"], behind="behind", col_stride=2),              # Steel Scimitar
    1874: LayerSpec("equipment/weapon/sword/scimitar", tint=_TINT["gold"], behind="behind", col_stride=2),               # Gold Scimitar
    # ---- Wands (slash sheet only; walk/idle pin to slash frame 0) ----
    1800: LayerSpec("equipment/weapon/magic/wand/male", colour="wand"),                                                  # Wooden Wand
    1801: LayerSpec("equipment/weapon/magic/wand/male", colour="wand", tint=_TINT["crystal"]),                           # Crystal Wand
    1802: LayerSpec("equipment/weapon/magic/wand/male", colour="wand", tint=(255, 150,  50, 255)),                       # Fire Wand
    1803: LayerSpec("equipment/weapon/magic/wand/male", colour="wand", tint=(255, 230,  50, 255)),                       # Storm Wand
    1804: LayerSpec("equipment/weapon/magic/wand/male", colour="wand", tint=(120, 220,  80, 255)),                       # Nature Wand
    1805: LayerSpec("equipment/weapon/magic/wand/male", colour="wand", tint=(130,  70, 200, 255)),                       # Shadow Wand
    # ---- Axes (tool — smash animation) ----
    2000: LayerSpec("equipment/tools/smash/universal/male", colour="axe"),                # Scrap Axe
    2050: LayerSpec("equipment/tools/smash/universal/male", colour="axe"),                # Wooden Axe
    2051: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["stone"]),    # Stone Axe
    2100: LayerSpec("equipment/tools/smash/universal/male", colour="axe"),                # Iron Axe
    2150: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["copper"]),   # Copper Axe
    2200: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["bronze"]),   # Bronze Axe
    2250: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["steel"]),    # Steel Axe
    2300: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["gold"]),     # Gold Axe
    2350: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["crystal"]),  # Crystal Axe
    2400: LayerSpec("equipment/tools/smash/universal/male", colour="axe", tint=_TINT["obsidian"]), # Obsidian Axe
    # ---- Pickaxes (tool — smash animation) ----
    2001: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe"),                         # Scrap Pickaxe
    2052: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe"),                         # Wooden Pickaxe
    2053: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["stone"]),   # Stone Pickaxe
    2101: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe"),                         # Iron Pickaxe
    2151: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["copper"]),  # Copper Pickaxe
    2201: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["bronze"]),  # Bronze Pickaxe
    2251: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["steel"]),   # Steel Pickaxe
    2301: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["gold"]),    # Gold Pickaxe
    2351: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["crystal"]),   # Crystal Pickaxe
    2401: LayerSpec("equipment/tools/smash/universal/male", colour="pickaxe", tint=_TINT["obsidian"]),  # Obsidian Pickaxe
    # ---- Hammers (tool — smash animation) ----
    2500: LayerSpec("equipment/tools/smash/universal/male", colour="hammer"),                          # Iron Hammer
    2550: LayerSpec("equipment/tools/smash/universal/male", colour="hammer", tint=_TINT["copper"]),   # Copper Hammer
    2600: LayerSpec("equipment/tools/smash/universal/male", colour="hammer", tint=_TINT["bronze"]),   # Bronze Hammer
    2650: LayerSpec("equipment/tools/smash/universal/male", colour="hammer", tint=_TINT["steel"]),    # Steel Hammer
    2700: LayerSpec("equipment/tools/smash/universal/male", colour="hammer", tint=_TINT["gold"]),     # Gold Hammer
    2750: LayerSpec("equipment/tools/smash/universal/male", colour="hammer", tint=_TINT["crystal"]),  # Crystal Hammer
}

# ---------------------------------------------------------------------------
# Cape / cloak slot (inventory index 44 = back)
# Rendered BEFORE body so the cloak appears behind the character.
# ---------------------------------------------------------------------------
_CAPE: dict[int, LayerSpec] = {
    3500: LayerSpec("equipment/cape/solid/male", "green",   tint=_TINT["leaf"]),     # Leaf Cloak
    3501: LayerSpec("equipment/cape/solid/male", "brown"),                            # Herb Pouch
    3502: LayerSpec("equipment/cape/solid/male", "gray"),                             # Iron Cape
    3503: LayerSpec("equipment/cape/solid/male", "brown",   tint=_TINT["bronze"]),   # Bronze Cloak
    3504: LayerSpec("equipment/cape/solid/male", "blue",    tint=_TINT["steel"]),    # Steel Cape
    3505: LayerSpec("equipment/cape/solid/male", "yellow",  tint=_TINT["gold"]),     # Gold Cloak
    3506: LayerSpec("equipment/cape/solid/male", "red"),                              # Crimson Cloak
    3507: LayerSpec("equipment/cape/solid/male", "black",   tint=_TINT["obsidian"]), # Shadow Cloak
    3508: LayerSpec("equipment/cape/solid/male", "lavender", tint=_TINT["crystal"]), # Crystal Cloak
}

# ---------------------------------------------------------------------------
# Wing items (back slot, index 44) — premium cosmetic wings
# Each entry maps item_id → (bg_folder, fg_folder, colour) for the LPC wing renderer.
# Wings are rendered as two layers (bg behind body, fg in front).
# ---------------------------------------------------------------------------
_WINGS: dict[int, tuple[str, str, str]] = {
    3520: ("humanoid/body/wings/bat/adult/bg",       "humanoid/body/wings/bat/adult/fg",       "black"),        # Bat Wings
    3521: ("humanoid/body/wings/feathered/adult/bg",  "humanoid/body/wings/feathered/adult/fg", "white"),        # Angel Wings
    3522: ("humanoid/body/wings/feathered/adult/bg",  "humanoid/body/wings/feathered/adult/fg", "black"),        # Dark Angel Wings
    3523: ("humanoid/body/wings/feathered/adult/bg",  "humanoid/body/wings/feathered/adult/fg", "blue"),         # Sky Wings
    3524: ("humanoid/body/wings/monarch/base/bg",     "humanoid/body/wings/monarch/base/fg",    "orange"),       # Monarch Wings
    3525: ("humanoid/body/wings/dragonfly/solid/bg",  "humanoid/body/wings/dragonfly/solid/fg", "blue"),         # Dragonfly Wings
    3526: ("humanoid/body/wings/pixie/solid/bg",      "humanoid/body/wings/pixie/solid/fg",     "bright_green"), # Pixie Wings
}

# ---------------------------------------------------------------------------
# Necklace slot (inventory index 43)
# Rendered as a standard equipment layer (on top of body/torso).
# ---------------------------------------------------------------------------
_NECK: dict[int, LayerSpec] = {
    3650: LayerSpec("equipment/neck/necklace/chain/male", "copper"),                 # Shell Necklace
    3651: LayerSpec("equipment/neck/amulet/star/male",    "silver_blue"),            # Snow Pendant
    3652: LayerSpec("equipment/neck/necklace/chain/male", "gold"),                   # Gold Chain
    3653: LayerSpec("equipment/neck/amulet/cross/male",   "iron_red"),               # Iron Cross
    3654: LayerSpec("equipment/neck/amulet/star/male",    "gold_yellow"),            # Sun Amulet
    3655: LayerSpec("equipment/neck/amulet/cross/male",   "gold_blue"),              # Holy Pendant
    3656: LayerSpec("equipment/neck/necklace/chain/male", "silver"),                 # Silver Chain
    3657: LayerSpec("equipment/neck/amulet/star/male",    "bronze_purple"),          # Shadow Star
}

_HOTBAR_START = 27  # inventory slot index of hotbar slot 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _slot_item_id(inventory: list, index: int) -> int | None:
    """Return the item_id from an inventory slot, or None if empty."""
    slot = inventory[index] if index < len(inventory) else None
    if slot is None:
        return None
    # Slot format: [item_id, qty, ...] or just item_id
    if isinstance(slot, (list, tuple)):
        return slot[0]
    return int(slot)


def get_layers(inventory: list) -> list[LayerSpec]:
    """
    Build the ordered layer stack for a player's current equipment.

    inventory: the full 45-slot inventory list (from config.player_inventory or
               a remote player's equip data).

    Returns a list of LayerSpec in bottom-to-top render order:
      [legs, torso?, arms?, feet?, head?]
    The body is handled separately (always the first blit in player.py).
    """
    layers: list[LayerSpec] = []

    # 1. Legs / pants (always present — slot 40)
    legs_id = _slot_item_id(inventory, 40)
    layers.append(_LEGS.get(legs_id, _LEGS_DEFAULT))

    # 2. Necklace (slot 43) — optional, renders on top of torso
    neck_id = _slot_item_id(inventory, 43)
    if neck_id is not None and neck_id in _NECK:
        layers.append(_NECK[neck_id])

    # 3. Torso / chest armor (slot 37) — optional
    torso_id = _slot_item_id(inventory, 37)
    if torso_id is not None and torso_id in _TORSO:
        layers.append(_TORSO[torso_id])

    # 4. Arms / bracers (slot 42) — optional
    arms_id = _slot_item_id(inventory, 42)
    if arms_id is not None and arms_id in _ARMS:
        layers.append(_ARMS[arms_id])

    # 5. Feet / boots (slot 41) — optional
    feet_id = _slot_item_id(inventory, 41)
    if feet_id is not None and feet_id in _FEET:
        layers.append(_FEET[feet_id])

    # 6. Head / helmet (slot 36) — optional
    head_id = _slot_item_id(inventory, 36)
    if head_id is not None and head_id in _HEAD:
        layers.append(_HEAD[head_id])

    # 7. Shoulders (slot 46) — optional, renders on top of torso/under head
    shoulders_id = _slot_item_id(inventory, 46)
    if shoulders_id is not None and shoulders_id in _SHOULDERS:
        layers.append(_SHOULDERS[shoulders_id])

    # 8. gloves (slot 47) — optional
    hands_id = _slot_item_id(inventory, 47)
    if hands_id is not None and hands_id in _GLOVES:
        layers.append(_GLOVES[hands_id])

    # 9. Shield (slot 45) — optional, renders on top
    shield_id = _slot_item_id(inventory, 45)
    if shield_id is not None and shield_id in _SHIELD:
        layers.append(_SHIELD[shield_id])

    return layers


def get_back_layer(inventory: list) -> LayerSpec | None:
    """
    Return the LayerSpec for the cape/cloak worn in slot 44 (back),
    or None if the slot is empty or holds an unknown item.
    Capes must be rendered BEFORE the body so they appear behind the character.
    """
    cape_id = _slot_item_id(inventory, 44)
    return _CAPE.get(cape_id) if cape_id is not None else None


def get_wing_item(inventory: list) -> tuple[str, str, str] | None:
    """
    Return (bg_folder, fg_folder, colour) for a wing item equipped in slot 44 (back),
    or None if no wing item is equipped there.
    Wings render as two layers (bg + fg) around the body.
    """
    back_id = _slot_item_id(inventory, 44)
    return _WINGS.get(back_id) if back_id is not None else None


def get_layers_from_equip_ids(equip_ids: dict) -> list[LayerSpec]:
    """
    Build layer stack from a compact {slot_index: item_id} dict.
    Used for remote players where only equip slot IDs are transmitted.
    """
    # Build a minimal 47-slot list with only the equip slots filled
    inv: list = [None] * 47
    for slot_idx, item_id in equip_ids.items():
        try:
            inv[int(slot_idx)] = [item_id, 1]
        except (IndexError, ValueError):
            pass
    return get_layers(inv)


def get_back_layer_from_equip_ids(equip_ids: dict) -> LayerSpec | None:
    """Return the back/cape LayerSpec from a compact {slot_index: item_id} dict."""
    item_id = equip_ids.get(44) or equip_ids.get("44")
    return _CAPE.get(item_id) if item_id is not None else None


def get_wing_item_from_equip_ids(equip_ids: dict) -> tuple[str, str, str] | None:
    """Return (bg_folder, fg_folder, colour) from a compact {slot_index: item_id} dict, or None."""
    item_id = equip_ids.get(44) or equip_ids.get("44")
    return _WINGS.get(item_id) if item_id is not None else None


def get_weapon_layer(inventory: list) -> LayerSpec | None:
    """Return LayerSpec for the currently held hotbar item, or None."""
    import config as _cfg
    held_idx = _HOTBAR_START + _cfg.hotbar_slot
    item_id  = _slot_item_id(inventory, held_idx)
    if item_id is None:
        return None
    return _WEAPON.get(item_id)


def get_weapon_attack_anim(inventory: list) -> str:
    """Return the body attack animation for the currently held hotbar item.
    'slash' for weapons and tools (6 frames, syncs with smash overlay),
    'thrust' for unarmed."""
    import config as _cfg
    held_idx = _HOTBAR_START + _cfg.hotbar_slot
    item_id  = _slot_item_id(inventory, held_idx)
    if item_id is None:
        return "thrust"   # unarmed
    return "slash" if item_id in _WEAPON else "thrust"


def get_weapon_layer_from_id(item_id: int | None) -> LayerSpec | None:
    """Return LayerSpec for a weapon/tool by item ID (for remote players)."""
    if item_id is None:
        return None
    return _WEAPON.get(item_id)

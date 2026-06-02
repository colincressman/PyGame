import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pygame
pygame.init()
pygame.display.set_mode((1, 1))

CELL = 64

sheets = [
    (r'client\Universal-LPC-Spritesheet-Character-Generator\spritesheets\weapon\sword\katana\walk\katana.png', 'walk_front'),
    (r'client\Universal-LPC-Spritesheet-Character-Generator\spritesheets\weapon\sword\katana\walk\behind\katana.png', 'walk_behind'),
    (r'client\Universal-LPC-Spritesheet-Character-Generator\spritesheets\weapon\sword\katana\slash\katana.png', 'slash_front'),
    (r'client\Universal-LPC-Spritesheet-Character-Generator\spritesheets\weapon\sword\katana\slash\behind\katana.png', 'slash_behind'),
]

# Extract one composite image per sheet showing each row
for fname, name in sheets:
    surf = pygame.image.load(fname).convert_alpha()
    w, h = surf.get_size()
    n_rows = h // CELL
    n_cols = w // CELL

    # For each row that has content, save 6 frames as a strip
    for r in range(n_rows):
        row_surf = surf.subsurface(pygame.Rect(0, r * CELL, min(6 * CELL, w), CELL))
        # Check if it has any pixels
        has_pixel = any(row_surf.get_at((x, y))[3] > 0
                        for x in range(0, min(6*CELL, w), 8)
                        for y in range(0, CELL, 8))
        if has_pixel:
            print(f"  {name} row {r}: HAS CONTENT (first 6 frames shown)")
            out_path = f"tools/katana_{name}_row{r}.png"
            # Save all columns
            full_row = surf.subsurface(pygame.Rect(0, r * CELL, w, CELL))
            pygame.image.save(full_row, out_path)
            print(f"    Saved: {out_path}")
        else:
            print(f"  {name} row {r}: empty")

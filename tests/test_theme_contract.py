import unittest
from pathlib import Path

from tests.test_support import ROOT


class ThemeContractTests(unittest.TestCase):
    def test_menu_surfaces_import_shared_theme(self):
        modules = [
            "client/rendering/inventory.py",
            "client/rendering/chest.py",
            "client/rendering/crafting.py",
            "client/rendering/combiner.py",
            "client/rendering/embedder.py",
            "client/rendering/repair.py",
            "client/rendering/menu.py",
            "client/rendering/stat_screen.py",
        ]
        for rel_path in modules:
            text = (ROOT / rel_path).read_text(encoding="utf-8")
            self.assertIn("from rendering import ui_theme as _T", text, rel_path)

    def test_primary_menus_reference_shared_panel_tokens(self):
        expectations = {
            "client/rendering/menu.py": ["_T.OVERLAY_ALPHA", "_T.BORDER", "_T.TITLE_BAR", "_T.HINT_TXT"],
            "client/rendering/stat_screen.py": ["_T.OVERLAY_ALPHA", "_T.BORDER", "_T.TITLE_BAR", "_T.HINT_TXT"],
            "client/rendering/crafting.py": ["_T.BG_FILL", "_T.BORDER", "_T.TITLE_BAR"],
            "client/rendering/chest.py": ["_T.BG_FILL", "_T.BORDER", "_T.TITLE_BAR"],
        }
        for rel_path, tokens in expectations.items():
            text = (ROOT / rel_path).read_text(encoding="utf-8")
            for token in tokens:
                self.assertIn(token, text, f"{rel_path} missing {token}")


if __name__ == "__main__":
    unittest.main()

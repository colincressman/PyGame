import unittest
from unittest import mock

from tests.test_support import make_surface, reset_client_config, surface_has_color

import config
from rendering import ui_theme as _T
from rendering import crafting, embedder, menu, repair, stat_screen
from rendering.combiner import draw_combiner_popup


class CombinerSlotValidationTests(unittest.TestCase):
    """Armour slot-2 must accept handle/core; never binding."""

    def _patched_get_item(self, iid, slot_val):
        import rendering.combiner as c
        c._get_item = lambda x: {"part_stats": {"slot": slot_val}} if x == iid else {}

    def test_armor_slot2_accepts_lining(self):
        import rendering.combiner as c
        orig = c._get_item
        c._get_item = lambda x: {"part_stats": {"slot": "lining"}} if x == 297 else {}
        result = c.valid_for_slot(297, 2, mold_id=194)
        c._get_item = orig
        self.assertTrue(result)

    def test_armor_slot2_rejects_handle(self):
        import rendering.combiner as c
        orig = c._get_item
        c._get_item = lambda x: {"part_stats": {"slot": "handle"}}
        result = c.valid_for_slot(264, 2, mold_id=194)
        c._get_item = orig
        self.assertFalse(result)

    def test_armor_slot3_accepts_binding(self):
        import rendering.combiner as c
        orig = c._get_item
        c._get_item = lambda x: {"part_stats": {"slot": "binding"}}
        result = c.valid_for_slot(272, 3, mold_id=194)
        c._get_item = orig
        self.assertTrue(result)

    def test_part_maker_tabs_no_empty_category_tabs(self):
        from rendering.crafting import _PART_MAKER_TABS, _PART_MAKER_RANGES
        tab_keys = [key for _, key in _PART_MAKER_TABS]
        # All tabs must either have a range-based filter or be genuinely populated
        for key in tab_keys:
            self.assertIn(key, _PART_MAKER_RANGES, f"Tab '{key}' has no range filter")

    def test_armor_slot2_label_is_lining(self):
        from rendering.combiner import _slot_labels_for_mold, _ARMOR_MOLD_IDS
        for mold_id in _ARMOR_MOLD_IDS:
            labels = _slot_labels_for_mold(mold_id)
            self.assertEqual(labels[2], "Lining", f"Mold {mold_id} slot2 label wrong")


class MenuRenderingTests(unittest.TestCase):
    def setUp(self):
        reset_client_config()

    def test_pause_menu_renders_shared_theme_colors(self):
        screen = make_surface()

        with mock.patch("pygame.mouse.get_pos", return_value=(0, 0)):
            result = menu.draw_menu(screen, 1280, 720)

        self.assertIsNone(result)
        self.assertTrue(surface_has_color(screen, _T.TITLE_BAR))
        self.assertTrue(surface_has_color(screen, _T.NAV_BG))
        self.assertTrue(surface_has_color(screen, _T.BORDER))

    def test_stat_screen_renders_shared_theme_colors(self):
        screen = make_surface()
        config.player_stat_points = 2

        with mock.patch("pygame.mouse.get_pos", return_value=(0, 0)):
            result = stat_screen.draw_stat_screen(screen, 1280, 720)

        self.assertIsNone(result)
        self.assertTrue(surface_has_color(screen, _T.TITLE_BAR))
        self.assertTrue(surface_has_color(screen, _T.BORDER))
        self.assertTrue(surface_has_color(screen, _T.BTN_BG))


class PopupRenderingTests(unittest.TestCase):
    def setUp(self):
        reset_client_config()

    def test_station_popup_renders_shared_theme_colors(self):
        screen = make_surface()
        config.station_popup_tab = "weapon"
        config.station_popup_recipe = None
        config.station_popup_scroll = 0

        crafting.draw_station_popup(screen, "crafting_table", 1280, 720)

        self.assertTrue(surface_has_color(screen, _T.TITLE_BAR))
        self.assertTrue(surface_has_color(screen, _T.BORDER))

    def test_combiner_popup_renders_without_error(self):
        screen = make_surface()
        config.show_station_popup = "part_combiner"

        with mock.patch("pygame.mouse.get_pos", return_value=(0, 0)):
            draw_combiner_popup(screen, 1280, 720)

        self.assertTrue(surface_has_color(screen, _T.TITLE_BAR))
        self.assertTrue(surface_has_color(screen, _T.BORDER))

    def test_embedder_popup_renders_without_error(self):
        screen = make_surface()

        with mock.patch("pygame.mouse.get_pos", return_value=(0, 0)):
            embedder.draw_embedder_popup(screen, 1280, 720)

        self.assertTrue(surface_has_color(screen, _T.TITLE_BAR))
        self.assertTrue(surface_has_color(screen, _T.BORDER))

    def test_repair_panel_renders_with_button_theme(self):
        screen = make_surface()
        config.repair_selected_slot = None

        repair.draw_repair_panel(screen, 400, 160, 480, 260)

        self.assertTrue(surface_has_color(screen, _T.SLOT_BG))
        self.assertTrue(surface_has_color(screen, _T.BTN_DIS_BG))


if __name__ == "__main__":
    unittest.main()

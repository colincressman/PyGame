import unittest

import pygame

from tests.test_support import make_surface, reset_client_config


class CharCreatorTests(unittest.TestCase):
    def setUp(self):
        self.config = reset_client_config()
        self.config.show_char_creator = False
        pygame.event.clear()

    def tearDown(self):
        pygame.event.clear()

    def test_send_appearance_clears_legacy_creator_cosmetics(self):
        from rendering import char_creator

        self.config.player_appearance.update({
            "body": "female",
            "hair_style": "bob",
            "back_ext": "feathered",
            "back_ext_color": "red",
            "aura": "fire",
        })

        char_creator._send_appearance()

        payload = self.config.state_outbox.get_nowait()
        self.assertEqual(payload["appearance"]["body"], "female")
        self.assertEqual(payload["appearance"]["hair_style"], "bob")
        self.assertIsNone(payload["appearance"]["back_ext"])
        self.assertIsNone(payload["appearance"]["aura"])

    def test_open_close_toggles_visibility(self):
        from rendering import char_creator

        char_creator.open_char_creator()
        char_creator.close_char_creator()

        self.assertFalse(self.config.show_char_creator)

        char_creator.open_char_creator()
        self.assertTrue(self.config.show_char_creator)

    def test_ctrl_c_toggles_char_creator(self):
        from input.controls import handle_events

        state = {
            "running": True,
            "show_map": False,
            "map_needs_redraw": False,
            "screen": make_surface(),
            "WINDOW_WIDTH": 1280,
            "WINDOW_HEIGHT": 720,
        }

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=pygame.KMOD_CTRL))
        handle_events(state)
        self.assertTrue(self.config.show_char_creator)

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=pygame.KMOD_CTRL))
        handle_events(state)
        self.assertFalse(self.config.show_char_creator)

    def test_apply_updates_local_appearance_from_draft(self):
        from rendering import char_creator

        screen = make_surface()
        panel_x = (screen.get_width() - char_creator.PANEL_W) // 2
        panel_y = (screen.get_height() - char_creator.PANEL_H) // 2
        char_creator.open_char_creator()
        char_creator.draw_char_creator(screen)

        hair_rect, hair_style = next((rect, style) for rect, style in char_creator._HAIR_RECTS if style == "braid")
        char_creator.handle_click(hair_rect.centerx + panel_x, hair_rect.centery + panel_y, screen)

        self.assertEqual(char_creator._draft_appearance["hair_style"], hair_style)
        self.assertEqual(self.config.player_appearance["hair_style"], "plain")

        confirm = char_creator._CONFIRM_RECT
        char_creator.handle_click(confirm.centerx + panel_x, confirm.centery + panel_y, screen)

        payload = self.config.state_outbox.get_nowait()
        self.assertEqual(payload["appearance"]["hair_style"], "braid")
        self.assertEqual(self.config.player_appearance["hair_style"], "braid")

    def test_reopen_creator_keeps_buttons_working(self):
        from rendering import char_creator

        screen = make_surface()
        panel_x = (screen.get_width() - char_creator.PANEL_W) // 2
        panel_y = (screen.get_height() - char_creator.PANEL_H) // 2
        char_creator.open_char_creator()
        char_creator.draw_char_creator(screen)

        confirm = char_creator._CONFIRM_RECT
        char_creator.handle_click(confirm.centerx + panel_x, confirm.centery + panel_y, screen)
        self.assertFalse(self.config.show_char_creator)

        char_creator.open_char_creator()
        char_creator.draw_char_creator(screen)

        body_rect, _ = next((rect, body) for rect, body in char_creator._BODY_RECTS if body == "teen")
        char_creator.handle_click(body_rect.centerx + panel_x, body_rect.centery + panel_y, screen)

        self.assertEqual(char_creator._draft_appearance["body"], "teen")


if __name__ == "__main__":
    unittest.main()

import unittest

import pygame

from tests.test_support import reset_client_config


class _FakeKeys:
    def __init__(self, pressed: set[int] | None = None):
        self._pressed = pressed or set()

    def __getitem__(self, key: int) -> int:
        return 1 if key in self._pressed else 0


class DeadMovementTests(unittest.TestCase):
    def setUp(self):
        self.config = reset_client_config()
        self.config.player_dead = True

    def test_dead_players_do_not_move(self):
        from input.controls_movement_v2 import handle_movement

        state = {"player_data": {"pos": [8.0, 9.0]}}
        keys = pygame.key.get_pressed()

        handle_movement(state, keys, 0.25)

        self.assertEqual(state["player_data"]["pos"], [8.0, 9.0])
        self.assertFalse(self.config.is_moving)
        self.assertFalse(self.config.is_running)
        self.assertFalse(self.config.is_stealthy)
        self.assertFalse(self.config.is_blocking)


class PlacedObjectCollisionTests(unittest.TestCase):
    def setUp(self):
        self.config = reset_client_config()

    def test_move_with_collisions_does_not_tunnel_through_wall(self):
        from input.controls_movement_v2 import _move_with_collisions

        self.config.set_placed_objects({
            "wall": {"type": "stone_brick_wall", "pos": [1, 0]},
        })

        px, py, _ = _move_with_collisions(0.2, 0.0, 1.5, 0.0, 0.25)

        self.assertLess(px, 1.0)
        self.assertAlmostEqual(py, 0.0, places=3)

    def test_handle_movement_stops_against_wall_during_long_frame(self):
        from input.controls_movement_v2 import handle_movement

        self.config.set_placed_objects({
            "wall": {"type": "stone_brick_wall", "pos": [1, 0]},
        })
        state = {"player_data": {"pos": [0.2, 0.0]}}
        pressed = _FakeKeys({self.config.keybinds["move_right"]})

        handle_movement(state, pressed, 0.25)

        self.assertLess(state["player_data"]["pos"][0], 1.0)


if __name__ == "__main__":
    unittest.main()

import unittest

from tests.test_support import reset_client_config


class ClientNetworkingRespawnTests(unittest.TestCase):
    def setUp(self):
        reset_client_config()

    def test_authoritative_self_pos_applies_after_respawn(self):
        from client.networking.handlers import _apply_authoritative_self_pos

        player_data = {"pos": [25.0, 40.0], "knockback_vel": [1.0, 0.0]}
        self_data = {"pos": [2.0, 3.0], "dead": False}

        _apply_authoritative_self_pos(self_data, player_data, was_dead=True)

        self.assertEqual(player_data["pos"], [2.0, 3.0])
        self.assertNotIn("knockback_vel", player_data)

    def test_authoritative_self_pos_ignores_small_live_drift(self):
        from client.networking.handlers import _apply_authoritative_self_pos

        player_data = {"pos": [10.5, 10.5]}
        self_data = {"pos": [10.0, 10.0], "dead": False}

        _apply_authoritative_self_pos(self_data, player_data, was_dead=False)

        self.assertEqual(player_data["pos"], [10.5, 10.5])


if __name__ == "__main__":
    unittest.main()

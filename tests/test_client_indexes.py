import unittest

from tests.test_support import reset_client_config

import config
from input.controls_building import handle_world_left_click
from input.placeable_data import PLACEABLE_ITEMS


class ClientLookupIndexTests(unittest.TestCase):
    def setUp(self):
        reset_client_config()

    def test_setters_rebuild_tile_indexes(self):
        config.set_world_nodes({
            "node:a": {"type": "tree", "wx": 10, "wy": 12, "max_hp": 3, "hits": 0},
        })
        config.set_placed_objects({
            "obj:a": {"uid": "obj:a", "type": "chest", "pos": [7, 8], "placed_by": ""},
            "floor:a": {"uid": "floor:a", "type": "stone_brick_floor", "pos": [3, 4], "placed_by": ""},
        })

        self.assertEqual(config.node_by_tile[(10, 12)], {"node:a"})
        self.assertEqual(config.object_by_tile[(7, 8)], "obj:a")
        self.assertEqual(config.floor_by_tile[(3, 4)], "floor:a")
        self.assertIn("obj:a", config.stations_by_chunk[(0, 0)])

    def test_handle_world_left_click_uses_indexes_for_pickup_and_place(self):
        config.pickup_mode = True
        config.mouse_tile = (5, 6)
        config.set_placed_objects({
            "obj:a": {"uid": "obj:a", "type": "chest", "pos": [5, 6], "placed_by": ""},
        })

        handle_world_left_click(lambda _item_id: False, lambda _tool: False, lambda _tool: 1, 27)

        self.assertNotIn("obj:a", config.placed_objects)
        self.assertEqual(config.state_outbox.get_nowait()["type"], "remove_object")

        reset_client_config()
        config.mouse_tile = (9, 10)
        config.placement_blocked = False
        placeable_item_id = next(iter(PLACEABLE_ITEMS))
        config.player_inventory[27] = [placeable_item_id, 1]

        handle_world_left_click(lambda _item_id: False, lambda _tool: False, lambda _tool: 1, 27)

        self.assertIn((9, 10), config.object_by_tile)
        opt_uid = config.object_by_tile[(9, 10)]
        self.assertEqual(config.placed_objects[opt_uid]["pos"], [9, 10])


if __name__ == "__main__":
    unittest.main()

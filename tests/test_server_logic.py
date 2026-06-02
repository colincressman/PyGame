import unittest
from unittest import mock

from tests.test_support import find_item

from server.game_state import world_items
from server.network import tcp_routes, tcp_state_handlers_v2


class GiveItemTests(unittest.TestCase):
    def test_give_item_rejects_unknown_item_id(self):
        player = {"inventory": [None] * 45}

        added = tcp_routes._give_item(player, -999999, 1)

        self.assertFalse(added)
        self.assertEqual(player["inventory"], [None] * 45)

    def test_give_item_stacks_then_spills_to_next_slot(self):
        item_id, item_def = find_item(
            lambda iid, item: iid != 1 and item.get("stackable") and item.get("max_stack", 1) > 1
        )
        max_stack = item_def["max_stack"]
        player = {"inventory": [None] * 45}
        player["inventory"][0] = [item_id, max_stack - 1]

        added = tcp_routes._give_item(player, item_id, 2)

        self.assertTrue(added)
        self.assertEqual(player["inventory"][0], [item_id, max_stack])
        self.assertEqual(player["inventory"][1], [item_id, 1])


class WorldItemPickupTests(unittest.TestCase):
    def setUp(self):
        self.players = {"p1": {"pos": [5.0, 5.0], "inventory": [None] * 45, "coins": 0}}
        world_items.set_world_items_refs({"players": self.players})
        world_items.world_items.clear()

    def tearDown(self):
        world_items.world_items.clear()

    def test_pickup_tick_moves_coins_to_wallet_and_items_to_inventory(self):
        item_id, _item_def = find_item(lambda iid, item: iid != 1 and item.get("stackable"))
        world_items.spawn_world_item(1, [5.0, 5.0], qty=7)
        world_items.spawn_world_item(item_id, [5.1, 5.0], qty=3)

        with mock.patch("server.game_state.game_sync.mark_inventory_dirty") as mark_dirty:
            world_items.pickup_tick()

        self.assertEqual(self.players["p1"]["coins"], 7)
        self.assertIn([item_id, 3], self.players["p1"]["inventory"][:36])
        mark_dirty.assert_called_once_with("p1")
        self.assertEqual(world_items.world_items, {})


class TcpStateDispatchTests(unittest.TestCase):
    def test_dispatch_message_returns_false_for_unknown_type(self):
        handled = tcp_state_handlers_v2.dispatch_message({"type": "missing"}, "p1", {}, mock.Mock(), {})

        self.assertFalse(handled)

    def test_handle_gather_planted_node_awards_loot_and_durability(self):
        players = {"p1": {"pos": [10.0, 10.0], "inventory": [None] * 45, "hotbar_slot": 0}}
        give_item = mock.Mock()

        import server.world.resource_nodes as resource_nodes

        with mock.patch.object(resource_nodes, "get_planted_node", return_value={"type": "tree", "wx": 10, "wy": 10}), \
             mock.patch.object(resource_nodes, "NODE_TYPES", {"tree": {"tool": None}}), \
             mock.patch.object(resource_nodes, "tool_mining_damage", return_value=2), \
             mock.patch.object(resource_nodes, "tool_satisfies", return_value=True), \
             mock.patch.object(resource_nodes, "damage_node", return_value=[(2, 1)]), \
             mock.patch("server.network.tcp_state_handlers_v2.drain_durability") as drain, \
             mock.patch("server.network.tcp_state_handlers_v2.mark_inventory_dirty") as mark_dirty:
            tcp_state_handlers_v2._handle_gather({"type": "gather", "node_id": "planted:test"}, "p1", players, give_item, {})

        give_item.assert_called_once_with(players["p1"], 2, 1)
        drain.assert_called_once_with(players["p1"]["inventory"], 27)
        mark_dirty.assert_called_once_with("p1")


if __name__ == "__main__":
    unittest.main()

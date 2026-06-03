import unittest
from unittest import mock

from tests.test_support import find_item

from server.game_state import world_items
from server.game_state import game_sync
from server.game_state import gem_data
from server.game_state import mold_data
from server.game_state import progression_data
from server.game_state import placed_objects
from server.game_state import repair
from server import item_data
from server.network import combat, tcp_routes, tcp_state_handlers_v2
from server.network import commands
from server import session_auth
from server.world import npc_shops
from server.world import tool_data


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

    def test_dispatch_message_rejects_non_dict_packet(self):
        handled = tcp_state_handlers_v2.dispatch_message(["not", "a", "dict"], "p1", {}, mock.Mock(), {})

        self.assertFalse(handled)

    def test_forget_chunks_filters_malformed_entries(self):
        with mock.patch("server.game_state.sync.forget_player_chunks") as forget:
            tcp_state_handlers_v2._handle_forget_chunks(
                {"type": "forget_chunks", "chunks": [[1, 2], ["bad", 3], [4], [5, 6, 7], (8, 9)]},
                "p1",
                {},
                mock.Mock(),
                {},
            )

        forget.assert_called_once_with("p1", [[1, 2], [8, 9]])

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


class SessionAuthTests(unittest.TestCase):
    def tearDown(self):
        session_auth.clear_tokens()

    def test_issue_verify_and_revoke_token(self):
        token = session_auth.issue_token("p1")

        self.assertTrue(session_auth.verify_token("p1", token))
        self.assertFalse(session_auth.verify_token("p1", "wrong"))

        session_auth.revoke_token("p1")

        self.assertFalse(session_auth.verify_token("p1", token))

    def test_tcp_handshake_requires_valid_token(self):
        token = session_auth.issue_token("p1")

        valid = tcp_routes._valid_handshake(
            {"socket_type": "world", "player_id": "p1", "session_token": token},
            "world",
            ("127.0.0.1", 1234),
        )
        missing = tcp_routes._valid_handshake(
            {"socket_type": "world", "player_id": "p1"},
            "world",
            ("127.0.0.1", 1234),
        )

        self.assertEqual(valid, "p1")
        self.assertIsNone(missing)


class CombatValidationTests(unittest.TestCase):
    def setUp(self):
        combat._last_attack_times.clear()

    def tearDown(self):
        combat._last_attack_times.clear()

    def test_attack_cooldown_rejects_repeated_swing(self):
        players = {
            "p1": {
                "pos": [0.0, 0.0],
                "inventory": [None] * 48,
                "hotbar_slot": 0,
                "attack_power": 10.0,
                "stamina": 100.0,
            },
            "p2": {
                "pos": [0.0, 1.0],
                "inventory": [None] * 48,
                "health": 100.0,
            },
        }

        with mock.patch("server.network.combat.time.monotonic", side_effect=[10.0, 10.1, 10.6]):
            combat.handle_attack("p1", "down", [0.0, 0.0], players)
            after_first = players["p2"]["health"]
            combat.handle_attack("p1", "down", [0.0, 0.0], players)
            after_second = players["p2"]["health"]
            combat.handle_attack("p1", "down", [0.0, 0.0], players)

        self.assertLess(after_first, 100.0)
        self.assertEqual(after_second, after_first)
        self.assertLess(players["p2"]["health"], after_second)

    def test_light_gem_uses_lifesteal_effect(self):
        players = {
            "p1": {
                "pos": [0.0, 0.0],
                "inventory": [None] * 48,
                "hotbar_slot": 0,
                "attack_power": 10.0,
                "health": 50.0,
                "health_max": 100.0,
                "stamina": 100.0,
            },
            "p2": {
                "pos": [0.0, 1.0],
                "inventory": [None] * 48,
                "health": 100.0,
            },
        }
        players["p1"]["inventory"][27] = [1100, 1, {"gem_trait": "Light"}]

        with mock.patch("server.network.combat.time.monotonic", return_value=10.0):
            combat.handle_attack("p1", "down", [0.0, 0.0], players)

        self.assertGreater(players["p1"]["health"], 50.0)
        self.assertLess(players["p2"]["health"], 100.0)


class DeathRespawnTests(unittest.TestCase):
    def test_tick_player_deaths_marks_dead_and_respawns_after_delay(self):
        players = {
            "p1": {
                "pos": [5.0, 5.0],
                "health": 0.0,
                "health_max": 100.0,
                "bed_spawn": [2.0, 3.0],
            }
        }

        with mock.patch("server.game_state.game_sync.time.time", side_effect=[100.0, 100.0 + game_sync._RESPAWN_DELAY + 0.1]):
            game_sync.tick_player_deaths(players)
            self.assertIn("dead_since", players["p1"])
            game_sync.tick_player_deaths(players)

        self.assertEqual(players["p1"]["pos"], [2.0, 3.0])
        self.assertNotIn("dead_since", players["p1"])
        self.assertGreater(players["p1"]["health"], 0.0)

    def test_tick_player_deaths_uses_origin_fallback_without_bed(self):
        players = {
            "p1": {
                "pos": [5.0, 5.0],
                "health": 0.0,
                "health_max": 10.0,
            }
        }

        with mock.patch("server.game_state.game_sync.time.time", side_effect=[200.0, 200.0 + game_sync._RESPAWN_DELAY + 0.1]):
            game_sync.tick_player_deaths(players)
            game_sync.tick_player_deaths(players)

        self.assertEqual(players["p1"]["pos"], [0.0, 0.0])
        self.assertGreaterEqual(players["p1"]["health"], game_sync._RESPAWN_HP_MIN)


class DataRegistryTests(unittest.TestCase):
    def test_shop_catalogue_loads_from_json(self):
        shop = npc_shops.get_shop("merchant")

        self.assertTrue(shop)
        self.assertEqual(shop[0]["id"], 4000)
        self.assertIn("price", shop[0])

    def test_repair_cost_comes_from_json_rules(self):
        self.assertEqual(repair._get_repair_cost([1100, 1, {"dur": 1, "dur_max": 10}]), (100, 2))
        self.assertIsNone(repair._get_repair_cost([999999, 1]))

    def test_mold_catalogue_loads_from_json(self):
        katana = mold_data.get_mold_entry(199)

        self.assertIsNotNone(katana)
        self.assertEqual(katana["base_item_id"], 1850)
        self.assertEqual(katana["output_name"], "Katana")
        self.assertEqual(katana["primary_slot"], "blade")

    def test_tool_registry_loads_from_json(self):
        self.assertIn(2401, tool_data.TOOL_ITEMS["pickaxe_steel"])
        self.assertEqual(tool_data.TOOL_DAMAGE[2401], 18)
        self.assertEqual(tool_data.PICK_TIER_RANK["pickaxe_iron"], 2)

    def test_gem_registry_loads_light_lifesteal_mapping(self):
        self.assertEqual(gem_data.get_gem_entry(55)["trait"], "Light")
        self.assertEqual(gem_data.get_gem_effect("Light"), "lifesteal")

    def test_progression_registry_loads_quality_and_stat_upgrade_data(self):
        self.assertEqual(progression_data.QUALITY_SELL_MULT["Rare"], 4)
        self.assertEqual(progression_data.STAT_UPGRADES["health_max"]["amount"], 20.0)
        self.assertEqual(progression_data.CRAFT_QUALITY_TIERS[0]["name"], "Common")


class ShopBuybackTests(unittest.TestCase):
    def tearDown(self):
        npc_shops._dynamic_inv.clear()

    def test_buyback_preserves_meta_for_rolled_item(self):
        player = {
            "coins": 0,
            "inventory": [None] * 48,
        }
        rolled = [1100, 1, {"quality": "Rare", "stats": {"attack_power": 42}, "dur": 88, "dur_max": 120}]
        player["inventory"][0] = rolled.copy()
        players = {"p1": player}

        ok, _ = npc_shops.handle_shop_sell("p1", 0, "merchant", players)
        self.assertTrue(ok)
        self.assertIsNone(player["inventory"][0])
        self.assertEqual(len(npc_shops._dynamic_inv["merchant"]), 1)
        self.assertIn("slot", npc_shops._dynamic_inv["merchant"][0])

        player["coins"] = npc_shops._dynamic_inv["merchant"][0]["price"]
        ok, _ = npc_shops.handle_shop_buy("p1", "merchant", npc_shops._static_shop_len("merchant"), players, tcp_routes._give_item)
        self.assertTrue(ok)

        restored = next(slot for slot in player["inventory"][:36] if slot is not None)
        self.assertEqual(restored[0], 1100)
        self.assertEqual(restored[2]["quality"], "Rare")
        self.assertEqual(restored[2]["stats"]["attack_power"], 42)
        self.assertEqual(restored[2]["dur"], 88)


class EffectiveHealthTests(unittest.TestCase):
    def test_effective_health_max_includes_equipment_and_hotbar(self):
        player = {
            "health_max": 100.0,
            "hotbar_slot": 0,
            "inventory": [None] * 48,
        }
        player["inventory"][27] = [9001, 1, {"stats": {"health_max": 24.0}}]
        player["inventory"][36] = [9002, 1, {"stats": {"health_max": 750.0}}]

        self.assertEqual(item_data.get_effective_health_max(player), 874.0)

    def test_heal_command_uses_effective_health_max(self):
        players = {
            "p1": {
                "health": 10.0,
                "health_max": 100.0,
                "hotbar_slot": 0,
                "inventory": [None] * 48,
            }
        }
        players["p1"]["inventory"][36] = [9002, 1, {"stats": {"health_max": 774.0}}]

        result = commands.process_command("/heal", "p1", players, mock.Mock())

        self.assertEqual(players["p1"]["health"], 874.0)
        self.assertEqual(result[0]["text"], "You have been healed.")


if __name__ == "__main__":
    unittest.main()

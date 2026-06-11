import unittest
from unittest import mock
import tempfile
import os
import json
from pathlib import Path

from tests.test_support import find_item

from server.game_state import world_items
from server.game_state import game_sync
from server.game_state import gem_data
from server.game_state import mold_data
from server.game_state import placeable_data
from server.game_state import progression_data
from server.game_state import placed_objects
from server.game_state import repair
from server import item_data
from server import data_validation
from server import cleanup
from server.network import combat, tcp_routes, tcp_state_handlers_v2
from server.network import commands
from server import session_auth
from server.world import npc_shops
from server.world import resource_node_data
from server.world import tool_data
from server.world import world_types
from server import player_save


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

    def test_world_items_persist_and_reload(self):
        item_id, _item_def = find_item(lambda iid, item: iid != 1 and item.get("stackable"))
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = os.path.join(tmpdir, "world_items.json")
            with mock.patch.object(world_items, "_PERSIST_PATH", persist_path), \
                 mock.patch.object(world_items, "save_persistence_async"):
                world_items.world_items.clear()
                world_items._item_cells.clear()
                world_items.spawn_world_item(item_id, [12.5, 7.25], qty=4)
                world_items.save_persistence_sync()
                world_items.world_items.clear()
                world_items._item_cells.clear()

                world_items.load_persistence()

        self.assertEqual(len(world_items.world_items), 1)
        restored = next(iter(world_items.world_items.values()))
        self.assertEqual(restored["item_id"], item_id)
        self.assertEqual(restored["qty"], 4)
        self.assertEqual(restored["pos"], [12.5, 7.25])
        self.assertIn("spawned_at", restored)

    def test_prune_expired_items_unloads_old_drops(self):
        item_id, _item_def = find_item(lambda iid, item: iid != 1 and item.get("stackable"))
        with mock.patch.object(world_items, "save_persistence_async") as save_persistence:
            uid = world_items.spawn_world_item(item_id, [3.0, 4.0], qty=2)
            world_items.world_items[uid]["spawned_at"] = 10.0

            expired = world_items.prune_expired_items(now=40.0, lifetime=20.0)

        self.assertEqual(expired, [uid])
        self.assertNotIn(uid, world_items.world_items)
        self.assertFalse(any(uid in cell for cell in world_items._item_cells.values()))
        self.assertGreaterEqual(save_persistence.call_count, 2)


class CleanupTests(unittest.TestCase):
    def test_cleanup_stale_players_removes_only_expired_entries(self):
        cleanup.players = {
            "fresh": {"last_seen": 95.0},
            "stale": {"last_seen": 10.0},
        }

        with mock.patch("server.cleanup.cleanup_player") as cleanup_player:
            stale_ids = cleanup.cleanup_stale_players(now=100.0, timeout=15.0)

        self.assertEqual(stale_ids, ["stale"])
        cleanup_player.assert_called_once_with("stale")


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

    def test_update_appearance_completes_first_join_setup(self):
        players = {
            "p1": {
                "inventory": [None] * 48,
                "first_join_complete": False,
            }
        }

        with mock.patch("server.network.tcp_state_handlers_v2.save_player") as save_player_mock, \
             mock.patch("server.network.tcp_state_handlers_v2.mark_inventory_dirty") as mark_dirty:
            tcp_state_handlers_v2._handle_update_appearance(
                {"type": "update_appearance", "appearance": {"body": "female", "aura": "ice"}},
                "p1",
                players,
                mock.Mock(),
                {},
            )

        self.assertTrue(players["p1"]["first_join_complete"])
        self.assertEqual(players["p1"]["appearance"]["body"], "female")
        save_player_mock.assert_called_once()
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

    def test_player_hit_drains_shield_shoulders_and_gloves(self):
        armor_id, armor_def = find_item(
            lambda iid, item: item.get("slot_type") == "shield" and item.get("durability")
        )
        shoulder_id, shoulder_def = find_item(
            lambda iid, item: item.get("slot_type") == "shoulders" and item.get("durability")
        )
        glove_id, glove_def = find_item(
            lambda iid, item: item.get("slot_type") == "hands" and item.get("durability")
        )
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
        players["p2"]["inventory"][45] = [armor_id, 1, {"dur": armor_def["durability"], "dur_max": armor_def["durability"]}]
        players["p2"]["inventory"][46] = [shoulder_id, 1, {"dur": shoulder_def["durability"], "dur_max": shoulder_def["durability"]}]
        players["p2"]["inventory"][47] = [glove_id, 1, {"dur": glove_def["durability"], "dur_max": glove_def["durability"]}]

        with mock.patch("server.network.combat.time.monotonic", return_value=10.0), \
             mock.patch("server.game_state.game_sync.mark_inventory_dirty") as mark_dirty:
            combat.handle_attack("p1", "down", [0.0, 0.0], players)

        self.assertEqual(players["p2"]["inventory"][45][2]["dur"], armor_def["durability"] - 1)
        self.assertEqual(players["p2"]["inventory"][46][2]["dur"], shoulder_def["durability"] - 1)
        self.assertEqual(players["p2"]["inventory"][47][2]["dur"], glove_def["durability"] - 1)
        mark_dirty.assert_any_call("p2")


class SpellDurabilityTests(unittest.TestCase):
    def test_fire_spell_drains_active_wand_durability(self):
        wand_id, wand_def = find_item(
            lambda iid, item: item.get("projectile") and item.get("durability")
        )
        players = {
            "p1": {
                "pos": [0.0, 0.0],
                "inventory": [None] * 48,
                "hotbar_slot": 0,
                "attack_power": 10.0,
            }
        }
        players["p1"]["inventory"][27] = [wand_id, 1, {"dur": wand_def["durability"], "dur_max": wand_def["durability"]}]

        with mock.patch("server.network.tcp_state_handlers_v2.mark_inventory_dirty") as mark_dirty:
            tcp_state_handlers_v2._handle_fire_spell(
                {"type": "fire_spell", "dx": 1.0, "dy": 0.0},
                "p1",
                players,
                mock.Mock(),
                {},
            )

        self.assertEqual(players["p1"]["inventory"][27][2]["dur"], wand_def["durability"] - 1)
        mark_dirty.assert_called_once_with("p1")


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
        game_sync._player_positions = {"p1": {"pos": [5.0, 5.0], "vel": [1.0, 0.0], "timestamp": 90.0, "seq": 4}}
        teleports = []
        game_sync._send_to_player = lambda pid, packet: teleports.append((pid, packet))

        with mock.patch("server.game_state.game_sync.time.time", side_effect=[100.0, 100.0 + game_sync._RESPAWN_DELAY + 0.1]):
            game_sync.tick_player_deaths(players)
            self.assertIn("dead_since", players["p1"])
            with mock.patch("server.game_state.sync.invalidate_player") as invalidate_player, \
                 mock.patch("server.game_state.game_sync.invalidate_player_cache") as invalidate_player_cache:
                game_sync.tick_player_deaths(players)
                invalidate_player.assert_called_once_with("p1")
                invalidate_player_cache.assert_called_once_with("p1")

        self.assertEqual(players["p1"]["pos"], [2.0, 3.0])
        self.assertEqual(game_sync._player_positions["p1"]["pos"], [2.0, 3.0])
        self.assertEqual(game_sync._player_positions["p1"]["vel"], [0.0, 0.0])
        self.assertNotIn("dead_since", players["p1"])
        self.assertGreater(players["p1"]["health"], 0.0)
        self.assertEqual(teleports, [("p1", {"type": "teleport", "pos": [2.0, 3.0]})])

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

    def test_tick_player_deaths_uses_home_when_bed_missing(self):
        players = {
            "p1": {
                "pos": [5.0, 5.0],
                "health": 0.0,
                "health_max": 10.0,
                "home_pos": [9.0, 11.0],
            }
        }

        with mock.patch("server.game_state.game_sync.time.time", side_effect=[300.0, 300.0 + game_sync._RESPAWN_DELAY + 0.1]):
            game_sync.tick_player_deaths(players)
            game_sync.tick_player_deaths(players)

        self.assertEqual(players["p1"]["pos"], [9.0, 11.0])

    def test_send_game_state_includes_authoritative_self_position(self):
        game_sync._players = {
            "p1": {
                "pos": [7.0, 13.0],
                "health": 50.0,
                "health_max": 100.0,
                "inventory": [None] * 48,
                "hotbar_slot": 0,
                "level": 1,
                "exp": 0,
                "exp_next": 100,
                "stat_points": 0,
                "coins": 0,
            }
        }
        game_sync._player_positions = {
            "p1": {"pos": [7.0, 13.0], "vel": [0.0, 0.0], "timestamp": 10.0, "seq": 1}
        }
        game_sync._state_send_cache.clear()
        game_sync._inventory_sent.clear()
        game_sync._inventory_dirty.clear()
        game_sync._node_snapshot_sent.clear()
        game_sync._planted_snapshot_sent.clear()

        sent_payloads = []

        with mock.patch("server.game_state.game_sync.send_json", side_effect=lambda _sock, payload: sent_payloads.append(payload)), \
             mock.patch("server.game_state.game_sync._get_nearby_placed", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_npcs_near", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_dungeons_near", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_built_dungeons", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_built_towns", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_claim_overlays", return_value=[]), \
             mock.patch("server.game_state.game_sync.get_nearby_items", return_value=[]), \
             mock.patch("server.game_state.game_sync.get_nearby_mobs", return_value={}), \
             mock.patch("server.game_state.game_sync._get_node_updates", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_depleted_snapshot", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_planted_snapshot", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_planted_updates", return_value=[]), \
             mock.patch("server.game_state.game_sync._ensure_towns_near"), \
             mock.patch("server.game_state.game_sync._ensure_dungeons_near"), \
             mock.patch("server.game_state.game_sync._check_boss_trigger", return_value=[]), \
             mock.patch("server.game_state.game_sync._get_weather", return_value="clear", create=True), \
             mock.patch("server.network.projectiles.get_snapshot", return_value=[]), \
             mock.patch("server.game_state.game_sync.time.time", return_value=123.0):
            game_sync.send_game_state("p1", mock.Mock())

        self.assertEqual(sent_payloads[0]["self"]["pos"], [7.0, 13.0])

    def test_tick_player_deaths_drops_partial_stackable_backpack_items(self):
        players = {
            "p1": {
                "pos": [5.0, 6.0],
                "health": 0.0,
                "health_max": 100.0,
                "inventory": [[1, 10], [1000, 1], [2, 1]] + [None] * 45,
            }
        }
        game_sync._player_positions = {}

        dropped = []
        with mock.patch("server.game_state.game_sync.spawn_world_item", side_effect=lambda item_id, pos, qty=1: dropped.append((item_id, pos, qty))), \
             mock.patch("server.game_state.game_sync.random.random", side_effect=[0.0, 0.99]), \
             mock.patch("server.game_state.game_sync.random.uniform", side_effect=[0.1, -0.1]), \
             mock.patch("server.game_state.game_sync.mark_inventory_dirty") as mark_dirty, \
             mock.patch("server.game_state.game_sync.time.time", return_value=100.0):
            game_sync.tick_player_deaths(players)

        self.assertIn("dead_since", players["p1"])
        self.assertEqual(players["p1"]["inventory"][0], [1, 5])
        self.assertEqual(players["p1"]["inventory"][1], [1000, 1])
        self.assertEqual(dropped, [(1, [5.1, 5.9], 5)])
        mark_dirty.assert_called_once_with("p1")

    def test_tick_player_deaths_keeps_hotbar_items(self):
        inventory = [None] * 48
        inventory[27] = [1, 20]
        players = {
            "p1": {
                "pos": [5.0, 6.0],
                "health": 0.0,
                "health_max": 100.0,
                "inventory": inventory,
            }
        }
        game_sync._player_positions = {}

        with mock.patch("server.game_state.game_sync.spawn_world_item") as spawn_drop, \
             mock.patch("server.game_state.game_sync.time.time", return_value=100.0):
            game_sync.tick_player_deaths(players)

        self.assertEqual(players["p1"]["inventory"][27], [1, 20])
        spawn_drop.assert_not_called()


class CommandTeleportTests(unittest.TestCase):
    def setUp(self):
        commands._pending_tp.clear()
        commands.set_server_refs({})

    def tearDown(self):
        commands._pending_tp.clear()
        commands.set_server_refs({})

    def test_tp_updates_player_and_position_cache_and_sends_teleport_packet(self):
        sent_packets = []
        player_positions = {"admin": {"pos": [0.0, 0.0], "vel": [0, 0], "timestamp": 0.0, "seq": 0}}
        commands.set_server_refs({
            "send_to_player": lambda pid, packet: sent_packets.append((pid, packet)),
            "player_positions": player_positions,
        })
        players = {
            "admin": {"pos": [0.0, 0.0], "seq": 0},
            "target": {"pos": [12.0, 18.0]},
        }

        with mock.patch("server.network.commands.is_op", return_value=True):
            replies = commands.process_command("/tp target", "admin", players, mock.Mock())

        self.assertEqual(players["admin"]["pos"], [12.0, 18.0])
        self.assertEqual(player_positions["admin"]["pos"], [12.0, 18.0])
        self.assertEqual(sent_packets[0], ("admin", {"type": "teleport", "pos": [12.0, 18.0]}))
        self.assertEqual(replies[0]["text"], "Teleported to target.")

    def test_tprequest_accept_teleports_requester(self):
        sent_packets = []
        player_positions = {"alice": {"pos": [1.0, 1.0], "vel": [0, 0], "timestamp": 0.0, "seq": 0}}
        commands.set_server_refs({
            "send_to_player": lambda pid, packet: sent_packets.append((pid, packet)),
            "player_positions": player_positions,
        })
        players = {
            "alice": {"pos": [1.0, 1.0], "seq": 0},
            "bob": {"pos": [20.0, 30.0], "seq": 0},
        }

        commands.process_command("/tprequest bob", "alice", players, mock.Mock())
        replies = commands.process_command("/tpaccept", "bob", players, mock.Mock())

        self.assertEqual(players["alice"]["pos"], [20.0, 30.0])
        self.assertEqual(player_positions["alice"]["pos"], [20.0, 30.0])
        self.assertIn(("alice", {"type": "teleport", "pos": [20.0, 30.0]}), sent_packets)
        self.assertEqual(replies[0]["text"], "Teleported alice to you.")

    def test_sethome_persists_and_home_teleports(self):
        sent_packets = []
        player_positions = {"p1": {"pos": [4.0, 9.0], "vel": [0, 0], "timestamp": 0.0, "seq": 0}}
        commands.set_server_refs({
            "send_to_player": lambda pid, packet: sent_packets.append((pid, packet)),
            "player_positions": player_positions,
        })
        players = {"p1": {"pos": [4.0, 9.0], "seq": 0}}

        with mock.patch("server.network.commands.save_player") as save_player_mock:
            sethome_replies = commands.process_command("/sethome", "p1", players, mock.Mock())

        players["p1"]["pos"] = [50.0, 60.0]
        home_replies = commands.process_command("/home", "p1", players, mock.Mock())

        self.assertEqual(players["p1"]["home_pos"], [4.0, 9.0])
        save_player_mock.assert_called_once()
        self.assertEqual(players["p1"]["pos"], [4.0, 9.0])
        self.assertIn(("p1", {"type": "teleport", "pos": [4.0, 9.0]}), sent_packets)
        self.assertEqual(sethome_replies[0]["text"], "Home set to (4.0, 9.0).")
        self.assertEqual(home_replies[0]["text"], "Teleported home.")


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

    def test_resource_node_registry_loads_biomes_and_seed_drop_data(self):
        self.assertEqual(resource_node_data.NODE_TYPES["obsidian"]["hp"], 50)
        self.assertIn(world_types.BIOME_ID_MAP["mountain"], resource_node_data.NODE_TYPES["obsidian"]["biomes"])
        self.assertEqual(resource_node_data.NODE_TYPES["tree"]["seed_drop"], (34, 0.2))

    def test_placeable_registry_loads_growth_and_solids(self):
        self.assertEqual(placeable_data.PLACEABLE_ITEMS[254], "stone_brick_floor")
        self.assertIn("stone_brick_floor", placeable_data.FLOOR_TYPES)
        self.assertEqual(placeable_data.GROWS_INTO["obsidian_seed"], "obsidian")

    def test_world_type_registry_loads_biome_and_cliff_ids(self):
        self.assertEqual(world_types.BIOME_ID_MAP["river"], 3)
        self.assertEqual(world_types.ID_TO_CLIFF[108], "cliff_tall_south")
        self.assertEqual(world_types.WATER_BIOMES, frozenset({0, 3}))

    def test_data_validation_passes_for_live_registry_files(self):
        self.assertEqual(data_validation.validate_game_data(), [])

    def test_data_validation_reports_broken_cross_file_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "server").mkdir()
            (root / "data").mkdir()
            (root / "data" / "shops").mkdir()
            (root / "data" / "mobs").mkdir()

            (root / "server" / "items.json").write_text(
                json.dumps({"1": {"name": "Stick", "stackable": True, "max_stack": 99}}),
                encoding="utf-8",
            )
            (root / "server" / "recipes.json").write_text(
                json.dumps(
                    {
                        "10": {
                            "name": "Bad Recipe",
                            "ingredients": [[999, 1]],
                            "result": [1, 1],
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "world_types.json").write_text(
                json.dumps({"biomes": {"forest": 5}, "cliffs": {}, "water_biomes": []}),
                encoding="utf-8",
            )
            (root / "data" / "tools.json").write_text(
                json.dumps(
                    {
                        "tool_items": {"axe": [1]},
                        "tool_damage": {"1": 2},
                        "pick_tier_rank": {"pickaxe": 0},
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "placeables.json").write_text(
                json.dumps(
                    {
                        "placeables": [
                            {
                                "item_id": 1,
                                "type": "bad_sapling",
                                "grow_time": 60,
                                "grows_into": "missing_node",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "resource_nodes.json").write_text(
                json.dumps(
                    {
                        "tree": {
                            "yields": [{"item_id": 1234, "min": 1, "max": 1}],
                            "spawn_biomes": ["unknown_biome"],
                            "tool": "missing_tool",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "repair.json").write_text(
                json.dumps(
                    {
                        "range_rules": [{"min_id": 1, "max_id": 10, "material_id": 4321, "qty": 1}],
                        "part_rules": {"999": {"material_id": 1, "qty": 1}},
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "shops" / "merchant.json").write_text(
                json.dumps([{"id": 777, "qty": 1}]),
                encoding="utf-8",
            )
            (root / "data" / "mobs" / "slime.json").write_text(
                json.dumps(
                    {
                        "drop_id": 888,
                        "spawn_biomes": ["unknown_biome"],
                        "sprite": {"type": "walk_strip"},
                    }
                ),
                encoding="utf-8",
            )

            errors = data_validation.validate_game_data(root)

        self.assertTrue(any("recipe 10 ingredient item 999" in error for error in errors))
        self.assertTrue(any("shop merchant entry 0 item 777" in error for error in errors))
        self.assertTrue(any("grows_into missing_node" in error for error in errors))
        self.assertTrue(any("yield item 1234" in error for error in errors))
        self.assertTrue(any("spawn biome unknown_biome" in error for error in errors))
        self.assertTrue(any("tool missing_tool" in error for error in errors))
        self.assertTrue(any("repair range rule 0 material 4321" in error for error in errors))
        self.assertTrue(any("mob slime drop item 888" in error for error in errors))
        self.assertTrue(any("mob slime sprite missing path" in error for error in errors))


class PersistenceConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.orig_objects = dict(placed_objects.placed_objects)
        self.orig_tile_index = dict(placed_objects._tile_index)
        self.orig_floor_index = dict(placed_objects._floor_index)
        self.orig_dirty = placed_objects._dirty

    def tearDown(self):
        placed_objects.placed_objects.clear()
        placed_objects.placed_objects.update(self.orig_objects)
        placed_objects._tile_index.clear()
        placed_objects._tile_index.update(self.orig_tile_index)
        placed_objects._floor_index.clear()
        placed_objects._floor_index.update(self.orig_floor_index)
        placed_objects._dirty = self.orig_dirty

    def test_load_player_treats_legacy_save_as_first_join_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.object(player_save, "SAVE_DIR", tmpdir):
            save_path = Path(tmpdir) / "legacy.json"
            save_path.write_text(
                json.dumps(
                    {
                        "pos": [4, 9],
                        "inventory": [[10, 3]],
                    }
                ),
                encoding="utf-8",
            )

            loaded = player_save.load_player("legacy")

        self.assertIsNotNone(loaded)
        self.assertTrue(loaded["first_join_complete"])
        self.assertEqual(loaded["inventory"][0], [10, 3])
        self.assertEqual(len(loaded["inventory"]), 48)

    def test_use_bed_persists_bed_spawn_immediately(self):
        placed_objects.placed_objects.clear()
        placed_objects._tile_index.clear()
        placed_objects._floor_index.clear()
        placed_objects.placed_objects["bed-1"] = {
            "type": "bed",
            "pos": [12, 18],
            "placed_by": "p1",
        }
        placed_objects._tile_index[(12, 18)] = "bed-1"
        players = {
            "p1": {
                "health_max": 100.0,
                "inventory": [None] * 48,
                "pos": [12.0, 18.0],
            }
        }

        with mock.patch("server.game_state.placed_objects._can_build_at", return_value=True), \
             mock.patch("server.player_save.save_player") as save_player_mock:
            ok = placed_objects.use_bed("bed-1", "p1", players)

        self.assertTrue(ok)
        self.assertEqual(players["p1"]["bed_spawn"], [12, 18])
        save_player_mock.assert_called_once()

    def test_flush_now_persists_placed_objects_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.object(placed_objects, "_SAVE_PATH", os.path.join(tmpdir, "placed_objects.json")):
            placed_objects.placed_objects.clear()
            placed_objects._tile_index.clear()
            placed_objects._floor_index.clear()
            placed_objects.placed_objects["obj-1"] = {"type": "campfire", "pos": [3, 4], "placed_by": "p1"}
            placed_objects._tile_index[(3, 4)] = "obj-1"
            placed_objects._dirty = True

            placed_objects.flush_now()

            saved = json.loads(Path(placed_objects._SAVE_PATH).read_text(encoding="utf-8"))

        self.assertIn("obj-1", saved)
        self.assertFalse(placed_objects._dirty)


class PlacedObjectIndexTests(unittest.TestCase):
    def setUp(self):
        self.orig_objects = dict(placed_objects.placed_objects)
        self.orig_tile_index = dict(placed_objects._tile_index)
        self.orig_floor_index = dict(placed_objects._floor_index)
        placed_objects.placed_objects.clear()
        placed_objects._tile_index.clear()
        placed_objects._floor_index.clear()

    def tearDown(self):
        placed_objects.placed_objects.clear()
        placed_objects.placed_objects.update(self.orig_objects)
        placed_objects._tile_index.clear()
        placed_objects._tile_index.update(self.orig_tile_index)
        placed_objects._floor_index.clear()
        placed_objects._floor_index.update(self.orig_floor_index)

    def test_place_floor_tracks_floor_index_not_solid_tile_index(self):
        inventory = [None] * 45
        inventory[0] = [254, 1]

        ok, uid = placed_objects.place_object("p1", "stone_brick_floor", [12, 18], inventory)

        self.assertTrue(ok)
        self.assertEqual(placed_objects._floor_index[(12, 18)], uid)
        self.assertNotIn((12, 18), placed_objects._tile_index)


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

        with mock.patch("server.network.commands.is_op", return_value=True):
            result = commands.process_command("/heal", "p1", players, mock.Mock())

        self.assertEqual(players["p1"]["health"], 874.0)
        self.assertEqual(result[0]["text"], "You have been healed.")


class PlantedOreRegrowthTests(unittest.TestCase):
    def tearDown(self):
        resource_node_data = __import__("server.world.resource_node_data", fromlist=["NODE_TYPES"])
        resource_nodes = __import__("server.world.resource_nodes", fromlist=["_planted_nodes", "_node_hp", "_node_respawn"])
        placed_objects.placed_objects.clear()
        placed_objects._tile_index.clear()
        placed_objects._floor_index.clear()
        resource_nodes._planted_nodes.clear()
        resource_nodes._node_hp.clear()
        resource_nodes._node_respawn.clear()

    def test_harvested_planted_iron_ore_replants_seed_object(self):
        from server.world import resource_nodes

        resource_nodes._planted_nodes["planted:test"] = {
            "type": "iron_ore",
            "wx": 12,
            "wy": 18,
        }
        node_def = resource_node_data.NODE_TYPES["iron_ore"]

        with mock.patch("server.world.resource_nodes._save_persistence_async"), \
             mock.patch("server.world.resource_nodes.time.time", return_value=100.0):
            loot = resource_nodes.damage_node("planted:test", node_def, damage=node_def["hp"], node_type="iron_ore")

        self.assertIsNotNone(loot)
        self.assertNotIn("planted:test", resource_nodes._planted_nodes)
        seed_entry = next(
            obj for obj in placed_objects.placed_objects.values()
            if obj["type"] == "iron_seed" and obj["pos"] == [12, 18]
        )
        self.assertEqual(seed_entry["grow_time"], placed_objects.GROW_TIMES["iron_seed"])
        self.assertEqual(seed_entry["planted_at"], 100.0)


if __name__ == "__main__":
    unittest.main()

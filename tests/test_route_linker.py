"""Generic recorded-route linking and CT retake handoff."""
import json
import unittest
from pathlib import Path

import agent
from mirage_user_ct_routes import RETAKES
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads(
    (ROOT / "walklab/src/map-fixtures/mirage_static.json").read_text())["map"]
FRAMES = RETAKES["B_to_A"][0]["frames"]
ROUTE_NAME = "B_to_A_1"


class RouteLinkerTests(unittest.TestCase):
    def setUp(self):
        self.player = agent.Player()
        self.player.load_map(MAP)

    def obs(self, pos, tick=1000):
        o = observation(pos[0], pos[1], 0.0, z=pos[2], match_map=MAP,
                        tick=tick)
        o.update(side="defend", match_tick=tick,
                 static_schema_hash=MAP["geometry_hash"])
        return o

    def test_link_to_route_uses_astar_until_entry(self):
        start = [150.0, 100.0, 16.0]
        o = self.obs(start)
        action = self.player.link_to_route(
            o, start, {}, FRAMES, 0, agent.RETAKE_JOIN_DISTANCE,
            via_key=("test_link", 1))
        self.assertIsNotNone(action)
        self.assertEqual(self.player.goal, list(FRAMES[0][:3]))
        self.assertTrue(self.player.path)
        self.assertGreater(agent.distance(start, FRAMES[0]), 6.0)

    def test_link_to_route_returns_none_inside_entry_radius(self):
        entry = FRAMES[0]
        o = self.obs(entry)
        action = self.player.link_to_route(
            o, list(entry[:3]), {}, FRAMES, 0,
            agent.RETAKE_JOIN_DISTANCE)
        self.assertIsNone(action)

    def test_choose_retake_retries_until_entry_is_reachable(self):
        target = MAP["sites"][0]  # A
        o = {"side": "defend", "static_schema_hash": MAP["geometry_hash"],
             "match_tick": 1000, "seat": 0, "round_index": 0}
        far = [40.0, 120.0, 16.0]
        self.player.choose_retake(o, far, target)
        self.assertIsNone(self.player.retake_route)
        self.assertFalse(self.player.retake_checked)
        o["match_tick"] += 60
        self.player.choose_retake(o, list(FRAMES[0][:3]), target)
        self.assertEqual(self.player.retake_route, FRAMES)
        self.assertTrue(self.player.retake_checked)

    def test_choose_retake_allows_mid_route_entry(self):
        target = MAP["sites"][0]  # A
        mid = len(FRAMES) // 2
        pos = list(FRAMES[mid][:3])
        o = {"side": "defend", "static_schema_hash": MAP["geometry_hash"],
             "match_tick": 1000, "seat": 0, "round_index": 0}
        self.player.choose_retake(o, pos, target)
        self.assertEqual(self.player.retake_route, FRAMES)
        self.assertTrue(self.player.choose_route_entry(o, pos, FRAMES))
        entry = self.player.retake_entry_frame
        self.assertIsNotNone(entry)
        self.assertLess(agent.distance(pos, FRAMES[entry][:3]), 1.0)

    def test_choose_retake_decision_window_expires_out_of_range(self):
        target = MAP["sites"][0]
        o = {"side": "defend", "static_schema_hash": MAP["geometry_hash"],
             "match_tick": 1000, "seat": 0, "round_index": 0}
        far = [40.0, 120.0, 16.0]
        self.player.choose_retake(o, far, target)
        o["match_tick"] += agent.RETAKE_DECISION_TICKS
        self.player.choose_retake(o, far, target)
        self.assertIsNone(self.player.retake_route)
        self.assertTrue(self.player.retake_checked)

    def test_choose_retake_does_not_cross_when_already_on_site(self):
        target = MAP["sites"][0]
        o = {"side": "defend", "static_schema_hash": MAP["geometry_hash"],
             "match_tick": 1000, "seat": 0, "round_index": 0}
        self.player.choose_retake(o, list(target["center"]), target)
        self.assertIsNone(self.player.retake_route)
        self.assertTrue(self.player.retake_checked)

    def test_follow_retake_enters_at_the_nearest_mid_route_frame(self):
        mid = len(FRAMES) // 2
        pos = list(FRAMES[mid][:3])
        self.player.retake_route = FRAMES
        self.player.retake_route_name = ROUTE_NAME
        o = self.obs(pos)
        action = self.player.follow_retake(o, pos, {}, [45.0, 88.0, 15.5])
        self.assertIsNotNone(action)
        entry = self.player.retake_entry_frame
        self.assertIsNotNone(entry)
        self.assertLess(agent.distance(pos, FRAMES[entry][:3]), 1.0)
        self.assertTrue(self.player.retake_entry_logged)
        self.assertGreaterEqual(self.player.retake_cursor, entry)

    def test_b_hold_pairs_join_the_retake_lane_after_a_plant(self):
        from mirage_user_ct_routes import PAIRS

        target = MAP["sites"][0]  # A
        entries = []
        for pair in (p for p in PAIRS if p["site"] == "B"):
            with self.subTest(pair=pair["name"]):
                player = agent.Player()
                player.load_map(MAP)
                player.ct_recorded_pair = pair
                pos = list(pair["hold"][-1][:3])
                o = self.obs(pos)
                o["bomb"] = {"state": "planted", "site": "A",
                             "position": target["center"]}
                player.choose_retake(o, pos, target)
                self.assertIsNotNone(player.retake_route)
                action = player.follow_retake(o, pos, {}, target["center"])
                self.assertIsNotNone(action)
                self.assertIsNotNone(player.retake_entry_frame)
                entries.append(player.retake_entry_frame)
                self.assertTrue(player.retake_entry_logged
                                or player.goal is not None)
        # Mid-route entry is allowed: at least one B hold is closer to a
        # later frame than to the recorded B-site start.
        self.assertTrue(any(entry > 0 for entry in entries))

    def test_turning_toward_the_entry_is_not_treated_as_blocked(self):
        index = 100
        pos = list(FRAMES[index][:3])
        self.player.retake_route = FRAMES
        self.player.retake_route_name = ROUTE_NAME
        self.player.retake_entry_frame = index
        self.player.retake_entry_candidates = [(1.0, index), (2.0, 130)]
        self.player.retake_anchor_pos = list(pos[:2])
        self.player.retake_anchor_tick = 1000 - agent.REPLAY_BLOCK_TICKS
        # The A* link target is behind the agent, so the link is turning.
        self.player.goal = [pos[0] - 10.0, pos[1], pos[2]]
        o = self.obs(pos, tick=1000)
        self.player.follow_retake(o, pos, {}, [45.0, 88.0, 15.5])
        self.assertEqual(self.player.retake_entry_frame, index)
        self.assertFalse(self.player.retake_done)

    def test_follow_retake_end_links_to_bomb_with_astar(self):
        self.player.retake_route = FRAMES
        self.player.retake_route_name = ROUTE_NAME
        self.player.retake_entry_frame = len(FRAMES) - 1
        self.player.retake_entry_logged = True
        self.player.retake_cursor = len(FRAMES) - 1
        end = FRAMES[-1]
        bomb = [45.0, 88.0, 15.5]
        o = self.obs(end)
        action = self.player.follow_retake(o, list(end[:3]), {}, bomb)
        self.assertIsNotNone(action)
        self.assertEqual(self.player.goal, list(bomb))
        self.assertTrue(self.player.path)


if __name__ == "__main__":
    unittest.main()

import math
import unittest

from scripts.pro_demo_routes import classify_route, source_to_platform
from scripts.build_pro_retakes import compile_routes, convert_frame
import agent
import json
from pathlib import Path
from tests.test_movement import observation


class ProDemoRouteTests(unittest.TestCase):
    def test_demo_angles_convert_to_platform_coordinates(self):
        row = convert_frame({"x": 100, "y": 100, "z": 20,
                             "yaw": 0, "pitch": 10, "tick": 4})
        self.assertAlmostEqual(row[3], -math.pi / 2, places=4)
        self.assertAlmostEqual(row[4], -math.radians(10), places=4)

    def test_compiled_routes_check_map_identity_and_both_directions(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "dust2_static.json").read_text())["map"]
        sites = {s["id"]: s["center"] for s in fixture["sites"]}
        routes = {"map_id": fixture["id"],
                  "geometry_hash": fixture["geometry_hash"],
                  "candidates": []}
        for direction in ("A_to_B", "B_to_A"):
            start, end = sites[direction[0]], sites[direction[-1]]
            routes["candidates"].append({
                "direction": direction, "player": "sample", "round": 1,
                "aim_forward_fraction": 0.9,
                "frames": [{"x": start[0] + (end[0] - start[0]) * i / 20,
                            "y": start[1] + (end[1] - start[1]) * i / 20,
                            "z": start[2], "yaw": 45, "pitch": 0}
                           for i in range(21)]})
        compiled = compile_routes(routes, fixture)
        self.assertIn("A_to_B", compiled)
        self.assertIn("B_to_A", compiled)
        self.assertTrue(all(len(route["frames"]) >= 10
                            for group in compiled.values() for route in group))
        fixture["geometry_hash"] = "wrong"
        with self.assertRaises(ValueError):
            compile_routes(routes, fixture)

    def test_source_coordinates_match_platform_axes(self):
        self.assertEqual(source_to_platform(-603, -1984, -180),
                         (49.6064, 84.6838, 15.428))

    def test_classifies_b_to_a_retake_with_forward_aim(self):
        sites = {"A": (45, 88), "B": (107, 48)}
        frames = [
            {"tick": i * 16, "x": 107 - i * 3.1,
             "y": 48 + i * 2, "yaw": math.degrees(math.atan2(-3.1, 2)),
             "pitch": 0}
            for i in range(21)
        ]
        result = classify_route(frames, sites, "A")
        self.assertEqual(result["direction"], "B_to_A")
        self.assertGreater(result["aim_forward_fraction"], 0.9)

    def test_rejects_route_that_does_not_leave_origin_site(self):
        sites = {"A": (45, 88), "B": (107, 48)}
        frames = [{"tick": i * 16, "x": 107, "y": 48,
                   "yaw": 0, "pitch": 0} for i in range(21)]
        self.assertIsNone(classify_route(frames, sites, "A"))

    def test_rejects_aiming_backwards(self):
        sites = {"A": (45, 88), "B": (107, 48)}
        frames = [{"tick": i * 16, "x": 107 - i * 3.1,
                   "y": 48 + i * 2, "yaw": 123, "pitch": 0}
                  for i in range(21)]
        result = classify_route(frames, sites, "A")
        self.assertLess(result["aim_forward_fraction"], 0.1)

    def test_ct_retake_uses_demo_route_then_goes_directly_to_bomb(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        routes = agent.pro_retake_routes(row["id"], row["geometry_hash"])
        self.assertTrue(routes["A_to_B"])
        start = routes["A_to_B"][0]["frames"][0]
        obs = observation(start[0], start[1], start[3], z=start[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash=row["geometry_hash"])
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"],
                       "fuse_end_tick": obs["match_tick"] + 2400}
        agent.init({})
        action = agent.act(obs)
        self.assertIsNotNone(agent._player.retake_route)
        self.assertTrue(action["sprint"])
        self.assertFalse(action["walk"])

        obs.pop("map")
        obs["visible"] = [{"x": start[0] + 5, "y": start[1],
                           "z": start[2], "parts": ["chest"],
                           "crouch": False}]
        cursor = agent._player.retake_cursor
        fighting = agent.act(obs)
        self.assertEqual(fighting["move_forward"], 0.0)
        self.assertEqual(agent._player.retake_cursor, cursor)

        obs["visible"] = []
        obs["match_tick"] += agent.COMBAT_MEMORY_TICKS + 3
        resumed = agent.act(obs)
        self.assertEqual(agent._player.retake_cursor, cursor)
        self.assertFalse(agent._player.retake_done)
        self.assertTrue(resumed["sprint"])
        obs["me"].update(x=routes["A_to_B"][0]["frames"][-1][0],
                         y=routes["A_to_B"][0]["frames"][-1][1])
        obs["match_tick"] += agent.COMBAT_MEMORY_TICKS + 3
        last_leg = agent.act(obs)
        self.assertFalse(agent._player.retake_done)
        self.assertIsNone(agent._player.goal)
        self.assertTrue(last_leg["sprint"])
        self.assertTrue(abs(last_leg["move_forward"]) > 0.1
                        or abs(last_leg["move_right"]) > 0.1)

    def test_ct_retake_does_not_start_on_wrong_map_or_from_target_site(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        a = row["sites"][0]["center"]
        obs = observation(a[0], a[1], 0, z=a[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash="wrong")
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"]}
        agent.init({})
        agent.act(obs)
        self.assertIsNone(agent._player.retake_route)
        obs.pop("map")
        obs["static_schema_hash"] = row["geometry_hash"]
        obs["me"].update(x=row["sites"][1]["center"][0],
                         y=row["sites"][1]["center"][1])
        agent.act(obs)
        self.assertIsNone(agent._player.retake_route)

    def test_both_maps_have_both_retake_directions(self):
        for filename in ("dust2", "mirage"):
            with self.subTest(map=filename):
                path = (Path(__file__).parent / "fixtures/dust2_static.json"
                        if filename == "dust2" else
                        Path(__file__).resolve().parents[1] /
                        "walklab/src/map-fixtures/mirage_static.json")
                row = json.loads(path.read_text())["map"]
                routes = agent.pro_retake_routes(row["id"], row["geometry_hash"])
                self.assertEqual(set(routes), {"A_to_B", "B_to_A"})
                for direction, candidates in routes.items():
                    start = candidates[0]["frames"][0]
                    obs = observation(start[0], start[1], start[3],
                                      z=start[2], match_map=row)
                    obs.update(map_id=row["id"],
                               static_schema_hash=row["geometry_hash"])
                    target = direction[-1]
                    obs["bomb"] = {"state": "planted", "site": target,
                                   "position": next(s["center"] for s in row["sites"]
                                                    if s["id"] == target)}
                    agent.init({})
                    agent.act(obs)
                    self.assertIsNotNone(agent._player.retake_route)

    def test_retake_requires_live_ct_and_plant(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        start = agent.pro_retake_routes(
            row["id"], row["geometry_hash"])["A_to_B"][0]["frames"][0]
        obs = observation(start[0], start[1], start[3], z=start[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash=row["geometry_hash"])
        agent.init({})
        agent.act(obs)
        self.assertIsNone(agent._player.retake_route)
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"]}
        obs["me"]["alive"] = False
        agent.act(obs)
        self.assertIsNone(agent._player.retake_route)

    def test_stalled_retake_hands_back_to_navigation(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        start = agent.pro_retake_routes(
            row["id"], row["geometry_hash"])["A_to_B"][0]["frames"][0]
        obs = observation(start[0], start[1], start[3], z=start[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash=row["geometry_hash"])
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"]}
        agent.init({})
        agent.act(obs)
        obs.pop("map")
        obs["match_tick"] += agent.REPLAY_BLOCK_TICKS + 3
        agent.act(obs)
        self.assertTrue(agent._player.retake_done)
        self.assertIsNotNone(agent._player.goal)

    def test_low_fuse_time_keeps_sprinting_on_demo_route(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        start = agent.pro_retake_routes(
            row["id"], row["geometry_hash"])["A_to_B"][0]["frames"][0]
        obs = observation(start[0], start[1], start[3], z=start[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash=row["geometry_hash"])
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"],
                       "fuse_end_tick": obs["match_tick"] + 800}
        agent.init({})
        action = agent.act(obs)
        self.assertFalse(agent._player.retake_done)
        self.assertIsNotNone(agent._player.retake_route)
        self.assertTrue(action["sprint"])
        self.assertIsNone(agent._player.goal)

    def test_route_join_steers_directly_without_astar(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        a = row["sites"][0]["center"]
        obs = observation(a[0], a[1], 0, z=a[2], match_map=row)
        obs.update(map_id=row["id"], static_schema_hash=row["geometry_hash"])
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"],
                       "fuse_end_tick": obs["match_tick"] + 800}
        agent.init({})
        action = agent.act(obs)
        self.assertIsNotNone(agent._player.retake_route)
        self.assertIsNone(agent._player.goal)
        self.assertTrue(action["sprint"])


if __name__ == "__main__":
    unittest.main()

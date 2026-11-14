import unittest

from scripts import pro_demo_walklab as routes
from scripts.pro_demo_walklab import (candidate_group, clean_interval,
                                      route_label, to_walklab)


class ProDemoWalklabTests(unittest.TestCase):
    def test_hold_requires_continuous_local_movement_and_aim(self):
        self.assertTrue(hasattr(routes, "hold_candidate"))
        hold_candidate = routes.hold_candidate
        frames = [{"tick": i * 4, "x": 160 + i * 0.015,
                   "y": 125 + (i % 12) * 0.03, "z": 20,
                   "yaw": 90 + (i % 40) * 0.5, "pitch": 0}
                  for i in range(160)]
        fixture = {"id": "dust2-cs2-v54", "sites": []}
        route = hold_candidate(frames, "steamid", 4, "A", (160, 125),
                               {"death": []}, fixture, "hash")
        self.assertIsNotNone(route)
        self.assertEqual(route["purpose"], "hold")
        self.assertEqual(route["side"], "defend")
        self.assertLessEqual(route["end_tick"] - route["start_tick"], 8 * 64)
        self.assertEqual(route["frames"][0]["tick"], route["start_tick"])

        dead = {"death": [(400, "enemy", "steamid")]}
        self.assertIsNone(hold_candidate(frames, "steamid", 4, "A",
                                         (160, 125), dead, fixture, "hash"))
        passing = [dict(f, x=160 + i * 0.3) for i, f in enumerate(frames)]
        self.assertIsNone(hold_candidate(passing, "steamid", 4, "A",
                                         (160, 125), {"death": []},
                                         fixture, "hash"))

    def test_hold_searches_past_a_rotation_after_arrival(self):
        frames = [{"tick": i * 4,
                   "x": 160 + min(i, 90) * 0.13 + (i % 16) * 0.02 if i >= 90
                   else 160 + i * 0.13,
                   "y": 125, "z": 20, "yaw": 90 + i * 0.2, "pitch": 0}
                  for i in range(240)]
        route = routes.hold_candidate(frames, "steamid", 4, "A", (171.7, 125),
                                      {"death": []},
                                      {"id": "dust2-cs2-v54"}, "hash")
        self.assertIsNotNone(route)
        self.assertGreaterEqual(route["start_tick"], 90 * 4)
        self.assertLessEqual(route["length"], 20)

    def test_postplant_hold_is_attack_side_and_keeps_site(self):
        frames = [{"tick": 1024 + i * 4, "x": 165 + (i % 8) * 0.03,
                   "y": 130, "z": 22, "yaw": 90 + i * 0.2, "pitch": 0}
                  for i in range(160)]
        route = routes.hold_candidate(frames, "steamid", 4, "A", (166, 130),
                                      {"death": []},
                                      {"id": "dust2-cs2-v54"}, "hash",
                                      side="attack")
        self.assertIsNotNone(route)
        self.assertEqual(route["purpose"], "postplant_hold")
        self.assertEqual(route["targetSite"], "A")
        self.assertEqual(route["side"], "attack")

    def test_keeps_distinct_attack_entries_in_distinct_groups(self):
        a_long = {"purpose": "attack", "name": "Dust2 T 进攻 A 大 · R1 p"}
        a_short = {"purpose": "attack", "name": "Dust2 T 进攻 A 小 · R2 p"}
        self.assertNotEqual(candidate_group(a_long), candidate_group(a_short))

    def test_labels_only_a_confirmed_entry(self):
        frames = [{"x": 131, "y": 140, "z": 20},
                  {"x": 158, "y": 134, "z": 20}]
        self.assertEqual(route_label("dust2-cs2-v54", "A", frames), "A 大")
        self.assertEqual(route_label("dust2-cs2-v54", "B", frames), "B")

    def test_allows_combat_but_rejects_death_during_route(self):
        events = {"fire": [(120, "p")], "hurt": [(125, "p", "q"),
                  (130, "q", "p")], "death": []}
        self.assertTrue(clean_interval(events, "p", 100, 140))
        events["death"] = [(135, "q", "p")]
        self.assertFalse(clean_interval(events, "p", 100, 140))
        self.assertTrue(clean_interval(events, "p", 100, 134))
        events["death"] = [(135, "p", "q")]
        self.assertTrue(clean_interval(events, "p", 100, 140))

    def test_converts_demo_pose_to_named_walklab_route(self):
        candidate = {"id": "mirage-t-a-r1-p", "name": "Mirage T A",
                     "side": "attack", "purpose": "attack", "targetSite": "A",
                     "player": "p", "round": 1, "start_tick": 100,
                     "end_tick": 108, "demo_hash": "digest",
                     "frames": [{"tick": 100, "x": 1, "y": 2, "z": 3,
                                 "yaw": 90, "pitch": 10},
                                {"tick": 104, "x": 2, "y": 2, "z": 3,
                                 "yaw": 90, "pitch": 10},
                                {"tick": 108, "x": 3, "y": 2, "z": 3,
                                 "yaw": 90, "pitch": 10}]}
        route = to_walklab(candidate, {"id": "mirage-cs2-v54",
                                       "geometry_hash": "hash"}, "demo.dem")
        self.assertEqual(route["name"], "Mirage T A")
        self.assertEqual(route["mapHash"], "hash")
        self.assertEqual(route["frames"][0]["position"], [1, 2, 3])
        self.assertEqual(route["frames"][0]["yaw"], 0)
        self.assertEqual([f["tick"] for f in route["frames"]], [0, 1, 2])
        self.assertEqual(route["frames"][0]["keys"], [])


if __name__ == "__main__":
    unittest.main()

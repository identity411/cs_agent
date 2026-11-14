"""Nevaio user-recorded T attacks, CT openings and site rotations."""
import json
import math
import unittest
from pathlib import Path

import agent
from scripts import build_nevaio_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "walklab/src/map-fixtures/nevaio_static.json").read_text())
T_MANIFEST = ROOT / "recordings/nevaio_t/manifest.json"
CT_MANIFEST = ROOT / "recordings/nevaio_ct/manifest.json"


class NevaioRouteTests(unittest.TestCase):
    def test_t_compiler_emits_four_site_scoped_attacks(self):
        result = build_nevaio_routes.compile_t_manifest(T_MANIFEST, FIXTURE)
        self.assertEqual([route["name"] for route in result["attacks"]],
                         ["A_mid", "A_long", "B_mid", "B_long"])
        sites = {site["id"]: site["center"]
                 for site in FIXTURE["map"]["sites"]}
        for route in result["attacks"]:
            center = sites[route["site"]]
            cutoff = route["carrier_cutoff"]
            self.assertLessEqual(
                math.dist(route["frames"][cutoff][:2], center[:2]), 12.0)
            self.assertTrue(all(
                math.dist(frame[:2], center[:2]) > 12.0
                for frame in route["frames"][:cutoff]))
            self.assertFalse(route["terminal_hold"])
            self.assertTrue(any(frame[5] & 16 for frame in route["frames"]))

    def test_compiler_rejects_wrong_map_hash(self):
        bad = json.loads(json.dumps(FIXTURE))
        bad["map"]["geometry_hash"] = "wrong"
        for compile_manifest, manifest in (
                (build_nevaio_routes.compile_t_manifest, T_MANIFEST),
                (build_nevaio_routes.compile_ct_manifest, CT_MANIFEST)):
            with self.assertRaises(ValueError):
                compile_manifest(manifest, bad)

    def test_ct_compiler_synthesizes_final_pose_holds(self):
        result = build_nevaio_routes.compile_ct_manifest(
            CT_MANIFEST, FIXTURE)
        self.assertEqual(len(result["pairs"]), 4)
        for pair in result["pairs"]:
            self.assertEqual(pair["holdMode"], "final_pose")
            self.assertEqual(pair["hold"], (pair["opening"][-1],))
            self.assertIsNone(pair["sha256"]["hold"])
        self.assertEqual({direction: len(routes)
                          for direction, routes in result["retakes"].items()},
                         {"A_to_B": 2, "B_to_A": 2})

    def test_compiled_frames_match_source_json(self):
        from nevaio_user_t_routes import ATTACKS
        source = json.loads((ROOT / "recordings/nevaio_t"
                             / "nevaio-walk-t-a-mid.json").read_text())
        frames = next(route["frames"] for route in ATTACKS
                      if route["name"] == "A_mid")
        for index in (0, len(frames) // 2, len(frames) - 1):
            raw = source["frames"][index]
            self.assertEqual(frames[index][:3],
                             tuple(round(v, 4) for v in raw["position"]))
            self.assertEqual(frames[index][3],
                             round(raw["yaw"], 4))
            self.assertEqual(frames[index][4],
                             round(raw["pitch"], 4))

    def test_t_route_options_keep_legacy_and_add_four(self):
        from nevaio_user_t_routes import MAP_HASH
        options = agent.recorded_route_options("nevaio-r3-v54", MAP_HASH)
        self.assertEqual([option["name"] for option in options],
                         ["legacy", "A_mid", "A_long", "B_mid", "B_long"])
        self.assertIsNone(agent.recorded_site("nevaio-r3-v54", MAP_HASH))
        self.assertEqual(
            agent.recorded_route_options("nevaio-r3-v54", "wrong"), ())

    def test_t_route_selection_is_site_scoped(self):
        from nevaio_user_t_routes import MAP_HASH, MAP_ID
        player = agent.Player()
        player.map_id = MAP_ID
        obs = {"static_schema_hash": MAP_HASH, "round_index": 0, "seat": 0}
        player._sync_route_memory(obs)
        spawn = [18.2, 110.0, 0.0]
        self.assertIn(player._select_recorded_route(obs, spawn, "A")["name"],
                      {"legacy", "A_mid", "A_long"})
        self.assertIn(player._select_recorded_route(obs, spawn, "B")["name"],
                      {"B_mid", "B_long"})

    def test_t_site_plan_can_reach_b(self):
        from nevaio_user_t_routes import MAP_HASH, MAP_ID
        player = agent.Player()
        player.map_id = MAP_ID
        player.sites = FIXTURE["map"]["sites"]
        planned = []
        for round_index in range(4):
            obs = observation(18.2, 110.0, -1.5708,
                              round_index=round_index, tick=1000,
                              match_map=FIXTURE["map"])
            obs.update(side="attack", map_id=MAP_ID,
                       static_schema_hash=MAP_HASH)
            obs["me"]["carrying_bomb"] = False
            planned.append(player.choose_site(obs)["id"])
        self.assertIn("B", planned)

    def test_ct_pairs_select_by_site_and_seat(self):
        from nevaio_user_ct_routes import MAP_HASH, MAP_ID
        for seat in range(5):
            for site, allowed in (("A", {"A_mid", "A_long"}),
                                  ("B", {"B_mid", "B_long"})):
                player = agent.Player()
                player.map_id = MAP_ID
                player.choose_ct_recorded(
                    {"side": "defend", "seat": seat,
                     "static_schema_hash": MAP_HASH}, {"id": site})
                self.assertIn(player.ct_recorded_pair["name"], allowed)

    def test_ct_opening_advances_to_final_pose_hold(self):
        from nevaio_user_ct_routes import MAP_HASH, PAIRS
        pair = next(pair for pair in PAIRS if pair["name"] == "A_mid")
        last = pair["opening"][-1]
        player = agent.Player()
        player.ct_recorded_pair = pair
        player.ct_recorded_phase = "opening"
        player.ct_recorded_cursor = len(pair["opening"]) - 8
        obs = observation(last[0], last[1], last[3], z=last[2])
        obs.update(side="defend", static_schema_hash=MAP_HASH)
        player.follow_ct_recorded(obs, list(last[:3]), {})
        self.assertEqual(player.ct_recorded_phase, "hold")
        self.assertIs(player.ct_recorded_pair, pair)

    def test_ct_final_pose_hold_keeps_recorded_view(self):
        from nevaio_user_ct_routes import PAIRS
        pair = next(pair for pair in PAIRS if pair["name"] == "B_long")
        last = pair["hold"][0]
        player = agent.Player()
        player.ct_recorded_pair = pair
        player.ct_recorded_phase = "hold"
        obs = observation(last[0], last[1], last[3], z=last[2])
        obs["match_tick"] = 100
        action = player.follow_ct_recorded(obs, list(last[:3]), {})
        self.assertIsNotNone(action)
        self.assertAlmostEqual(action["move_forward"], 0.0)
        self.assertAlmostEqual(action["move_right"], 0.0)
        self.assertIs(player.ct_recorded_pair, pair)

    def test_ct_retakes_are_registered_both_directions(self):
        from nevaio_user_ct_routes import MAP_HASH, RETAKES
        pairs, retakes = agent.user_ct_routes("nevaio-r3-v54", MAP_HASH)
        self.assertEqual(len(pairs), 4)
        self.assertEqual(set(retakes), {"A_to_B", "B_to_A"})
        self.assertEqual(agent.user_ct_routes("nevaio-r3-v54", "wrong"),
                         ((), {}))
        route = RETAKES["A_to_B"][0]
        player = agent.Player()
        player.map_id = "nevaio-r3-v54"
        player.sites = FIXTURE["map"]["sites"]
        target = next(site for site in player.sites if site["id"] == "B")
        obs = {"side": "defend", "static_schema_hash": MAP_HASH,
               "match_tick": 100, "seat": 0, "round_index": 0}
        player.choose_retake(obs, list(route["frames"][0][:3]), target)
        self.assertIs(player.retake_route, route["frames"])
        self.assertEqual(player.retake_route_name, route["name"])

    def test_wrong_hash_disables_t_routes(self):
        self.assertEqual(agent.user_t_routes("nevaio-r3-v54", "wrong"),
                         ((), {}))
        self.assertEqual(
            agent.user_t_routes("mirage-cs2-v54",
                                "78137c32df32b0f734cc25c35c943176"
                                "32084f15c18d846114b3e5314b9e67e3"),
            ((), {}))


if __name__ == "__main__":
    unittest.main()

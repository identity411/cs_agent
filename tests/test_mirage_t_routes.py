"""Approved Mirage T demo routes and their user-recorded handoff."""
import json
import math
import unittest
from pathlib import Path

import agent
from scripts import build_mirage_t_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "walklab/src/map-fixtures/mirage_static.json").read_text())
MANIFEST = ROOT / "recordings/mirage_t/manifest.json"


class MirageTRoutesTests(unittest.TestCase):
    def test_compiler_selects_only_approved_routes_and_handoff(self):
        result = build_mirage_t_routes.compile_manifest(MANIFEST, FIXTURE)
        self.assertEqual(len(result["attacks"]), 5)
        self.assertEqual({r["site"] for r in result["attacks"]}, {"A", "B"})
        bshort = next(r for r in result["attacks"] if r["name"] == "B_short_R14_karnez")
        self.assertEqual(bshort["frames"][0][:3], (98.9367, 133.8346, 15.7336))
        b2 = next(r for r in result["attacks"] if r["name"] == "B_apps_R13_Salazar")
        self.assertEqual(b2["handoff_index"], 267)
        self.assertEqual(len(b2["frames"]), 469)
        self.assertGreater(b2["frames"][266][2] - b2["frames"][267][2], 2.5)
        self.assertEqual(len(result["postplant"]["A"]), 1)

    def test_compiler_rejects_wrong_hash(self):
        bad = json.loads(json.dumps(FIXTURE))
        bad["map"]["geometry_hash"] = "wrong"
        with self.assertRaises(ValueError):
            build_mirage_t_routes.compile_manifest(MANIFEST, bad)

    def test_registered_attacks_are_site_scoped(self):
        from mirage_user_t_routes import MAP_HASH
        options = agent.recorded_route_options("mirage-cs2-v54", MAP_HASH)
        self.assertEqual(len([o for o in options if o["name"] != "legacy"]), 5)
        self.assertEqual(len([o for o in options if o["site"] == "A"]), 3)
        self.assertEqual(len([o for o in options if o["site"] == "B"]), 2)
        self.assertEqual(len(agent.recorded_route_options("mirage-cs2-v54", "wrong")), 0)

    def test_a_postplant_uses_approved_hold_only_after_plant(self):
        from mirage_user_t_routes import MAP_HASH, POSTPLANT
        row = FIXTURE["map"]
        frame = POSTPLANT["A"][0]["frames"][0]
        obs = observation(*frame[:2], frame[3], z=frame[2], match_map=row)
        obs.update(side="attack", static_schema_hash=MAP_HASH)
        obs["bomb"] = {"state": "planted", "site": "A",
                       "position": row["sites"][0]["center"]}
        player = agent.Player()
        action = player.act(obs)
        self.assertIsNotNone(player.t_postplant_route)
        self.assertTrue(math.isfinite(action.get("yaw_rate", 0)))

    def test_postplant_aim_frames_advance_while_stationary(self):
        from mirage_user_t_routes import MAP_HASH, POSTPLANT
        row = FIXTURE["map"]
        frame = POSTPLANT["A"][0]["frames"][0]
        obs = observation(frame[0], frame[1], frame[3], z=frame[2], match_map=row)
        obs.update(side="attack", static_schema_hash=MAP_HASH)
        obs["bomb"] = {"state": "planted", "site": "A",
                       "position": row["sites"][0]["center"]}
        player = agent.Player()
        player.act(obs)
        obs.pop("map")
        obs["match_tick"] += 20
        player.act(obs)
        self.assertGreaterEqual(player.t_postplant_cursor, 5)

    def test_b_apps_terminal_hold_stops_at_last_pose(self):
        from mirage_user_t_routes import ATTACKS, MAP_HASH
        route = next(r for r in ATTACKS if r["name"] == "B_apps_R13_Salazar")
        row = FIXTURE["map"]
        end = route["frames"][-1]
        obs = observation(end[0], end[1], end[3], z=end[2], match_map=row)
        obs.update(side="attack", static_schema_hash=MAP_HASH)
        obs["bomb"] = {"state": "carried", "site": "B"}
        player = agent.Player()
        player.load_map(row)
        player.selected_replay = {"name": route["name"], "site": "B",
                                  "frames": route["frames"],
                                  "terminal_hold": True,
                                  "carrier_cutoff": route["carrier_cutoff"]}
        player.round = obs["round_index"]
        player.replay_done = True
        obs.pop("map")
        action = player.act(obs)
        self.assertAlmostEqual(action["move_forward"], 0.0)
        self.assertAlmostEqual(action["move_right"], 0.0)


if __name__ == "__main__":
    unittest.main()

"""Dust2 user-recorded CT car-spot route intake and two-stage playback."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import agent
import dust2_user_ct_routes
import mirage_user_ct_routes
from scripts import build_dust2_ct_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/dust2_static.json").read_text())
MANIFEST = ROOT / "recordings/dust2_ct/manifest.json"


class Dust2UserCtTests(unittest.TestCase):
    def test_manifest_compiles_a_and_b_car_pairs(self):
        result = build_dust2_ct_routes.compile_manifest(MANIFEST, FIXTURE)
        self.assertEqual([pair["name"] for pair in result["pairs"]],
                         ["A_1", "B_1"])
        self.assertEqual([pair["site"] for pair in result["pairs"]],
                         ["A", "B"])
        self.assertFalse(result["retakes"]["B_to_A"])
        for pair in result["pairs"]:
            self.assertLess(agent.distance(pair["opening"][-1][:3],
                                           pair["hold"][0][:3]), 0.2)
            self.assertLess(agent.distance(pair["hold"][-1][:3],
                                           pair["hold"][0][:3]), 2.0)
            travel = sum(agent.distance(a[:3], b[:3])
                         for a, b in zip(pair["opening"],
                                         pair["opening"][1:]))
            self.assertGreater(travel, 10.0)
            self.assertTrue(any(frame[5] & 16 for frame in pair["opening"]))

    def test_generated_module_matches_source_hashes(self):
        result = build_dust2_ct_routes.compile_manifest(MANIFEST, FIXTURE)
        generated = {pair["name"]: pair for pair in dust2_user_ct_routes.PAIRS}
        for pair in result["pairs"]:
            module_pair = generated[pair["name"]]
            self.assertEqual(module_pair["site"], pair["site"])
            self.assertEqual(module_pair["sha256"], pair["sha256"])
            self.assertEqual(module_pair["opening"], pair["opening"])
            self.assertEqual(module_pair["hold"], pair["hold"])

    def test_compiler_rejects_wrong_map_hash(self):
        bad = json.loads(json.dumps(FIXTURE))
        bad["map"]["geometry_hash"] = "wrong"
        with self.assertRaises(ValueError):
            build_dust2_ct_routes.compile_manifest(MANIFEST, bad)

    def test_compiler_rejects_a_hold_from_the_other_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("dust2 ct 走a 车位.json", "dust2 ct 守b车位.json"):
                shutil.copy(ROOT / "recordings/dust2_ct" / name, root / name)
            (root / "manifest.json").write_text(json.dumps({
                "mapId": dust2_user_ct_routes.MAP_ID,
                "mapHash": dust2_user_ct_routes.MAP_HASH,
                "pairs": [{"name": "A_1", "site": "A",
                           "opening": "dust2 ct 走a 车位.json",
                           "hold": "dust2 ct 守b车位.json"}]}))
            with self.assertRaises(ValueError):
                build_dust2_ct_routes.compile_manifest(
                    root / "manifest.json", FIXTURE)

    def test_agent_dispatch_adds_dust2_and_keeps_mirage(self):
        pairs, retakes = agent.user_ct_routes(
            "dust2-cs2-v54", dust2_user_ct_routes.MAP_HASH)
        self.assertEqual([pair["name"] for pair in pairs], ["A_1", "B_1"])
        self.assertEqual(retakes, {})
        self.assertEqual(agent.user_ct_routes("dust2-cs2-v54", "wrong"),
                         ((), {}))
        self.assertEqual(agent.user_ct_routes(
            mirage_user_ct_routes.MAP_ID,
            mirage_user_ct_routes.MAP_HASH),
            (mirage_user_ct_routes.PAIRS,
             mirage_user_ct_routes.RETAKES))

    def test_site_selection_uses_the_recorded_car_pair(self):
        for seat in range(6):
            for site, name in (("A", "A_1"), ("B", "B_1")):
                player = agent.Player()
                player.map_id = dust2_user_ct_routes.MAP_ID
                player.choose_ct_recorded(
                    {"side": "defend", "seat": seat,
                     "static_schema_hash": dust2_user_ct_routes.MAP_HASH},
                    {"id": site})
                self.assertEqual(player.ct_recorded_pair["name"], name)

    def test_ct_opening_advances_to_hold_and_plant_ends_the_loop(self):
        pair = next(pair for pair in dust2_user_ct_routes.PAIRS
                    if pair["name"] == "A_1")
        row = FIXTURE["map"]
        first = pair["opening"][0]
        obs = observation(first[0], first[1], first[3], z=first[2],
                          match_map=row)
        obs.update(side="defend", seat=0,
                   static_schema_hash=dust2_user_ct_routes.MAP_HASH)
        obs["bomb"] = {"state": "carried", "site": "A"}
        player = agent.Player()
        player.act(obs)
        self.assertEqual(player.ct_recorded_pair["name"], "A_1")
        self.assertEqual(player.ct_recorded_phase, "opening")
        last = pair["opening"][-1]
        obs.pop("map")
        obs["me"].update(x=last[0], y=last[1], z=last[2])
        player.ct_recorded_cursor = len(pair["opening"]) - 8
        obs["match_tick"] += 3
        player.act(obs)
        self.assertEqual(player.ct_recorded_phase, "hold")
        obs["bomb"] = {"state": "planted", "site": "A",
                       "position": row["sites"][0]["center"]}
        obs["match_tick"] += 3
        player.act(obs)
        # The pair is retained for handoff logging; follow_ct_recorded() is
        # guarded by ``not planted``.  Dust2 has no recorded retake yet.
        self.assertIsNotNone(player.ct_recorded_pair)
        self.assertIsNone(player.retake_route)
        self.assertTrue(player.retake_checked)

    def test_stationary_b_hold_does_not_count_as_stuck(self):
        pair = next(pair for pair in dust2_user_ct_routes.PAIRS
                    if pair["name"] == "B_1")
        frame = pair["hold"][0]
        player = agent.Player()
        player.ct_recorded_pair = pair
        player.ct_recorded_phase = "hold"
        obs = observation(frame[0], frame[1], frame[3], z=frame[2])
        obs["match_tick"] = 100
        player.follow_ct_recorded(obs, list(frame[:3]), {})
        obs["match_tick"] += agent.REPLAY_BLOCK_TICKS + 3
        player.follow_ct_recorded(obs, list(frame[:3]), {})
        self.assertIsNotNone(player.ct_recorded_pair)


if __name__ == "__main__":
    unittest.main()

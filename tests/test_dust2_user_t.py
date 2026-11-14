"""Dust2 user-recorded T mid-B route and B post-plant car hold."""
import hashlib
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import agent
import dust2_user_ct_routes
import dust2_user_t_routes
import mirage_user_t_routes
from scripts import build_dust2_t_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/dust2_static.json").read_text())
MANIFEST = ROOT / "recordings/dust2_t/manifest.json"
ATTACK_SOURCE = ROOT / "recordings/dust2_t/dust2 t 中门夹b.json"
CT_HOLD_SOURCE = ROOT / "recordings/dust2_ct/dust2 ct 守b车位.json"


class Dust2UserTTests(unittest.TestCase):
    def test_manifest_compiles_mid_b_and_the_ct_car_hold(self):
        result = build_dust2_t_routes.compile_manifest(MANIFEST, FIXTURE)
        self.assertEqual([route["name"] for route in result["attacks"]],
                         ["B_mid_doors_20261114"])
        attack = result["attacks"][0]
        self.assertEqual(attack["site"], "B")
        self.assertEqual(len(attack["frames"]), 720)
        self.assertEqual(attack["carrier_cutoff"], len(attack["frames"]) - 1)
        self.assertEqual(attack["carrier_cutoff_kind"], "route_end")
        self.assertFalse(attack["terminal_hold"])
        hold = result["postplant"]["B"][0]
        self.assertEqual(hold["name"], "B_car_hold")
        self.assertEqual(hold["source_side"], "defend")
        self.assertEqual(len(hold["frames"]), 230)
        self.assertEqual(attack["sha256"],
                         hashlib.sha256(ATTACK_SOURCE.read_bytes()).hexdigest())
        self.assertEqual(hold["sha256"],
                         hashlib.sha256(CT_HOLD_SOURCE.read_bytes()).hexdigest())
        ct_pair = next(pair for pair in dust2_user_ct_routes.PAIRS
                       if pair["name"] == "B_1")
        self.assertEqual(hold["frames"], ct_pair["hold"])

    def test_compiler_rejects_wrong_map_hash(self):
        bad = json.loads(json.dumps(FIXTURE))
        bad["map"]["geometry_hash"] = "wrong"
        with self.assertRaises(ValueError):
            build_dust2_t_routes.compile_manifest(MANIFEST, bad)

    def test_compiler_rejects_a_ct_recording_as_an_attack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ATTACK_SOURCE, root / ATTACK_SOURCE.name)
            shutil.copy(CT_HOLD_SOURCE, root / CT_HOLD_SOURCE.name)
            (root / "manifest.json").write_text(json.dumps({
                "mapId": dust2_user_t_routes.MAP_ID,
                "mapHash": dust2_user_t_routes.MAP_HASH,
                "attacks": [{"name": "bad", "site": "B",
                             "source": CT_HOLD_SOURCE.name}]}))
            with self.assertRaises(ValueError):
                build_dust2_t_routes.compile_manifest(
                    root / "manifest.json", FIXTURE)

    def test_agent_dispatch_adds_dust2_and_keeps_mirage(self):
        attacks, holds = agent.user_t_routes(
            "dust2-cs2-v54", dust2_user_t_routes.MAP_HASH)
        self.assertEqual([route["name"] for route in attacks],
                         ["B_mid_doors_20261114"])
        self.assertEqual(holds["B"][0]["name"], "B_car_hold")
        self.assertEqual(agent.user_t_routes("dust2-cs2-v54", "wrong"),
                         ((), {}))
        self.assertEqual(
            agent.user_t_routes(mirage_user_t_routes.MAP_ID,
                                mirage_user_t_routes.MAP_HASH),
            (mirage_user_t_routes.ATTACKS, mirage_user_t_routes.POSTPLANT))

    def test_attack_options_add_the_new_route_and_respect_the_site(self):
        names = [option["name"] for option in agent.recorded_route_options(
            "dust2-cs2-v54", dust2_user_t_routes.MAP_HASH)]
        self.assertEqual(names, ["legacy", "B_site_20261113",
                                 "B_mid_doors_20261114"])
        self.assertEqual(agent.recorded_route_options(
            "dust2-cs2-v54", "wrong"), ())
        player = agent.Player()
        player.map_id = "dust2-cs2-v54"
        player.route_scores = {"legacy": 0.1, "B_site_20261113": 0.1,
                               "B_mid_doors_20261114": 1.0}
        obs = {"static_schema_hash": dust2_user_t_routes.MAP_HASH,
               "round_index": 0, "seat": 0}
        pos = [76.8352, 81.3056, 23.0]
        self.assertEqual(
            player._select_recorded_route(obs, pos, "A")["name"], "legacy")
        self.assertEqual(
            player._select_recorded_route(obs, pos, "B")["name"],
            "B_mid_doors_20261114")

    def test_planted_b_uses_the_ct_car_hold(self):
        frame = dust2_user_t_routes.POSTPLANT["B"][0]["frames"][0]
        row = FIXTURE["map"]
        obs = observation(frame[0], frame[1], frame[3], z=frame[2],
                          match_map=row)
        obs.update(side="attack",
                   static_schema_hash=dust2_user_t_routes.MAP_HASH)
        obs["bomb"] = {"state": "planted", "site": "B",
                       "position": row["sites"][1]["center"]}
        player = agent.Player()
        action = player.act(obs)
        self.assertIsNotNone(player.t_postplant_route)
        self.assertEqual(player.t_postplant_route["name"], "B_car_hold")
        self.assertTrue(math.isfinite(action.get("yaw_rate", 0)))

    def test_car_hold_is_not_used_before_the_plant(self):
        frame = dust2_user_t_routes.POSTPLANT["B"][0]["frames"][0]
        row = FIXTURE["map"]
        obs = observation(frame[0], frame[1], frame[3], z=frame[2],
                          match_map=row)
        obs.update(side="attack",
                   static_schema_hash=dust2_user_t_routes.MAP_HASH)
        obs["bomb"] = {"state": "carried", "site": "B"}
        player = agent.Player()
        player.act(obs)
        self.assertIsNone(player.t_postplant_route)


if __name__ == "__main__":
    unittest.main()

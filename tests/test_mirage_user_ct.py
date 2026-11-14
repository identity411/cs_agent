"""Mirage user-recorded CT route intake and two-stage playback."""
import json
import math
import unittest
from pathlib import Path

import agent
from scripts import build_mirage_ct_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "walklab/src/map-fixtures/mirage_static.json").read_text())


class MirageUserCtTests(unittest.TestCase):
    def test_manifest_compiles_six_pairs_and_two_b_to_a_retakes(self):
        result = build_mirage_ct_routes.compile_manifest(
            ROOT / "recordings/mirage_ct/manifest.json", FIXTURE)
        self.assertEqual(len(result["pairs"]), 6)
        self.assertEqual(len(result["retakes"]["B_to_A"]), 2)
        for pair in result["pairs"]:
            self.assertLess(agent.distance(pair["opening"][-1][:3],
                                           pair["hold"][0][:3]), 0.2)
            self.assertLess(agent.distance(pair["hold"][-1][:3],
                                           pair["hold"][0][:3]), 1.0)
        self.assertTrue(any(frame[5] & 32 for pair in result["pairs"]
                            for frame in pair["opening"]))
        self.assertTrue(any(all(frame[5] == 0 for frame in pair["hold"])
                            for pair in result["pairs"]))

    def test_compiler_rejects_wrong_map_hash(self):
        bad = json.loads(json.dumps(FIXTURE))
        bad["map"]["geometry_hash"] = "wrong"
        with self.assertRaises(ValueError):
            build_mirage_ct_routes.compile_manifest(
                ROOT / "recordings/mirage_ct/manifest.json", bad)

    def test_b_two_box_route_is_not_selected_for_matches(self):
        from mirage_user_ct_routes import MAP_HASH, MAP_ID
        for seat in range(6):
            player = agent.Player()
            player.map_id = MAP_ID
            player.choose_ct_recorded(
                {"side": "defend", "seat": seat,
                 "static_schema_hash": MAP_HASH}, {"id": "B"})
            self.assertIn(player.ct_recorded_pair["name"], ("B_1", "B_2"))

    def test_ct_opening_advances_to_hold_and_bomb_interrupts_it(self):
        from mirage_user_ct_routes import MAP_HASH, PAIRS, RETAKES
        pair = PAIRS[0]
        row = FIXTURE["map"]
        first = pair["opening"][0]
        obs = observation(first[0], first[1], first[3], z=first[2], match_map=row)
        obs.update(side="defend", seat=0, static_schema_hash=MAP_HASH)
        obs["bomb"] = {"state": "carried", "site": pair["site"]}
        player = agent.Player()
        player.act(obs)
        self.assertIsNotNone(player.ct_recorded_pair)
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
        obs["me"].update(x=RETAKES["B_to_A"][0]["frames"][0][0],
                         y=RETAKES["B_to_A"][0]["frames"][0][1])
        obs["match_tick"] += 3
        player.act(obs)
        # The pair is retained for handoff logging; follow_ct_recorded() is
        # guarded by ``not planted`` so the hold loop itself stops.
        self.assertIsNotNone(player.ct_recorded_pair)
        self.assertEqual(player.retake_route, RETAKES["B_to_A"][0]["frames"])

    def test_mirage_does_not_offer_pro_retake_without_user_route(self):
        row = FIXTURE["map"]
        player = agent.Player()
        player.load_map(row)
        player.choose_retake({"side": "defend", "static_schema_hash": row["geometry_hash"]},
                             row["sites"][0]["center"], row["sites"][1])
        self.assertIsNone(player.retake_route)

    def test_stationary_hold_does_not_count_as_stuck(self):
        from mirage_user_ct_routes import PAIRS
        pair = next(p for p in PAIRS if p["name"] == "A_2")
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

    def test_ct_climb_allows_jump_retries_then_falls_back(self):
        from mirage_user_ct_routes import MAP_HASH, MAP_ID, PAIRS
        player = agent.Player()
        player.map_id = MAP_ID
        player.ct_recorded_pair = PAIRS[0]
        player.ct_recorded_cursor = 80
        pos = [38.747, 65.007, 14.3105]
        obs = observation(pos[0], pos[1], -1.64, z=pos[2])
        obs.update(side="defend", static_schema_hash=MAP_HASH,
                   match_tick=15800)
        player.follow_ct_recorded(obs, pos, {})
        obs["match_tick"] += agent.REPLAY_BLOCK_TICKS + 3
        player.follow_ct_recorded(obs, pos, {})
        self.assertIsNotNone(player.ct_recorded_pair)
        obs["match_tick"] += 3 * agent.JUMP_COOLDOWN_TICKS + 3
        player.follow_ct_recorded(obs, pos, {})
        self.assertIsNone(player.ct_recorded_pair)

    def test_jungle_block_does_not_reselect_failed_ct_opening(self):
        from mirage_user_ct_routes import MAP_HASH, MAP_ID, PAIRS
        player = agent.Player()
        player.map_id = MAP_ID
        player.ct_recorded_pair = next(p for p in PAIRS if p["name"] == "A_3")
        player.ct_recorded_cursor = 211
        pos = [58.86, 79.98, 15.63]
        obs = observation(pos[0], pos[1], 0.0, z=pos[2])
        obs.update(side="defend", seat=2, static_schema_hash=MAP_HASH,
                   match_tick=103200)
        player.follow_ct_recorded(obs, pos, {})
        obs["match_tick"] += agent.REPLAY_BLOCK_TICKS + 3
        player.follow_ct_recorded(obs, pos, {})
        self.assertEqual(player.ct_recorded_pair["name"], "A_3")
        obs["match_tick"] += agent.REPLAY_AVOID_TICKS
        player.follow_ct_recorded(obs, pos, {})
        self.assertEqual(player.ct_recorded_pair["name"], "A_3")
        obs["match_tick"] += agent.REPLAY_AVOID_TICKS
        player.follow_ct_recorded(obs, pos, {})
        self.assertIsNone(player.ct_recorded_pair and player.ct_recorded_pair["name"])
        player.choose_ct_recorded(obs, {"id": "A"})
        self.assertIsNone(player.ct_recorded_pair)
        player._reset_ct_recorded()
        player.choose_ct_recorded(obs, {"id": "A"})
        self.assertEqual(player.ct_recorded_pair["name"], "A_3")

    def test_jungle_block_tries_open_side_with_forward_motion(self):
        from mirage_user_ct_routes import MAP_HASH, MAP_ID, PAIRS
        player = agent.Player()
        player.map_id = MAP_ID
        player.ct_recorded_pair = next(p for p in PAIRS if p["name"] == "A_3")
        player.ct_recorded_cursor = 211
        pos = [58.86, 79.98, 15.63]
        yaw = 0.3924
        obs = observation(pos[0], pos[1], yaw, z=pos[2])
        obs.update(side="defend", seat=5, static_schema_hash=MAP_HASH,
                   match_tick=103200)
        player.follow_ct_recorded(obs, pos, {})
        obs["match_tick"] += agent.REPLAY_BLOCK_TICKS + 3
        detour = player.follow_ct_recorded(obs, pos, {})
        self.assertIsNotNone(detour)
        world_x = (detour["move_forward"] * math.cos(yaw)
                   + detour["move_right"] * math.sin(yaw))
        world_y = (-detour["move_forward"] * math.sin(yaw)
                   + detour["move_right"] * math.cos(yaw))
        self.assertGreater(world_x, 0.2)
        self.assertLess(world_y, 0.0)
        self.assertFalse(detour["sprint"])
        anchor_tick = player.ct_recorded_anchor_tick
        obs["match_tick"] += 3
        player.follow_ct_recorded(obs, [58.47, 79.98, 15.60], {})
        self.assertEqual(player.ct_recorded_anchor_tick, anchor_tick)
        obs["match_tick"] += agent.REPLAY_AVOID_TICKS
        other_side = player.follow_ct_recorded(obs, pos, {})
        self.assertIsNotNone(other_side)
        self.assertEqual(player.ct_recorded_detour_attempts, 2)
        self.assertEqual(player.ct_recorded_detour_side, -1)


if __name__ == "__main__":
    unittest.main()

"""Regression harness for the 2026-11-14 replay-follow wedge.

Match 439a8cec: seat 5 followed A_palace from a north-off-lane spawn join,
backpedaled (-0.99) into the T-spawn west corner, and the forward-only
anti-block test kept resetting, leaving the seat frozen for ~112 s in three
rounds.  These tests pin the entry policy, the total-intent block test,
off-lane rejoin, the cursor watchdog, and the stalled-route penalty.
"""
import json
import math
import unittest
from pathlib import Path

import agent
import mirage_user_t_routes
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "walklab/src/map-fixtures/mirage_static.json").read_text())
ROW = FIXTURE["map"]
ROUTE = next(route for route in mirage_user_t_routes.ATTACKS
             if route["name"] == "A_palace_R4_ay0k")
# Public frame at t=10 s of the badcase: 0.99 m north of route frame 37.
WEDGE_POS = (89.686, 133.152, 15.743)
WEDGE_YAW = 0.125


def attack_obs(x=96.7124, y=135.5791, z=15.7755, yaw=-1.5708,
               tick=600, round_index=0, seat=5):
    o = observation(x, y, yaw, round_index=round_index, tick=tick,
                    match_map=ROW, seat=seat, z=z)
    o.update(side="attack", team=1, attack_team=1,
             map_id=ROW["id"], static_schema_hash=ROW["geometry_hash"])
    o["me"]["carrying_bomb"] = False
    o["bomb"] = {"state": "carried", "carrier": 9, "site": "A"}
    o.pop("map", None)
    return o


def route_info():
    return {"name": ROUTE["name"], "frames": ROUTE["frames"],
            "site": ROUTE["site"],
            "carrier_cutoff": ROUTE["carrier_cutoff"],
            "terminal_hold": ROUTE["terminal_hold"]}


class ReplayWedgeTest(unittest.TestCase):
    def setUp(self):
        agent.init({})

    def test_backpedal_counts_as_movement_intent(self):
        """move_forward=-0.99 is intent, not a recorded aim pause."""
        player = agent.Player()
        pos = [0.0, 0.0, 0.0]
        player.replay_anchor_pos = list(pos)
        player.replay_anchor_tick = 0
        tick = agent.REPLAY_BLOCK_TICKS
        action = {"move_forward": -0.99, "move_right": -0.14}
        player.avoid_replay_block(
            {"match_tick": tick, "seat": 0, "round_index": 0}, action, pos)
        self.assertEqual(player.replay_avoid_attempts, 1)

    def test_recorded_aim_pause_does_not_age_watchdog(self):
        player = agent.Player()
        pos = [0.0, 0.0, 0.0]
        player.replay_anchor_pos = list(pos)
        player.replay_anchor_tick = 0
        for tick in range(agent.REPLAY_BLOCK_TICKS, 200, 20):
            player.avoid_replay_block(
                {"match_tick": tick, "seat": 0, "round_index": 0},
                {"move_forward": 0.0, "move_right": 0.0}, pos)
        self.assertEqual(player.replay_avoid_attempts, 0)

    def test_attack_entry_uses_frame_zero_from_spawn(self):
        """A spawn join must A* to frames[0], not the nearest mid-lane frame."""
        player = agent.Player()
        player.load_map(ROW)
        o = attack_obs()
        pos = [o["me"]["x"], o["me"]["y"], o["me"]["z"]]
        self.assertTrue(player.choose_route_entry(
            o, pos, ROUTE["frames"], policy="first",
            route_name=ROUTE["name"], segment="attack"))
        self.assertEqual(player.link.entry_frame, 0)
        self.assertIn(0, [index for _, index in player.link.candidates])
        action = player.follow_attack_link(
            o, pos, ROUTE["frames"], route_info(), {"weapon_slot": 1})
        self.assertIsNotNone(action)
        self.assertEqual(tuple(round(v, 2) for v in player.goal),
                         tuple(round(v, 2) for v in ROUTE["frames"][0][:3]))
        self.assertFalse(player.link.entered)

    def test_off_lane_follow_rejoins_to_current_lane_frame(self):
        """The 1.0 m-north wedge state must A* back to frame 37."""
        player = agent.Player()
        player.load_map(ROW)
        player.round = 0
        player.replay_round = 0
        player.selected_replay = route_info()
        player.replay_cursor = 37
        player.link.segment = "attack"
        player.link.route_name = ROUTE["name"]
        player.link.frames = ROUTE["frames"]
        player.link.entry_frame = 37
        player.link.entered = True
        player._reset_replay_progress(37)

        o = attack_obs(*WEDGE_POS, yaw=WEDGE_YAW, tick=603)
        action = player.act(o)

        self.assertFalse(player.link.entered)
        self.assertEqual(player.link.entry_frame, 37)
        self.assertIsNotNone(player.goal)
        lane = ROUTE["frames"][37][:3]
        self.assertLess(math.dist(player.goal, lane), 0.05)
        # The old code backpedaled (move_forward=-0.99) into the corner.
        self.assertLess(abs(action.get("move_forward", 0.0)), 0.5)

    def test_cursor_watchdog_fires_without_advancing(self):
        player = agent.Player()
        player._reset_replay_progress(10)
        fired = False
        for tick in range(0, 200):
            fired = player._replay_progress_stalled(
                {"match_tick": tick},
                {0: 10, 1: 10, 2: 10}.get(tick, 10),
                {"move_forward": -0.99, "move_right": -0.14})
            if fired:
                break
        self.assertTrue(fired)
        self.assertGreaterEqual(tick, agent.REPLAY_CURSOR_TIMEOUT_TICKS)

    def test_cursor_watchdog_ignores_recorded_pauses_and_progress(self):
        player = agent.Player()
        player._reset_replay_progress(10)
        for tick in range(0, 400):
            self.assertFalse(player._replay_progress_stalled(
                {"match_tick": tick}, 10,
                {"move_forward": 0.0, "move_right": 0.0}))
        player._reset_replay_progress(10)
        for tick in range(0, 150):
            self.assertFalse(player._replay_progress_stalled(
                {"match_tick": tick}, 10 + tick // 2,
                {"move_forward": 1.0, "move_right": 0.0}))

    def test_stalled_route_is_penalized_at_round_end(self):
        player = agent.Player()
        player.route_scores = {ROUTE["name"]: 1.0}
        player.route_attempt = ROUTE["name"]
        player.route_started = True
        player.route_reached = False
        player.selected_replay = route_info()
        player._abandon_recorded_route(
            {"match_tick": 600, "seat": 5, "round_index": 0},
            list(WEDGE_POS), "test")
        self.assertTrue(player.route_stalled)
        player._finalize_route_round({
            "match_tick": 700, "seat": 5, "round_index": 1,
            "round_wins": [1, 0], "team": 1})
        self.assertEqual(player.route_scores[ROUTE["name"]],
                         agent.ROUTE_WEIGHT_FAILURE)
        self.assertTrue(player.route_last_failed)
        self.assertEqual(player.route_last, ROUTE["name"])

    def test_link_state_aliases_stay_compatible(self):
        player = agent.Player()
        player.retake_entry_frame = 12
        player.retake_entry_candidates = [(1.0, 12)]
        player.retake_entry_choice = 0
        player.retake_link_started = 99
        player.retake_entry_logged = True
        player.retake_fail_logged = False
        self.assertEqual(player.link.entry_frame, 12)
        self.assertEqual(player.link.candidates, [(1.0, 12)])
        self.assertEqual(player.link.started_tick, 99)
        self.assertTrue(player.link.entered)
        self.assertFalse(player.link.fail_logged)


if __name__ == "__main__":
    unittest.main()

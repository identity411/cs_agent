"""T-side recorded-route weight rotation (docs/spec/11-13-t-route-rotation.md)."""
import contextlib
import io
import json
import math
import unittest
from pathlib import Path

import agent
from scripts.dust2_regression import load_fixed_map
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
DUST2 = ROOT / "tests" / "fixtures" / "dust2_static.json"
MIRAGE = ROOT / "walklab" / "src" / "map-fixtures" / "mirage_static.json"


def dust2_observation(row, *, round_index=0, tick=0, seat=0, side="attack",
                      alive=True, wins=(0, 0), site="B", carrying=False):
    spawn = row["spawns"]["T"][0]["position"]
    obs = observation(spawn[0], spawn[1], -math.pi / 2,
                      match_map=row, z=spawn[2],
                      round_index=round_index, tick=tick, seat=seat)
    obs.update(side=side, map_id=row["id"],
               static_schema_hash=row["geometry_hash"])
    obs["team"] = 1
    obs["round_wins"] = [wins[0], wins[1]]
    obs["me"]["alive"] = alive
    obs["me"]["carrying_bomb"] = carrying
    obs["bomb"]["site"] = site
    return obs


def die(player, obs):
    obs.pop("map", None)
    obs["me"]["alive"] = False
    obs["match_tick"] += 3
    player.act(obs)
    obs["me"]["alive"] = True


class RouteRotationTest(unittest.TestCase):
    def setUp(self):
        agent.init({})
        self.row = load_fixed_map(DUST2)
        self.player = agent._player

    def _start_round(self, round_index, *, tick=0, seat=0, wins=(0, 0),
                     side="attack"):
        obs = dust2_observation(self.row, round_index=round_index,
                                tick=tick, seat=seat, wins=wins, side=side)
        self.player.act(obs)
        return obs

    def test_initial_choice_keeps_the_mirage_tie_break(self):
        # Round parity still picks the same first route as before rotation.
        obs = self._start_round(0, seat=0)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")
        self.assertTrue(self.player.route_started)
        self.assertEqual(self.player.route_last, "B_site_20261113")
        agent.init({})
        self.player = agent._player
        self._start_round(1, seat=0)
        self.assertEqual(self.player.selected_replay["name"], "legacy")

    def test_death_and_round_loss_halves_weight_and_switches(self):
        obs = self._start_round(0)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")
        die(self.player, obs)
        self.assertTrue(self.player.route_death_pending)
        # Team 1 lost the round: the enemy team's account moved.
        self._start_round(1, tick=obs["match_tick"] + 3, wins=(1, 0))
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 0.5)
        self.assertEqual(self.player.selected_replay["name"], "legacy")
        self.assertEqual(self.player.route_last, "legacy")

    def test_death_but_team_win_keeps_the_route(self):
        obs = self._start_round(0)
        die(self.player, obs)
        self._start_round(1, tick=obs["match_tick"] + 3, wins=(0, 1))
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 1.0)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")

    def test_success_restores_weight_and_stays_sticky(self):
        obs = self._start_round(0)
        self.player.route_scores["B_site_20261113"] = 0.5
        self.player.replay_done = True
        obs.pop("map", None)
        obs["match_tick"] += 3
        self.player.act(obs)
        self.assertTrue(self.player.route_reached)
        self.assertEqual(self.player.route_success, "B_site_20261113")
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 1.0)
        # Round 1 parity alone would pick legacy; the success route wins.
        self._start_round(1, tick=obs["match_tick"] + 3)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")

    def test_plant_while_route_active_is_success(self):
        obs = self._start_round(0)
        self.player.route_scores["B_site_20261113"] = 0.5
        obs.pop("map", None)
        obs["match_tick"] += 3
        obs["bomb"]["state"] = "planted"
        self.player.act(obs)
        self.assertTrue(self.player.route_reached)
        self.assertEqual(self.player.route_success, "B_site_20261113")
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 1.0)

    def test_plant_on_another_site_is_not_route_success(self):
        obs = self._start_round(0)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")
        self.player.route_scores["B_site_20261113"] = 0.5
        obs.pop("map", None)
        obs["match_tick"] += 3
        obs["bomb"]["state"] = "planted"
        obs["bomb"]["site"] = "A"
        self.player.act(obs)
        self.assertFalse(self.player.route_reached)
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 0.5)

    def test_all_routes_failed_keeps_rotating(self):
        obs = self._start_round(0)
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")
        die(self.player, obs)
        obs = self._start_round(1, tick=obs["match_tick"] + 3, wins=(1, 0))
        self.assertEqual(self.player.selected_replay["name"], "legacy")
        die(self.player, obs)
        self._start_round(2, tick=obs["match_tick"] + 3, wins=(2, 0))
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 0.5)
        self.assertAlmostEqual(self.player.route_scores["legacy"], 0.5)
        # Both failed: cycle to the route after the last failed one.
        self.assertEqual(self.player.selected_replay["name"],
                         "B_site_20261113")

    def test_weight_floor_and_missing_round_wins_are_neutral(self):
        next_obs = {"round_index": 4, "round_wins": [1, 0], "team": 1,
                    "seat": 0}
        self.player.route_scores["legacy"] = 0.15
        self.player.route_attempt = "legacy"
        self.player.route_started = True
        self.player.route_death_pending = True
        self.player.route_start_wins = [0, 0]
        self.player.route_start_team = 1
        self.player.round = 3
        self.player._finalize_route_round(next_obs)
        self.assertAlmostEqual(self.player.route_scores["legacy"], 0.1)

        self.player.route_scores["legacy"] = 0.5
        self.player.route_attempt = "legacy"
        self.player.route_started = True
        self.player.route_death_pending = True
        self.player.route_start_wins = [0, 0]
        self.player.route_start_team = 1
        self.player.round = 3
        self.player._finalize_route_round(
            {"round_index": 4, "team": 1, "seat": 0})
        self.assertAlmostEqual(self.player.route_scores["legacy"], 0.5)

    def test_ct_round_and_death_leave_route_state_alone(self):
        obs = self._start_round(0, side="defend")
        self.assertIsNone(self.player.selected_replay)
        self.assertFalse(self.player.route_started)
        die(self.player, obs)
        self.assertFalse(self.player.route_death_pending)
        self._start_round(1, tick=obs["match_tick"] + 3, side="defend",
                          wins=(1, 0))
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 1.0)
        self.assertIsNone(self.player.route_success)

    def test_single_route_map_is_unchanged(self):
        mirage = json.loads(MIRAGE.read_text())["map"]
        agent.init({})
        player = agent._player
        player.map_id = mirage["id"]
        o = {"static_schema_hash": mirage["geometry_hash"],
             "round_index": 0, "seat": 0}
        player._sync_route_memory(o)
        options = agent.recorded_route_options(
            mirage["id"], mirage["geometry_hash"])
        self.assertEqual([option["name"] for option in options], ["legacy"])
        route = player._select_recorded_route(o, [0.0, 0.0, 0.0], "A")
        self.assertEqual(route["name"], "legacy")

    def test_route_memory_resets_when_map_key_changes(self):
        obs = self._start_round(0)
        self.player.route_scores["B_site_20261113"] = 0.5
        self.player._sync_route_memory(
            dict(obs, static_schema_hash="different-map"))
        self.assertEqual(self.player.route_scores, {})
        self.assertIsNone(self.player.route_success)
        self.player._sync_route_memory(obs)
        self.assertAlmostEqual(
            self.player.route_scores["B_site_20261113"], 1.0)

    def test_death_switch_is_logged_to_stderr_only(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            obs = self._start_round(0)
            die(self.player, obs)
            self._start_round(1, tick=obs["match_tick"] + 3, wins=(1, 0))
        self.assertEqual(stdout.getvalue(), "")
        log = stderr.getvalue()
        self.assertIn("route map=dust2-cs2-v54", log)
        self.assertIn("exec=B_site_20261113 result=death", log)
        self.assertIn("weight=0.50", log)


if __name__ == "__main__":
    unittest.main()

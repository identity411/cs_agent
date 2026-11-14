"""Opening-observation handling: chunked nav build and first-tick safety."""
import json
import math
import unittest
from pathlib import Path

import agent
from tests.test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
MIRAGE = ROOT / "walklab" / "src" / "map-fixtures" / "mirage_static.json"


def buy_observation(row, *, seat=5, phase="buy", tick=0):
    spawn = row["spawns"]["T"][0]["position"]
    obs = observation(spawn[0], spawn[1], -math.pi / 2, round_index=0,
                      tick=tick, seat=seat, match_map=row, z=spawn[2])
    obs.update(side="attack", map_id=row["id"],
               static_schema_hash=row["geometry_hash"], phase=phase)
    obs["team"] = 1
    obs["bomb"]["site"] = None
    obs["me"].update(cash=800, armor=0, helmet=False, has_kit=False)
    obs["me"]["weapons"] = [
        None,
        {"id": "pistol", "ammo": 20, "reserve": 60,
         "reload_until": None, "shot_ready": 0,
         "recoil_pitch": 0.0, "recoil_yaw": 0.0,
         "shots": 0, "last_shot": None},
        {"id": "knife", "ammo": 0, "reserve": 0,
         "reload_until": None, "shot_ready": 0,
         "recoil_pitch": 0.0, "recoil_yaw": 0.0,
         "shots": 0, "last_shot": None},
    ]
    return obs


class FirstCallbackTest(unittest.TestCase):
    def setUp(self):
        agent.init({})
        self.row = json.loads(MIRAGE.read_text())["map"]
        ref = agent.Player()
        ref.load_map(self.row)
        self.ref_nodes = ref.nodes
        self.ref_edges = ref.edges

    def test_opening_buy_skips_nav_build_then_chunks(self):
        obs = buy_observation(self.row)
        action = agent.act(obs)
        self.assertEqual(action, {"buy": "armor"})

        player = agent._player
        self.assertEqual(player.map_id, self.row["id"])
        self.assertFalse(player.map_ready)
        self.assertEqual(player.nodes, {})
        self.assertEqual(player.edges, {})
        self.assertTrue(player._map_build_skipped)

        # The map key can stay in repeated test observations; the same map
        # identity must not reset the in-progress build.
        consecutive = []
        for step in range(1, 40):
            obs["match_tick"] = step * 3
            agent.act(obs)
            consecutive.append(len(player.nodes))
            if player.map_ready:
                break
        self.assertTrue(player.map_ready)
        self.assertEqual(player.nodes, self.ref_nodes)
        self.assertEqual(player.edges, self.ref_edges)
        self.assertIn("legacy", player.route_scores)
        self.assertTrue(all(b >= a for a, b in zip(consecutive,
                                                   consecutive[1:])))
        # One callback may not build more than the configured chunk.
        self.assertLessEqual(consecutive[0], agent.MAP_BUILD_CHUNK)

    def test_live_first_observation_builds_immediately(self):
        obs = buy_observation(self.row, phase="live")
        agent.act(obs)
        player = agent._player
        self.assertTrue(player.map_ready)
        self.assertEqual(player.nodes, self.ref_nodes)
        self.assertEqual(player.edges, self.ref_edges)
        self.assertIn("legacy", player.route_scores)

    def test_route_finishes_pending_build_before_pathing(self):
        player = agent._player
        player.begin_map_load(self.row)
        self.assertFalse(player.map_ready)
        spawn = self.row["spawns"]["T"][0]["position"]
        goal = self.row["sites"][0]["center"]
        path, node_ids = player.route(spawn, goal)
        self.assertTrue(player.map_ready)
        self.assertTrue(path)
        self.assertEqual(len(path), len(node_ids))
        self.assertEqual(len(player.nodes), len(self.row["nav"]["nodes"]))


if __name__ == "__main__":
    unittest.main()

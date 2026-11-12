"""Regression tests for the stuck / waypoint selection fix.

Run with: python3 -m unittest discover -s tests -v
"""
import math
import unittest

import agent

# Minimal slice of nevaio-r3-v54 around the CT spawn.  The two waypoints
# behind the agent are the ones that trapped it in the 2026-11-12 match.
MAP = {
    "sites": [
        {"id": "A", "center": [112.0, 90.0, 2.4], "radius": 4.0},
        {"id": "B", "center": [52.0, 26.0, 0.0], "radius": 4.0},
    ],
    "nav": {
        "nodes": [
            {"id": "ct", "position": [118.0, 18.0, 0.0]},
            {"id": "rear_corner", "position": [118.0, 22.0, 0.0]},
            {"id": "equipment", "position": [118.0, 66.0, 0.0]},
            {"id": "equipment_n", "position": [118.0, 90.0, 2.4]},
            {"id": "A", "position": [112.0, 90.0, 2.4]},
            {"id": "B", "position": [52.0, 26.0, 0.0]},
        ],
        "edges": [
            {"from": "ct", "to": "rear_corner", "kind": "walk"},
            {"from": "rear_corner", "to": "equipment", "kind": "walk"},
            {"from": "equipment", "to": "equipment_n", "kind": "walk"},
            {"from": "equipment_n", "to": "A", "kind": "walk"},
        ],
    },
}

OPEN_MAP = {
    "sites": [{"id": "A", "center": [10.0, 0.0, 0.0], "radius": 2.0}],
    "nav": {
        "nodes": [
            {"id": "start", "position": [0.0, 0.0, 0.0]},
            {"id": "goal", "position": [10.0, 0.0, 0.0]},
        ],
        "edges": [{"from": "start", "to": "goal", "kind": "walk"}],
    },
}

# The real dust2 site/waypoint parameters that produced the R2 hold at B.
DUST2_MAP = {
    "sites": [
        {"id": "A", "center": [166.694, 130.0736, 22.54], "radius": 6.1},
        {"id": "B", "center": [167.3735, 60.2617, 20.2032], "radius": 6.3},
    ],
    "nav": {
        "nodes": [
            {"id": "A", "position": [166.694, 130.0736, 22.54]},
            {"id": "B", "position": [167.3735, 60.2617, 20.2032]},
            {"id": "ct", "position": [157.1595, 108.0804, 17.2266]},
        ],
        "edges": [{"from": "ct", "to": "B", "kind": "walk"}],
    },
    "bot_waypoints": {
        "holdB": [[169.0, 54.0, 20.8], [168.0, 62.0, 20.3],
                  [170.0, 66.0, 20.4], [165.0, 57.0, 20.3]],
        "watchB_CT": [[157.0, 57.0, 21.5], [166.0, 70.0, 23.0],
                      [156.0, 72.0, 21.0]],
    },
}

# A tiny graph where BFS (fewest edges) would pick the 200 m detour but
# A* (distance weights) must pick the 10 m path.
ASTAR_MAP = {
    "sites": [{"id": "A", "center": [0.0, 10.0, 0.0], "radius": 2.0}],
    "nav": {
        "nodes": [
            {"id": "start", "position": [0.0, 0.0, 0.0]},
            {"id": "far", "position": [100.0, 0.0, 0.0]},
            {"id": "m1", "position": [0.0, 3.0, 0.0]},
            {"id": "m2", "position": [0.0, 6.0, 0.0]},
            {"id": "goal", "position": [0.0, 10.0, 0.0]},
        ],
        "edges": [
            {"from": "start", "to": "far", "kind": "walk"},
            {"from": "far", "to": "goal", "kind": "walk"},
            {"from": "start", "to": "m1", "kind": "walk"},
            {"from": "m1", "to": "m2", "kind": "walk"},
            {"from": "m2", "to": "goal", "kind": "walk"},
        ],
    },
}

ROUTE_SPREAD_MAP = {
    "sites": [{"id": "A", "center": [30.0, 0.0, 0.0], "radius": 2.0}],
    "nav": {
        "nodes": [
            {"id": "start", "position": [0.0, 0.0, 0.0]},
            {"id": "l1", "position": [15.0, 0.0, 0.0]},
            {"id": "l2", "position": [15.0, 1.0, 0.0]},
            {"id": "A", "position": [30.0, 0.0, 0.0]},
        ],
        "edges": [
            {"from": "start", "to": "l1", "kind": "walk"},
            {"from": "l1", "to": "A", "kind": "walk"},
            {"from": "start", "to": "l2", "kind": "walk"},
            {"from": "l2", "to": "A", "kind": "walk"},
        ],
    },
    "bot_waypoints": {
        "l1": [15.0, 0.0, 0.0],
        "l2": [15.0, 1.0, 0.0],
        "attackRoutes": {
            "L1": ["l1", "A"],
            "L2": ["l2", "A"],
        },
    },
}

ATTACK_MAP = {
    "sites": [
        {"id": "A", "center": [30.0, 0.0, 0.0], "radius": 2.0},
        {"id": "B", "center": [30.0, 20.0, 0.0], "radius": 2.0},
    ],
    "nav": {
        "nodes": [
            {"id": "start", "position": [0.0, 0.0, 0.0]},
            {"id": "long", "position": [10.0, 0.0, 0.0]},
            {"id": "mid", "position": [10.0, 10.0, 0.0]},
            {"id": "short", "position": [20.0, 0.0, 0.0]},
            {"id": "doors", "position": [10.0, 20.0, 0.0]},
            {"id": "A", "position": [30.0, 0.0, 0.0]},
            {"id": "B", "position": [30.0, 20.0, 0.0]},
        ],
        "edges": [
            {"from": "start", "to": "long", "kind": "walk"},
            {"from": "long", "to": "A", "kind": "walk"},
            {"from": "start", "to": "mid", "kind": "walk"},
            {"from": "mid", "to": "short", "kind": "walk"},
            {"from": "short", "to": "A", "kind": "walk"},
            {"from": "mid", "to": "doors", "kind": "walk"},
            {"from": "doors", "to": "B", "kind": "walk"},
        ],
    },
    "bot_waypoints": {
        "long": [10.0, 0.0, 0.0],
        "mid": [10.0, 10.0, 0.0],
        "short": [20.0, 0.0, 0.0],
        "doors": [10.0, 20.0, 0.0],
        "attackRoutes": {
            "A_long": ["long", "A"],
            "A_split": ["mid", "short", "A"],
            "B_split": ["mid", "doors", "B"],
        },
    },
    "plant_zones": {
        "A": {"polygon": [[28.0, -2.0], [32.0, -2.0],
                          [32.0, 2.0], [28.0, 2.0]]},
    },
}


def observation(x, y, yaw, *, round_index=7, tick=37800, match_map=MAP,
                seat=7, z=0.0):
    return {
        "rules_version": "rsi-fps-5.5", "seat": seat, "team": 1,
        "side": "defend", "role": 0, "match_tick": tick,
        "round_index": round_index, "round_tick": tick, "phase": "live",
        "phase_remaining_ticks": 6900, "round_wins": [0, 0],
        "alive_by_team": [5, 5], "attack_team": 0,
        "period": "regulation", "overtime_number": 0, "win_target": 13,
        "buy_deadline_tick": 1860, "loss_level": 1,
        "me": {
            "x": x, "y": y, "z": z, "yaw": yaw, "pitch": 0.0,
            "vx": 0.0, "vy": 0.0, "vz": 0.0, "crouch": False,
            "lean_offset": 0.0, "grounded": True, "sprinting": False,
            "stamina": 1.0, "hp": 100, "armor": 100, "helmet": False,
            "alive": True, "blind_ticks": 0, "cash": 5000,
            "weapons": [
                {"id": "m4a1", "ammo": 20, "reserve": 60,
                 "reload_until": None, "shot_ready": 0,
                 "recoil_pitch": 0.0, "recoil_yaw": 0.0,
                 "shots": 0, "last_shot": None},
                {"id": "usp", "ammo": 12, "reserve": 24,
                 "reload_until": None, "shot_ready": 0,
                 "recoil_pitch": 0.0, "recoil_yaw": 0.0,
                 "shots": 0, "last_shot": None},
                {"id": "knife", "ammo": 0, "reserve": 0,
                 "reload_until": None, "shot_ready": 0,
                 "recoil_pitch": 0.0, "recoil_yaw": 0.0,
                 "shots": 0, "last_shot": None},
            ],
            "active_slot": 0, "carrying_bomb": False, "has_kit": False,
            "pickup_ready_tick": 0, "switch_until": 0, "throw_ready": 0,
            "ads_progress": 0.0, "slots": [], "throwables": [],
            "throwable_kinds": [], "ammo": 20, "reload": 0.0,
            "recoil": 0.0, "weapon_status": "ready", "walk": False,
            "quiet": False, "duck": False, "zoom_level": 0,
            "ladder_id": None, "movement_mode": "ground", "shot_ready": True,
        },
        "teammates": [], "visible": [], "sounds": [], "heard": [],
        "bomb": {"state": "carried", "fuse_end_tick": None},
        "world_items": [], "messages": [], "receipts": [],
        "map_id": "nevaio-r3-v54", "static_schema_hash": "test",
        "map": match_map,
    }


class NavigationRegression(unittest.TestCase):
    def setUp(self):
        agent.init({})

    def test_passed_waypoint_is_not_targeted_again(self):
        # 2026-11-12 R7 frame: position (117.67, 19.52), yaw 1.357.
        # The old code kept `ct` as path[0] and walked back into it.
        obs = observation(117.67, 19.52, 1.357)
        action = agent.act(obs)
        self.assertEqual(tuple(agent._player.path[0]), (118.0, 22.0, 0.0))
        self.assertLess(action["yaw_rate"], -0.5)

    def test_spawn_starts_at_forward_node(self):
        obs = observation(117.1, 18.0, math.pi / 2)
        action = agent.act(obs)
        self.assertEqual(tuple(agent._player.path[0]), (118.0, 22.0, 0.0))
        self.assertLess(action["yaw_rate"], -0.5)

    def test_blocked_waypoint_is_skipped_instead_of_looped(self):
        obs = observation(117.67, 19.52, 1.357)
        for step in range(220):
            if step:
                obs.pop("map", None)  # `map` is sent only on the first tick
            obs["match_tick"] = 37800 + step * 3
            agent.act(obs)
        # The agent cannot move in this synthetic stall; it must advance
        # through the path rather than re-selecting `ct` forever.
        self.assertIn((118.0, 22.0, 0.0), agent._player.blocked)
        self.assertNotEqual(tuple(agent._player.path[0]), (118.0, 22.0, 0.0))
        self.assertTrue(any(value > 0
                            for value in agent._player.edge_penalty.values()))

    def test_site_center_uses_patrol_waypoints(self):
        # 2026-11-12 R2: seat 3 stood on B center with speed ~1.4 but no
        # displacement.  It must target a public hold point instead.
        obs = observation(167.37, 60.24, 0.431, round_index=2,
                          tick=21000, match_map=DUST2_MAP, seat=3, z=20.13)
        agent.act(obs)
        self.assertEqual(agent._player.goal, [169.0, 54.0, 20.8])
        self.assertNotEqual(tuple(agent._player.goal),
                            (167.3735, 60.2617, 20.2032))

        # Reaching the first hold point advances to the next one; it does
        # not keep re-targeting the same spot.
        obs2 = observation(169.0, 54.0, 0.0, round_index=2,
                           tick=21003, match_map=DUST2_MAP, seat=3, z=20.8)
        obs2.pop("map", None)  # map is sent only on the first tick
        agent.act(obs2)
        self.assertEqual(agent._player.patrol_index, 1)
        self.assertEqual(agent._player.goal, [168.0, 62.0, 20.3])

    def test_patrol_advances_when_position_is_blocked(self):
        obs = observation(167.37, 60.24, 0.431, round_index=2,
                          tick=21000, match_map=DUST2_MAP, seat=3, z=20.13)
        for step in range(60):
            if step:
                obs.pop("map", None)
            obs["match_tick"] = 21000 + step * 3
            agent.act(obs)
        self.assertGreater(agent._player.patrol_index, 0)

    def test_open_floor_moves_forward(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        action = agent.act(obs)
        self.assertAlmostEqual(action["move_forward"], 0.75)
        self.assertAlmostEqual(action["yaw_rate"], 0.0)

    def test_astar_prefers_shorter_distance_not_fewer_edges(self):
        agent._player.load_map(ASTAR_MAP)
        path, node_ids = agent._player.route([0.0, 0.0, 0.0],
                                             [0.0, 10.0, 0.0])
        self.assertTrue(any(
            math.hypot(point[0], point[1] - 3.0) < 0.1 for point in path))
        self.assertFalse(any(
            math.hypot(point[0] - 100.0, point[1]) < 0.1 for point in path))
        self.assertEqual(len(path), len(node_ids))

    def test_attack_route_lane_and_sprint(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=ATTACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["attack_team"] = 0
        action = agent.act(obs)
        self.assertEqual(agent._player.attack_route_name, "A_long")
        self.assertEqual(tuple(agent._player.attack_route_points[0]),
                         (10.0, 0.0, 0.0))
        self.assertIsNotNone(agent._player.via_key)
        self.assertTrue(any(tuple(point) == (10.0, 0.0, 0.0)
                            for point in agent._player.path))
        self.assertIs(action["sprint"], True)
        self.assertIs(action["walk"], False)

    def test_similar_attack_routes_spread_across_seats(self):
        routes = []
        for seat in (0, 1):
            agent.init({})
            obs = observation(0.0, 0.0, 0.0, round_index=0, tick=400,
                              match_map=ROUTE_SPREAD_MAP, seat=seat)
            obs["side"] = "attack"
            obs["attack_team"] = 0
            obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                           "site": "A"}
            agent.act(obs)
            routes.append(agent._player.attack_route_name)
        self.assertEqual(set(routes), {"L1", "L2"})

    def test_bomb_site_overrides_seat_parity(self):
        # seat 3 / round 12 would fall back to B; the visible bomb says A.
        obs = observation(0.0, 0.0, 0.0, round_index=12, tick=400,
                          match_map=ATTACK_MAP, seat=3)
        obs["side"] = "attack"
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [30.0, 0.0, 0.0])

    def test_plant_zone_allows_plant(self):
        obs = observation(30.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=ATTACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["attack_team"] = 0
        obs["me"]["carrying_bomb"] = True
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        action = agent.act(obs)
        self.assertEqual(action.get("use"), "plant")

    def test_combat_strafes_then_resumes_path(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["visible"] = [{
            "seat": 5, "team": 1, "x": 10.0, "y": 10.0, "z": 0.0,
            "yaw": 0.0, "pitch": 0.0, "crouch": False,
            "lean": 0.0, "parts": ["chest"], "weapon": "ak47",
        }]
        first = agent.act(obs)
        self.assertFalse(first["crouch"])
        self.assertNotEqual(first.get("move_right", 0.0), 0.0)
        for step in range(1, 35):
            obs.pop("map", None)
            obs["match_tick"] = step * 3
            action = agent.act(obs)
        self.assertGreater(agent._player.combat_cooldown_until,
                           obs["match_tick"])
        self.assertIsNotNone(action.get("move_forward"))


if __name__ == "__main__":
    unittest.main()

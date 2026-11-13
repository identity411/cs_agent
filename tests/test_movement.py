"""Regression tests for the stuck / waypoint selection fix.

Run with: python3 -m unittest discover -s tests -v
"""
import math
import json
import unittest
from pathlib import Path

import advance_holds
import agent
import map_patches

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

# Mirage's crouch-only passage into VIP ("dog hole") at (75.3, 66.2).
# The agent must crouch through the low passage instead of jumping.
MIRAGE_DOGHOLE_MAP = {
    "id": "mirage-cs2-v54",
    "sites": [{"id": "A", "center": [75.3, 69.0, 15.83],
               "radius": 6.0}],
    "nav": {
        "nodes": [
            {"id": "south", "position": [75.3, 62.0, 15.83]},
            {"id": "gate", "position": [75.3, 66.2, 15.83]},
            {"id": "north", "position": [75.3, 69.0, 15.83]},
            {"id": "site", "position": [75.3, 80.0, 15.83]},
        ],
        "edges": [
            {"from": "south", "to": "gate", "kind": "walk"},
            {"from": "gate", "to": "north", "kind": "walk"},
            {"from": "north", "to": "site", "kind": "walk"},
        ],
    },
    "spawns": {
        "T": [{"position": [75.3, 62.0, 15.83], "yaw": 0.0}],
        "CT": [{"position": [75.3, 62.0, 15.83], "yaw": 0.0}],
    },
}

# Minimal Mirage A-site anchor: the CT should hold at the east edge and
# keep the crosshair on the A-ramp choke, not turn into the boxes.
MIRAGE_A_MAP = {
    "id": "mirage-cs2-v54",
    "sites": [{"id": "A", "center": [51.5, 87.3, 15.55],
               "radius": 6.0}],
    "nav": {
        "nodes": [{"id": "a", "position": [51.5, 87.3, 15.55]}],
        "edges": [],
    },
    "spawns": {
        "T": [{"position": [96.6, 130.1, 15.83], "yaw": 0.0}],
        "CT": [{"position": [51.5, 53.3, 13.05], "yaw": 0.0}],
    },
}

# A nav edge that ends on a 1.2 m ledge.  Mirage's CT->A approach has the
# same shape: the next node is above the agent and needs a forward jump.
STEP_MAP = {
    "sites": [{"id": "A", "center": [2.0, 0.0, 1.2], "radius": 1.0}],
    "nav": {
        "nodes": [
            {"id": "start", "position": [0.0, 0.0, 0.0]},
            {"id": "ledge", "position": [2.0, 0.0, 1.2]},
        ],
        "edges": [{"from": "start", "to": "ledge", "kind": "walk"}],
    },
}

# T-side temporary fallback target: after 40 s without a plant, T walks to
# the CT spawn instead of staying pinned in its own spawn area.
T_FALLBACK_MAP = {
    "id": "test-t-fallback",
    "sites": [{"id": "A", "center": [10.0, 0.0, 0.0], "radius": 2.0}],
    "nav": {
        "nodes": [
            {"id": "spawn", "position": [0.0, 0.0, 0.0]},
            {"id": "site", "position": [10.0, 0.0, 0.0]},
            {"id": "ct", "position": [0.0, 20.0, 0.0]},
        ],
        "edges": [
            {"from": "spawn", "to": "site", "kind": "walk"},
            {"from": "spawn", "to": "ct", "kind": "walk"},
        ],
    },
    "spawns": {
        "T": [{"position": [0.0, 0.0, 0.0], "yaw": 0.0, "nav_id": "spawn"}],
        "CT": [{"position": [0.0, 20.0, 0.0], "yaw": 0.0, "nav_id": "ct"}],
    },
}

# Mirage post-plant hold fixture.  A-box / sofa / B-short coordinates are
# sampled from account2 match 125a716a (plants and post-plant positions).
MIRAGE_HOLD_MAP = {
    "id": "mirage-cs2-v54",
    "sites": [
        {"id": "A", "center": [44.67, 88.18, 15.43], "radius": 6.1},
        {"id": "B", "center": [107.1, 47.87, 15.94], "radius": 6.3},
    ],
    "nav": {
        "nodes": [
            {"id": "ct", "position": [51.5, 53.3, 13.05]},
            {"id": "a", "position": [48.6, 89.8, 15.43]},
            {"id": "b", "position": [109.4, 54.1, 15.7]},
            {"id": "bshort", "position": [98.6, 50.5, 15.8]},
            {"id": "market", "position": [98.0, 66.0, 15.83]},
        ],
        "edges": [
            {"from": "ct", "to": "a", "kind": "walk"},
            {"from": "a", "to": "b", "kind": "walk"},
            {"from": "b", "to": "bshort", "kind": "walk"},
            {"from": "bshort", "to": "market", "kind": "walk"},
        ],
    },
    "spawns": {
        "T": [{"position": [96.6, 130.1, 15.8]}],
        "CT": [{"position": [51.5, 53.3, 13.05]}],
    },
}

# Two equal-length nevaio CT->B routes.  The warm_hall route is shorter to
# warm_gate (66 m vs 74 m), so the hazard test is not vacuous.
NEVAIO_ROUTE_MAP = {
    "id": "nevaio-r3-v54",
    "sites": [
        {"id": "B", "center": [52.0, 26.0, 0.0], "radius": 4.0},
    ],
    "nav": {
        "nodes": [
            {"id": "ct", "position": [118.0, 18.0, 0.0]},
            {"id": "warm_hall", "position": [86.0, 18.0, 0.0]},
            {"id": "warm_gate", "position": [52.0, 18.0, 0.0]},
            {"id": "rear_corner", "position": [118.0, 22.0, 0.0]},
            {"id": "rear_door", "position": [52.0, 22.0, 0.0]},
            {"id": "B", "position": [52.0, 26.0, 0.0]},
        ],
        "edges": [
            {"from": "ct", "to": "warm_hall", "kind": "walk"},
            {"from": "warm_hall", "to": "warm_gate", "kind": "walk"},
            {"from": "warm_gate", "to": "rear_door", "kind": "walk"},
            {"from": "ct", "to": "rear_corner", "kind": "walk"},
            {"from": "rear_corner", "to": "rear_door", "kind": "walk"},
            {"from": "rear_door", "to": "B", "kind": "walk"},
            {"from": "warm_gate", "to": "B", "kind": "walk"},
        ],
    },
    "spawns": {
        "T": [{"position": [20.0, 110.0, 0.0]}],
        "CT": [{"position": [118.0, 18.0, 0.0]}],
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

    def test_recorded_route_tracks_position_instead_of_playback_time(self):
        track = [
            (0.0, 0.0, 0.0, 0.0, 0.0, 1),
            (1.0, 0.0, 0.0, 0.2, 0.0, 1),
            (2.0, 1.0, 0.0, 0.4, 0.0, 9),
            (2.0, 2.0, 0.0, 0.6, 0.1, 8),
        ]
        cursor, action = agent.follow_trajectory(
            track, 0, [0.9, 0.0, 0.0], yaw=0.0, pitch=0.0)
        self.assertGreaterEqual(cursor, 1)
        self.assertGreater(action["yaw_rate"], 0.0)
        self.assertGreater(action["pitch_rate"], 0.0)
        self.assertGreater(action["move_forward"], 0.0)
        self.assertFalse(action["walk"])

    def test_recorded_route_uses_recorded_input_and_pauses_without_movement(self):
        track = [
            (0.0, 0.0, 0.0, 0.0, 0.0, 0),
            (0.0, 1.0, 0.0, 0.0, 0.0, 8),
            (0.0, 2.0, 0.0, 0.0, 0.0, 8 | 16),
        ]
        _cursor, action = agent.follow_trajectory(
            track, 0, [0.0, 1.8, 0.0], yaw=0.0, pitch=0.0)
        self.assertGreater(action["move_right"], 0.0)
        self.assertTrue(action["sprint"])

    def test_recorded_route_replays_stationary_mouse_aim_one_frame_at_a_time(self):
        track = [
            (0.0, 0.0, 0.0, 0.0, 0.0, 0),
            (0.0, 0.0, 0.0, 0.2, 0.1, 0),
            (1.0, 0.0, 0.0, 0.2, 0.1, 1),
        ]
        cursor, action = agent.follow_trajectory(
            track, 0, [0.0, 0.0, 0.0], yaw=0.0, pitch=0.0)
        self.assertEqual(cursor, 1)
        self.assertEqual(action["move_forward"], 0.0)
        self.assertEqual(action["move_right"], 0.0)
        self.assertGreater(action["yaw_rate"], 0.0)
        self.assertGreater(action["pitch_rate"], 0.0)

    def test_dust2_replay_stops_for_enemy_then_resumes_from_same_cursor(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        obs = observation(76.8352, 81.3056, -math.pi / 2,
                          match_map=row, z=23.0252)
        obs.update(side="attack", map_id=row["id"],
                   static_schema_hash=row["geometry_hash"])
        obs["bomb"]["site"] = "B"
        obs["visible"] = [{"x": 76.8352, "y": 86.3056,
                            "z": 23.4652, "parts": ["chest"],
                            "crouch": False}]
        fighting = agent.act(obs)
        self.assertEqual(fighting["move_forward"], 0.0)
        self.assertEqual(fighting["move_right"], 0.0)
        self.assertTrue(fighting["fire"])
        self.assertEqual(agent._player.replay_cursor, 0)
        obs.pop("map")
        obs["visible"] = []
        # Visibility flicker is bridged for COMBAT_MEMORY_TICKS so the
        # replay does not resume between samples.
        for _ in range(2):
            obs["match_tick"] += 3
            held = agent.act(obs)
            self.assertEqual(held["move_forward"], 0.0)
            self.assertFalse(held["fire"])
            self.assertEqual(agent._player.replay_cursor, 0)
        obs["match_tick"] += agent.COMBAT_MEMORY_TICKS
        resumed = agent.act(obs)
        self.assertEqual(resumed["move_forward"], 0.0)
        self.assertGreater(agent._player.replay_cursor, 0)
        for _ in range(100):
            obs["match_tick"] += 3
            resumed = agent.act(obs)
            if resumed["move_forward"] > 0.0:
                break
        self.assertGreater(resumed["move_forward"], 0.0)

    def test_dust2_replay_rejoins_with_nav_after_large_displacement(self):
        row = json.loads((Path(__file__).parent / "fixtures" /
                          "dust2_static.json").read_text())["map"]
        obs = observation(93.0, 81.0, -math.pi / 2,
                          match_map=row, z=20.0)
        obs.update(side="attack", map_id=row["id"],
                   static_schema_hash=row["geometry_hash"])
        obs["bomb"]["site"] = "B"
        action = agent.act(obs)
        self.assertTrue(agent._player.path)
        self.assertTrue(action.get("sprint"))

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

    def test_t_fallback_exempts_bomb_carrier(self):
        # Before 40 s T keeps the normal site goal.
        agent.init({})
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=2399,
                          match_map=T_FALLBACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [10.0, 0.0, 0.0])

        # After 40 s a non-carrier still walks to CT spawn.
        agent.init({})
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=2400,
                          match_map=T_FALLBACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [0.0, 20.0, 0.0])

        # The carrier is exempt: it must go to the plant point, not CT.
        agent.init({})
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=2400,
                          match_map=T_FALLBACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["me"]["carrying_bomb"] = True
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [10.0, 0.0, 0.0])
        self.assertNotEqual(agent._player.goal, [0.0, 20.0, 0.0])

    def test_t_carrier_plants_after_40s_in_zone(self):
        obs = observation(30.0, 0.0, 0.0, round_index=0, tick=2400,
                          match_map=ATTACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["me"]["carrying_bomb"] = True
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        action = agent.act(obs)
        self.assertEqual(action.get("use"), "plant")

    def test_t_fallback_does_not_override_planted_bomb_or_ct_side(self):
        agent.init({})
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=2400,
                          match_map=T_FALLBACK_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "planted", "position": [10.0, 0.0, 0.0],
                       "fuse_end_tick": 10000}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [10.0, 0.0, 0.0])

        agent.init({})
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=2400,
                          match_map=T_FALLBACK_MAP, seat=5)
        obs["side"] = "defend"
        obs["team"] = 1
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        agent.act(obs)
        self.assertEqual(agent._player.goal, [10.0, 0.0, 0.0])

    def test_map_patch_hazards_are_applied_by_map_id(self):
        self.assertTrue(map_patches.for_map("mirage-cs2-v54").hazards)
        self.assertTrue(map_patches.for_map("nevaio-r3-v54").hazards)
        self.assertEqual(map_patches.for_map("unknown-map").hazards, ())

        row = {
            "id": "mirage-cs2-v54",
            "sites": [{"id": "A", "center": [10.0, 0.0, 0.0],
                       "radius": 2.0}],
            "nav": {
                "nodes": [
                    {"id": "start", "position": [0.0, 0.0, 0.0]},
                    {"id": "hazard", "position": [42.8, 66.4, 0.0]},
                    {"id": "goal", "position": [10.0, 0.0, 0.0]},
                ],
                "edges": [
                    {"from": "start", "to": "hazard", "kind": "walk"},
                    {"from": "hazard", "to": "goal", "kind": "walk"},
                ],
            },
        }
        agent._player.load_map(row)
        self.assertTrue(any(value > 0
                            for value in agent._player.edge_penalty.values()))

    def test_nevaio_hazard_forces_rear_corner_route(self):
        player = agent.Player()
        # Without the patch, warm_gate is 66 m via warm_hall.
        player.load_map(dict(NEVAIO_ROUTE_MAP, id="no-hazard-nevaio"))
        _path, ids = player.route([118.0, 18.0, 0.0], [52.0, 18.0, 0.0])
        self.assertIn("warm_hall", ids)

        # The real nevaio patch penalizes warm_hall; the 74 m rear route wins.
        player.load_map(NEVAIO_ROUTE_MAP)
        _path, ids = player.route([118.0, 18.0, 0.0], [52.0, 18.0, 0.0])
        self.assertNotIn("warm_hall", ids)
        self.assertIn("rear_corner", ids)

    def test_round_reset_clears_learned_penalties_but_keeps_hazards(self):
        agent.init({})
        obs = observation(118.0, 18.0, 0.0, round_index=0, tick=0,
                          match_map=NEVAIO_ROUTE_MAP, seat=0)
        obs["side"] = "defend"
        obs["team"] = 0
        obs["attack_team"] = 1
        obs["bomb"] = {"state": "carried", "site": "B",
                       "fuse_end_tick": None}
        agent.act(obs)
        player = agent._player
        player.edge_penalty[("ct", "rear_corner")] = agent.EDGE_PENALTY_MAX
        self.assertEqual(player.edge_penalty.get(("ct", "warm_hall")),
                         agent.EDGE_PENALTY_MAX)

        # A new round must drop the stale rear-route penalty but keep the
        # permanent warm_hall hazard.
        obs.pop("map", None)
        obs["round_index"] = 1
        obs["match_tick"] = 5000
        agent.act(obs)
        self.assertNotIn(("ct", "rear_corner"), player.edge_penalty)
        self.assertEqual(player.edge_penalty.get(("ct", "warm_hall")),
                         agent.EDGE_PENALTY_MAX)
        _path, ids = player.route([118.0, 18.0, 0.0], [52.0, 18.0, 0.0])
        self.assertIn("rear_corner", ids)
        self.assertNotIn("warm_hall", ids)

    def test_step_up_waypoint_triggers_forward_jump(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=STEP_MAP, seat=0)
        action = agent.act(obs)
        self.assertIs(action.get("jump"), True)
        self.assertGreater(action["move_forward"], 0.0)
        self.assertIs(action["walk"], False)

    def test_sliding_stall_jumps_forward_instead_of_waiting(self):
        # R6 Mirage carrier slid east/west at the T-spawn corner for the
        # whole round.  Position changes every tick, so the old stuck test
        # never fired; net progress toward the waypoint was zero.
        obs = observation(1.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=OPEN_MAP, seat=0)
        jump_actions = []
        for step in range(20):
            if step:
                obs.pop("map", None)
            obs["match_tick"] = 400 + step * 3
            obs["me"]["x"] = 1.3 if step % 2 else 0.7
            action = agent.act(obs)
            if action.get("jump"):
                jump_actions.append(action)
        self.assertTrue(jump_actions)
        self.assertGreater(jump_actions[0]["move_forward"], 0.0)

    def test_mirage_doghole_is_crossed_crouched_without_jump(self):
        obs = observation(75.3, 64.5, 0.0, round_index=0, tick=400,
                          match_map=MIRAGE_DOGHOLE_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                       "site": "A"}
        action = agent.act(obs)
        self.assertTrue(action.get("crouch"))
        self.assertIsNone(action.get("jump"))

        obs.pop("map", None)
        obs["match_tick"] = 403
        obs["me"]["x"], obs["me"]["y"] = 75.3, 67.0
        action = agent.act(obs)
        self.assertTrue(action.get("crouch"))
        self.assertIsNone(action.get("jump"))

        obs["match_tick"] = 406
        obs["me"]["x"], obs["me"]["y"] = 75.3, 68.0
        action = agent.act(obs)
        self.assertFalse(action.get("crouch"))
        self.assertIsNot(action.get("jump"), True)

    def test_mirage_ct_a_holds_and_aims_a_long(self):
        obs = observation(51.5, 87.3, 0.0, round_index=7, tick=400,
                          match_map=MIRAGE_A_MAP, seat=7, z=15.55)
        action = agent.act(obs)
        self.assertEqual(action.get("move_forward"), 0.0)
        self.assertEqual(action.get("move_right"), 0.0)
        self.assertFalse(action.get("crouch"))
        self.assertIsNone(action.get("jump"))
        # A long is north of the anchor: the engine yaw must decrease.
        self.assertLess(action.get("yaw_rate"), 0.0)

    def test_preaim_keeps_crosshair_on_aim_while_pathing(self):
        agent._player.load_map(OPEN_MAP)
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=OPEN_MAP, seat=0)
        action = agent._player.move(obs, [10.0, 0.0, 0.0],
                                    {"weapon_slot": 0},
                                    aim=(0.0, 10.0, 0.0))
        self.assertLess(action["yaw_rate"], 0.0)
        self.assertGreater(action["move_forward"], 0.0)

    def test_t_lane_preaim_uses_advance_aim_point(self):
        agent._player.load_map(OPEN_MAP)
        points = advance_holds.for_map("nevaio-r3-v54").lane(
            "attack", "A", "A_long").points
        aim = agent._player.advance_aim(points, [60.0, 111.0, 1.2])
        self.assertAlmostEqual(aim[0], 123.0)
        self.assertAlmostEqual(aim[1], 77.8)
        self.assertAlmostEqual(aim[2], 2.84)
        self.assertIsNone(agent._player.advance_aim(
            points, [0.0, 0.0, 0.0]))

    def test_stuck_recovery_tries_forward_jump_before_backoff(self):
        obs = observation(1.0, 0.0, 0.0, round_index=0, tick=400,
                          match_map=OPEN_MAP, seat=0)
        first_jump = None
        for step in range(40):
            if step:
                obs.pop("map", None)
            obs["match_tick"] = 400 + step * 3
            action = agent.act(obs)
            if action.get("jump") and first_jump is None:
                first_jump = action
        self.assertIsNotNone(first_jump)
        self.assertGreater(first_jump["move_forward"], 0.0)

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

    def test_mirage_post_plant_a_watches_ct_jungle_arch(self):
        agent.init({})
        obs = observation(48.6, 89.8, 0.0, round_index=0, tick=0,
                          match_map=MIRAGE_HOLD_MAP, seat=0, z=15.43)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "planted", "position": [48.6, 89.8, 15.43],
                       "fuse_end_tick": 100000, "site": "A"}
        action = agent.act(obs)
        self.assertIsNotNone(agent._player.post_plant_plan)
        self.assertEqual(agent._player.post_plant_plan.name, "A_boxes")
        self.assertEqual(action.get("move_forward", 0.0), 0.0)
        self.assertEqual(action.get("move_right", 0.0), 0.0)
        self.assertNotEqual(action.get("yaw_rate"), 0.15)
        self.assertEqual(agent._player.post_plant_look, 0)

        # The CT-spawn look lasts one dwell; the next look is jungle.
        obs.pop("map", None)
        obs["match_tick"] = 181
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_look, 1)
        obs["match_tick"] = 362
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_look, 2)
        obs["match_tick"] = 543
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_look, 0)

    def test_mirage_post_plant_b_loops_sofa_and_short(self):
        agent.init({})
        obs = observation(109.4, 54.1, 0.0, round_index=0, tick=0,
                          match_map=MIRAGE_HOLD_MAP, seat=0, z=15.7)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "planted", "position": [108.1, 50.7, 15.9],
                       "fuse_end_tick": 100000, "site": "B"}
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_spot, 0)
        self.assertEqual(agent._player.post_plant_look, 0)

        obs.pop("map", None)
        obs["match_tick"] = 181
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_spot, 0)
        self.assertEqual(agent._player.post_plant_look, 1)

        # After both sofa looks, the loop moves to the B-short cover.
        obs["match_tick"] = 362
        action = agent.act(obs)
        self.assertEqual(agent._player.post_plant_spot, 1)
        self.assertEqual(agent._player.goal, [98.6, 50.5, 15.8])
        self.assertGreater(abs(action.get("move_forward", 0.0))
                           + abs(action.get("move_right", 0.0)), 0.0)

        # Standing on the short cover advances to its market look, then
        # wraps back to the sofa spot.
        obs["me"]["x"], obs["me"]["y"], obs["me"]["z"] = (
            98.6, 50.5, 15.8)
        obs["match_tick"] = 363
        action = agent.act(obs)
        self.assertEqual(action.get("move_forward", 0.0), 0.0)
        self.assertEqual(agent._player.post_plant_spot, 1)
        obs["match_tick"] = 544
        agent.act(obs)
        self.assertEqual(agent._player.post_plant_spot, 0)
        self.assertEqual(agent._player.post_plant_look, 0)

    def test_generic_post_plant_hold_does_not_spin(self):
        agent.init({})
        obs = observation(10.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["side"] = "attack"
        obs["team"] = 0
        obs["attack_team"] = 0
        obs["bomb"] = {"state": "planted", "position": [10.0, 0.0, 0.0],
                       "fuse_end_tick": 100000, "site": "A"}
        action = agent.act(obs)
        self.assertEqual(action.get("move_forward", 0.0), 0.0)
        self.assertNotEqual(action.get("yaw_rate"), 0.15)
        self.assertIsNotNone(agent._player.post_plant_plan)

    def test_combat_brakes_then_resumes_path(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["visible"] = [{
            "seat": 5, "team": 1, "x": 10.0, "y": 10.0, "z": 0.0,
            "yaw": 0.0, "pitch": 0.0, "crouch": False,
            "lean": 0.0, "parts": ["chest"], "weapon": "ak47",
        }]
        first = agent.act(obs)
        # Seeing an enemy brakes immediately: no strafe, no forward move.
        self.assertFalse(first["crouch"])
        self.assertEqual(first.get("move_right", 0.0), 0.0)
        self.assertEqual(first.get("move_forward", 0.0), 0.0)
        for step in range(1, 35):
            obs.pop("map", None)
            obs["match_tick"] = step * 3
            action = agent.act(obs)
        self.assertGreater(agent._player.combat_cooldown_until,
                           obs["match_tick"])
        self.assertIsNotNone(action.get("move_forward"))
        # The cooldown branch may move, but never while pulling the trigger.
        self.assertFalse(action.get("fire"))

    def test_fire_bands_follow_mirage_a_to_ct_spawn(self):
        # The close band is the measured Mirage A site centre -> CT spawn
        # distance (32.56 m); tap runs to 1.5x that, then the trigger holds.
        self.assertAlmostEqual(agent.SPRAY_RANGE, 32.5, places=1)
        self.assertAlmostEqual(agent.TAP_RANGE, 48.75, places=2)
        self.assertEqual(agent.fire_mode(10.0, ["chest"]), "spray")
        self.assertEqual(agent.fire_mode(agent.SPRAY_RANGE, ["chest"]),
                         "spray")
        self.assertEqual(agent.fire_mode(agent.SPRAY_RANGE + 0.1,
                                         ["chest"]), "tap")
        self.assertEqual(agent.fire_mode(agent.TAP_RANGE, ["head"]),
                         "tap")
        self.assertEqual(agent.fire_mode(agent.TAP_RANGE + 0.1, ["head"]),
                         "tap_long")
        # A head-only target inside the close band is tapped, not sprayed.
        self.assertEqual(agent.fire_mode(10.0, ["head"]), "tap")

    def test_mid_range_taps_head_on_a_0_7_second_cadence(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["visible"] = [{
            "seat": 5, "team": 1, "x": 40.0, "y": 0.0, "z": -0.02,
            "yaw": 0.0, "pitch": 0.0, "crouch": False,
            "lean": 0.0, "parts": ["head"], "weapon": "ak47",
        }]
        obs["me"]["speed"] = 0.0
        fires = []
        for step in range(40):
            if step:
                obs.pop("map", None)
            obs["match_tick"] = step * 3
            action = agent.act(obs)
            self.assertEqual(action.get("move_forward", 0.0), 0.0)
            self.assertEqual(action.get("move_right", 0.0), 0.0)
            fires.append(bool(action.get("fire")))
        self.assertGreaterEqual(sum(fires), 2)
        self.assertIn(False, fires)
        fire_ticks = [i * 3 for i, fired in enumerate(fires) if fired]
        for earlier, later in zip(fire_ticks, fire_ticks[1:]):
            self.assertGreaterEqual(later - earlier, agent.TAP_INTERVAL_TICKS)
        self.assertEqual(agent.TAP_INTERVAL_TICKS, 42)  # 0.7 s at 60 Hz

    def test_body_only_target_never_fires_outside_spray_band(self):
        # "只点头": chest/abdomen visible but no head -> no shot at range.
        for x in (40.0, 50.0):
            agent.init({})
            obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                              match_map=OPEN_MAP, seat=0)
            obs["visible"] = [{
                "seat": 5, "team": 1, "x": x, "y": 0.0, "z": 0.44,
                "yaw": 0.0, "pitch": 0.0, "crouch": False,
                "lean": 0.0, "parts": ["chest"], "weapon": "ak47",
            }]
            obs["me"]["speed"] = 0.0
            for step in range(20):
                if step:
                    obs.pop("map", None)
                obs["match_tick"] = step * 3
                self.assertFalse(agent.act(obs).get("fire"))

    def test_beyond_1_5x_spray_range_taps_head_once_per_second(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["visible"] = [{
            "seat": 5, "team": 1, "x": 50.0, "y": 0.0, "z": -0.02,
            "yaw": 0.0, "pitch": 0.0, "crouch": False,
            "lean": 0.0, "parts": ["head"], "weapon": "ak47",
        }]
        obs["me"]["speed"] = 0.0
        fires = []
        for step in range(50):
            if step:
                obs.pop("map", None)
            obs["match_tick"] = step * 3
            action = agent.act(obs)
            self.assertEqual(action.get("move_forward", 0.0), 0.0)
            self.assertEqual(action.get("move_right", 0.0), 0.0)
            fires.append(bool(action.get("fire")))
        self.assertGreaterEqual(sum(fires), 2)
        self.assertFalse(all(fires))
        fire_ticks = [i * 3 for i, fired in enumerate(fires) if fired]
        for earlier, later in zip(fire_ticks, fire_ticks[1:]):
            self.assertGreaterEqual(later - earlier,
                                    agent.LONG_TAP_INTERVAL_TICKS)
        self.assertEqual(agent.LONG_TAP_INTERVAL_TICKS, 60)  # 1 s at 60 Hz

    def test_close_body_sprays_inside_the_band(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        obs["visible"] = [{
            "seat": 5, "team": 1, "x": 10.0, "y": 0.0, "z": 0.44,
            "yaw": 0.0, "pitch": 0.0, "crouch": False,
            "lean": 0.0, "parts": ["chest", "head"], "weapon": "ak47",
        }]
        obs["me"]["speed"] = 0.0
        self.assertTrue(agent.act(obs).get("fire"))

    def test_combat_bridges_visibility_flicker_and_keeps_target(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        near = {"seat": 5, "team": 1, "x": 25.0, "y": 0.0, "z": 0.44,
                "yaw": 0.0, "pitch": 0.0, "crouch": False,
                "lean": 0.0, "parts": ["chest"], "weapon": "ak47"}
        far = {"seat": 8, "team": 1, "x": 50.0, "y": 0.0, "z": -0.02,
               "yaw": 0.0, "pitch": 0.0, "crouch": False,
               "lean": 0.0, "parts": ["head"], "weapon": "ak47"}
        obs["visible"] = [near, far]
        obs["me"]["speed"] = 0.0
        first = agent.act(obs)
        self.assertFalse(first["crouch"])
        self.assertEqual(agent._player.combat_target_seat, 5)
        obs.pop("map", None)
        for _ in range(2):
            obs["visible"] = []
            obs["match_tick"] += 3
            held = agent.act(obs)
            self.assertEqual(held["move_forward"], 0.0)
            self.assertEqual(held["move_right"], 0.0)
            self.assertFalse(held["fire"])
            self.assertEqual(agent._player.combat_target_seat, 5)
        obs["visible"] = [near, far]
        obs["match_tick"] += 3
        resumed = agent.act(obs)
        self.assertEqual(agent._player.combat_target_seat, 5)
        self.assertFalse(resumed["crouch"])

    def test_locked_target_does_not_flap_to_a_far_enemy(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        near = {"seat": 5, "team": 1, "x": 25.0, "y": 0.0, "z": 0.44,
                "yaw": 0.0, "pitch": 0.0, "crouch": False,
                "lean": 0.0, "parts": ["chest"], "weapon": "ak47"}
        far = {"seat": 8, "team": 1, "x": 50.0, "y": 0.0, "z": -0.02,
               "yaw": 0.0, "pitch": 0.0, "crouch": False,
               "lean": 0.0, "parts": ["head"], "weapon": "ak47"}
        obs["visible"] = [near, far]
        obs["me"]["speed"] = 0.0
        agent.act(obs)
        self.assertEqual(agent._player.combat_target_seat, 5)
        obs.pop("map", None)
        # The near target peeks behind cover: only the far one is visible.
        obs["visible"] = [far]
        obs["match_tick"] += 3
        held = agent.act(obs)
        self.assertEqual(agent._player.combat_target_seat, 5)
        self.assertFalse(held["fire"])

    def test_replay_sidesteps_when_blocked_by_a_teammate(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        player = agent._player
        player.replay_anchor_pos = [0.0, 0.0, 0.0]
        player.replay_anchor_tick = 0
        action = {"move_forward": 0.6, "move_right": 0.0,
                  "sprint": False, "walk": False}
        obs["match_tick"] = agent.REPLAY_BLOCK_TICKS
        out = player.avoid_replay_block(obs, dict(action), [0.0, 0.0, 0.0])
        self.assertEqual(out["move_forward"], 0.0)
        self.assertNotEqual(out["move_right"], 0.0)
        self.assertGreater(player.replay_avoid_until, obs["match_tick"])
        # While the sidestep is active it keeps steering laterally.
        obs["match_tick"] += 3
        out = player.avoid_replay_block(obs, dict(action), [0.0, 0.0, 0.0])
        self.assertEqual(out["move_forward"], 0.0)
        self.assertNotEqual(out["move_right"], 0.0)
        # Progress resets the block timer without a sidestep.
        player.replay_avoid_until = 0
        obs["match_tick"] += 3
        out = player.avoid_replay_block(obs, dict(action), [3.0, 0.0, 0.0])
        self.assertEqual(out["move_forward"], 0.6)
        self.assertEqual(player.replay_anchor_pos, [3.0, 0.0, 0.0])

    def test_replay_abandons_route_after_repeated_blocks(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        player = agent._player
        player.replay_avoid_attempts = agent.REPLAY_AVOID_ATTEMPTS
        player.replay_anchor_pos = [0.0, 0.0, 0.0]
        player.replay_anchor_tick = 0
        obs["match_tick"] = agent.REPLAY_BLOCK_TICKS
        action = {"move_forward": 0.6, "move_right": 0.0}
        player.avoid_replay_block(obs, action, [0.0, 0.0, 0.0])
        self.assertTrue(player.replay_done)
        self.assertTrue(player.replay_abandoned)

    def test_combat_does_not_fire_while_airborne_or_moving(self):
        for grounded, speed in ((False, 0.0), (True, 5.0)):
            agent.init({})
            obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                              match_map=OPEN_MAP, seat=0)
            obs["visible"] = [{
                "seat": 5, "team": 1, "x": 10.0, "y": 0.0, "z": 0.44,
                "yaw": 0.0, "pitch": 0.0, "crouch": False,
                "lean": 0.0, "parts": ["chest"], "weapon": "ak47",
            }]
            obs["me"]["grounded"] = grounded
            obs["me"]["speed"] = speed
            action = agent.act(obs)
            self.assertFalse(action.get("fire"))
            self.assertEqual(action.get("move_forward", 0.0), 0.0)
            self.assertEqual(action.get("move_right", 0.0), 0.0)


class AdvanceHoldsRegression(unittest.TestCase):
    def test_pre_45_anchors_exist_for_all_sampled_maps(self):
        for map_id in ("nevaio-r3-v54", "mirage-cs2-v54",
                       "dust2-cs2-v54", "borgo-r3-v54"):
            data = advance_holds.for_map(map_id)
            self.assertIsNotNone(data.anchor("defend", "A"), map_id)

    def test_nevaio_pre_45_lanes(self):
        data = advance_holds.for_map("nevaio-r3-v54")
        for site, name in (("A", "A_long"), ("A", "A_mid"),
                           ("B", "B_drill")):
            lane = data.lane("attack", site, name)
            self.assertIsNotNone(lane, name)
            self.assertGreater(len(lane.points), 0)

    def test_mirage_post_plant_holds(self):
        data = advance_holds.for_map("mirage-cs2-v54")
        a = data.plant_hold("A")
        b = data.plant_hold("B")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(len(a.spots), 1)
        self.assertEqual(len(a.spots[0].looks), 3)
        self.assertEqual(len(b.spots), 2)
        self.assertEqual(len(b.spots[0].looks), 2)
        # PlantLook stores absolute aim height; HEAD_HEIGHT is not added.
        self.assertAlmostEqual(a.spots[0].looks[0].aim_z, 14.7)
        self.assertEqual(data.plant_hold("nope"), None)

    def test_unknown_map_is_neutral(self):
        data = advance_holds.for_map("unknown-map")
        self.assertEqual(data.lanes, {})
        self.assertEqual(data.anchors, {})
        self.assertEqual(data.plant_holds, {})


if __name__ == "__main__":
    unittest.main()

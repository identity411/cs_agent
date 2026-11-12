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


def observation(x, y, yaw, *, round_index=7, tick=37800, match_map=MAP,
                seat=7):
    return {
        "rules_version": "rsi-fps-5.5", "seat": seat, "team": 1,
        "side": "defend", "role": 0, "match_tick": tick,
        "round_index": round_index, "round_tick": tick, "phase": "live",
        "phase_remaining_ticks": 6900, "round_wins": [0, 0],
        "alive_by_team": [5, 5], "attack_team": 0,
        "period": "regulation", "overtime_number": 0, "win_target": 13,
        "buy_deadline_tick": 1860, "loss_level": 1,
        "me": {
            "x": x, "y": y, "z": 0.0, "yaw": yaw, "pitch": 0.0,
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

    def test_open_floor_moves_forward(self):
        obs = observation(0.0, 0.0, 0.0, round_index=0, tick=0,
                          match_map=OPEN_MAP, seat=0)
        action = agent.act(obs)
        self.assertAlmostEqual(action["move_forward"], 0.75)
        self.assertAlmostEqual(action["yaw_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()

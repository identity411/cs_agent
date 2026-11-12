#!/usr/bin/env python3
"""Repeatable nav-level simulator for the collected AGX static map.

This uses the platform's own coordinate system and nav graph, not the
original CS2 .nav file.  It is a kinematic test: no collision mesh, but it
can inject known badcase areas as circular obstacles and check whether the
current agent reaches the site, plants, reroutes, or stalls.

Usage:
  python3 scripts/simulate_nav.py
  python3 scripts/simulate_nav.py --legacy-stuck
  python3 scripts/simulate_nav.py --site A --round 13 --obstacle 83.4,88.2,1.8
  python3 scripts/simulate_nav.py --carrying --site B --round 14
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_movement import observation  # noqa: E402

DEFAULT_MAP = ROOT / "tests" / "fixtures" / "dust2_static.json"
DEFAULT_AGENT = ROOT / "agent.py"
# v0.02 seat 3 T-side stall; used only when --legacy-stuck is passed.
LEGACY_STUCK = (83.4, 88.2, 1.8)


def load_agent(path: Path):
    spec = importlib.util.spec_from_file_location("sim_agent", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def parse_obstacle(value: str):
    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("obstacle must be x,y,radius")
    return tuple(float(part) for part in parts)


def parse_point(value: str):
    parts = value.split(",")
    if len(parts) not in (2, 3):
        raise argparse.ArgumentTypeError("point must be x,y[,z]")
    return tuple(float(part) for part in parts)


def simulate(module, map_row: dict, site_id: str, round_index: int,
             seat: int, carrying: bool, obstacles: tuple,
             max_steps: int, side: str = "attack",
             start: tuple | None = None) -> dict:
    module.init({})
    spawns = map_row["spawn_pads_by_side"][side]
    if start is not None:
        pos = [float(start[0]), float(start[1]),
               float(start[2] if len(start) > 2 else spawns[0][2])]
    else:
        pos = [sum(p[0] for p in spawns) / len(spawns),
               sum(p[1] for p in spawns) / len(spawns),
               spawns[0][2]]
    yaw, tick = 0.0, 400
    obs = observation(pos[0], pos[1], yaw, round_index=round_index,
                      tick=tick, match_map=map_row, seat=seat, z=pos[2])
    obs["side"] = side
    obs["team"] = 0
    obs["attack_team"] = 0 if side == "attack" else 1
    obs["me"]["carrying_bomb"] = carrying and side == "attack"
    obs["me"]["stamina"] = 1.0
    obs["bomb"] = {"state": "carried", "fuse_end_tick": None,
                   "site": site_id}
    site = next(item for item in map_row["sites"]
                if item["id"] == site_id)
    last, still = list(pos), 0
    status, steps = "timeout", max_steps
    for step in range(max_steps):
        if step:
            obs.pop("map", None)  # map is sent only on the first observation
        obs["match_tick"] = tick
        obs["round_tick"] = tick
        obs["me"]["x"], obs["me"]["y"], obs["me"]["z"] = pos
        obs["me"]["yaw"] = yaw
        action = module.act(obs)
        if action.get("use") == "plant":
            status, steps = "plant", step
            break
        yaw += float(action.get("yaw_rate") or 0.0) * 0.20
        if action.get("sprint"):
            speed = 4.2
        elif action.get("walk", True):
            speed = 1.9
        else:
            speed = 3.0
        forward = float(action.get("move_forward") or 0.0)
        right = float(action.get("move_right") or 0.0)
        vx = forward * math.cos(yaw) + right * math.sin(yaw)
        vy = -forward * math.sin(yaw) + right * math.cos(yaw)
        next_x = pos[0] + vx * speed * 0.05
        next_y = pos[1] + vy * speed * 0.05
        blocked = any(
            math.hypot(next_x - ox, next_y - oy) < radius
            for ox, oy, radius in obstacles)
        if not blocked:
            pos[0], pos[1] = next_x, next_y
        player = module._player
        if (player.path
                and math.hypot(pos[0] - player.path[0][0],
                               pos[1] - player.path[0][1]) < 2.5):
            # Nav-level stand-in for ramps/stairs: follow the waypoint's z.
            pos[2] = player.path[0][2]
        tick += 3
        if math.hypot(pos[0] - site["center"][0],
                      pos[1] - site["center"][1]) < site["radius"]:
            status, steps = "reached", step
            break
        if math.hypot(pos[0] - last[0], pos[1] - last[1]) < 0.03:
            still += 1
        else:
            still = 0
        last = list(pos)
        if still > 600:
            status, steps = "stuck", step
            break
    player = module._player
    return {
        "site": site_id,
        "round": round_index,
        "seat": seat,
        "carrying": carrying,
        "status": status,
        "steps": steps,
        "seconds": round(steps * 0.05, 1),
        "position": [round(pos[0], 1), round(pos[1], 1)],
        "goal": [round(value, 1) for value in player.goal],
        "route": getattr(player, "attack_route_name", None),
        "blocked_nodes": len(getattr(player, "blocked", ())),
        "penalized_edges": len(getattr(player, "edge_penalty", {})),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP,
                        help="collected static.json")
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT,
                        help="agent.py or a submission snapshot")
    parser.add_argument("--side", choices=["attack", "defend"],
                        default="attack",
                        help="attack (T) or defend (CT)")
    parser.add_argument("--site", choices=["A", "B"],
                        help="site to attack/defend; default = legacy rounds")
    parser.add_argument("--round", type=int, action="append",
                        help="round index; repeatable")
    parser.add_argument("--seat", type=int, default=3)
    parser.add_argument("--carrying", action="store_true",
                        help="simulate the bomb carrier")
    parser.add_argument("--obstacle", action="append", type=parse_obstacle,
                        default=[], metavar="X,Y,R",
                        help="inject a circular obstacle; repeatable")
    parser.add_argument("--legacy-stuck", action="store_true",
                        help="inject the v0.02 T-side stall area")
    parser.add_argument("--start", type=parse_point,
                        metavar="X,Y[,Z]",
                        help="optional starting position, e.g. 167.37,60.24,20.13")
    parser.add_argument("--max-steps", type=int, default=2400,
                        help="action steps at 20 Hz (default 2400 = 120 s)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    map_row = json.loads(args.map.read_text()).get("map")
    if not map_row:
        raise SystemExit("static.json did not contain a map object")
    module = load_agent(args.agent)
    obstacles = list(args.obstacle)
    if args.legacy_stuck:
        obstacles.append(LEGACY_STUCK)
    if args.site:
        cases = [(args.site, r) for r in (args.round or [13])]
    elif args.side == "defend":
        # Known CT cases: R2 site-center hold + early CT rounds.
        cases = [("B", 2), ("A", 0), ("B", 2), ("A", 3)]
        if args.round:
            cases = [(site, r) for site, _ in cases for r in args.round]
    else:
        # The rounds where v0.02 seat 3 never reached A/B.
        cases = [("A", 13), ("B", 14), ("A", 15), ("A", 17), ("A", 19)]
        if args.round:
            cases = [(site, r) for site, _ in cases for r in args.round]
    start = None
    if args.start:
        if len(args.start) == 2:
            start = (args.start[0], args.start[1])
        else:
            start = tuple(args.start[:3])[:3]
    rows = []
    for site, round_index in cases:
        rows.append(simulate(module, map_row, site, round_index, args.seat,
                             args.carrying, tuple(obstacles),
                             args.max_steps, side=args.side,
                             start=start))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"static: {args.map}")
    print(f"obstacles: {obstacles or 'none'}  (nav-level kinematic sim, "
          "no collision mesh)")
    print(f"{'site':4s} {'round':>5s} {'carry':>5s} {'status':8s} "
          f"{'steps':>5s} {'sec':>6s} {'route':10s} {'blocked':>7s}")
    for row in rows:
        print(f"{row['site']:4s} {row['round']:5d} "
              f"{str(row['carrying']):>5s} {row['status']:8s} "
              f"{row['steps']:5d} {row['seconds']:6.1f} "
              f"{str(row['route']):10s} {row['blocked_nodes']:7d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

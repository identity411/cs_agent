#!/usr/bin/env python3
"""Reproduce the R2 dust2 site-center hold with the public map parameters.

This is a code-level reproduction: it feeds the public R2 frame values into
the v0.02 snapshot and the current agent.  It does not run the collision
world; a real match is still the final check.

Usage:
  python3 scripts/reproduce_r2_patrol.py
  python3 scripts/reproduce_r2_patrol.py --map path/to/static.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = (ROOT / "data" / "accounts" / "main" / "matches"
               / "36cf9b6c-78ec-469f-b008-daca03bf0e73" / "static.json")
OLD = ROOT / "docs" / "submissions" / "1112-v0.02" / "agent.py"
NEW = ROOT / "agent.py"


def load_agent(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def observation(map_row: dict) -> dict:
    """Public R2 frame at tick 21000: seat 3 at dust2 B center."""
    return {
        "rules_version": "rsi-fps-5.5", "seat": 3, "team": 0,
        "side": "defend", "role": 0, "match_tick": 21000,
        "round_index": 2, "round_tick": 5880, "phase": "live",
        "phase_remaining_ticks": 2000, "round_wins": [1, 1],
        "alive_by_team": [5, 5], "attack_team": 1,
        "period": "regulation", "overtime_number": 0, "win_target": 13,
        "buy_deadline_tick": 1860, "loss_level": 1,
        "me": {
            "x": 167.37, "y": 60.24, "z": 20.13,
            "yaw": 0.431, "pitch": 0.0, "vx": 0.0, "vy": 0.0, "vz": 0.0,
            "crouch": False, "lean_offset": 0.0, "grounded": True,
            "sprinting": False, "stamina": 100.0, "hp": 100.0,
            "armor": 100.0, "helmet": False, "alive": True,
            "blind_ticks": 0, "cash": 150,
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
            "pickup_ready_tick": 0, "switch_until": 15492,
            "throw_ready": 0, "ads_progress": 0.0, "slots": {},
            "throwables": [], "throwable_kinds": [], "ammo": 20,
            "reload": 0.0, "recoil": 0.0, "weapon_status": "ready",
            "walk": False, "quiet": False, "duck": False,
            "zoom_level": 0, "ladder_id": None,
            "movement_mode": "ground", "shot_ready": 0,
        },
        "teammates": [], "visible": [], "sounds": [], "heard": [],
        "bomb": {"state": "carried", "fuse_end_tick": None},
        "world_items": [], "messages": [], "receipts": [],
        "map_id": "dust2-cs2-v54", "static_schema_hash": "public",
        "map": map_row,
    }


def action_summary(action: dict) -> dict:
    return {key: action.get(key) for key in
            ("weapon_slot", "move_forward", "move_right", "yaw_rate",
             "jump", "use")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--old", type=Path, default=OLD)
    parser.add_argument("--new", type=Path, default=NEW)
    args = parser.parse_args()

    if not args.map.is_file():
        raise SystemExit(f"missing map parameters: {args.map}\n"
                         "Run `agx-match-query collect --replays` first.")
    static = json.loads(args.map.read_text())
    map_row = static.get("map", static)
    obs = observation(map_row)

    for label, path, module_name in (
            ("v0.02", args.old, "agent_v002"),
            ("current", args.new, "agent_current")):
        module = load_agent(module_name, path)
        module.init({})
        action = module.act(obs)
        player = module._player
        print(f"\n=== {label} ===")
        print("goal:", player.goal)
        print("path:", player.path[:4])
        print("patrol_index:", getattr(player, "patrol_index", "n/a"))
        print("action:", action_summary(action))

    # Current code: hold the same position; the patrol watchdog should
    # advance after ~2 s instead of holding the same coordinate forever.
    module = load_agent("agent_current_loop", args.new)
    module.init({})
    for step in range(60):
        tick_obs = json.loads(json.dumps(obs))
        tick_obs["match_tick"] = 21000 + step * 3
        if step:
            tick_obs.pop("map", None)
        module.act(tick_obs)
    print("\n=== current after 60 fixed-position ticks ===")
    print("patrol_index:", module._player.patrol_index)
    print("goal:", module._player.goal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

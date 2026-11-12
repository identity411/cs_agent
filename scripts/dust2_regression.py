"""Run fixed Dust2 navigation checks and inspect sampled position traces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_MAP = ROOT / "tests" / "fixtures" / "dust2_static.json"


def load_observation_builder():
    spec = importlib.util.spec_from_file_location(
        "dust2_observation_builder", ROOT / "scripts" / "reproduce_r2_patrol.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observation


def load_fixed_map(path):
    static = json.loads(Path(path).read_text())
    row = static.get("map", static)
    if row.get("id") != "dust2-cs2-v54" or not row.get("nav"):
        raise ValueError("expected a dust2-cs2-v54 public map")
    return row


def probe_spawns(agent_path, map_row):
    spec = importlib.util.spec_from_file_location("dust2_probe_agent", agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_observation = load_observation_builder()
    results = []
    for side, pads in map_row["spawns"].items():
        for index, pad in enumerate(pads):
            module.init({})
            obs = build_observation(map_row)
            obs.update(seat=index + (0 if side == "T" else 5),
                       team=0 if side == "T" else 1,
                       side="attack" if side == "T" else "defend",
                       attack_team=0, round_index=0, match_tick=400,
                       round_tick=400)
            pos = pad["position"]
            obs["me"].update(x=pos[0], y=pos[1], z=pos[2],
                             yaw=pad["yaw"])
            action = module.act(obs)
            moving = any(abs(action.get(key, 0)) > 0.01 for key in
                         ("move_forward", "move_right", "yaw_rate"))
            results.append({"side": side, "pad": index,
                            "ok": bool(moving and module._player.path),
                            "goal": module._player.goal,
                            "first_waypoint": (module._player.path[0]
                                               if module._player.path else None)})
    return results


def detect_traps(samples, *, min_ticks=300, radius=1.5):
    """Find sustained confinement in a sampled trace (60 ticks/second)."""
    samples = sorted(samples, key=lambda row: row["tick"])
    events = []
    i = 0
    while i < len(samples):
        start = samples[i]
        if not start.get("alive", True):
            i += 1
            continue
        j = i + 1
        travel = 0.0
        while j < len(samples):
            previous, current = samples[j - 1], samples[j]
            if (not current.get("alive", True)
                    or current["tick"] - previous["tick"] > 120
                    or math.dist(current["pos"][:2], start["pos"][:2]) > radius):
                break
            travel += math.dist(previous["pos"][:2], current["pos"][:2])
            j += 1
        if j > i + 1 and samples[j - 1]["tick"] - start["tick"] >= min_ticks:
            window = samples[i:j]
            spread = max(math.dist(row["pos"][:2], start["pos"][:2])
                         for row in window)
            events.append({
                "kind": "stationary" if spread <= 0.25 else "local_loop",
                "start_tick": start["tick"],
                "end_tick": window[-1]["tick"],
                "center": start["pos"],
                "max_radius": round(spread, 2),
                "travel": round(travel, 2),
            })
            i = j
        else:
            i += 1
    return events


def load_trace(path, seat=None):
    raw = Path(path).read_text().strip()
    rows = (json.loads(raw) if raw.startswith("[") else
            [json.loads(line) for line in raw.splitlines() if line.strip()])
    by_round = {}
    for row in rows:
        if row.get("phase") not in (None, "live"):
            continue
        if "players" in row:
            if seat is None:
                raise ValueError("--seat is required for replay frames")
            player = row["players"][seat]
            sample = {"tick": row["match_tick"],
                      "pos": [player["x"], player["y"], player["z"]],
                      "alive": player.get("alive", True)}
        else:
            sample = row
        by_round.setdefault(row.get("round_index", 0), []).append(sample)
    return [by_round[key] for key in sorted(by_round)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", type=Path, default=ROOT / "agent.py")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--trace", type=Path,
                        help="replay frames JSONL or sample JSON array")
    parser.add_argument("--seat", type=int,
                        help="player seat when --trace contains replay frames")
    args = parser.parse_args()
    map_row = load_fixed_map(args.map)
    spawns = probe_spawns(args.agent, map_row)
    traps = []
    if args.trace:
        for round_samples in load_trace(args.trace, seat=args.seat):
            traps.extend(detect_traps(round_samples))
    print(json.dumps({"map_id": map_row["id"],
                      "spawns_checked": len(spawns),
                      "spawn_failures": [row for row in spawns if not row["ok"]],
                      "suspected_traps": traps}, indent=2))
    return 1 if traps or any(not row["ok"] for row in spawns) else 0


if __name__ == "__main__":
    raise SystemExit(main())

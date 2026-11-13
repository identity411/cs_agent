"""Extract site-to-site CT rotations from CS2 professional demos.

Requires demoparser2. Source demo coordinates are Valve inches; the FPS map
fixtures use the same mesh with swapped horizontal axes and a 100 m offset.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


METERS_PER_INCH = 0.0254


def source_to_platform(x, y, z):
    return (round(100 + y * METERS_PER_INCH, 4),
            round(100 + x * METERS_PER_INCH, 4),
            round(20 + z * METERS_PER_INCH, 4))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def classify_route(frames, sites, target_site):
    if len(frames) < 8:
        return None
    origin_site = "B" if target_site == "A" else "A"
    origin, target = sites[origin_site], sites[target_site]
    first = next((i for i, f in enumerate(frames)
                  if distance((f["x"], f["y"]), origin) <= 24), None)
    if first is None:
        return None
    last = next((i for i in range(len(frames) - 1, first, -1)
                 if distance((frames[i]["x"], frames[i]["y"]), target) <= 24), None)
    if last is None or last - first < 7:
        return None
    route = frames[first:last + 1]
    if distance((route[0]["x"], route[0]["y"]),
                (route[-1]["x"], route[-1]["y"])) < 25:
        return None
    forward = []
    for a, b in zip(route, route[1:]):
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        if math.hypot(dx, dy) < 0.25:
            continue
        # CS yaw is measured from source +X toward source +Y.
        travel_yaw = math.degrees(math.atan2(dx, dy))
        forward.append(angle_difference(a["yaw"], travel_yaw) <= 85
                     and abs(a["pitch"]) <= 35)
    if not forward:
        return None
    return {"direction": f"{origin_site}_to_{target_site}",
            "start_tick": int(route[0]["tick"]),
            "end_tick": int(route[-1]["tick"]),
            "aim_forward_fraction": round(sum(forward) / len(forward), 3),
            "frames": route}


def extract(demo_path, map_path, sample_step=4):
    from demoparser2 import DemoParser

    fixture = json.loads(Path(map_path).read_text())["map"]
    sites = {site["id"]: site["center"][:2] for site in fixture["sites"]}
    parser = DemoParser(str(demo_path))
    header = parser.parse_header()
    player_names = {str(row.steamid): row.name
                    for row in parser.parse_player_info().itertuples(index=False)}
    expected = "de_" + fixture["id"].split("-")[0]
    if header["map_name"] != expected:
        raise ValueError(f"demo map {header['map_name']} != fixture {expected}")
    ends = parser.parse_event("round_end").sort_values("tick")
    plants = parser.parse_event("bomb_planted").sort_values("tick")
    starts = parser.parse_event("round_freeze_end").sort_values("tick")
    last_tick = int(ends["tick"].max())
    tick_samples = list(range(0, last_tick + 1, sample_step))
    ticks = parser.parse_ticks(
        ["X", "Y", "Z", "pitch", "yaw", "team_num", "is_alive"],
        ticks=tick_samples)
    ticks = ticks[(ticks.team_num == 3) & ticks.is_alive]
    by_player = defaultdict(list)
    for row in ticks.itertuples(index=False):
        x, y, z = source_to_platform(row.X, row.Y, row.Z)
        by_player[row.steamid].append({"tick": int(row.tick), "x": x,
                                       "y": y, "z": z,
                                       "yaw": round(float(row.yaw), 2),
                                       "pitch": round(float(row.pitch), 2)})

    candidates = []
    previous_end = 0
    for end in ends.itertuples(index=False):
        round_number = int(end.round)
        round_end = int(end.tick)
        if round_number <= 0:
            previous_end = round_end
            continue
        round_starts = starts[(starts.tick > previous_end) &
                              (starts.tick < round_end)]
        round_start = int(round_starts.tick.iloc[0]) if len(round_starts) else previous_end
        round_plants = plants[(plants.tick > round_start) &
                              (plants.tick < round_end)]
        if not len(round_plants):
            previous_end = round_end
            continue
        plant_tick = int(round_plants.tick.iloc[0])
        plant_frames = parser.parse_ticks(["X", "Y", "Z"], ticks=[plant_tick])
        planter = str(round_plants.user_steamid.iloc[0])
        plant_pos = plant_frames[plant_frames.steamid.astype(str) == planter]
        if not len(plant_pos):
            previous_end = round_end
            continue
        pos = source_to_platform(*plant_pos.iloc[0][["X", "Y", "Z"]])
        target = min(sites, key=lambda s: distance(pos, sites[s]))
        for steamid, all_frames in by_player.items():
            window = [f for f in all_frames
                      if max(round_start, plant_tick - 20 * 64) <= f["tick"]
                      <= min(round_end, plant_tick + 45 * 64)]
            route = classify_route(window, sites, target)
            if route:
                route.update({"round": round_number, "steamid": str(steamid),
                              "player": player_names.get(str(steamid), "unknown"),
                              "plant_tick": plant_tick, "target_site": target,
                              "map_id": fixture["id"]})
                candidates.append(route)
        previous_end = round_end
    candidates.sort(key=lambda r: (-r["aim_forward_fraction"],
                                   r["direction"], r["round"]))
    return {"source_demo": str(demo_path), "demo_header": header,
            "map_id": fixture["id"], "geometry_hash": fixture["geometry_hash"],
            "sample_step_ticks": sample_step, "sites": sites,
            "candidates": candidates}


def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument("demo", type=Path)
    argp.add_argument("map_fixture", type=Path)
    argp.add_argument("output", type=Path)
    args = argp.parse_args()
    result = extract(args.demo, args.map_fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, separators=(",", ":")))
    print(json.dumps({"map": result["map_id"],
                      "candidates": len(result["candidates"]),
                      "by_direction": {direction: sum(
                          x["direction"] == direction for x in result["candidates"])
                          for direction in ("A_to_B", "B_to_A")}}))


if __name__ == "__main__":
    main()

"""Compile extracted professional CT rotations into a small agent module."""

import argparse
import json
import math
from pathlib import Path


def convert_frame(frame):
    return (round(frame["x"], 3), round(frame["y"], 3),
            round(frame["z"], 3),
            round(math.radians(frame["yaw"] - 90), 4),
            round(-math.radians(frame["pitch"]), 4))


def compile_routes(data, fixture):
    if (data["map_id"] != fixture["id"]
            or data["geometry_hash"] != fixture["geometry_hash"]):
        raise ValueError("professional demo route map identity mismatch")
    result = {}
    for direction in ("A_to_B", "B_to_A"):
        candidates = sorted(
            (c for c in data["candidates"]
             if c["direction"] == direction and c["aim_forward_fraction"] >= 0.8),
            key=lambda c: -c["aim_forward_fraction"])[:3]
        compiled = []
        for candidate in candidates:
            frames = []
            for source in candidate["frames"]:
                frame = convert_frame(source)
                if frames:
                    prev = frames[-1]
                    gap = math.hypot(frame[0] - prev[0], frame[1] - prev[1])
                    aim_change = abs((frame[3] - prev[3] + math.pi)
                                     % (2 * math.pi) - math.pi)
                    if gap < 0.8 and aim_change < 0.25:
                        continue
                frames.append(frame)
            last = convert_frame(candidate["frames"][-1])
            if frames[-1] != last:
                frames.append(last)
            if len(frames) >= 10:
                compiled.append({"player": candidate["player"],
                                 "round": candidate["round"],
                                 "aim_forward_fraction": candidate["aim_forward_fraction"],
                                 "frames": tuple(frames)})
        if not compiled:
            raise ValueError(f"no suitable {direction} route")
        result[direction] = tuple(compiled)
    return result


def build(dust2_data, dust2_fixture, mirage_data, mirage_fixture, output):
    maps = {}
    for data_path, fixture_path in ((dust2_data, dust2_fixture),
                                    (mirage_data, mirage_fixture)):
        data = json.loads(Path(data_path).read_text())
        fixture = json.loads(Path(fixture_path).read_text())["map"]
        maps[fixture["id"]] = {
            "hash": fixture["geometry_hash"],
            "routes": compile_routes(data, fixture),
        }
    lines = ['"""Professional CS2 CT retakes, compiled from match 2393178."""',
             "MAPS = {"]
    for map_id, item in maps.items():
        lines.append(f"    {map_id!r}: {{'hash': {item['hash']!r}, 'routes': {{")
        for direction, routes in item["routes"].items():
            lines.append(f"        {direction!r}: (")
            for route in routes:
                lines.append("            {")
                for key in ("player", "round", "aim_forward_fraction"):
                    lines.append(f"                {key!r}: {route[key]!r},")
                lines.append("                'frames': (")
                lines.extend(f"                    {frame!r},"
                             for frame in route["frames"])
                lines.append("                ),")
                lines.append("            },")
            lines.append("        ),")
        lines.append("    }},")
    lines.append("}")
    Path(output).write_text("\n".join(lines) + "\n")
    return maps


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("dust2_data", type=Path)
    p.add_argument("dust2_fixture", type=Path)
    p.add_argument("mirage_data", type=Path)
    p.add_argument("mirage_fixture", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    result = build(a.dust2_data, a.dust2_fixture, a.mirage_data,
                   a.mirage_fixture, a.output)
    print({name: {d: len(v) for d, v in item["routes"].items()}
           for name, item in result.items()})

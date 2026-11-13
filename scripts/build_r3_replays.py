"""Compile fixed-version R3 walklab recordings for the FPS agent."""

import argparse
import hashlib
import json
import math
from pathlib import Path

KEY_BITS = {"KeyW": 1, "KeyA": 2, "KeyS": 4, "KeyD": 8,
            "ShiftLeft": 16, "Space": 32}
CARRIER_HANDOFF_DISTANCE = 12.0


def compile_recording(source, output, static_map, site_id):
    raw = source.read_bytes()
    data = json.loads(raw)
    map_data = static_map["map"]
    if (data.get("format") != "walklab-v2"
            or data.get("mapId") != map_data["id"]
            or data.get("mapHash") != map_data["geometry_hash"]
            or data.get("hz") != 20):
        raise ValueError("recording map identity or format mismatch")
    site = next((item for item in map_data["sites"]
                 if item["id"] == site_id), None)
    if site is None:
        raise ValueError("unknown plant site")
    rows = []
    for expected_tick, frame in enumerate(data["frames"]):
        if frame["tick"] != expected_tick:
            raise ValueError("recording ticks are not contiguous")
        values = [*frame["position"], frame["yaw"], frame["pitch"]]
        if len(values) != 5 or not all(math.isfinite(value) for value in values):
            raise ValueError("nonfinite or incomplete frame")
        keys = frame["keys"]
        if any(key not in KEY_BITS for key in keys):
            raise ValueError("unsupported recording key")
        mask = sum(KEY_BITS[key] for key in set(keys))
        rows.append(tuple(round(value, 4) for value in values) + (mask,))
    if len(rows) < 2:
        raise ValueError("recording is too short")
    center = site["center"]
    cutoff = next((index for index, row in enumerate(rows)
                   if math.hypot(row[0] - center[0],
                                 row[1] - center[1]) <= CARRIER_HANDOFF_DISTANCE),
                  None)
    if cutoff is None:
        raise ValueError("recording never approaches the plant site")
    lines = [f'"""{map_data["id"]} walk, compiled from {source.name}."""',
             f"SOURCE_SHA256 = {hashlib.sha256(raw).hexdigest()!r}",
             f"MAP_ID = {map_data['id']!r}",
             f"MAP_HASH = {map_data['geometry_hash']!r}",
             f"SITE = {site_id!r}",
             f"CARRIER_CUTOFF = {cutoff}",
             "ROUTE = ("]
    lines.extend(f"    {row!r}," for row in rows)
    lines.append(")")
    output.write_text("\n".join(lines) + "\n")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("static_map", type=Path)
    parser.add_argument("site", choices=("A", "B"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.static_map.read_text())
    print(f"compiled {compile_recording(args.source, args.output, fixture, args.site)} frames")

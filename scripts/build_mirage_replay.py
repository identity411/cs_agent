"""Compile a fixed-version Mirage walklab recording for the Python agent."""

import argparse
import hashlib
import json
import math
from pathlib import Path

KEY_BITS = {"KeyW": 1, "KeyA": 2, "KeyS": 4, "KeyD": 8,
            "ShiftLeft": 16}
MAP_ID = "mirage-cs2-v54"
MAP_HASH = "ef9384945046620f3f61ac579ae91f0beac8d5541c871e1996faf7a36f2e39db"


def compile_recording(source, output):
    raw = source.read_bytes()
    data = json.loads(raw)
    if (data.get("format") != "walklab-v2" or data.get("mapId") != MAP_ID
            or data.get("mapHash") != MAP_HASH or data.get("hz") != 20):
        raise ValueError("recording map or format does not match Mirage")
    rows = []
    for expected_tick, frame in enumerate(data["frames"]):
        if frame["tick"] != expected_tick:
            raise ValueError("recording ticks are not contiguous")
        values = [*frame["position"], frame["yaw"], frame["pitch"]]
        if len(values) != 5 or not all(math.isfinite(value) for value in values):
            raise ValueError("nonfinite or incomplete recording frame")
        keys = frame["keys"]
        if any(key not in KEY_BITS for key in keys):
            raise ValueError("unsupported recording key")
        mask = sum(KEY_BITS[key] for key in set(keys))
        rows.append(tuple(round(value, 4) for value in values) + (mask,))
    if len(rows) < 2:
        raise ValueError("recording is too short")
    lines = [f'"""Mirage user walk, compiled from {source.name}."""',
             f"SOURCE_SHA256 = {hashlib.sha256(raw).hexdigest()!r}",
             f"MAP_ID = {MAP_ID!r}", f"MAP_HASH = {MAP_HASH!r}", "ROUTE = ("]
    lines.extend(f"    {row!r}," for row in rows)
    lines.append(")")
    output.write_text("\n".join(lines) + "\n")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"compiled {compile_recording(args.source, args.output)} frames")

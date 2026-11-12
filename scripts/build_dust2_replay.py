"""Compile a walklab recording into a compact, submission-ready route."""

import argparse
import hashlib
import json
import math
from pathlib import Path


KEY_BITS = {"KeyW": 1, "KeyA": 2, "KeyS": 4, "KeyD": 8,
            "ShiftLeft": 16}
MAP_ID = "dust2-cs2-v54"
MAP_HASH = "b0c308526d55e56e3a50a5ecf9bdd1b70a02daf560a9a8157931f3b340fb8d66"


def compile_recording(source, output):
    raw = source.read_bytes()
    data = json.loads(raw)
    if (data.get("format") != "dust2-walk-v1" or data.get("mapId") != MAP_ID
            or data.get("mapHash") != MAP_HASH or data.get("hz") != 20):
        raise ValueError("recording map or format does not match Dust2")
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
    lines = ["\"\"\"Dust2 user walk, compiled from dust2-walk-v1.\"\"\"",
             f"SOURCE_SHA256 = {hashlib.sha256(raw).hexdigest()!r}",
             f"MAP_HASH = {MAP_HASH!r}", "ROUTE = ("]
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

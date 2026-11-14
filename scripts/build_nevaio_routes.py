"""Compile user-recorded Nevaio T attacks and CT routes from Walklab JSON."""

import argparse
import base64
import hashlib
import json
import math
import zlib
from pathlib import Path

from scripts.build_r3_replays import KEY_BITS


CARRIER_HANDOFF_DISTANCE = 12.0


def _recording(path, map_id, map_hash):
    raw = path.read_bytes()
    data = json.loads(raw)
    if (data.get("format") != "walklab-v2"
            or data.get("mapId") != map_id
            or data.get("mapHash") != map_hash
            or data.get("hz") != 20):
        raise ValueError(f"invalid recording identity: {path.name}")
    rows = []
    for tick, frame in enumerate(data.get("frames", ())):
        if frame.get("tick") != tick:
            raise ValueError(f"noncontiguous ticks: {path.name}")
        values = [*(frame.get("position") or ()), frame.get("yaw"),
                  frame.get("pitch")]
        if (len(values) != 5
                or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                       for v in values)):
            raise ValueError(f"invalid pose: {path.name}")
        keys = frame.get("keys")
        if not isinstance(keys, list) or any(key not in KEY_BITS for key in keys):
            raise ValueError(f"invalid keys: {path.name}")
        rows.append(tuple(round(v, 4) for v in values)
                    + (sum(KEY_BITS[key] for key in set(keys)),))
    if len(rows) < 2:
        raise ValueError(f"too few frames: {path.name}")
    travelled = sum(math.dist(a[:2], b[:2]) for a, b in zip(rows, rows[1:]))
    if travelled < 1.0:
        raise ValueError(f"recording does not move: {path.name}")
    return tuple(rows), hashlib.sha256(raw).hexdigest()


def _fixture(manifest_path, static_map):
    manifest = json.loads(manifest_path.read_text())
    map_data = static_map["map"]
    if (manifest["mapId"] != map_data["id"]
            or manifest["mapHash"] != map_data["geometry_hash"]):
        raise ValueError("Nevaio fixture hash mismatch")
    return manifest, map_data


def _source_reader(manifest_path):
    seen = set()

    def read(name):
        if name in seen or Path(name).name != name:
            raise ValueError(f"duplicate or unsafe source: {name}")
        seen.add(name)
        return manifest_path.parent / name

    return read


def compile_t_manifest(manifest_path, static_map):
    manifest, map_data = _fixture(manifest_path, static_map)
    sites = {site["id"]: site["center"] for site in map_data["sites"]}
    source = _source_reader(manifest_path)
    attacks = []
    names = set()
    for item in manifest["attacks"]:
        if item["name"] in names or item["site"] not in sites:
            raise ValueError(f"invalid attack route: {item['name']}")
        names.add(item["name"])
        frames, sha = _recording(source(item["source"]),
                                 map_data["id"], map_data["geometry_hash"])
        center = sites[item["site"]]
        cutoff = next((index for index, row in enumerate(frames)
                       if math.dist(row[:2], center[:2])
                       <= CARRIER_HANDOFF_DISTANCE), None)
        if cutoff is None:
            raise ValueError(f"attack never approaches its plant site: {item['name']}")
        if math.dist(frames[-1][:2], center[:2]) > CARRIER_HANDOFF_DISTANCE:
            raise ValueError(f"attack ends outside its plant site: {item['name']}")
        attacks.append({"name": item["name"], "site": item["site"],
                        "via": item["via"], "carrier_cutoff": cutoff,
                        "terminal_hold": False, "source": item["source"],
                        "sha256": sha, "frames": frames})
    if not attacks:
        raise ValueError("T manifest has no attacks")
    return {"map_id": map_data["id"], "map_hash": map_data["geometry_hash"],
            "attacks": attacks}


def compile_ct_manifest(manifest_path, static_map):
    manifest, map_data = _fixture(manifest_path, static_map)
    sites = {site["id"]: site["center"] for site in map_data["sites"]}
    source = _source_reader(manifest_path)
    pairs = []
    names = set()
    for item in manifest["pairs"]:
        if item["name"] in names or item["site"] not in sites:
            raise ValueError(f"invalid CT pair: {item['name']}")
        names.add(item["name"])
        opening, open_sha = _recording(source(item["opening"]),
                                       map_data["id"],
                                       map_data["geometry_hash"])
        center = sites[item["site"]]
        if math.dist(opening[-1][:2], center[:2]) > CARRIER_HANDOFF_DISTANCE:
            raise ValueError(f"CT opening ends outside its site: {item['name']}")
        if item.get("hold") is None:
            # Older Walklab exports only contain the opening.  The chosen
            # match behavior is a static final-pose hold, not a fabricated
            # hold recording: pin the last recorded position and view.
            if item.get("holdMode") != "final_pose":
                raise ValueError(f"missing CT hold mode: {item['name']}")
            hold, hold_sha, hold_mode = (opening[-1],), None, "final_pose"
        else:
            hold, hold_sha = _recording(source(item["hold"]),
                                        map_data["id"],
                                        map_data["geometry_hash"])
            if (math.dist(opening[-1][:3], hold[0][:3]) > 0.2
                    or math.dist(hold[-1][:3], hold[0][:3]) > 1.0):
                raise ValueError(f"disconnected CT pair: {item['name']}")
            hold_mode = "recorded"
        pairs.append({"name": item["name"], "site": item["site"],
                      "via": item["via"], "holdMode": hold_mode,
                      "sha256": {"opening": open_sha, "hold": hold_sha},
                      "opening": opening, "hold": hold})
    retakes = {}
    for item in manifest["retakes"]:
        origin, target = item["origin"], item["target"]
        if (origin not in sites or target not in sites
                or origin == target):
            raise ValueError(f"invalid retake direction: {item['name']}")
        frames, sha = _recording(source(item["source"]),
                                 map_data["id"], map_data["geometry_hash"])
        if (math.dist(frames[0][:2], sites[origin][:2])
                > CARRIER_HANDOFF_DISTANCE
                or math.dist(frames[-1][:2], sites[target][:2])
                > CARRIER_HANDOFF_DISTANCE):
            raise ValueError(f"retake does not span its sites: {item['name']}")
        direction = f"{origin}_to_{target}"
        retakes.setdefault(direction, []).append(
            {"name": item["name"], "origin": origin, "target": target,
             "via": item["via"], "sha256": sha, "frames": frames})
    if not pairs or not retakes:
        raise ValueError("CT manifest needs pairs and retakes")
    return {"map_id": map_data["id"], "map_hash": map_data["geometry_hash"],
            "pairs": pairs, "retakes": retakes}


def _encode_frames(frames):
    raw = json.dumps([list(frame) for frame in frames],
                     separators=(",", ":")).encode("ascii")
    return base64.b85encode(zlib.compress(raw, 9)).decode("ascii")


def _payload_lines(payload, indent):
    return [f'{indent}"{payload[i:i + 96]}"'
            for i in range(0, len(payload), 96)]


def _write_frames(lines, key, frames, indent="        "):
    lines.append(f"{indent}{key!r}: _frames(")
    lines.extend(_payload_lines(_encode_frames(frames), indent + "    "))
    lines.append(f"{indent}),")


def write_t_module(compiled, output):
    lines = ['"""User-recorded Nevaio T routes; generated by build_nevaio_routes.py."""',
             "import base64",
             "import json",
             "import zlib",
             "",
             "",
             "def _frames(payload):",
             "    data = zlib.decompress(base64.b85decode(payload))",
             "    return tuple(tuple(row) for row in json.loads(data))",
             "",
             "",
             f"MAP_ID = {compiled['map_id']!r}",
             f"MAP_HASH = {compiled['map_hash']!r}",
             "ATTACKS = ("]
    for route in compiled["attacks"]:
        lines.append("    {")
        for key in ("name", "site", "via", "carrier_cutoff",
                    "terminal_hold", "source", "sha256"):
            lines.append(f"        {key!r}: {route[key]!r},")
        _write_frames(lines, "frames", route["frames"])
        lines.append("    },")
    lines.extend((")", "POSTPLANT = {}"))
    output.write_text("\n".join(lines) + "\n")


def write_ct_module(compiled, output):
    lines = ['"""User-recorded Nevaio CT routes; generated by build_nevaio_routes.py."""',
             "import base64",
             "import json",
             "import zlib",
             "",
             "",
             "def _frames(payload):",
             "    data = zlib.decompress(base64.b85decode(payload))",
             "    return tuple(tuple(row) for row in json.loads(data))",
             "",
             "",
             f"MAP_ID = {compiled['map_id']!r}",
             f"MAP_HASH = {compiled['map_hash']!r}",
             "PAIRS = ("]
    for pair in compiled["pairs"]:
        lines.append("    {")
        for key in ("name", "site", "via", "holdMode", "sha256"):
            lines.append(f"        {key!r}: {pair[key]!r},")
        for key in ("opening", "hold"):
            _write_frames(lines, key, pair[key])
        lines.append("    },")
    lines.extend((")", "RETAKES = {"))
    for direction in sorted(compiled["retakes"]):
        lines.append(f"    {direction!r}: (")
        for route in compiled["retakes"][direction]:
            lines.append("        {")
            for key in ("name", "origin", "target", "via", "sha256"):
                lines.append(f"            {key!r}: {route[key]!r},")
            _write_frames(lines, "frames", route["frames"], "            ")
            lines.append("        },")
        lines.append("    ),")
    lines.extend(("}",))
    output.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("side", choices=("t", "ct"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("static_map", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    static_map = json.loads(args.static_map.read_text())
    if args.side == "t":
        write_t_module(compile_t_manifest(args.manifest, static_map),
                       args.output)
    else:
        write_ct_module(compile_ct_manifest(args.manifest, static_map),
                        args.output)

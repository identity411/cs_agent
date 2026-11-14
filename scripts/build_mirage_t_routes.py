"""Compile explicitly approved Mirage T demo routes and a Walklab handoff."""

import argparse
import base64
import hashlib
import json
import math
import zlib
from pathlib import Path

from scripts.build_r3_replays import KEY_BITS


def _frames(route):
    rows = []
    for tick, frame in enumerate(route["frames"]):
        if frame.get("tick") != tick:
            raise ValueError("noncontiguous route ticks")
        values = [*(frame.get("position") or ()), frame.get("yaw"),
                  frame.get("pitch")]
        if (len(values) != 5
                or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                       for v in values)):
            raise ValueError("invalid route pose")
        keys = frame.get("keys")
        if not isinstance(keys, list) or any(k not in KEY_BITS for k in keys):
            raise ValueError("invalid route keys")
        rows.append(tuple(round(v, 4) for v in values)
                    + (sum(KEY_BITS[k] for k in set(keys)),))
    return tuple(rows)


def compile_manifest(manifest_path, static_map):
    manifest = json.loads(manifest_path.read_text())
    fixture = static_map["map"]
    if (manifest["mapId"] != fixture["id"]
            or manifest["mapHash"] != fixture["geometry_hash"]):
        raise ValueError("Mirage fixture hash mismatch")
    catalog_path = (manifest_path.parent / manifest["catalog"]).resolve()
    catalog_raw = catalog_path.read_bytes()
    catalog = json.loads(catalog_raw)
    if (catalog["mapId"] != fixture["id"]
            or catalog["mapHash"] != fixture["geometry_hash"]):
        raise ValueError("demo catalog map mismatch")
    by_id = {route["id"]: route for route in catalog["routes"]}
    attacks = []
    seen = set()
    sites = {site["id"]: site["center"] for site in fixture["sites"]}
    for item in manifest["attacks"]:
        if item["id"] in seen:
            raise ValueError("duplicate approved demo route")
        seen.add(item["id"])
        source = by_id[item["id"]]
        if (source["side"] != "attack" or source["purpose"] != "attack"
                or source["targetSite"] != item["site"] or source["hz"] != 16):
            raise ValueError("invalid attack route metadata")
        rows = _frames(source)[item["startFrame"]:]
        if len(rows) < 2:
            raise ValueError("attack slice too short")
        handoff_index = None
        handoff_sha = None
        if item.get("handoff"):
            path = manifest_path.parent / item["handoff"]
            raw = path.read_bytes()
            handoff = json.loads(raw)
            if (handoff.get("format") != "walklab-v2"
                    or handoff.get("mapId") != fixture["id"]
                    or handoff.get("mapHash") != fixture["geometry_hash"]
                    or handoff.get("side") != "attack" or handoff.get("hz") != 20):
                raise ValueError("invalid handoff map or format")
            continuation = _frames(handoff)
            if math.dist(rows[-1][:2], continuation[0][:2]) > 0.2:
                raise ValueError("handoff does not join demo route")
            handoff_index = len(rows)
            handoff_sha = hashlib.sha256(raw).hexdigest()
            rows += continuation
        center = sites[item["site"]]
        cutoff = next((i for i, row in enumerate(rows)
                       if math.dist(row[:2], center[:2]) <= 12), None)
        if cutoff is None:
            raise ValueError("attack never approaches its plant site")
        attacks.append({"name": item["name"], "site": item["site"],
                        "frames": rows, "carrier_cutoff": cutoff,
                        "start_frame": item["startFrame"],
                        "source_id": item["id"],
                        "handoff_index": handoff_index,
                        "handoff_sha256": handoff_sha,
                        "terminal_hold": bool(item.get("terminalHold"))})
    postplant = {"A": []}
    for item in manifest["postplant"]:
        source = by_id[item["id"]]
        if (source["side"] != "attack"
                or source["purpose"] != "postplant_hold"
                or source["targetSite"] != item["site"]
                or source["hz"] != 16):
            raise ValueError("invalid postplant metadata")
        postplant[item["site"]].append({"name": item["name"],
                                        "frames": _frames(source),
                                        "source_id": item["id"]})
    return {"map_id": fixture["id"], "map_hash": fixture["geometry_hash"],
            "catalog_sha256": hashlib.sha256(catalog_raw).hexdigest(),
            "attacks": attacks, "postplant": postplant}


def _encode_frames(frames):
    raw = json.dumps([list(frame) for frame in frames],
                     separators=(",", ":")).encode("ascii")
    return base64.b85encode(zlib.compress(raw, 9)).decode("ascii")


def _payload_lines(payload, indent):
    return [f'{indent}"{payload[i:i + 96]}"'
            for i in range(0, len(payload), 96)]


def write_module(result, output):
    lines = ['"""Approved Mirage T routes; generated by build_mirage_t_routes.py."""',
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
             f"MAP_ID = {result['map_id']!r}",
             f"MAP_HASH = {result['map_hash']!r}",
             f"CATALOG_SHA256 = {result['catalog_sha256']!r}",
             "ATTACKS = ("]
    for route in result["attacks"]:
        lines.append("    {")
        for key in ("name", "site", "carrier_cutoff", "start_frame",
                    "source_id", "handoff_index", "handoff_sha256",
                    "terminal_hold"):
            lines.append(f"        {key!r}: {route[key]!r},")
        lines.append("        'frames': _frames(")
        lines.extend(_payload_lines(_encode_frames(route["frames"]), "            "))
        lines.extend(("        ),", "    },"))
    lines.extend((")", "POSTPLANT = {", "    'A': ("))
    for route in result["postplant"]["A"]:
        lines.append(f"        {{'name': {route['name']!r}, 'source_id': {route['source_id']!r}, 'frames': _frames(")
        lines.extend(_payload_lines(_encode_frames(route["frames"]), "            "))
        lines.append("        )},")
    lines.extend(("    ),", "}"))
    output.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("static_map", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_module(compile_manifest(args.manifest,
                                  json.loads(args.static_map.read_text())), args.output)

"""Extract surviving player routes and original aim from a professional demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from scripts.pro_demo_routes import distance, source_to_platform


def clean_interval(events, player, first, last):
    return not any(first <= tick <= last and victim == player
                   for tick, _attacker, victim in events["death"])


def to_walklab(candidate, fixture, demo_name):
    frames = candidate["frames"]
    result = {"format": "walklab-v2", "id": candidate["id"],
              "name": candidate["name"], "mapId": fixture["id"],
              "mapHash": fixture["geometry_hash"], "hz": 16,
              "side": candidate["side"], "purpose": candidate["purpose"],
              "source": {"demo": demo_name, "player": candidate["player"],
                         "sha256": candidate["demo_hash"],
                         "round": candidate["round"],
                         "startTick": candidate["start_tick"],
                         "endTick": candidate["end_tick"],
                         "survivalFilter": "player did not die during this route; combat allowed"},
              "start": {"position": [frames[0][k] for k in ("x", "y", "z")],
                        "yaw": round(math.radians(frames[0]["yaw"] - 90), 4),
                        "pitch": round(-math.radians(frames[0]["pitch"]), 4),
                        "source": "demo"},
              "frames": []}
    for i, frame in enumerate(frames):
        result["frames"].append({"tick": i, "keys": [], "mouse": [0, 0],
                                 "position": [frame[k] for k in ("x", "y", "z")],
                                 "yaw": round(math.radians(frame["yaw"] - 90), 4),
                                 "pitch": round(-math.radians(frame["pitch"]), 4)})
    if candidate.get("targetSite"):
        result["targetSite"] = candidate["targetSite"]
    if candidate.get("originSite"):
        result["originSite"] = candidate["originSite"]
    if candidate.get("area"):
        result["area"] = candidate["area"]
    return result


def path_length(frames):
    return sum(distance((a["x"], a["y"]), (b["x"], b["y"]))
               for a, b in zip(frames, frames[1:]))


def first_reached(frames, point, radius, start=0):
    return next((i for i in range(start, len(frames))
                 if distance((frames[i]["x"], frames[i]["y"]), point) <= radius), None)


def route_label(map_id, site, frames):
    near = lambda point: min(distance((f["x"], f["y"]), point)
                             for f in frames)
    if map_id.startswith("dust2"):
        checks = {"A": [("A 大", (131, 140)), ("A 小", (148, 107))],
                  "B": [("B 洞", (127, 57)), ("B 门", (148, 89))]}
    else:
        checks = {"A": [("A 大", (60, 110)), ("A 小", (62, 75))],
                  "B": [("B 二楼", (116, 118)), ("B 小", (94, 51))]}
    matches = [(name, near(point)) for name, point in checks[site]
               if near(point) <= 9]
    if matches:
        return min(matches, key=lambda item: item[1])[0]
    if map_id.startswith("mirage") and site == "A" and frames[-1]["z"] > 18:
        return "A 二楼"
    return site


def candidate_group(candidate):
    return candidate["name"].split(" · ")[0]


def candidate_for(frames, player, round_no, kind, target, events, fixture,
                  demo_hash, origin=None):
    if len(frames) < 12:
        return None
    sites = {site["id"]: site["center"] for site in fixture["sites"]}
    if kind == "retake":
        start = first_reached(frames, sites[origin], 12)
        end = first_reached(frames, sites[target], 12, (start or 0) + 1)
    elif kind == "attack":
        start = 0
        end = first_reached(frames, sites[target], 10)
    else:
        start = 0
        end = first_reached(frames, target[1], 8)
    if start is None or end is None or end - start < 10:
        return None
    route = frames[start:end + 1]
    if path_length(route) < 25 or not clean_interval(
            events, player, route[0]["tick"], route[-1]["tick"]):
        return None
    label = target if isinstance(target, str) else target[0]
    if kind == "attack":
        label = route_label(fixture["id"], target, route)
    route_id = f"{fixture['id'].split('-')[0]}-{kind}-{label}-r{round_no}-{player[-6:]}"
    route_id = route_id.lower().replace("_", "-")
    return {"id": route_id, "name": f"{fixture['id'].split('-')[0].title()} "
            f"{'T 进攻' if kind == 'attack' else 'CT 回防' if kind == 'retake' else 'CT 开局'} "
            f"{origin + '→' if origin else ''}{label} · R{round_no} {player[-6:]}",
            "side": "attack" if kind == "attack" else "defend",
            "purpose": kind, "targetSite": target if kind != "opening" else None,
            "originSite": origin, "area": label if kind == "opening" else None,
            "player": player, "round": round_no,
            "start_tick": route[0]["tick"], "end_tick": route[-1]["tick"],
            "frames": route, "demo_hash": demo_hash,
            "length": round(path_length(route), 1)}


def hold_candidate(frames, player, round_no, label, point, events, fixture,
                   demo_hash, side="defend"):
    """Keep a continuous CT pose window after reaching a defensive area."""
    arrival = first_reached(frames, point, 8)
    if arrival is None:
        return None
    start_tick = frames[arrival]["tick"] + 64
    best = None
    for start in range(arrival, len(frames) - 95, 16):
        if frames[start]["tick"] < start_tick:
            continue
        route = frames[start:start + 129]
        if (route[-1]["tick"] - route[0]["tick"] < 6 * 64
                or any(b["tick"] - a["tick"] != 4 for a, b in zip(route, route[1:]))
                or any(distance((f["x"], f["y"]), point) > 12 for f in route)
                or not clean_interval(events, player, route[0]["tick"], route[-1]["tick"])):
            continue
        travel = path_length(route)
        aim_change = sum(abs((b["yaw"] - a["yaw"] + 180) % 360 - 180)
                         + abs(b["pitch"] - a["pitch"])
                         for a, b in zip(route, route[1:]))
        if 0.4 <= travel <= 20 and aim_change >= 8:
            if best is None or travel < best[0]:
                best = travel, route
    if best is None:
        return None
    travel, route = best
    map_name = fixture["id"].split("-")[0]
    purpose = "hold" if side == "defend" else "postplant_hold"
    route_id = f"{map_name}-{purpose}-{label}-r{round_no}-{player[-6:]}".lower()
    title = f"CT 守 {label}" if side == "defend" else f"T 守包 {label}"
    return {"id": route_id, "name": f"{map_name.title()} {title} · R{round_no} {player[-6:]}",
            "side": side, "purpose": purpose, "area": label,
            "targetSite": label[0] if label.startswith(("A", "B")) else None,
            "player": player, "round": round_no,
            "start_tick": route[0]["tick"], "end_tick": route[-1]["tick"],
            "frames": route, "demo_hash": demo_hash,
            "length": round(travel, 1)}


def extract(demo_path, fixture_path, limit=2):
    from demoparser2 import DemoParser

    fixture = json.loads(Path(fixture_path).read_text())["map"]
    parser = DemoParser(str(demo_path))
    expected = "de_" + fixture["id"].split("-")[0]
    if parser.parse_header()["map_name"] != expected:
        raise ValueError("demo and map fixture do not match")
    digest = hashlib.sha256()
    with Path(demo_path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    demo_hash = digest.hexdigest()
    rounds = parser.parse_event("round_end").sort_values("tick")
    starts = parser.parse_event("round_freeze_end").sort_values("tick")
    plants = parser.parse_event("bomb_planted")
    deaths = parser.parse_event("player_death")
    events = {
        "death": [(int(r.tick), str(r.attacker_steamid), str(r.user_steamid))
                  for r in deaths.itertuples(index=False)],
    }
    last_tick = int(rounds.tick.max())
    ticks = parser.parse_ticks(["X", "Y", "Z", "pitch", "yaw", "team_num",
                                "is_alive"], ticks=list(range(0, last_tick + 1, 4)))
    ticks = ticks[ticks.is_alive & ticks.team_num.isin([2, 3])]
    players = {str(r.steamid): r.name for r in parser.parse_player_info().itertuples(index=False)}
    rows = defaultdict(list)
    for r in ticks.itertuples(index=False):
        x, y, z = source_to_platform(r.X, r.Y, r.Z)
        rows[(str(r.steamid), int(r.team_num))].append(
            {"tick": int(r.tick), "x": x, "y": y, "z": z,
             "yaw": float(r.yaw), "pitch": float(r.pitch)})
    sites = {s["id"]: s["center"] for s in fixture["sites"]}
    # Opening destinations are map coordinates, not an inferred combat label.
    opening = {"A": sites["A"], "B": sites["B"]}
    if fixture["id"].startswith("dust2"):
        opening.update({"A小": [153, 108], "中门": [148, 89]})
        hold_points = {"A": sites["A"], "A 小": [153, 108],
                       "中门": [148, 89], "B": sites["B"]}
    else:
        opening.update({"中路": [76, 77], "连接": [62, 75]})
        hold_points = {"A": sites["A"], "中路": [76, 77],
                       "连接": [62, 75], "B": sites["B"]}
    candidates = []
    previous_end = 0
    for end_row in rounds.itertuples(index=False):
        round_no, round_end = int(end_row.round), int(end_row.tick)
        if round_no <= 0:
            previous_end = round_end
            continue
        starts_here = starts[(starts.tick > previous_end) & (starts.tick < round_end)]
        if starts_here.empty:
            previous_end = round_end
            continue
        round_start = int(starts_here.tick.iloc[0])
        planted = plants[(plants.tick >= round_start) & (plants.tick < round_end)]
        plant_tick = int(planted.tick.iloc[0]) if not planted.empty else None
        planted_pos = None
        if plant_tick:
            plant_frames = parser.parse_ticks(["X", "Y", "Z"], ticks=[plant_tick])
            planter = str(planted.user_steamid.iloc[0])
            planter_frame = plant_frames[plant_frames.steamid.astype(str) == planter]
            if not planter_frame.empty:
                planted_pos = source_to_platform(*planter_frame.iloc[0][["X", "Y", "Z"]])
        for (steamid, team), all_frames in rows.items():
            name = players.get(steamid, steamid)
            pre = [f for f in all_frames if round_start <= f["tick"]
                   <= min(round_end, plant_tick or round_end)]
            if team == 2:
                for site in sites:
                    c = candidate_for(pre, steamid, round_no, "attack", site,
                                      events, fixture, demo_hash)
                    if c:
                        c["player"] = name
                        candidates.append(c)
                if plant_tick and planted_pos:
                    planted_site = min(
                        sites, key=lambda site: distance(planted_pos, sites[site]))
                    post = [f for f in all_frames if plant_tick <= f["tick"] <= round_end]
                    c = hold_candidate(post, steamid, round_no, planted_site,
                                       sites[planted_site], events, fixture,
                                       demo_hash, side="attack")
                    if c:
                        c["player"] = name
                        candidates.append(c)
            else:
                opening_frames = [f for f in pre if f["tick"] <= round_start + 30 * 64]
                for label, point in opening.items():
                    c = candidate_for(opening_frames, steamid, round_no,
                                      "opening", (label, point), events,
                                      fixture, demo_hash)
                    if c:
                        c["player"] = name
                        candidates.append(c)
                for label, point in hold_points.items():
                    c = hold_candidate(pre, steamid, round_no, label, point,
                                       events, fixture, demo_hash)
                    if c:
                        c["player"] = name
                        candidates.append(c)
                if planted_pos:
                    target = min(sites, key=lambda site: distance(planted_pos, sites[site]))
                    origin = "B" if target == "A" else "A"
                    retake = [f for f in all_frames if plant_tick - 20 * 64
                              <= f["tick"] <= min(round_end, plant_tick + 45 * 64)]
                    c = candidate_for(retake, steamid, round_no, "retake",
                                      target, events, fixture, demo_hash, origin)
                    if c:
                        c["player"] = name
                        candidates.append(c)
        previous_end = round_end
    groups = defaultdict(list)
    for c in candidates:
        groups[candidate_group(c)].append(c)
    selected = []
    for group in groups.values():
        group.sort(key=lambda c: (c["length"], c["end_tick"] - c["start_tick"]))
        for c in group[:limit]:
            c["name"] = c["name"].rsplit(" ", 1)[0] + " " + c["player"]
            selected.append(c)
    return {"demo": Path(demo_path).name, "sha256": demo_hash,
            "mapId": fixture["id"], "mapHash": fixture["geometry_hash"],
            "routes": [to_walklab(c, fixture, Path(demo_path).name)
                       for c in selected]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("demo", type=Path)
    p.add_argument("fixture", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    data = extract(args.demo, args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"map": data["mapId"], "routes": len(data["routes"]),
                      "names": [r["name"] for r in data["routes"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

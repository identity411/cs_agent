#!/usr/bin/env python3
"""Read-only observability metrics for collected AGX FPS matches.

Computes the metrics defined in docs/spec/11-12-match-observability.md:

- combat participation: fires / hits / kills / deaths / being hit;
- accuracy = hits / fires;
- site reach, spawn-stuck, and time-to-site from sparse public frames;
- post-plant rotation attempt / arrival using the public bomb position.

This script only reads data already written by ``agx_matches.py collect
--replays`` and public frame ranges.  It never uploads, activates, or changes
competition state.  A match must have been collected first:

    python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect --replays

Example:

    python3 .claude/skills/agx-match-query/scripts/agx_observe.py \\
      --match main:36cf9b6c-78ec-469f-b008-daca03bf0e73:v0.02-main \\
      --match account2:6de14096-e31a-4b71-b9ac-42acad434113:v0.02-account2 \\
      --match main:da110811-9f35-4c86-9492-b322b1302391:v0.01 \\
      --out data/analysis/2026-11-12-observability.json

Use the same ``:LABEL`` on multiple matches to get a pooled aggregate for
one code version; per-match rows remain in ``matches``.
"""
from __future__ import annotations

import argparse
import bisect
import concurrent.futures
import importlib.util
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MATCHES_SCRIPT = (Path(__file__).resolve().parent / "agx_matches.py")
DATA_DIR = REPO_ROOT / "data" / "accounts"

# Metric thresholds.  Keep these in sync with the spec.
SAMPLE_STEP = 120          # ticks; 2 s at 60 Hz
SITE_REACH_PAD = 6.0       # units outside site.radius that still count
SPAWN_LEAVE_DIST = 12.0    # max distance from own spawn to count as "left"
STUCK_MOVE_DIST = 20.0     # below this with no site reach => true stuck
SITE_FAST_SECONDS = 40.0   # "reached site in time" threshold
ROTATE_MIN_DIST = 25.0     # post-plant distance that needs a rotation
ROTATE_ATTEMPT_DROP = 10.0 # closing distance that counts as an attempt
ROTATE_ARRIVE_DIST = 8.0   # close enough to count as arrival


def load_match_helper():
    spec = importlib.util.spec_from_file_location(
        "agx_matches", MATCHES_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AM = load_match_helper()


def dist2(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def parse_match_arg(value: str) -> tuple[str, str, str]:
    parts = value.split(":", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            "--match must be ACCOUNT:MATCH_ID[:LABEL]")
    account, match_id = parts[0], parts[1]
    label = parts[2] if len(parts) == 3 and parts[2] else match_id[:8]
    return account, match_id, label


def account_client(account: str):
    args = argparse.Namespace(account=account, base_url=None, game_id="fps",
                              competition_id="fps", agent_id=None)
    return AM.make_client(args)


def match_dir(account: str, match_id: str) -> Path:
    return DATA_DIR / account / "matches" / match_id


def load_collected(account: str, match_id: str):
    base = match_dir(account, match_id)
    required = [base / "events.jsonl", base / "static.json",
                DATA_DIR / account / "snapshot.json"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(
            "missing collected data: " + ", ".join(missing) +
            "\nrun: python3 .claude/skills/agx-match-query/scripts/"
            "agx_matches.py collect --replays")
    events = [json.loads(line) for line in (base / "events.jsonl").open()]
    static = json.load((base / "static.json").open())
    snapshot = json.load((DATA_DIR / account / "snapshot.json").open())
    matches = snapshot.get("matches") or []
    meta = next((m for m in matches if m.get("id") == match_id), None)
    if not meta or meta.get("my_seat") is None:
        raise SystemExit(
            f"match {match_id} is not in {account}/snapshot.json; "
            "re-run collect")
    return base, events, static, snapshot, meta


def fetch_frame(client, match_id: str, record: dict, chunk_base: str):
    """Fetch one frame record, joining the frame across chunk boundaries."""
    offset, length = record["offset"], record["length"]
    parts = []
    pos = offset
    target = offset + length
    while pos < target:
        chunk = pos // AM.FRAME_CHUNK
        within = pos - chunk * AM.FRAME_CHUNK
        size = min(target - pos, AM.FRAME_CHUNK - within)
        last_error = None
        for _ in range(4):
            status, _headers, raw = client.request(
                "GET", chunk_base + str(chunk),
                headers={"Range": f"bytes={within}-{within + size - 1}"})
            if status == 200:
                raw = raw[within:within + size]
                last_error = None
                break
            if status == 206 and len(raw) >= size:
                raw = raw[:size]
                last_error = None
                break
            last_error = f"HTTP {status}, {len(raw)} bytes"
        if last_error:
            return None
        parts.append(raw)
        pos += size
    try:
        return json.loads(b"".join(parts))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def sample_frames(client, match_id: str, ticks: list[int],
                  max_workers: int) -> dict[int, dict]:
    index = AM.fetch_index(client, match_id)
    records = index["records"]
    times = [record["t"] for record in records]
    wanted = []
    for tick in ticks:
        i = bisect.bisect_left(times, tick / 60.0)
        wanted.append((tick, min(i, len(records) - 1)))
    chunk_base = AM.recording_path(match_id) + "/streams/public_frames/chunks/"
    cache: dict[int, dict | None] = {}

    def one(item):
        tick, index = item
        if index not in cache:
            cache[index] = fetch_frame(client, match_id, records[index],
                                       chunk_base)
        return tick, cache[index]

    frames = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers) as executor:
        for tick, frame in executor.map(one, wanted):
            if frame is not None:
                frames[tick] = frame
    return frames


def round_spans(events: list) -> dict[int, dict]:
    rounds: dict[int, dict] = {}
    for event in events:
        if event.get("type") == "round_start":
            rounds.setdefault(event["round_index"], {}).update(
                start=event["match_tick"],
                freeze=event.get("buy_freeze_end_tick", 360),
                live_end=event.get("live_end_tick"),
                attack=event.get("attack_team"),
                defend=event.get("defend_team"))
        elif event.get("type") == "round_end":
            rounds.setdefault(event["round_index"], {}).update(
                end=event["match_tick"], winner=event.get("round_winner"),
                reason=event.get("reason"))
    return rounds


def is_combat_round(row: dict) -> bool:
    return bool(row["shots"] or row["hits"] or row["hits_taken"]
                or row["kills"] or row["deaths"])


def analyze_match(account: str, match_id: str, label: str,
                  sample_step: int, max_workers: int,
                  frames_enabled: bool) -> dict:
    base, events, static, snapshot, meta = load_collected(account, match_id)
    map_data = static["map"]
    sites = map_data["sites"]
    spawns = map_data["spawn_pads_by_side"]
    seat = meta["my_seat"]
    team = meta["result"]["teams"][seat]
    rounds = round_spans(events)

    fires = [e for e in events
             if e.get("type") == "fire" and e.get("player") == seat]
    hits = [e for e in events
            if e.get("type") == "hit" and e.get("player") == seat]
    hits_taken = [e for e in events
                  if e.get("type") == "hit" and e.get("target") == seat]
    kills = [e for e in events
             if e.get("type") == "kill" and seat in (e.get("attackers") or [])]
    deaths = [e for e in events
              if e.get("type") == "kill" and e.get("target") == seat]
    plants = [e for e in events if e.get("type") == "plant_complete"]
    plant_details = {e.get("item_id"): e for e in events
                     if e.get("type") == "plant_complete_detail"}
    defuse_starts = [e for e in events
                     if e.get("type") == "defuse_start"
                     and e.get("player") == seat]
    plant_starts = [e for e in events
                    if e.get("type") == "plant_start"
                    and e.get("player") == seat]
    faults = [e for e in events if e.get("type") == "fault"]
    all_fires = [e for e in events if e.get("type") == "fire"]
    team_fires = sum(1 for e in all_fires
                     if (e.get("player") or 0) // 5 == team)
    enemy_fires = len(all_fires) - team_fires

    frames = {}
    if frames_enabled:
        ticks = set()
        tick_round = {}
        for index, span in rounds.items():
            start = span.get("freeze") or 0
            end = span.get("end") or span.get("live_end") or 0
            ticks.add(span["start"])
            tick_round[span["start"]] = index
            tick = start
            while tick <= end:
                ticks.add(tick)
                tick_round[tick] = index
                tick += max(1, sample_step)
        client = account_client(account)
        frames = sample_frames(client, match_id, sorted(ticks), max_workers)

    by_round: dict[int, list] = {}
    for tick, frame in frames.items():
        index = frame.get("round_index")
        if index is None:
            index = tick_round.get(tick)
        by_round.setdefault(index, []).append(
            (frame.get("match_tick", tick), frame))
    for index in by_round:
        by_round[index].sort()

    rows = []
    for index in sorted(rounds):
        span = rounds[index]
        side = "attack" if team == span.get("attack") else "defend"
        spawn_center = [
            sum(point[0] for point in spawns[side]) / len(spawns[side]),
            sum(point[1] for point in spawns[side]) / len(spawns[side]),
        ]
        samples = []
        for tick, frame in by_round.get(index, []):
            player = frame["players"][seat]
            samples.append({
                "tick": tick,
                "alive": bool(player.get("alive")),
                "pos": [player.get("x", 0.0), player.get("y", 0.0),
                        player.get("z", 0.0)],
            })
        live = [s for s in samples if s["tick"] >= (span.get("freeze") or 0)]
        movement_known = bool(live)
        max_spawn_dist = (
            max(dist2(s["pos"], spawn_center) for s in live)
            if movement_known else None)
        site_ids = []
        first_site_tick = None
        min_clearance = None
        if movement_known:
            for sample in live:
                clearance = min(
                    dist2(sample["pos"], site["center"]) - site["radius"]
                    for site in sites)
                min_clearance = (clearance if min_clearance is None
                                 else min(min_clearance, clearance))
                for site in sites:
                    if dist2(sample["pos"], site["center"]) <= (
                            site["radius"] + SITE_REACH_PAD):
                        if site["id"] not in site_ids:
                            site_ids.append(site["id"])
                        if first_site_tick is None:
                            first_site_tick = sample["tick"]
        reached = bool(site_ids) if movement_known else None
        round_fires = [e for e in fires if e.get("round_index") == index]
        round_hits = [e for e in hits if e.get("round_index") == index]
        round_hits_taken = [
            e for e in hits_taken if e.get("round_index") == index]
        round_kills = [e for e in kills if e.get("round_index") == index]
        round_deaths = [e for e in deaths if e.get("round_index") == index]
        row = {
            "round": index,
            "side": side,
            "reason": span.get("reason"),
            "won": span.get("winner") == team,
            "shots": len(round_fires),
            "hits": len(round_hits),
            "hits_taken": len(round_hits_taken),
            "kills": len(round_kills),
            "deaths": len(round_deaths),
            "damage": round(
                sum(e.get("amount", 0.0) for e in round_hits), 1),
            "movement_known": movement_known,
            "left_spawn": (max_spawn_dist > SPAWN_LEAVE_DIST
                           if movement_known else None),
            "max_spawn_dist": (round(max_spawn_dist, 1)
                               if movement_known else None),
            "reached_site": reached,
            "sites": site_ids,
            "min_site_clearance": (
                round(min_clearance, 1) if min_clearance is not None else None),
            "first_site_tick": first_site_tick,
            "time_to_site_s": (
                round((first_site_tick - (span.get("freeze") or 0)) / 60.0, 1)
                if first_site_tick is not None else None),
            "sample_count": len(live),
            "death_tick": (round_deaths[0]["match_tick"]
                           if round_deaths else None),
            "rotation": None,
        }
        row["combat"] = is_combat_round(row)
        row["stuck_site"] = (not reached) if movement_known else None
        row["stuck_spawn"] = (not row["left_spawn"]
                              if movement_known else None)
        row["true_stuck"] = (
            (not reached and max_spawn_dist < STUCK_MOVE_DIST)
            if movement_known else None)
        row["no_site_moving"] = (
            (not reached and max_spawn_dist >= STUCK_MOVE_DIST)
            if movement_known else None)
        rows.append(row)

        plant = next((event for event in plants
                      if event.get("round_index") == index), None)
        if not plant:
            continue
        detail = plant_details.get(plant.get("item_id"))
        if not detail or not detail.get("position"):
            continue
        bomb = detail["position"]
        plant_tick = plant["match_tick"]
        after = []
        for tick, frame in by_round.get(index, []):
            if tick < plant_tick:
                continue
            player = frame["players"][seat]
            after.append({
                "tick": tick,
                "alive": bool(player.get("alive")),
                "pos": [player.get("x", 0.0), player.get("y", 0.0),
                        player.get("z", 0.0)],
            })
        if not after:
            continue
        first = after[0]
        initial = dist2(first["pos"], bomb)
        alive_after = [sample for sample in after if sample["alive"]]
        min_dist = min((dist2(sample["pos"], bomb)
                        for sample in alive_after), default=initial)
        end_tick = span.get("end")
        time_available = (
            max(0, end_tick - plant_tick) / 60.0 if end_tick else 0.0)
        own_defuse = [event for event in defuse_starts
                      if event.get("round_index") == index]
        row["rotation"] = {
            "bomb_site": detail.get("site"),
            "plant_tick": plant_tick,
            "alive_at_plant": first["alive"],
            "initial_dist": round(initial, 1),
            "min_dist": round(min_dist, 1),
            "closing": round(initial - min_dist, 1),
            "time_available": round(time_available, 1),
            "required_speed": (
                round((initial - ROTATE_ARRIVE_DIST) / time_available, 2)
                if time_available > 0 else None),
            "opportunity": (first["alive"]
                            and initial > ROTATE_MIN_DIST),
            "attempt": (bool(own_defuse)
                        or initial - min_dist >= ROTATE_ATTEMPT_DROP),
            "arrive": (bool(own_defuse)
                       or min_dist <= ROTATE_ARRIVE_DIST),
        }

    rotation_rows = [row["rotation"] for row in rows
                     if row["rotation"] and row["rotation"]["opportunity"]]
    accuracy = (round(100.0 * len(hits) / len(fires), 1) if fires else None)
    side_metrics = {}
    for side in ("attack", "defend"):
        subset = [row for row in rows if row["side"] == side]
        movement = [row for row in subset if row["movement_known"]]
        times = [row["time_to_site_s"] for row in subset
                 if row["time_to_site_s"] is not None]
        side_metrics[side] = {
            "rounds": len(subset),
            "movement_rounds": len(movement),
            "shots": sum(row["shots"] for row in subset),
            "rounds_with_fire": sum(1 for row in subset
                                    if row["shots"] > 0),
            "rounds_with_combat": sum(1 for row in subset
                                      if row["combat"]),
            "reached_site": sum(1 for row in subset
                                if row["reached_site"] is True),
            "no_site": sum(1 for row in subset
                           if row["stuck_site"] is True),
            "true_stuck": sum(1 for row in subset
                              if row["true_stuck"] is True),
            "no_site_moving": sum(1 for row in subset
                                  if row["no_site_moving"] is True),
            "spawn_stuck": sum(1 for row in subset
                               if row["stuck_spawn"] is True),
            "reached_site_within_time": sum(
                1 for row in subset
                if row["time_to_site_s"] is not None
                and row["time_to_site_s"] <= SITE_FAST_SECONDS),
            "time_to_site_s": times,
            "time_to_site_median_s": (round(statistics.median(times), 1)
                                      if times else None),
            "rotation_opportunities": sum(
                1 for row in subset if row["rotation"]
                and row["rotation"]["opportunity"]),
            "rotation_attempts": sum(
                1 for row in subset if row["rotation"]
                and row["rotation"]["opportunity"]
                and row["rotation"]["attempt"]),
            "rotation_arrivals": sum(
                1 for row in subset if row["rotation"]
                and row["rotation"]["opportunity"]
                and row["rotation"]["arrive"]),
        }
    seat_label = meta.get("my_seat_label") or (
        f"seat {seat} (0-based) = team {team} = 第 {seat + 1} 个玩家")
    return {
        "label": label,
        "account": account,
        "match_id": match_id,
        "map": map_data["id"],
        "seat": seat,
        "seat_position": seat + 1,
        "seat_label": seat_label,
        "team": team,
        "rounds": len(rows),
        "rounds_with_frames": sum(1 for row in rows
                                  if row["movement_known"]),
        "result_round_wins": meta.get("result", {}).get("round_wins"),
        "winner": meta.get("result", {}).get("winner"),
        "win": meta.get("result", {}).get("winner") == team,
        "sides": {
            "attack": sum(1 for row in rows if row["side"] == "attack"),
            "defend": sum(1 for row in rows if row["side"] == "defend"),
        },
        "shots": len(fires),
        "hits": len(hits),
        "hits_taken": len(hits_taken),
        "kills": len(kills),
        "deaths": len(deaths),
        "damage": round(sum(e.get("amount", 0.0) for e in hits), 1),
        "accuracy_percent": accuracy,
        "rounds_with_fire": sum(1 for row in rows if row["shots"] > 0),
        "rounds_with_combat": sum(1 for row in rows if row["combat"]),
        "zero_shot_rounds": [row["round"] for row in rows
                             if row["shots"] == 0],
        "combat_rounds": [row["round"] for row in rows if row["combat"]],
        "reached_site_rounds": [row["round"] for row in rows
                                if row["reached_site"] is True],
        "no_site_rounds": [row["round"] for row in rows
                           if row["stuck_site"] is True],
        "no_site_no_combat_rounds": [
            row["round"] for row in rows
            if row["stuck_site"] is True and not row["combat"]],
        "true_stuck_rounds": [row["round"] for row in rows
                              if row["true_stuck"] is True],
        "no_site_moving_rounds": [row["round"] for row in rows
                                  if row["no_site_moving"] is True],
        "spawn_stuck_rounds": [row["round"] for row in rows
                               if row["stuck_spawn"] is True],
        "time_to_site_s": [row["time_to_site_s"] for row in rows
                           if row["time_to_site_s"] is not None],
        "reached_site_within_time": sum(
            1 for row in rows if row["time_to_site_s"] is not None
            and row["time_to_site_s"] <= SITE_FAST_SECONDS),
        "rotation_opportunities": [row["round"] for row in rows
                                   if row["rotation"]
                                   and row["rotation"]["opportunity"]],
        "rotation_attempts": [row["round"] for row in rows
                              if row["rotation"]
                              and row["rotation"]["opportunity"]
                              and row["rotation"]["attempt"]],
        "rotation_arrivals": [row["round"] for row in rows
                              if row["rotation"]
                              and row["rotation"]["opportunity"]
                              and row["rotation"]["arrive"]],
        "rotation_rows": [
            {"round": row["round"], **row["rotation"]}
            for row in rows if row["rotation"]],
        "plant_rounds": [event["round_index"] for event in plants],
        "plant_starts": [event["round_index"] for event in plant_starts],
        "defuse_starts": [event["round_index"] for event in defuse_starts],
        "lobby_fires": len(all_fires),
        "team_fires": team_fires,
        "enemy_fires": enemy_fires,
        "lobby_zero_combat": not all_fires,
        "faults": len(faults),
        "seat_faults": sum(1 for event in faults
                           if event.get("seat") == seat),
        "side_metrics": side_metrics,
        "rows": rows,
    }


def rate(numerator: int, denominator: int):
    return (round(100.0 * numerator / denominator, 1)
            if denominator else None)


def aggregate_sides(matches: list[dict]) -> dict:
    result = {}
    for side in ("attack", "defend"):
        items = [match["side_metrics"][side] for match in matches]
        times = [value for item in items for value in item["time_to_site_s"]]
        result[side] = {
            "rounds": sum(item["rounds"] for item in items),
            "movement_rounds": sum(item["movement_rounds"] for item in items),
            "shots": sum(item["shots"] for item in items),
            "rounds_with_fire": sum(item["rounds_with_fire"]
                                    for item in items),
            "rounds_with_combat": sum(item["rounds_with_combat"]
                                      for item in items),
            "reached_site": sum(item["reached_site"] for item in items),
            "no_site": sum(item["no_site"] for item in items),
            "true_stuck": sum(item["true_stuck"] for item in items),
            "no_site_moving": sum(item["no_site_moving"] for item in items),
            "spawn_stuck": sum(item["spawn_stuck"] for item in items),
            "reached_site_within_time": sum(
                item["reached_site_within_time"] for item in items),
            "time_to_site_median_s": (round(statistics.median(times), 1)
                                      if times else None),
            "rotation_opportunities": sum(
                item["rotation_opportunities"] for item in items),
            "rotation_attempts": sum(
                item["rotation_attempts"] for item in items),
            "rotation_arrivals": sum(
                item["rotation_arrivals"] for item in items),
        }
    return result


def aggregate(matches: list[dict]) -> dict:
    rounds = sum(match["rounds"] for match in matches)
    movement_rounds = sum(match["rounds_with_frames"] for match in matches)
    shots = sum(match["shots"] for match in matches)
    hits = sum(match["hits"] for match in matches)
    fire_rounds = sum(match["rounds_with_fire"] for match in matches)
    combat_rounds = sum(match["rounds_with_combat"] for match in matches)
    reach_rounds = sum(len(match["reached_site_rounds"]) for match in matches)
    no_site = sum(len(match["no_site_rounds"]) for match in matches)
    true_stuck = sum(len(match["true_stuck_rounds"]) for match in matches)
    no_site_moving = sum(len(match["no_site_moving_rounds"])
                         for match in matches)
    spawn_stuck = sum(len(match["spawn_stuck_rounds"]) for match in matches)
    within_time = sum(match["reached_site_within_time"] for match in matches)
    rotations = sum(len(match["rotation_opportunities"]) for match in matches)
    attempts = sum(len(match["rotation_attempts"]) for match in matches)
    arrivals = sum(len(match["rotation_arrivals"]) for match in matches)
    tts = [value for match in matches for value in match["time_to_site_s"]]
    team_round_wins = sum(match["result_round_wins"][match["team"]]
                          for match in matches)
    team_rounds = sum(sum(match["result_round_wins"]) for match in matches)
    return {
        "matches": len(matches),
        "match_wins": sum(1 for match in matches if match["win"]),
        "rounds": rounds,
        "team_round_win_rate_percent": rate(team_round_wins, team_rounds),
        "shots": shots,
        "shots_per_round": round(shots / rounds, 2) if rounds else None,
        "hits": hits,
        "accuracy_percent": rate(hits, shots),
        "damage": round(sum(match["damage"] for match in matches), 1),
        "kills": sum(match["kills"] for match in matches),
        "deaths": sum(match["deaths"] for match in matches),
        "rounds_with_fire": fire_rounds,
        "fire_participation_percent": rate(fire_rounds, rounds),
        "rounds_with_combat": combat_rounds,
        "combat_participation_percent": rate(combat_rounds, rounds),
        "zero_shot_rate_percent": rate(rounds - fire_rounds, rounds),
        "movement_rounds": movement_rounds,
        "reached_site_rounds": reach_rounds,
        "site_reach_percent": rate(reach_rounds, movement_rounds),
        "no_site_rounds": no_site,
        "no_site_rate_percent": rate(no_site, movement_rounds),
        "true_stuck_rounds": true_stuck,
        "true_stuck_rate_percent": rate(true_stuck, movement_rounds),
        "no_site_moving_rounds": no_site_moving,
        "no_site_moving_rate_percent": rate(no_site_moving, movement_rounds),
        "spawn_stuck_rounds": spawn_stuck,
        "spawn_stuck_rate_percent": rate(spawn_stuck, movement_rounds),
        "reached_site_within_time": within_time,
        "reached_site_within_time_percent": rate(within_time,
                                                 movement_rounds),
        "time_to_site_median_s": (round(statistics.median(tts), 1)
                                  if tts else None),
        "rotation_opportunities": rotations,
        "rotation_attempts": attempts,
        "rotation_attempt_percent": rate(attempts, rotations),
        "rotation_arrivals": arrivals,
        "rotation_arrival_percent": rate(arrivals, rotations),
        "lobby_fires": sum(match["lobby_fires"] for match in matches),
        "lobby_zero_combat_matches": sum(
            1 for match in matches if match["lobby_zero_combat"]),
        "faults": sum(match["faults"] for match in matches),
        "side_metrics": aggregate_sides(matches),
    }


def fmt_value(value) -> str:
    return str(value) if value is not None else "-"


def fmt_percent(value) -> str:
    return f"{value:>5}" if value is not None else f"{'-':>5}"


def print_summary(matches: list[dict], aggregates: dict) -> None:
    print("match                         seat map                 rounds "
          "shots hits acc% fire% combat% site% stuck% rotA/rotN")
    for match in matches:
        print(f"{match['label']:<29} {match['seat']:>4} "
              f"{match['map']:<19} {match['rounds']:>6} "
              f"{match['shots']:>5} {match['hits']:>4} "
              f"{match['accuracy_percent'] if match['accuracy_percent'] is not None else '-':>5} "
              f"{fmt_percent(rate(match['rounds_with_fire'], match['rounds']))} "
              f"{fmt_percent(rate(match['rounds_with_combat'], match['rounds']))} "
              f"{fmt_percent(rate(len(match['reached_site_rounds']), match['rounds_with_frames']))} "
              f"{fmt_percent(rate(len(match['true_stuck_rounds']), match['rounds_with_frames']))} "
              f"{len(match['rotation_attempts'])}/{len(match['rotation_opportunities'])}")
    print("\nseat mapping:")
    for match in matches:
        print(f"  {match['label']}: {match['seat_label']}")
    print("\nversion aggregate:")
    for label, values in aggregates.items():
        print(f"  {label:<16} matches={values['matches']} rounds={values['rounds']} "
              f"shots={values['shots']} "
              f"acc={fmt_value(values['accuracy_percent'])} "
              f"fire={fmt_value(values['fire_participation_percent'])}% "
              f"combat={fmt_value(values['combat_participation_percent'])}% "
              f"site={fmt_value(values['site_reach_percent'])}% "
              f"stuck={fmt_value(values['true_stuck_rate_percent'])}% "
              f"rot={values['rotation_attempts']}/{values['rotation_opportunities']}")
    print("\nby map / side:")
    for match in matches:
        attack = match["side_metrics"]["attack"]
        defend = match["side_metrics"]["defend"]

        def side_value(side, key):
            if side["movement_rounds"] == 0:
                return "N/A"
            return f"{side[key]}/{side['movement_rounds']}"

        print(f"  {match['map']:<19} {match['label']:<16} "
              f"attack reach={side_value(attack, 'reached_site')} "
              f"stuck={side_value(attack, 'true_stuck')} | "
              f"defend reach={side_value(defend, 'reached_site')} "
              f"stuck={side_value(defend, 'true_stuck')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute read-only observability metrics for collected "
                    "AGX FPS matches.")
    parser.add_argument("--match", action="append", required=True,
                        type=parse_match_arg, metavar="ACCOUNT:MATCH_ID[:LABEL]",
                        help="collected match to include; repeatable")
    parser.add_argument("--out", help="write machine-readable JSON here")
    parser.add_argument("--sample-step", type=int, default=SAMPLE_STEP,
                        help=f"frame sampling step in ticks (default {SAMPLE_STEP})")
    parser.add_argument("--max-workers", type=int, default=12,
                        help="parallel frame range requests (default 12)")
    parser.add_argument("--no-frames", action="store_true",
                        help="skip public frames (event-only metrics)")
    args = parser.parse_args()
    if args.sample_step < 1:
        parser.error("--sample-step must be positive")
    if args.max_workers < 1:
        parser.error("--max-workers must be positive")

    AM.AGX.load_dotenv()
    matches = []
    for account, match_id, label in args.match:
        matches.append(analyze_match(
            account, match_id, label, args.sample_step, args.max_workers,
            not args.no_frames))

    by_label: dict[str, list[dict]] = {}
    for match in matches:
        by_label.setdefault(match["label"], []).append(match)
    aggregates = {label: aggregate(items)
                  for label, items in by_label.items()}
    by_map: dict[str, list[dict]] = {}
    for match in matches:
        by_map.setdefault(match["map"], []).append(match)
    by_map_aggregates = {
        name: {
            "labels": [match["label"] for match in items],
            "aggregate": aggregate(items),
        }
        for name, items in by_map.items()
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_step_ticks": args.sample_step,
        "thresholds": {
            "site_reach_pad": SITE_REACH_PAD,
            "spawn_leave_dist": SPAWN_LEAVE_DIST,
            "stuck_move_dist": STUCK_MOVE_DIST,
            "site_fast_seconds": SITE_FAST_SECONDS,
            "rotate_min_dist": ROTATE_MIN_DIST,
            "rotate_attempt_drop": ROTATE_ATTEMPT_DROP,
            "rotate_arrive_dist": ROTATE_ARRIVE_DIST,
        },
        "matches": matches,
        "aggregate": aggregates,
        "by_map": by_map_aggregates,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"wrote {out}", file=sys.stderr)
    print_summary(matches, aggregates)
    if not args.out:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

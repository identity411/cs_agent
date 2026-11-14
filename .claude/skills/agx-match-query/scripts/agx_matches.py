#!/usr/bin/env python3
"""Read-only AGX FPS match / public-replay query helper.

Credentials and the HTTP client are shared with the agx-submit skill; this
script never uploads, activates, or mutates competition state.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import struct
import sys
import urllib.parse
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path

FPS = "fps"
DEFAULT_GAME_ID = FPS
FRAME_CHUNK = 1048576
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "accounts"


def load_helper():
    helper = (Path(__file__).resolve().parents[2]
              / "agx-submit" / "scripts" / "agx_submit.py")
    if not helper.is_file():
        raise SystemExit(f"error: missing {helper}")
    spec = importlib.util.spec_from_file_location("agx_submit", helper)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AGX = load_helper()


class QueryError(RuntimeError):
    pass


def quote(value) -> str:
    return urllib.parse.quote(str(value), safe="")


def account_context(args):
    cached = getattr(args, "_account_context", None)
    if cached is not None:
        return cached
    account = AGX.resolve_account(name=getattr(args, "account", None))
    base = (getattr(args, "base_url", None) or account.base_url or "").strip()
    if not base:
        raise AGX.AccountError(
            f"account {account.name!r} has no base URL; set RSI_URL or "
            f"RSI_ACCOUNT_{account.name.upper()}_URL")
    if not base.startswith(("http://", "https://")):
        raise AGX.AccountError(
            f"account {account.name!r} base URL must start with "
            "http:// or https://")
    competition_id = AGX.resolve_competition_id(
        getattr(args, "competition_id", None),
        account=account,
        game_id=getattr(args, "game_id", None),
        environ=os.environ,
    )
    agent = getattr(args, "agent_id", None) or account.agent_id
    client = AGX.Client(base, account.key)
    args._account_context = (account, client, competition_id, agent)
    return args._account_context


def effective_game_id(args, competition_id: str) -> str:
    explicit = getattr(args, "game_id", None)
    if explicit:
        return explicit
    for game, mapped in AGX.competition_aliases().items():
        if mapped == competition_id:
            return game
    return FPS


def make_client(args):
    return account_context(args)[1]


def competition(args) -> str:
    return account_context(args)[2]


def agent_id(args) -> str | None:
    return account_context(args)[3]


def get_json(client, path: str, params: dict | None = None):
    url = path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    status, headers, raw = client.request("GET", url)
    data = AGX.decode_json(raw)
    if status != 200:
        detail = (json.dumps(data, ensure_ascii=False)
                  if isinstance(data, (dict, list)) else str(data)[:500])
        raise QueryError(f"GET {url} -> HTTP {status}: {detail}")
    return data


def get_bytes(client, path: str) -> bytes:
    status, headers, raw = client.request("GET", path)
    if status != 200:
        detail = AGX.decode_json(raw)
        raise QueryError(f"GET {path} -> HTTP {status}: {detail}")
    return raw


def my_competition(client, competition_id: str):
    data = get_json(client, "/api/v1/me/competitions")
    for item in data.get("items", []):
        if item.get("competition", {}).get("id") == competition_id:
            return item
    return None


def round_projection(client, competition_id: str):
    return get_json(
        client, f"/api/v1/competitions/{quote(competition_id)}/round")


def get_paged_items(client, path: str, limit: int = 100) -> list:
    """Fetch every page of a list endpoint.

    The live deployment defaults to 30 items; without pagination the current
    account's `is_mine` entry can be hidden on a later page.  `mine`/`agent_id`
    query params return 404, but `limit`/`offset` work.
    """
    items: list = []
    offset = 0
    while True:
        try:
            data = get_json(client, path, {
                "limit": limit, "offset": offset})
        except QueryError:
            if offset == 0:
                data = get_json(client, path)
            else:
                raise
        if not isinstance(data, dict):
            raise QueryError(f"GET {path} -> expected a JSON object")
        batch = data.get("items", [])
        items.extend(batch)
        total = data.get("total")
        if (not batch
                or (isinstance(total, int) and len(items) >= total)
                or (total is None and len(batch) < limit)):
            break
        offset += limit
        if offset >= 1000:
            break
    return items


def list_entries(client, competition_id: str):
    return get_paged_items(
        client, f"/api/v1/competitions/{quote(competition_id)}/entries")


def leaderboard(client, competition_id: str):
    return get_paged_items(
        client, f"/api/v1/competitions/{quote(competition_id)}/leaderboard")


def fps_matches(client, game_id: str = FPS, limit: int = 100,
                all_pages: bool = False):
    items = []
    offset = 0
    while True:
        try:
            data = get_json(client, "/api/v1/matches", {
                "game_id": game_id, "limit": limit, "offset": offset})
        except QueryError:
            # Some deployments do not accept the game_id filter; use the
            # unfiltered page and filter locally instead.
            data = get_json(client, "/api/v1/matches", {
                "limit": limit, "offset": offset})
        batch = [m for m in data.get("items", [])
                 if m.get("game_id") == game_id]
        items.extend(batch)
        if not all_pages or len(data.get("items", [])) < limit:
            break
        offset += limit
        if offset > 1000:
            break
    return items


def mine_participant(match):
    for participant in match.get("participants", []):
        if participant.get("is_mine"):
            return participant
    return None


def participant_team(match, seat):
    """Team for a 0-based seat in this match, or None when unknown."""
    if seat is None:
        return None
    for participant in match.get("participants", []):
        if participant.get("seat") == seat:
            return participant.get("team")
    return None


def seat_label(match, seat):
    """State the user's 0-based seat and the 1-based ten-player position.

    Seats in the API and in agent observations are 0-based.  The web viewer
    shows the 1-based "第几个玩家", which is seat + 1, so always report both.
    """
    if seat is None:
        return None
    team = participant_team(match, seat)
    team_text = f"team {team}" if team is not None else "team unknown"
    return f"seat {seat} (0-based) = {team_text} = 第 {seat + 1} 个玩家"


def find_match(client, competition_id: str, match_id: str | None,
               game_id: str):
    me = my_competition(client, competition_id)
    if match_id:
        for match in fps_matches(client, game_id=game_id, all_pages=True):
            if match.get("id") == match_id:
                return match, me
        raise QueryError(f"match not found in /api/v1/matches: {match_id}")
    # The round projection's job_id is the match id on the current schema.
    job_id = ((me or {}).get("round_match") or {}).get("job_id")
    matches = [m for m in fps_matches(client, game_id=game_id, all_pages=True)
               if m.get("competition_id") == competition_id]
    if job_id:
        for match in matches:
            if match.get("id") == job_id:
                return match, me
    mine = [m for m in matches if mine_participant(m)]
    if not mine:
        raise QueryError(
            "no match with a participant marked is_mine; pass --match-id")
    return max(mine, key=lambda m: m.get("finished_at")
               or m.get("created_at") or ""), me


def replay_link(client, match_id: str) -> str:
    return f"{client.base.rstrip('/')}/#/jobs/{quote(match_id)}"


def parse_recording_index(raw: bytes) -> dict:
    if raw[:5] != b"AGXI2":
        raise QueryError("unexpected replay index magic (expected AGXI2)")
    if len(raw) < 14:
        raise QueryError("truncated replay index header")
    frame_count = struct.unpack("<I", raw[6:10])[0]
    meta_len = struct.unpack("<I", raw[10:14])[0]
    meta = json.loads(raw[14:14 + meta_len])
    suffix = raw[14 + meta_len:]
    if len(suffix) != frame_count * 32:
        raise QueryError(
            f"unexpected frame table: {len(suffix)} bytes for "
            f"{frame_count} frames")
    records = []
    for i in range(frame_count):
        rec = suffix[i * 32:(i + 1) * 32]
        records.append({
            "t": struct.unpack("<d", rec[:8])[0],
            "offset": struct.unpack("<Q", rec[8:16])[0],
            "length": struct.unpack("<I", rec[16:20])[0],
        })
    return {
        "version": raw[5],
        "frame_count": frame_count,
        "meta": meta,
        "records": records,
    }


def recording_path(match_id: str) -> str:
    return f"/api/v1/python-submissions/recordings/{quote(match_id)}/replay"


def fetch_index(client, match_id: str) -> dict:
    raw = get_bytes(client, recording_path(match_id) + "/index")
    return parse_recording_index(raw)


def fetch_stream(client, match_id: str, index: dict, stream: str) -> bytes:
    layout = index["meta"].get("layout", {}).get(stream)
    if not layout:
        raise QueryError(f"stream {stream} missing from replay index")
    chunks = []
    for i in range(len(layout)):
        chunks.append(get_bytes(
            client,
            f"{recording_path(match_id)}/streams/{quote(stream)}/chunks/{i}",
        ))
    data = b"".join(chunks)
    expected = sum(layout)
    if len(data) != expected:
        raise QueryError(
            f"stream {stream}: got {len(data)} bytes, expected {expected}")
    return data


def fetch_static(client, match_id: str, index: dict) -> dict:
    return json.loads(fetch_stream(client, match_id, index, "public_static"))


def fetch_events(client, match_id: str, index: dict) -> list:
    raw = fetch_stream(client, match_id, index, "public_events")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def fetch_frames(client, match_id: str, index: dict,
                 start_tick: int, end_tick: int) -> list:
    records = index["records"]
    times = [record["t"] for record in records]
    t0 = start_tick / 60.0 - 0.1
    t1 = end_tick / 60.0 + 0.1
    i0 = bisect_left(times, t0)
    i1 = bisect_right(times, t1)
    if i0 >= i1:
        return []
    first, last = records[i0], records[i1 - 1]
    chunk0 = first["offset"] // FRAME_CHUNK
    chunk1 = (last["offset"] + last["length"] - 1) // FRAME_CHUNK
    cache = {}

    def chunk(i: int) -> bytes:
        if i not in cache:
            cache[i] = get_bytes(
                client,
                f"{recording_path(match_id)}/streams/public_frames/chunks/{i}",
            )
        return cache[i]

    data = b"".join(chunk(i) for i in range(chunk0, chunk1 + 1))
    base = chunk0 * FRAME_CHUNK
    frames = []
    for record in records[i0:i1]:
        blob = data[record["offset"] - base:
                    record["offset"] - base + record["length"]]
        try:
            frame = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if start_tick <= frame.get("match_tick", -1) <= end_tick:
            frames.append(frame)
    return frames


def seat_state(frame: dict, seat: int) -> dict:
    player = frame["players"][seat]
    weapons = player.get("weapons") or [None, None, None]
    primary = weapons[0] or {}
    secondary = weapons[1] or {}
    return {
        "t": round(frame.get("t", 0.0), 2),
        "tick": frame.get("match_tick"),
        "round": frame.get("round_index"),
        "phase": frame.get("phase"),
        "alive": player.get("alive"),
        "position": [round(player.get("x", 0.0), 2),
                     round(player.get("y", 0.0), 2),
                     round(player.get("z", 0.0), 2)],
        "yaw": round(player.get("yaw", 0.0), 3),
        "speed": round(player.get("speed", 0.0), 2),
        "active_slot": player.get("active_slot"),
        "weapon": player.get("weapon_id"),
        "activity": player.get("activity"),
        "primary": [primary.get("id"), primary.get("ammo"),
                    primary.get("reserve"), primary.get("reload_until")],
        "secondary": [secondary.get("id"), secondary.get("ammo"),
                      secondary.get("reserve"), secondary.get("reload_until")],
        "reload": player.get("reload"),
        "weapon_reject": player.get("weapon_reject"),
        "switch_until": player.get("switch_until"),
    }


def event_stats(events: list, seat: int) -> dict:
    fires = [e for e in events
             if e.get("type") == "fire" and e.get("player") == seat]
    hits = [e for e in events
            if e.get("type") == "hit" and e.get("player") == seat]
    kill_events = [e for e in events
                   if e.get("type") == "kill"
                   and seat in (e.get("attackers") or [])]
    kill_credits = [e for e in events
                    if e.get("type") == "kill_reward"
                    and e.get("killer") == seat]
    deaths = [e for e in events
              if e.get("type") == "kill" and e.get("target") == seat]
    reloads = [e for e in events
               if e.get("type", "").startswith("reload")
               and e.get("player") == seat]
    draws = [e for e in events
             if e.get("type") == "draw" and e.get("player") == seat]
    rounds = {}
    for event in events:
        if event.get("type") == "round_start":
            rounds.setdefault(event["round_index"], {})["start"] = \
                event["match_tick"]
        elif event.get("type") == "round_end":
            rounds.setdefault(event["round_index"], {}).update({
                "end": event["match_tick"],
                "winner": event.get("round_winner"),
                "reason": event.get("reason"),
            })
    zero_shot = []
    for index, span in rounds.items():
        count = sum(1 for e in fires if e.get("round_index") == index)
        if count == 0:
            zero_shot.append(index)
    return {
        "seat": seat,
        "shots": len(fires),
        "hits": len(hits),
        "accuracy_percent": (round(100.0 * len(hits) / len(fires), 1)
                              if fires else None),
        "damage": round(sum(e.get("amount", 0.0) for e in hits), 1),
        "kill_events_involving": len(kill_events),
        "kill_credits": len(kill_credits),
        "deaths": len(deaths),
        "reloads": reloads,
        "draws": draws,
        "zero_shot_rounds": zero_shot,
        "rounds": rounds,
    }


def print_event_stats(stats: dict) -> None:
    print(json.dumps({
        "seat": stats["seat"],
        "shots": stats["shots"],
        "hits": stats["hits"],
        "accuracy_percent": stats["accuracy_percent"],
        "damage": stats["damage"],
        "kill_events_involving": stats["kill_events_involving"],
        "kill_credits": stats["kill_credits"],
        "deaths": stats["deaths"],
        "zero_shot_rounds": stats["zero_shot_rounds"],
    }, ensure_ascii=False, indent=2))
    if stats["reloads"]:
        print("\nreload events:")
        for event in stats["reloads"]:
            print(json.dumps({
                k: event.get(k) for k in
                ("type", "match_tick", "round_index", "player", "weapon",
                 "empty", "duration")
            }, ensure_ascii=False))
    if stats["draws"]:
        print("\ndraw events:")
        for event in stats["draws"]:
            print(json.dumps({
                k: event.get(k) for k in
                ("match_tick", "round_index", "player", "weapon")
            }, ensure_ascii=False))


def compact_event(event: dict) -> dict:
    return {key: event.get(key) for key in
            ("type", "match_tick", "round_index", "player", "weapon",
             "empty", "duration")}


def find_round_span(events: list, round_index: int) -> tuple[int, int]:
    start = end = None
    for event in events:
        if event.get("round_index") != round_index:
            continue
        if event.get("type") == "round_start":
            start = event["match_tick"]
        elif event.get("type") == "round_end":
            end = event["match_tick"]
    if start is None or end is None:
        raise QueryError(f"round {round_index} has no start/end events")
    return start, end


def scan_frame_anomalies(frames: list, seat: int) -> dict:
    empty_primary = []
    for frame in frames:
        state = seat_state(frame, seat)
        primary = state["primary"]
        if primary[0] and primary[1] == 0 and primary[2] == 0:
            empty_primary.append(state)
    return {
        "frames": len(frames),
        "primary_zero_zero": len(empty_primary),
        "primary_zero_zero_samples": empty_primary[:20],
    }


def cmd_me(args) -> int:
    client = make_client(args)
    print(json.dumps(my_competition(client, competition(args)),
                     ensure_ascii=False, indent=2))
    return 0


def cmd_round(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    me = my_competition(client, competition_id)
    projection = round_projection(client, competition_id)
    entries = [e for e in list_entries(client, competition_id)
               if e.get("is_mine")]
    board = [e for e in leaderboard(client, competition_id)
             if e.get("is_mine")]
    print(json.dumps({
        "competition_id": competition_id,
        "me": {
            "standing": (me or {}).get("standing"),
            "round_match": (me or {}).get("round_match"),
            "next_round": (me or {}).get("next_round"),
        },
        "round": {
            "round_state": projection.get("round_state"),
            "round_match": projection.get("round_match"),
            "next_round": projection.get("next_round"),
        },
        "my_entry": entries,
        "my_leaderboard": board,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_matches(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    game_id = effective_game_id(args, competition_id)
    matches = [m for m in fps_matches(client, game_id=game_id,
                                      all_pages=args.all)
               if m.get("competition_id") == competition_id]
    for match in matches:
        mine = mine_participant(match)
        seat = mine.get("seat") if mine else None
        print(json.dumps({
            "id": match.get("id"),
            "finished_at": match.get("finished_at"),
            "status": match.get("status"),
            "replay_state": match.get("replay_state"),
            "result": match.get("result"),
            "my_seat": seat,
            "my_seat_position": seat + 1 if seat is not None else None,
            "my_team": participant_team(match, seat),
            "my_seat_label": seat_label(match, seat),
            "replay": replay_link(client, match["id"]),
        }, ensure_ascii=False))
    return 0


def cmd_report(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    game_id = effective_game_id(args, competition_id)
    match, me = find_match(client, competition_id, args.match_id, game_id)
    match_id = match["id"]
    mine = mine_participant(match)
    seat = args.seat if args.seat is not None else (
        mine.get("seat") if mine else None)
    if seat is None:
        raise SystemExit("error: no is_mine participant; pass --seat")

    entries = [e for e in list_entries(client, competition_id)
               if e.get("is_mine")]
    board = [e for e in leaderboard(client, competition_id)
             if e.get("is_mine")]
    projection = round_projection(client, competition_id)

    report = {
        "competition_id": competition_id,
        "round": projection.get("round_match"),
        "next_round": projection.get("next_round"),
        "standing": (me or {}).get("standing"),
        "my_entry": entries,
        "my_leaderboard": board,
        "match": {
            "id": match_id,
            "status": match.get("status"),
            "created_at": match.get("created_at"),
            "finished_at": match.get("finished_at"),
            "result": match.get("result"),
            "my_seat": seat,
            "my_seat_position": seat + 1,
            "my_team": participant_team(match, seat),
            "my_seat_label": seat_label(match, seat),
            "participants": match.get("participants"),
            "replay": replay_link(client, match_id),
        },
    }

    try:
        index = fetch_index(client, match_id)
        static = fetch_static(client, match_id, index)
        events = fetch_events(client, match_id, index)
        report["replay_index"] = {
            "frame_count": index["frame_count"],
            "streams": {
                name: {
                    "chunks": len(layout),
                    "bytes": sum(layout),
                }
                for name, layout in index["meta"].get("layout", {}).items()
            },
        }
        report["map_id"] = static.get("map", {}).get("id")
        report["events"] = {
            "count": len(events),
            "seat": seat,
            "seat_label": seat_label(match, seat),
            "stats": event_stats(events, seat),
        }
    except QueryError as exc:
        report["replay_error"] = str(exc)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=== competition ===")
        print(json.dumps({
            "competition_id": competition_id,
            "round": report["round"],
            "next_round": report["next_round"],
            "standing": report["standing"],
            "my_entry": report["my_entry"],
            "my_leaderboard": report["my_leaderboard"],
        }, ensure_ascii=False, indent=2))
        print("\n=== match ===")
        print(f"seat: {report['match']['my_seat_label']}")
        print(json.dumps(report["match"], ensure_ascii=False, indent=2))
        if "map_id" in report:
            print(f"\nmap: {report['map_id']}")
        if "replay_index" in report:
            print("\n=== replay index ===")
            print(json.dumps(report["replay_index"],
                             ensure_ascii=False, indent=2))
        if "events" in report:
            print("\n=== seat stats ===")
            print_event_stats(report["events"]["stats"])
            stats = report["events"]["stats"]
            empty_primary = [
                e for e in stats["reloads"]
                if e.get("type") == "reload_start" and e.get("empty")]
            print("\n=== badcase notes ===")
            print(f"empty reloads: {len(empty_primary)}"
                  + (f" -> {[e['weapon'] for e in empty_primary]}"
                     if empty_primary else ""))
            print("A (primary 0/0): run `frames --round R`; events do not "
                  "expose reserve.")
            print("B: check whether a draw to secondary happens between "
                  "reload_start and reload_finish.")
            print("C: check whether fire resumes after reload_finish.")
        if "replay_error" in report:
            print(f"\nreplay error: {report['replay_error']}")
    return 0


def cmd_events(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    game_id = effective_game_id(args, competition_id)
    match, _ = find_match(client, competition_id, args.match_id, game_id)
    seat = args.seat if args.seat is not None else (
        (mine_participant(match) or {}).get("seat"))
    if seat is None:
        raise SystemExit("error: no is_mine participant; pass --seat")
    index = fetch_index(client, match["id"])
    events = fetch_events(client, match["id"], index)
    stats = event_stats(events, seat)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(f"wrote {len(events)} events to {args.out}", file=sys.stderr)
    if args.json:
        print(json.dumps({
            **stats,
            "seat_position": seat + 1,
            "team": participant_team(match, seat),
            "seat_label": seat_label(match, seat),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"seat: {seat_label(match, seat)}")
        print_event_stats(stats)
    return 0


def cmd_frames(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    game_id = effective_game_id(args, competition_id)
    match, _ = find_match(client, competition_id, args.match_id, game_id)
    seat = args.seat if args.seat is not None else (
        (mine_participant(match) or {}).get("seat"))
    if seat is None:
        raise SystemExit("error: no is_mine participant; pass --seat")
    index = fetch_index(client, match["id"])
    events = fetch_events(client, match["id"], index)

    if args.round is not None:
        start_tick, end_tick = find_round_span(events, args.round)
    elif args.start_tick is not None and args.end_tick is not None:
        start_tick, end_tick = args.start_tick, args.end_tick
    else:
        raise SystemExit("error: pass --round or both --start-tick/--end-tick")

    frames = fetch_frames(client, match["id"], index, start_tick, end_tick)
    if not frames:
        raise QueryError(f"no frames in ticks {start_tick}..{end_tick}")

    stats = event_stats(events, seat)
    reloads = [event for event in stats["reloads"]
               if args.round is None or event.get("round_index") == args.round]
    draws = [event for event in stats["draws"]
             if args.round is None or event.get("round_index") == args.round]
    summary = {
        "match_id": match["id"],
        "seat": seat,
        "seat_position": seat + 1,
        "team": participant_team(match, seat),
        "seat_label": seat_label(match, seat),
        "round": args.round,
        "ticks": [start_tick, end_tick],
        "frame_count": len(frames),
        "anomalies": scan_frame_anomalies(frames, seat),
        "reloads": [compact_event(event) for event in reloads],
        "draws": [compact_event(event) for event in draws],
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            for frame in frames:
                handle.write(json.dumps(frame, ensure_ascii=False) + "\n")
        print(f"wrote {len(frames)} frames to {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps({
            "summary": summary,
            "samples": [seat_state(frame, seat)
                        for frame in frames[::max(1, int(24 * args.every))]],
        }, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\ntime tick round phase alive pos active weapon "
          "primary_ammo/reserve secondary_ammo/reserve activity")
    stride = max(1, int(24 * args.every))
    for frame in frames[::stride]:
        state = seat_state(frame, seat)
        print(json.dumps(state, ensure_ascii=False))
    return 0


def cmd_replay(args) -> int:
    client = make_client(args)
    competition_id = competition(args)
    game_id = effective_game_id(args, competition_id)
    match, _ = find_match(client, competition_id, args.match_id, game_id)
    index = fetch_index(client, match["id"])
    print(json.dumps({
        "match_id": match["id"],
        "frame_count": index["frame_count"],
        "version": index["version"],
        "layout": index["meta"].get("layout"),
        "replay": replay_link(client, match["id"]),
    }, ensure_ascii=False, indent=2))
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        static = fetch_static(client, match["id"], index)
        events = fetch_events(client, match["id"], index)
        (out / "static.json").write_text(
            json.dumps(static, ensure_ascii=False, indent=2) + "\n")
        (out / "events.jsonl").write_text(
            "".join(json.dumps(event, ensure_ascii=False) + "\n"
                    for event in events))
        print(f"wrote static.json and events.jsonl to {out}", file=sys.stderr)
    return 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    try:
        os.chmod(temporary, mode)
    except OSError:
        pass
    os.replace(temporary, path)


def write_snapshot(path: Path, data: dict, account_key: str) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if account_key and account_key in text:
        raise QueryError(
            f"refusing to write a snapshot containing an API key: {path}")
    atomic_write_text(path, text)


def registration_data(client, competition_id: str) -> dict:
    path = (
        "/api/v1/python-submissions/competitions/"
        + quote(competition_id)
        + "/registration"
    )
    status, _, raw = client.request("GET", path)
    data = AGX.decode_json(raw)
    if status == 200 and isinstance(data, dict):
        return data
    if status in {401, 403}:
        raise QueryError(f"GET {path} -> HTTP {status} (auth)")
    return {"registered": False, "status": status, "detail": data}


def competition_matches(client, competition_id: str, game_id: str,
                        all_pages: bool = True):
    return [
        match for match in fps_matches(
            client, game_id=game_id, all_pages=all_pages)
        if match.get("competition_id") == competition_id
    ]


def compact_match(client, match: dict) -> dict:
    mine = mine_participant(match)
    seat = mine.get("seat") if mine else None
    return {
        "id": match.get("id"),
        "status": match.get("status"),
        "created_at": match.get("created_at"),
        "finished_at": match.get("finished_at"),
        "result": match.get("result"),
        "replay_state": match.get("replay_state"),
        "my_seat": seat,
        "my_seat_position": seat + 1 if seat is not None else None,
        "my_team": participant_team(match, seat),
        "my_seat_label": seat_label(match, seat),
        "replay": replay_link(client, match["id"]) if match.get("id") else None,
    }


def sorted_mine_matches(client, competition_id: str, game_id: str):
    matches = competition_matches(client, competition_id, game_id, True)
    mine = [match for match in matches if mine_participant(match)]
    mine.sort(
        key=lambda match: (
            match.get("finished_at") or match.get("created_at") or ""),
        reverse=True,
    )
    return mine


def collect_replays(client, account, matches: list[dict], seat: int | None,
                    account_dir: Path, limit: int,
                    game_id: str = FPS) -> list[dict]:
    selected = matches if limit == 0 else matches[:limit]
    results = []
    for match in selected:
        match_id = match.get("id")
        if not match_id:
            continue
        mine = mine_participant(match)
        my_seat = seat if seat is not None else (
            mine.get("seat") if mine else None)
        item = {
            "match_id": match_id,
            "seat": my_seat,
            "seat_position": (my_seat + 1
                              if my_seat is not None else None),
            "team": participant_team(match, my_seat),
            "seat_label": seat_label(match, my_seat),
            "files": {},
        }
        try:
            index = fetch_index(client, match_id)
            static = fetch_static(client, match_id, index)
            events = fetch_events(client, match_id, index)
            match_dir = account_dir / "matches" / str(match_id)
            write_snapshot(match_dir / "replay_index.json", {
                "match_id": match_id,
                "version": index["version"],
                "frame_count": index["frame_count"],
                "layout": index["meta"].get("layout"),
            }, account.key)
            write_snapshot(match_dir / "static.json", static, account.key)
            events_text = "".join(
                json.dumps(event, ensure_ascii=False) + "\n"
                for event in events)
            if account.key and account.key in events_text:
                raise QueryError(
                    "refusing to write events containing an API key: "
                    f"{match_dir}")
            atomic_write_text(match_dir / "events.jsonl", events_text)
            item["frame_count"] = index["frame_count"]
            item["files"] = {
                "replay_index": str(match_dir / "replay_index.json"),
                "static": str(match_dir / "static.json"),
                "events": str(match_dir / "events.jsonl"),
            }
            if my_seat is not None and game_id == FPS:
                item["stats"] = event_stats(events, my_seat)
        except QueryError as exc:
            item["error"] = str(exc)
        results.append(item)
    return results


def collect_account(account, args) -> dict:
    base = (args.base_url or account.base_url or "").strip()
    competition_id = AGX.resolve_competition_id(
        args.competition_id,
        account=account,
        game_id=args.game_id,
        environ=os.environ,
    )
    game_id = effective_game_id(args, competition_id)
    snapshot = {
        "schema_version": 1,
        "collected_at": utc_now(),
        "account": AGX.public_account(account),
        "game_id": game_id,
        "competition_id": competition_id,
        "agent_id": args.agent_id or account.agent_id,
        "errors": [],
        "warnings": [],
    }
    if not account.key:
        snapshot["errors"].append("missing API key")
        return snapshot
    if not base:
        snapshot["errors"].append(
            f"no base URL; set RSI_URL or "
            f"RSI_ACCOUNT_{account.name.upper()}_URL")
        return snapshot
    if not base.startswith(("http://", "https://")):
        snapshot["errors"].append(
            f"base URL must start with http:// or https://: {base!r}")
        return snapshot
    snapshot["base_url"] = base
    client = AGX.Client(base, account.key)

    try:
        snapshot["me"] = my_competition(client, competition_id)
    except QueryError as exc:
        snapshot["errors"].append(f"me/competitions: {exc}")
    try:
        registration = registration_data(client, competition_id)
        snapshot["registration"] = registration
        if not args.agent_id:
            snapshot["agent_id"] = (
                registration.get("agent_id") or account.agent_id)
    except QueryError as exc:
        snapshot["errors"].append(f"registration: {exc}")
    try:
        snapshot["round"] = round_projection(client, competition_id)
    except QueryError as exc:
        snapshot["errors"].append(f"round: {exc}")
    try:
        entries = list_entries(client, competition_id)
        snapshot["my_entries"] = [
            entry for entry in entries if entry.get("is_mine")]
    except QueryError as exc:
        snapshot["errors"].append(f"entries: {exc}")
    try:
        board = leaderboard(client, competition_id)
        snapshot["my_leaderboard"] = [
            entry for entry in board if entry.get("is_mine")]
    except QueryError as exc:
        snapshot["errors"].append(f"leaderboard: {exc}")

    mine: list[dict] = []
    try:
        mine = sorted_mine_matches(client, competition_id, game_id)
        snapshot["matches"] = [compact_match(client, match) for match in mine]
        snapshot["matches_total"] = len(mine)
    except QueryError as exc:
        snapshot["errors"].append(f"matches: {exc}")
        snapshot["matches"] = []
        snapshot["matches_total"] = 0

    if args.replays:
        selected = mine if args.match_limit == 0 else mine[:args.match_limit]
        snapshot["replays_total"] = len(selected)
        if len(selected) < len(mine):
            snapshot["replays_truncated"] = len(mine) - len(selected)
        account_dir = (
            Path(args.data_dir).expanduser().resolve() / account.name)
        snapshot["replays"] = collect_replays(
            client, account, selected, args.seat, account_dir,
            args.match_limit, game_id)
        if any(item.get("error") for item in snapshot["replays"]):
            snapshot["warnings"].append(
                "some replays failed; see replay errors")
    return snapshot


def cmd_collect(args) -> int:
    if args.match_limit < 0:
        raise QueryError("--match-limit must be >= 0")
    accounts = AGX.discover_accounts()
    selected = AGX.select_accounts_for_cli(
        accounts,
        account=args.account,
        accounts_arg=args.accounts,
        all_accounts=args.all_accounts,
        default_all=True,
        environ=os.environ,
        require_keys=False,
    )
    if args.agent_id and len(selected) > 1:
        raise AGX.AccountError(
            "--agent-id is account-scoped; select a single account")
    if args.seat is not None and len(selected) > 1:
        raise AGX.AccountError(
            "--seat is account-scoped; select a single account")
    duplicates = AGX.duplicate_key_groups(selected)
    if duplicates:
        detail = "; ".join(
            f"{', '.join(names)} -> {fingerprint}"
            for fingerprint, names in duplicates.items())
        print(
            f"warning: selected accounts share an API key: {detail}",
            file=sys.stderr,
        )

    data_root = Path(args.data_dir).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": 1,
        "collected_at": utc_now(),
        "data_dir": str(data_root),
        "accounts": [],
    }
    failed = False
    for account in selected:
        try:
            snapshot = collect_account(account, args)
        except Exception as exc:
            snapshot = {
                "schema_version": 1,
                "collected_at": utc_now(),
                "account": AGX.public_account(account),
                "errors": [f"{type(exc).__name__}: {exc}"],
                "warnings": [],
            }
        account_dir = (data_root / account.name).resolve()
        try:
            account_dir.relative_to(data_root)
        except ValueError:
            raise AGX.AccountError(
                f"account directory escapes the data root: "
                f"{account.name!r}")
        account_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ")
        history_path = account_dir / "snapshots" / f"{timestamp}.json"
        latest_path = account_dir / "snapshot.json"
        write_snapshot(history_path, snapshot, account.key)
        write_snapshot(latest_path, snapshot, account.key)
        errors = list(snapshot.get("errors") or [])
        summary = {
            "name": account.name,
            "key_fingerprint": account.fingerprint,
            "ok": not errors,
            "snapshot": str(latest_path),
            "history": str(history_path),
            "matches": snapshot.get("matches_total"),
            "agent_id": snapshot.get("agent_id"),
            "standing": ((snapshot.get("me") or {}).get("standing")),
            "errors": errors,
        }
        index["accounts"].append(summary)
        if errors:
            failed = True
        if not args.json:
            if errors:
                print(
                    f"{account.name}: incomplete "
                    f"({len(errors)} errors) -> {latest_path}",
                    file=sys.stderr,
                )
                for error in errors:
                    print(f"  {error}", file=sys.stderr)
            else:
                print(
                    f"{account.name}: wrote {latest_path} "
                    f"({snapshot.get('matches_total', 0)} matches)",
                    file=sys.stderr,
                )
    index["ok"] = not failed
    write_snapshot(data_root / "index.json", index, "")
    if args.json:
        print(json.dumps(index, ensure_ascii=False, indent=2))
    return 2 if failed else 0


def kd_match(client, match: dict, seat: int | None = None) -> dict:
    mine = mine_participant(match)
    actual_seat = seat if seat is not None else (
        mine.get("seat") if mine else None)
    item = {
        "match_id": match.get("id"),
        "finished_at": match.get("finished_at"),
        "seat": actual_seat,
        "seat_position": (
            actual_seat + 1 if actual_seat is not None else None),
        "team": (participant_team(match, actual_seat)
                 if actual_seat is not None else None),
        "seat_label": (seat_label(match, actual_seat)
                       if actual_seat is not None else None),
        "result": match.get("result"),
    }
    if actual_seat is None:
        item["error"] = "no is_mine participant; pass --seat"
        return item
    try:
        index = fetch_index(client, match["id"])
        static = fetch_static(client, match["id"], index)
        events = fetch_events(client, match["id"], index)
        stats = event_stats(events, actual_seat)
        kills, deaths = stats["kill_credits"], stats["deaths"]
        item.update({
            "map_id": (static.get("map") or {}).get("id"),
            "kills": kills,
            "deaths": deaths,
            "kd": round(kills / deaths, 2) if deaths else None,
            "shots": stats["shots"],
            "hits": stats["hits"],
            "accuracy_percent": stats["accuracy_percent"],
            "damage": stats["damage"],
            "rounds": len(stats["rounds"]),
        })
    except QueryError as exc:
        item["error"] = str(exc)
    return item


def kd_result_text(item: dict) -> str:
    result = item.get("result") or {}
    scores = result.get("round_wins") or []
    team = item.get("team")
    winner = result.get("winner")
    if team not in (0, 1) or len(scores) < 2:
        return ""
    opponent = 1 - team
    outcome = "W" if winner == team else "L"
    return f"{outcome} {scores[team]}-{scores[opponent]}"


def kd_account(account, args) -> dict:
    base = (args.base_url or account.base_url or "").strip()
    entry = {
        "name": account.name,
        "key_fingerprint": account.fingerprint,
        "agent_id": args.agent_id or account.agent_id,
        "base_url": base or None,
        "matches": [],
        "errors": [],
    }
    if not account.key:
        entry["errors"].append("missing API key")
        return entry
    if not base:
        entry["errors"].append(
            f"no base URL; set RSI_URL or "
            f"RSI_ACCOUNT_{account.name.upper()}_URL")
        return entry
    if not base.startswith(("http://", "https://")):
        entry["errors"].append(
            f"base URL must start with http:// or https://: {base!r}")
        return entry
    try:
        competition_id = AGX.resolve_competition_id(
            args.competition_id,
            account=account,
            game_id=args.game_id,
            environ=os.environ,
        )
    except AGX.AccountError as exc:
        entry["errors"].append(str(exc))
        return entry
    game_id = effective_game_id(args, competition_id)
    entry["competition_id"] = competition_id
    entry["game_id"] = game_id
    client = AGX.Client(base, account.key)
    try:
        if args.match_id:
            match, _ = find_match(
                client, competition_id, args.match_id, game_id)
            matches = [match]
        else:
            matches = sorted_mine_matches(
                client, competition_id, game_id)[:args.match_limit]
        if not matches:
            entry["errors"].append("no finished matches")
    except QueryError as exc:
        entry["errors"].append(str(exc))
        matches = []
    for match in matches:
        item = kd_match(client, match, args.seat)
        entry["matches"].append(item)
        if item.get("error"):
            entry["errors"].append(
                f"{item.get('match_id')}: {item['error']}")
    played = [item for item in entry["matches"] if not item.get("error")]
    kills = sum(item.get("kills", 0) for item in played)
    deaths = sum(item.get("deaths", 0) for item in played)
    entry["aggregate"] = {
        "matches": len(played),
        "kills": kills,
        "deaths": deaths,
        "kd": round(kills / deaths, 2) if deaths else None,
    }
    return entry


def cmd_kd(args) -> int:
    if args.match_limit < 1:
        raise QueryError("--match-limit must be >= 1")
    accounts = AGX.discover_accounts()
    selected = AGX.select_accounts_for_cli(
        accounts,
        account=args.account,
        accounts_arg=args.accounts,
        all_accounts=args.all_accounts,
        default_all=True,
        environ=os.environ,
        require_keys=False,
    )
    if args.agent_id and len(selected) > 1:
        raise AGX.AccountError(
            "--agent-id is account-scoped; select a single account")
    if args.seat is not None and len(selected) > 1:
        raise AGX.AccountError(
            "--seat is account-scoped; select a single account")
    duplicates = AGX.duplicate_key_groups(selected)
    if duplicates:
        detail = "; ".join(
            f"{', '.join(names)} -> {fingerprint}"
            for fingerprint, names in duplicates.items())
        print(
            f"warning: selected accounts share an API key: {detail}",
            file=sys.stderr,
        )
    report = {"accounts": [], "ok": True}
    for account in selected:
        entry = kd_account(account, args)
        report["accounts"].append(entry)
        if entry["errors"]:
            report["ok"] = False
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2
    for entry in report["accounts"]:
        aggregate = entry.get("aggregate") or {}
        if not entry["matches"]:
            for error in entry["errors"]:
                print(f"{entry['name']}: error: {error}", file=sys.stderr)
            continue
        kd_value = aggregate.get("kd")
        pooled = ("inf" if kd_value is None and aggregate.get("kills")
                  else kd_value)
        print(f"{entry['name']}: K/D {aggregate.get('kills', 0)}/"
              f"{aggregate.get('deaths', 0)} = {pooled} "
              f"across {aggregate.get('matches', 0)} match(es)")
        for item in entry["matches"]:
            if item.get("error"):
                print(f"  {item.get('match_id')}: error: {item['error']}",
                      file=sys.stderr)
                continue
            ratio = item.get("kd")
            ratio_text = "inf" if ratio is None and item.get("kills") else ratio
            outcome = kd_result_text(item)
            print(f"  {item['match_id']}  {item.get('map_id') or '?'}  "
                  f"{item.get('finished_at') or '?'}  {outcome}  "
                  f"K/D {item.get('kills')}/{item.get('deaths')} = "
                  f"{ratio_text}  {item.get('seat_label')}  "
                  f"shots {item.get('shots')} hits {item.get('hits')} "
                  f"acc {item.get('accuracy_percent')}%  "
                  f"damage {item.get('damage')}  "
                  f"rounds {item.get('rounds')}")
    return 0 if report["ok"] else 2


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, *, multi=False):
        selectors = p.add_mutually_exclusive_group()
        selectors.add_argument(
            "--account", default=None,
            help="account name (default: RSI_ACCOUNT or main)")
        if multi:
            selectors.add_argument(
                "--accounts", default=None,
                help="comma-separated account names")
            selectors.add_argument(
                "--all-accounts", action="store_true",
                help="use every configured account")
        p.add_argument("--base-url", default=None)
        p.add_argument("--competition-id", default=None)
        p.add_argument("--agent-id", default=None)
        p.add_argument("--game-id", default=None)
        p.add_argument("--match-id")
        p.add_argument("--seat", type=int)

    me = sub.add_parser("me", help="current user competitions")
    common(me); me.set_defaults(func=cmd_me)

    rnd = sub.add_parser("round", help="round projection and my standing")
    common(rnd); rnd.set_defaults(func=cmd_round)

    matches = sub.add_parser("matches", help="list FPS matches")
    common(matches)
    matches.add_argument("--all", action="store_true")
    matches.set_defaults(func=cmd_matches)

    report = sub.add_parser(
        "report", help="latest match summary + public replay stats")
    common(report)
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)

    events = sub.add_parser("events", help="public events and seat stats")
    common(events)
    events.add_argument("--json", action="store_true")
    events.add_argument("--out")
    events.set_defaults(func=cmd_events)

    frames = sub.add_parser(
        "frames", help="public frames for a seat in a round / tick range")
    common(frames)
    frames.add_argument("--round", type=int)
    frames.add_argument("--start-tick", type=int)
    frames.add_argument("--end-tick", type=int)
    frames.add_argument("--every", type=float, default=1.0,
                        help="print one sample every N seconds")
    frames.add_argument("--json", action="store_true")
    frames.add_argument("--out")
    frames.set_defaults(func=cmd_frames)

    replay = sub.add_parser("replay", help="public recording index summary")
    common(replay)
    replay.add_argument("--out-dir")
    replay.set_defaults(func=cmd_replay)

    kd = sub.add_parser(
        "kd", help="latest-match K/D for one or all accounts")
    common(kd, multi=True)
    kd.add_argument(
        "--match-limit", type=int, default=1,
        help="recent matches per account (default: 1)")
    kd.add_argument("--json", action="store_true")
    kd.set_defaults(func=cmd_kd)

    collect = sub.add_parser(
        "collect", help="collect per-account snapshots under data/accounts")
    common(collect, multi=True)
    collect.add_argument(
        "--data-dir", default=str(DEFAULT_DATA_DIR),
        help="snapshot root (default: repo-root data/accounts)")
    collect.add_argument(
        "--replays", action="store_true",
        help="fetch public static/events for recent mine matches")
    collect.add_argument(
        "--match-limit", type=int, default=20,
        help="latest mine matches for --replays; 0 = all")
    collect.add_argument("--json", action="store_true")
    collect.set_defaults(func=cmd_collect)

    return parser


def main() -> int:
    AGX.load_dotenv()
    parser = make_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except AGX.AccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

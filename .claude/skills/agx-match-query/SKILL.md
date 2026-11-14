---
name: agx-match-query
description: Read-only AGX FPS match and public-replay query skill. Use to find the user's latest match, report round/standing/result, inspect public replay events and frames for a seat, check movement/empty-primary badcases, and compute per-version observability metrics (participation, accuracy, site reach, rotation). Reuses the agx-submit credentials; never uploads or activates anything.
---

# AGX match query

Read-only. Do **not** upload, activate, or mutate competition state. This
skill shares `RSI_URL` / the account API key with `agx-submit` and only
contacts the explicitly configured base URL.

## Inputs

- `RSI_URL` (or `--base-url`) — required unless the selected account has
  `RSI_ACCOUNT_<NAME>_URL`.
- Account API key — `RSI_ACCOUNT_API_KEY` (default account `main`),
  `RSI_ACCOUNT_<NAME>_API_KEY`, macOS Keychain `agx-api-key` /
  `agx-api-key-<name>`, or repo `.env`; never print it.
- `--account NAME` selects an account. Without it, `RSI_ACCOUNT` wins, then
  `main`, then a sole configured account; an ambiguous choice is an error.
  `collect` and `kd` default to **all** configured accounts.
- `RSI_COMPETITION_ID` — defaults to the FPS competition in `.env`;
  `RSI_ACCOUNT_<NAME>_COMPETITION_ID` can override per account.
  Competition aliases live in `RSI_COMPETITION_<GAME>` (for example
  `RSI_COMPETITION_FPS` / `RSI_COMPETITION_RACING`); use
  `--game-id fps|racing` or `--competition-id fps|racing` instead of UUIDs.
- Optional: `RSI_AGENT_ID` (`main` only), `--match-id`, `--seat`.
  `--agent-id` / `--seat` are rejected for multi-account `collect` / `kd`.

Account listing and read-only live checks live in the submit skill:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --json
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check
```

If the URL or a selected key is missing, stop and ask the user to configure
them. Only contact the explicitly configured URL.

## Commands

Match commands are under
`.claude/skills/agx-match-query/scripts/agx_matches.py`.  The aggregate
observability script is `agx_observe.py` (see below).

```sh
# What has my account got? Current/next round, my standing.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py round

# Same for a named account.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py round \
  --account alice
# Another game (competition resolved from RSI_COMPETITION_RACING):
python3 .claude/skills/agx-match-query/scripts/agx_matches.py round \
  --account alice --game-id racing

# Most recent match: round state, result, my entry/version, replay link,
# map, public-event seat stats, zero-shot rounds, reload/draw events.
# The human output prints my_seat_label:
#   seat 7 (0-based) = team 1 = 第 8 个玩家
python3 .claude/skills/agx-match-query/scripts/agx_matches.py report

# Same, for a specific match and seat.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py report \
  --match-id da110811-9f35-4c86-9492-b322b1302391 --seat 7

# Quick K/D from public events: latest finished match for every configured
# account (kills/deaths, K/D, score, map, shots/hits/accuracy/damage).
# Use --match-limit N for recent matches with a pooled K/D, or --match-id.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py kd
python3 .claude/skills/agx-match-query/scripts/agx_matches.py kd \
  --account main --match-limit 5
python3 .claude/skills/agx-match-query/scripts/agx_matches.py kd \
  --account account2 --match-id <id> --json

# List FPS matches; mine carry my_seat, my_seat_position, my_team, and
# my_seat_label (e.g. "seat 7 (0-based) = team 1 = 第 8 个玩家").
python3 .claude/skills/agx-match-query/scripts/agx_matches.py matches

# Public event stream + seat stats (writes JSONL with --out).
python3 .claude/skills/agx-match-query/scripts/agx_matches.py events \
  --match-id <id> --seat 7

# Public frames for one round / tick range.  `--every` only controls
# printing; every frame in the range is still used for anomalies.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id <id> --seat 7 --round 7 --every 5

# Tighter range (recommended for large scans).
python3 .claude/skills/agx-match-query/scripts/agx_matches.py frames \
  --match-id <id> --seat 7 --start-tick 62200 --end-tick 62500

# Public recording index summary; optionally export static + events.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py replay \
  --match-id <id> --out-dir /tmp/agx-replay

# Multi-account data collection (read-only).  No selector = all accounts.
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect --replays
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect \
  --account alice --replays --match-limit 5
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect \
  --accounts alice,bob --json
# Another game/competition (for example racing); no UUID needed:
python3 .claude/skills/agx-match-query/scripts/agx_matches.py collect \
  --game-id racing --replays
# A named account's default competition comes from
# RSI_ACCOUNT_<NAME>_COMPETITION_ID; --game-id overrides it.

# Aggregate observability metrics for collected matches (read-only).
# Prints a "seat mapping" block: seat N (0-based) = team T = 第 N+1 个玩家.
# Requires `collect --replays` first.  Movement metrics sample public frames
# at 2 s; use --no-frames for event-only combat/accuracy metrics.
python3 .claude/skills/agx-match-query/scripts/agx_observe.py \
  --match main:36cf9b6c-78ec-469f-b008-daca03bf0e73:v0.02-main \
  --match main:da110811-9f35-4c86-9492-b322b1302391:v0.01 \
  --out data/analysis/2026-11-12-observability.json
# The summary always includes a per-map / per-side line such as
#   dust2-cs2-v54 v0.02-main attack reach=4/9 stuck=5/9 | defend reach=12/12 ...
# JSON also contains top-level `by_map`.  Use the same `:LABEL` on multiple
# matches to get one pooled `aggregate` entry for that code version.
```

`report`, `frames`, `events`, and `collect` accept `--json` for
machine-readable output. `frames` also accepts `--out` to save the selected
frames as JSONL.

`collect` writes under the repo-root `data/accounts/` (gitignored; override
with `--data-dir`):

```
data/accounts/index.json                 # run summary for every account
data/accounts/<name>/snapshot.json       # latest snapshot
data/accounts/<name>/snapshots/<UTC>.json
data/accounts/<name>/matches/<match_id>/ # only with --replays
  replay_index.json
  static.json
  events.jsonl
```

Each snapshot contains `me/competitions`, registration, round projection,
`is_mine` entries / leaderboard, compact `is_mine` matches, and per-match
replay summaries with `event_stats`. It contains only the account name,
fingerprint, and key source — never the API key. `--match-limit` controls how
many recent mine matches get replays (default 20; `0` = all); truncation is
recorded. Full public frames are still fetched on demand with `frames`.

## API and replay facts (verified 2026-11-12)

- `GET /api/v1/competitions/{id}/entries` and `/leaderboard` work without
  query params. Passing `mine=True` / `agent_id=...` returned **404** on the
  live deployment; fetch all and filter `is_mine` locally. The default page is
  only 30 items, so use `limit=100&offset=…` and paginate; on 2026-11-12 the
  racing competition had 33 entries and `is_mine` only appeared on the second
  page. The helper now paginates automatically.
- `is_mine`, standings, versions, and matches are relative to the
  authenticated account. There is no cross-account flag: `collect` and
  `accounts --check` issue requests separately for each account key and never
  copy one account's `is_mine` data to another.
- Seats are **0-based** in participants, observations, and `--seat`; the web
  viewer's "第 N 个玩家" is `seat + 1`.  All match outputs now include
  `seat_label`, `*_seat_position`, and the participant team.
- `GET /api/v1/python-submissions/competitions/{id}/registration` returns
  `{registered, agent_id}` and is safe for read-only checks.
- `GET /api/v1/matches?game_id=fps&limit=100&offset=0` works and returns
  finished FPS replays. Passing `competition_id=...` returned **404**;
  filter `competition_id` locally. Without `game_id`, the list is dominated
  by other games.
- `GET /api/v1/competitions/{id}/matches` is **404**; use `/api/v1/matches`.
- `GET /api/v1/jobs/{job_id}/replay*` is **404** for this account even when
  the match shows `replay_state=available`. The public Python recording is:
  - `GET /api/v1/python-submissions/recordings/{match_id}/replay/index`
  - `GET .../replay/streams/{stream}/chunks/{i}` for
    `public_static`, `public_events`, `public_frames`.
- The current round's `round_match.job_id` is the match id. The web viewer
  route is `https://agx.cool/#/jobs/{match_id}` (the `/matches/{id}` URL
  redirects there).
- `/api/v1/me/competitions` may show `current_version: null`; use the
  entry's `version` and the match's `python_version` instead.
- The public replay is a **public projection**, not the private decision
  trace. `private_decisions` is not in the public index; do not claim to
  have per-seat legal observations or agent actions from it.

## Recording index format

The `/replay/index` response is:

```
AGXI2 | version u8 | frame_count u32 LE | meta_len u32 LE
      | meta JSON (meta_len bytes)
      | frame_count × 32-byte records
```

Each 32-byte record observed on 2026-11-12:

```
f64 LE time_seconds | u64 LE byte_offset | u32 LE frame_length | 12 reserved
```

`meta["layout"]` gives the chunk sizes for each stream. Public frame chunks
are 1,048,576 bytes; concatenate and slice using the frame records. Frames
are NDJSON with `match_tick`, `round_index`, `phase`, `players[]`, and full
public player state. The player object includes `weapons[0..2]` with
`ammo`, `reserve`, `reload_until`, plus `active_slot`, `weapon_id`,
`x/y/z/yaw`, `speed`, `activity`, `switch_until`, etc. This is enough to
check empty-primary / stuck badcases without the 1.63 GB of full frames if
you target a round or tick range.

`public_events` is NDJSON (`fire`, `hit`, `kill`, `reload_*`, `draw`,
`item_create`, `buy`, `round_start/end`, `match_end`, ...). `public_static`
is one JSON object with the map (`sites`, `nav`, `spawns`, `plant_zones`,
`route_landmarks`, ...).

## Output rules

- **Always state the seat in both conventions when reporting a match.**
  The API and agent observations use a **0-based** seat; the web viewer
  shows the **1-based** position among the ten players (= seat + 1).
  `matches`, `report`, `events`, `frames`, and `collect --replays` expose
  `seat_label` for exactly this:

  ```text
  seat 7 (0-based) = team 1 = 第 8 个玩家
  ```

  Examples: main seat 6 → team 1 → 第 7 个玩家；account2 seat 7 → team 1 →
  第 8 个玩家.  Never report only the 1-based position or omit the team;
  quote the 0-based seat as well, because that is the number the user
  reports.
- Report only what the API / public replay confirms. Upload/admission
  success is not a match result; a replay frame is not a private decision.
- Distinguish `is_mine` and seat from the match participant; never assume
  the user is seat 7. When reporting multiple accounts, label every result
  with its account name; do not mix seats or standings across accounts.
- When the public events cannot answer a question (ammo/reserve, private
  observations), say so and use `frames` for the public state.
- `collect` mutates only the local `data/accounts/` tree (gitignored). It
  never uploads, activates, or changes competition state, and never writes a
  key into a snapshot. `--agent-id` / `--seat` selectors are single-account
  only.
- `agx_observe.py` writes only the requested `--out` JSON and reads public
  frames; it never uploads or activates.  A match whose `lobby_fires` is 0 is
  marked `lobby_zero_combat`: do not use it for combat/accuracy/rotation
  conclusions, even though movement/site metrics remain observable.
- Metrics and verdict rules are defined in
  [11-12-match-observability.md](../../../docs/spec/11-12-match-observability.md).
- Related badcases:
  [11-12-empty-primary-switch-reload.md](../../../docs/spec/11-12-empty-primary-switch-reload.md)
  and
  [11-12-stuck-at-spawn.md](../../../docs/spec/11-12-stuck-at-spawn.md).

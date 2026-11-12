---
name: agx-submit
description: Build, validate, and submit this repo's Python FPS agent to an AGX competition via the Account API; poll admission, verify the immutable version, and archive the submission with a change note.
---

# AGX FPS submission

Use this skill for the AGX competition `2a97f94f-816a-52b7-b4b8-5925db160245` (FPS bomb mode) and for later versions of this agent.

## Required inputs

- `RSI_URL`: the base URL of the user's AGX instance. It has no safe default — never guess or substitute a search result.
- Account API key: read from `RSI_ACCOUNT_API_KEY`, the macOS Keychain item `agx-api-key`, or the repo-root `.env`. The helper loads `.env` from the cwd or repo root first; `.env` is gitignored and must be `chmod 600`. Never echo, print, log, commit, or pass the key on a command line.
- `RSI_COMPETITION_ID`: defaults to `2a97f94f-816a-52b7-b4b8-5925db160245`; it is already set in the local `.env`.
- Submission tree: defaults to the repository root, with `agent.py` at the root.
- `RSI_AGENT_ID`: only if the Python submission flow cannot discover it from the live API.

If the base URL or key is missing, stop and ask the user to configure them. Never ask for an account password.

## Credential setup

Preferred: store the key in the macOS Keychain (the user runs this themselves, outside the repository):

```sh
printf "AGX API key: "; read -r -s K; echo
security add-generic-password -U -a "$USER" -s agx-api-key -w "$K"
unset K
```

The helper reads that Keychain item without printing it. Alternatively, the user may edit the local `.env`:

```sh
chmod 600 .env
# fill RSI_URL and RSI_ACCOUNT_API_KEY in .env
```

`.env` is gitignored and must never be committed. The base URL is not secret; ask the user to paste it or put it in `RSI_URL`.

## Safety and evidence rules

- Do read-only discovery first. Show the user the game, competition, rules version, and contract before uploading.
- Before upload, show the ZIP manifest, file hashes, and total size. The user's request to submit authorizes the upload, but show what will be submitted.
- Access only the explicitly configured `RSI_URL`.
- Do not retry 4xx except 429. On 401/403 stop and ask for a new key. On 409 reuse the existing version/code hash; never bypass idempotency.
- Keep the same `Idempotency-Key` and exact body when retrying an upload whose response was lost.
- Admission or upload-check success is not a full match, score, or win. Report only what the API confirms.
- The live Python flow is under `/api/v1/python-submissions` and is **not** in `/api/openapi.json`. The routes verified on 2026-11-12 are:
  - `POST /api/v1/python-submissions/agents` `{game_id}` → `{id}`
  - `GET /api/v1/python-submissions/templates/{game_id}` → `{profile, files}`
  - `GET /api/v1/python-submissions/competitions/{competition_id}/registration` → `{registered, agent_id}`
  - `POST /api/v1/python-submissions/agents/{agent_id}/bundles` (binary ZIP, `Idempotency-Key`)
  - `GET /api/v1/python-submissions/bundles/{bundle_id}` → receipt (`admission: queued/running/passed/failed`)
  - `POST /api/v1/python-submissions/competitions/{competition_id}/versions` `{submission_id, auto_match: true}`
- Do not rely on the JS `example_code`/baseline to infer the submission language; the Python template is the authority for Python.
- The current baseline is not verified against the live competition. See `docs/spec/baseline-compatibility.md`. The account guide's "战术爆破赛制" may differ from the `rsi-fps-5.5` doc; always trust the live `GET /games/{game_id}` and `GET /competitions/{id}`.

## Workflow

### 1. Discover (read-only)

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py discover \
  --base-url "$RSI_URL" --competition-id "$RSI_COMPETITION_ID"
```

Confirm:

- `GET /api/v1/games` contains the FPS game; record its `id`, `participant_count`, `teams`, `roles`, `rules_version`, and `limits`.
- `GET /api/v1/competitions/{id}` matches the competition and game; record `rules_version`, `status`, and `match_interval_seconds`.
- The live rules match `docs/spec` and `docs/rules`. If the competition uses a different rules version, do not assume `rsi-fps-5.5` semantics.
- `/api/openapi.json` contains the exact Python bundle upload, admission, and version-selection paths. Inspect the relevant schemas before calling them.

### 2. Build and check locally

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py build \
  --submission-dir . --output /tmp/agx-agent.zip
```

The helper:

- requires root `agent.py`;
- includes root `*.py`, root `design.json`, and `weights/**/*.npz` by default;
- accepts additional files/directories with `--include`;
- excludes `.git`, `.claude`, `docs`, caches, and build artifacts;
- enforces the runtime and bundle limits below;
- refuses to package the account key if it finds it in the submission bytes;
- prints a manifest with per-file and ZIP SHA-256 values.

### 3. Submit (external action)

First run without `--yes` to see the plan, then run with `--yes` after confirmation:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --base-url "$RSI_URL" --competition-id "$RSI_COMPETITION_ID" \
  --zip /tmp/agx-agent.zip --yes
```

- The helper resolves the Python agent via `POST /api/v1/python-submissions/agents`, checks the template and registration, uploads the ZIP, validates the receipt (`bundle_sha256`, `runtime_id`, `profile_digest`), polls `GET /api/v1/python-submissions/bundles/{bundle_id}`, and then activates via `POST /api/v1/python-submissions/competitions/{id}/versions` unless `--no-activate` is passed.
- It uses a fresh `Idempotency-Key` and prints it, the ZIP hash, and the API receipts. Keep the same key and bytes on an uncertain retry.
- On 409, look up the existing bundle/version by hash; don't create a duplicate.
- Record `admission`, `fault_code`, `contract_id`, `rules_version`, `bundle_sha256`, `profile_digest`, `version_id`, and the accepted version `number`.

### 4. Archive after success

Create a new version under `docs/submissions/` (never mutate v000):

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py archive \
  --submission-dir . --label first-submission \
  --notes "First submission of the baseline for pipeline validation."
```

Then:

- add the version to `docs/spec/README.md` and backlink the change note from the affected spec;
- record the upload result in the version's `metadata.json`;
- keep the uploaded ZIP and API receipts out of the repository if they contain sensitive data.

## Runtime limits and faults

- Per seat: **64 CPU seconds for the whole match** (initialization included); initialization 2 s; ordinary callback 50 ms; ~2.6667 s/round against the 24-round cap.
- Clocks: 60 Hz physics, 20 Hz decisions (every 3 ticks), 24 Hz recording.
- The parent process profile (3300/3301 CPU s, 3300 s wall) and the separate 300 s validation budget are **not** part of the seat's strategy allowance.
- Faults: timeout, cumulative CPU exhaustion, exception, malformed output, illegal action, output limit, OOM, or worker exit records a participant fault, disables that seat, and uses neutral control. A legal but unavailable action is a rejection receipt, not a fault. All-seat failure produces an explicit forfeit final; rating is unchanged.
- A truncated or killed task is not a draw; only a complete 12:12 is a draw.
- Bundle limits (enforced by the helper): ZIP ≤64 MiB, expanded ≤128 MiB, ≤64 entries; single source/design file 256 KiB, source/design total 1 MiB; NPZ file and actual tensors ≤64 MiB; request/response frames 1 MiB/64 KiB. No venv, requirements, wheels, native libraries, or pickle.
- Best proof that the version is attached: `GET /api/v1/competitions/{id}/entries?agent_id=...` shows `version.number` and `code_hash_short`. `/api/v1/me/competitions` `current_version` can remain `null`.

## Key facts

- Competition ID: `2a97f94f-816a-52b7-b4b8-5925db160245`.
- API key: account-scoped, one-time display; never put it in code, docs, logs, or the ZIP.
- The account guide's JSON `source` upload path is for the QuickJS games (tank/poker); FPS is Python and uses the ZIP bundle flow.
- The `/api/v1/python-submissions` routes are **not in** `/api/openapi.json`; the verified routes are listed above. Do not substitute the JS `source` upload path.
- First verified submission: `v001-first-python-submission` — admission `passed`, version `1` activated. See `docs/submissions/v001-first-python-submission/README.md`.

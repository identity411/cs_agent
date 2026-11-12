---
name: agx-submit
description: Build, validate, and submit this repo's Python FPS agent to an AGX competition via the Account API; poll admission, verify the immutable version, and archive the submission with a change note.
---

# AGX FPS submission

Use this skill for the AGX competition `2a97f94f-816a-52b7-b4b8-5925db160245` (FPS bomb mode) and for later versions of this agent.

## Required inputs

- `RSI_URL`: the base URL of the user's AGX instance. It has no safe default — never guess or substitute a search result.
- Account API key(s): read from `RSI_ACCOUNT_API_KEY` (default account `main`), `RSI_ACCOUNT_<NAME>_API_KEY`, the macOS Keychain (`agx-api-key`, `agx-api-key-<name>`), or the repo-root `.env`. The helper loads `.env` from the cwd or repo root first; `.env` is gitignored and must be `chmod 600`. Never echo, print, log, commit, or pass a key on a command line.
- Account selection: `--account NAME` (single target) or `--accounts a,b` / `--all-accounts` (batch). With no selector, `RSI_ACCOUNT` wins, then `main`, then a sole configured account; an ambiguous choice is an error naming the accounts. See [`.env.example`](../../../.env.example) for the full multi-account template.
- `RSI_COMPETITION_ID`: defaults to `2a97f94f-816a-52b7-b4b8-5925db160245`; it is already set in the local `.env`. Competition aliases are `RSI_COMPETITION_<GAME>` (for example `RSI_COMPETITION_FPS`, `RSI_COMPETITION_RACING`); `--competition-id fps|racing` or `--game-id fps|racing` resolves them. Per-account `RSI_ACCOUNT_<NAME>_COMPETITION_ID` (UUID or alias) and `_URL` overrides are optional.
- Submission tree: defaults to the repository root, with `agent.py` at the root.
- Agent IDs are account-scoped. `RSI_AGENT_ID` applies only to `main`; named accounts use `RSI_ACCOUNT_<NAME>_AGENT_ID` or API discovery. `--agent-id` is rejected for multiple targets.

If the base URL or a selected key is missing, stop and ask the user to configure it. Never ask for an account password.

## Credential setup

Preferred: store the key in the macOS Keychain (the user runs this themselves, outside the repository):

```sh
printf "AGX API key: "; read -r -s K; echo
security add-generic-password -U -a "$USER" -s agx-api-key -w "$K"
unset K
```

The helper reads that Keychain item without printing it. Additional accounts can use Keychain services `agx-api-key-<name>`; declare Keychain-only accounts in `RSI_ACCOUNTS` (for example `RSI_ACCOUNTS=main,alice`).

Alternatively, the user may edit the local `.env`:

```sh
chmod 600 .env
# shared: RSI_URL, RSI_COMPETITION_ID, RSI_COMPETITION_FPS/RACING
# main (legacy names): RSI_ACCOUNT_API_KEY / RSI_AGENT_ID
# additional accounts: RSI_ACCOUNT_ALICE_API_KEY / RSI_ACCOUNT_ALICE_AGENT_ID
# account default competition: RSI_ACCOUNT_<NAME>_COMPETITION_ID (UUID or alias)
```

Account names start with a letter and contain only letters, digits, and underscores; matching is case-insensitive. Numbered shorthand is accepted too: `RSI_ACCOUNT_API_KEY_2` becomes account `account2` (optional `RSI_ACCOUNT_AGENT_ID_2` or `RSI_AGENT_ID_2`). `.env` is gitignored and must never be committed. The base URL is not secret; ask the user to paste it or put it in `RSI_URL`.

## Accounts (read-only)

List configured accounts without contacting the API:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --json
```

Add `--check` for GET-only registration, standing, and active-version checks:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check
# Check another competition (for example racing) for every account:
python3 .claude/skills/agx-submit/scripts/agx_submit.py accounts --check \
  --game-id racing
# --competition-id racing / --competition-id fps work as aliases too.
```

The check paginates entries/leaderboard (`limit=100&offset=…`); the default
30-item page can hide the current account's `is_mine` entry.

Output includes the account name, base URL, competition, configured agent ID, key source, and a `sha256:<12 hex>` fingerprint. It never prints a key. Duplicate keys across accounts are warned (and rejected for batch submission). Run `accounts --check` before a batch submit and show the user which accounts, agent IDs, and versions will be affected.

## Safety and evidence rules

- Do read-only discovery first. Show the user the game, competition, rules version, and contract before uploading. For multiple accounts, run `accounts --check` and show every target account and agent ID.
- Before upload, show the ZIP manifest, file hashes, and total size, plus the per-account submit plan. The user's request to submit authorizes the upload, but show what will be submitted.
- Access only the explicitly configured `RSI_URL` / `RSI_ACCOUNT_<NAME>_URL`.
- Do not retry 4xx except 429. On 401/403 for a selected account, mark that account failed; in batch mode continue with the other accounts and ask for a corrected key. On 409 reuse the existing version/code hash; never bypass idempotency.
- Keep the same `Idempotency-Key` and exact body when retrying an upload whose response was lost. Batch keys are stable per `(account, zip_sha256)`; do not change the ZIP for a retry.
- Agent IDs, registrations, versions, and `is_mine` flags are account-scoped. Never reuse another account's agent ID or key. `RSI_AGENT_ID` is only for `main`.
- Never print, log, or persist a key. Receipts, account listings, and snapshots may contain only `sha256:<12 hex>` fingerprints and key source names.
- Multiple accounts must be allowed by the platform/competition rules. If they are not, do not batch-submit; confirm with the user first.
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
- excludes `.git`, `.claude`, `docs`, `data`, caches, and build artifacts;
- enforces the runtime and bundle limits below;
- refuses to package any configured account key if it finds it in the submission bytes;
- prints a manifest with per-file and ZIP SHA-256 values.

### 3. Submit (external action)

Single account:

```sh
# Read-only plan (no POST, including no agent identity creation):
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --account alice --zip /tmp/agx-agent.zip
# After confirmation:
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --account alice --zip /tmp/agx-agent.zip --yes
```

For another game/competition, add `--game-id` (or `--competition-id`); no UUID
is needed when the alias is configured in `.env`:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --account account2 --game-id racing --zip /path/to/racing-agent.zip
```

Batch (same ZIP to every configured account, including `main`):

```sh
# Read-only plan for every account:
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --all-accounts --zip /tmp/agx-agent.zip
# After confirmation:
python3 .claude/skills/agx-submit/scripts/agx_submit.py submit \
  --all-accounts --zip /tmp/agx-agent.zip --yes \
  --receipt-out /tmp/agx-receipt.json
```

- Without `--yes`, the helper only performs GET preflight (competition, template, registration) for every target; it does not create agent identities or register. Show the plan and get confirmation before adding `--yes`.
- If any target fails preflight, abort the whole batch before uploading anything. During execution, record the failure and continue with the remaining accounts; exit code `2` if any account failed.
- `--accounts a,b` selects an explicit subset; `--account NAME` selects one. `--agent-id` and `--idempotency-key` are single-account only. Batch derives a stable per-account idempotency key from `(account, zip_sha256)` and prints it.
- Per account the helper resolves/creates the agent via `POST /api/v1/python-submissions/agents`, checks the template and registration, uploads the ZIP, validates the receipt (`bundle_sha256`, `runtime_id`, `profile_digest`), polls `GET /api/v1/python-submissions/bundles/{bundle_id}`, and then activates via `POST /api/v1/python-submissions/competitions/{id}/versions` unless `--no-activate` is passed.
- It uses a fresh `Idempotency-Key` for a single target and prints it, the ZIP hash, and the API receipts. Keep the same key and bytes on an uncertain retry.
- `--receipt-out` writes a per-account receipt incrementally (mode `0600`, no keys): status, agent ID, bundle ID, admission, activation, entry version, and errors. Use it for evidence and archive input.
- On 409, look up the existing bundle/version by hash; don't create a duplicate.
- Record per account `admission`, `fault_code`, `contract_id`, `rules_version`, `bundle_sha256`, `profile_digest`, `version_id`, and the accepted version `number`. Version numbers are per account.

### 4. Archive after success

Create a new version under `docs/submissions/` (never mutate existing snapshots). Directories use `MMDD-vX.YY`; baseline is `1112-v0.00`, the next submissions are `1112-v0.01`, `v0.02`, and so on:

```sh
python3 .claude/skills/agx-submit/scripts/agx_submit.py archive \
  --submission-dir . --notes-file /tmp/change-note.md
```

Then:

- add the version to `docs/spec/README.md` and backlink the change note from the affected spec;
- record the upload result in the version's `metadata.json`; a batch `--receipt-out` file can be passed as `archive --api-result`;
- keep the uploaded ZIP and API receipts out of the repository if they contain sensitive data.

## Runtime limits and faults

- Per seat: **64 CPU seconds for the whole match** (initialization included); initialization 2 s; ordinary callback 50 ms; ~2.6667 s/round against the 24-round cap.
- Clocks: 60 Hz physics, 20 Hz decisions (every 3 ticks), 24 Hz recording.
- The parent process profile (3300/3301 CPU s, 3300 s wall) and the separate 300 s validation budget are **not** part of the seat's strategy allowance.
- Faults: timeout, cumulative CPU exhaustion, exception, malformed output, illegal action, output limit, OOM, or worker exit records a participant fault, disables that seat, and uses neutral control. A legal but unavailable action is a rejection receipt, not a fault. All-seat failure produces an explicit forfeit final; rating is unchanged.
- A truncated or killed task is not a draw; only a complete 12:12 is a draw.
- Bundle limits (enforced by the helper): ZIP ≤64 MiB, expanded ≤128 MiB, ≤64 entries; single source/design file 256 KiB, source/design total 1 MiB; NPZ file and actual tensors ≤64 MiB; request/response frames 1 MiB/64 KiB. No venv, requirements, wheels, native libraries, or pickle.
- Best proof that the version is attached: `GET /api/v1/competitions/{id}/entries` shows `version.number` and `code_hash_short`; fetch all and filter `is_mine` locally (query params such as `agent_id` returned 404 on the live deployment). The endpoint defaults to 30 items, so use `?limit=100&offset=…` and paginate; otherwise the current account's `is_mine` entry can be on a later page. `/api/v1/me/competitions` `current_version` can remain `null`.
- `accounts --check` and batch submit use paginated entries, so `--receipt-out` includes the `is_mine` entry when it exists.

## Key facts

- Competition ID: `2a97f94f-816a-52b7-b4b8-5925db160245`.
- Account config: legacy `RSI_ACCOUNT_API_KEY` / `RSI_AGENT_ID` = `main`; extra accounts use `RSI_ACCOUNT_<NAME>_API_KEY` / `_AGENT_ID` / `_URL` / `_COMPETITION_ID`; numbered `RSI_ACCOUNT_API_KEY_2` = `account2`; `RSI_ACCOUNT` selects the default; `RSI_ACCOUNTS` sets order/declares Keychain-only accounts. See `.env.example`.
- Competition aliases: `RSI_COMPETITION_FPS` / `RSI_COMPETITION_RACING` (or `RSI_COMPETITION_ID_<GAME>`); use `--game-id fps|racing` or `--competition-id fps|racing` instead of pasting UUIDs. Per-account defaults use `RSI_ACCOUNT_<NAME>_COMPETITION_ID`.
- API keys: account-scoped, one-time display; never put them in code, docs, logs, receipts, account listings, snapshots, or the ZIP. Use `--receipt-out` for batch evidence; it contains fingerprints only.
- Batch submit targets all accounts with `--all-accounts` (or `--accounts a,b`), preflights read-only first, and never shares an agent ID or idempotency key across accounts.
- The account guide's JSON `source` upload path is for the QuickJS games (tank/poker); FPS is Python and uses the ZIP bundle flow.
- The `/api/v1/python-submissions` routes are **not in** `/api/openapi.json`; the verified routes are listed above. Do not substitute the JS `source` upload path.
- First verified submission: `1112-v0.01` — admission `passed`, version `1` activated. See `docs/submissions/1112-v0.01/README.md`.
- For match results, standings, public replay events/frames, and badcase evidence, use the separate `agx-match-query` skill (`.claude/skills/agx-match-query/`). This skill only builds/uploads/activates/archives.

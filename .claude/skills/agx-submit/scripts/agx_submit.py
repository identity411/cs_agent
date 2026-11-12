#!/usr/bin/env python3
"""AGX Python submission helper.

Security:
- The account API key is read from RSI_ACCOUNT_API_KEY or the macOS Keychain
  item "agx-api-key". It is never printed, logged, or written to disk here.
- Only the explicitly configured base URL is contacted.
- Upload is an external action; submit requires --yes.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_COMPETITION_ID = "2a97f94f-816a-52b7-b4b8-5925db160245"
TRANSIENT = {429, 502, 503, 504}
EXCLUDED_DIRS = {
    ".git", ".claude", ".venv", "venv", "node_modules",
    "docs", "__pycache__", "build", "dist", "output",
}
ALLOWED_SUFFIXES = {".py", ".json", ".npz"}
SOURCE_LIMIT = 256 * 1024
SOURCE_TOTAL_LIMIT = 1 * 1024 * 1024
NPZ_LIMIT = 64 * 1024 * 1024
ZIP_LIMIT = 64 * 1024 * 1024
EXPANDED_LIMIT = 128 * 1024 * 1024
ENTRY_LIMIT = 64


def die(message: str, code: int = 1) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_dotenv() -> None:
    """Load .env from the cwd or repo root without echoing values."""
    paths = [Path.cwd() / ".env"]
    try:
        repo_env = Path(__file__).resolve().parents[4] / ".env"
        if repo_env != paths[0]:
            paths.append(repo_env)
    except IndexError:
        pass
    for path in paths:
        if not path.is_file():
            continue
        try:
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:
                print(
                    f"warning: {path} is group/other-accessible; run chmod 600 {path}",
                    file=sys.stderr,
                )
        except OSError:
            pass
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            name, value = line.split("=", 1)
            name = name.strip()
            value = value.strip().strip("'\"")
            if name:
                os.environ.setdefault(name, value)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "submission"


def find_key() -> str | None:
    key = os.environ.get("RSI_ACCOUNT_API_KEY")
    if key:
        return key
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", "agx-api-key", "-w"],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def require_key() -> str:
    key = find_key()
    if not key:
        die(
            "no AGX account API key. Set RSI_ACCOUNT_API_KEY or add the macOS "
            "Keychain item 'agx-api-key'."
        )
    competition_id = os.environ.get("RSI_COMPETITION_ID", DEFAULT_COMPETITION_ID)
    if key.strip() == competition_id:
        die(
            "RSI_ACCOUNT_API_KEY is set to the competition ID, not an API key. "
            "Create an account API key in the AGX account settings."
        )
    return key


def header_value(headers: dict, name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return ""


def retry_delay(headers: dict, default: float | int = 3) -> float:
    value = header_value(headers, "Retry-After").strip()
    if value.isdigit():
        return max(1.0, float(value))
    if value:
        try:
            when = parsedate_to_datetime(value)
            return max(1.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            pass
    return float(default)


def decode_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", "replace")


def show(label: str, status: int, data, limit: int = 20000) -> None:
    print(f"\n=== {label} -> {status} ===")
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = str(data)
    print(text[:limit] + ("..." if len(text) > limit else ""))


def find_first_key(obj, names: tuple[str, ...]):
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name):
                return obj[name]
        for value in obj.values():
            found = find_first_key(value, names)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_first_key(value, names)
            if found:
                return found
    return None


class Client:
    def __init__(self, base_url: str, key: str):
        self.base = base_url.rstrip("/")
        if not self.base.startswith(("http://", "https://")):
            die("RSI_URL/--base-url must start with http:// or https://")
        if self.base.endswith("/api/v1"):
            self.base = self.base[: -len("/api/v1")]
        self.key = key
        # Ignore environment proxies, matching the account guide's example.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, body=None, headers=None, timeout=30):
        url = path if path.startswith(("http://", "https://")) else self.base + "/" + path.lstrip("/")
        request_headers = {
            "Authorization": "Bearer " + self.key,
            "Accept": "application/json",
            "User-Agent": "csagent-agx-submit/1",
        }
        if headers:
            request_headers.update(headers)
        data = body
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def request(self, method: str, path: str, attempts: int = 5, **kwargs):
        for attempt in range(attempts):
            try:
                status, headers, raw = self._request(method, path, **kwargs)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == attempts - 1:
                    raise
                time.sleep(min(60, 2 ** attempt))
                continue
            if status not in TRANSIENT or attempt == attempts - 1:
                return status, headers, raw
            time.sleep(retry_delay(headers, min(60, 2 ** attempt)))
        raise RuntimeError("unreachable")


def is_excluded(rel: Path) -> bool:
    if rel.is_absolute() or ".." in rel.parts:
        return True
    if any(part.startswith(".") for part in rel.parts):
        return True
    return any(part in EXCLUDED_DIRS for part in rel.parts)


def gather_submission(root: Path, includes: list[str]) -> list[tuple[Path, Path]]:
    root = root.resolve()
    agent = root / "agent.py"
    if not agent.is_file():
        die(f"{agent} does not exist")

    candidates: list[Path] = [agent]
    candidates.extend(sorted(p for p in root.glob("*.py") if p.is_file() and p != agent))
    design = root / "design.json"
    if design.is_file():
        candidates.append(design)
    weights = root / "weights"
    if weights.is_dir():
        candidates.extend(sorted(weights.rglob("*.npz")))

    for item in includes:
        path = (root / item).resolve()
        if not path.exists():
            die(f"include path does not exist: {item}")
        if path.is_file():
            candidates.append(path)
        else:
            candidates.extend(sorted(p for p in path.rglob("*") if p.is_file()))

    files: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            die(f"submission file is outside the submission directory: {path}")
        if is_excluded(rel):
            continue
        if rel.suffix not in ALLOWED_SUFFIXES:
            die(f"unsupported submission file type: {rel.as_posix()} (allowed: .py, root design.json, .npz)")
        if rel.suffix == ".json" and rel.as_posix() != "design.json":
            die(f"only root design.json is allowed, got: {rel.as_posix()}")
        if rel.as_posix() in seen:
            continue
        seen.add(rel.as_posix())
        files.append((rel, path.resolve()))

    if not any(rel.as_posix() == "agent.py" for rel, _ in files):
        die("agent.py must be at the submission root")
    files.sort(key=lambda item: item[0].as_posix())
    return files


def validate_limits(files: list[tuple[Path, Path]]) -> None:
    if len(files) > ENTRY_LIMIT:
        die(f"too many files: {len(files)} > {ENTRY_LIMIT}")
    source_total = 0
    expanded = 0
    for rel, path in files:
        size = path.stat().st_size
        expanded += size
        if rel.suffix in {".py", ".json"}:
            if size > SOURCE_LIMIT:
                die(f"{rel.as_posix()} is {size} bytes; source/design limit is {SOURCE_LIMIT}")
            source_total += size
        elif rel.suffix == ".npz" and size > NPZ_LIMIT:
            die(f"{rel.as_posix()} is {size} bytes; NPZ limit is {NPZ_LIMIT}")
    if source_total > SOURCE_TOTAL_LIMIT:
        die(f"source/design total is {source_total} bytes; limit is {SOURCE_TOTAL_LIMIT}")
    if expanded > EXPANDED_LIMIT:
        die(f"expanded size is {expanded} bytes; limit is {EXPANDED_LIMIT}")


def assert_no_key(files: list[tuple[Path, Path]], zip_path: Path | None = None) -> None:
    key = find_key()
    if not key:
        return
    needle = key.encode("utf-8")
    for rel, path in files:
        if needle in path.read_bytes():
            die(f"refusing to package: the account API key appears in {rel.as_posix()}")
    if zip_path and zip_path.exists() and needle in zip_path.read_bytes():
        die("refusing to package: the account API key appears in the ZIP")


def build_zip(files: list[tuple[Path, Path]], output: Path) -> dict:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel, path in files:
            archive.write(path, rel.as_posix())
    size = output.stat().st_size
    if size > ZIP_LIMIT:
        die(f"ZIP is {size} bytes; limit is {ZIP_LIMIT}")
    assert_no_key(files, output)
    manifest = {
        "zip": str(output),
        "zip_bytes": size,
        "zip_sha256": sha256_file(output),
        "files": [
            {
                "path": rel.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for rel, path in files
        ],
    }
    return manifest


def cmd_discover(args) -> int:
    key = require_key()
    client = Client(args.base_url, key)
    endpoints = [
        "/api/v1/games",
        f"/api/v1/competitions/{args.competition_id}",
        f"/api/v1/me/competitions/{args.competition_id}/versions",
        "/api/openapi.json",
    ]
    openapi_path = Path(args.save_openapi).expanduser()
    for endpoint in endpoints:
        try:
            status, headers, raw = client.request("GET", endpoint)
        except Exception as exc:
            print(f"\n=== GET {endpoint} -> network error: {type(exc).__name__} ===", file=sys.stderr)
            continue
        data = decode_json(raw)
        if endpoint == "/api/openapi.json" and isinstance(data, dict):
            openapi_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            paths = data.get("paths") or {}
            matches = [
                path for path in sorted(paths)
                if any(token in path.lower() for token in ("python", "bundle", "submission"))
            ]
            print(f"\n=== GET {endpoint} -> {status} ===")
            print(f"saved OpenAPI to {openapi_path}")
            print("relevant paths:")
            for path in matches:
                methods = ", ".join(sorted(m.upper() for m in paths[path] if m.lower() in {"get", "post", "put", "patch", "delete"}))
                print(f"  {methods or '?':12} {path}")
            if not matches:
                print("  (none matched python/bundle/submission)")
            continue
        show(f"GET {endpoint}", status, data)
        if endpoint != "/api/openapi.json" and status in {401, 403}:
            print("authentication/permission failure; stop and fix the account key before submitting.", file=sys.stderr)
    print("\nNext: confirm the live rules_version/contract and inspect the OpenAPI schemas before upload.")
    return 0


def cmd_build(args) -> int:
    root = Path(args.submission_dir)
    files = gather_submission(root, args.include)
    validate_limits(files)

    for rel, path in files:
        if rel.suffix != ".py":
            continue
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=rel.as_posix())
        except SyntaxError as exc:
            die(f"syntax error in {rel.as_posix()}: {exc}")
        if rel.as_posix() == "agent.py":
            functions = {
                node.name for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "act" not in functions:
                die("agent.py must define a top-level act(observation) function")

    manifest = build_zip(files, Path(args.output))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def validate_python_receipt(data, zip_sha: str, profile_digest: str | None) -> dict:
    if not isinstance(data, dict):
        die("invalid Python receipt: expected a JSON object")
    for field in ("id", "bundle_sha256", "runtime_id", "profile_digest"):
        if not isinstance(data.get(field), str) or not data[field]:
            die(f"invalid Python receipt: missing {field}")
    if data["bundle_sha256"] != zip_sha:
        die(
            "invalid Python receipt: bundle_sha256 does not match the ZIP "
            f"({data['bundle_sha256']} != {zip_sha})"
        )
    if data["runtime_id"] != "python-agent-v1":
        die(f"invalid Python receipt: unexpected runtime_id {data['runtime_id']!r}")
    if profile_digest and data["profile_digest"] != profile_digest:
        die(
            "invalid Python receipt: profile_digest does not match the live "
            f"template ({data['profile_digest']} != {profile_digest})"
        )
    if data.get("admission") not in {"queued", "running", "passed", "failed"}:
        die(f"invalid Python receipt: unexpected admission {data.get('admission')!r}")
    return data


def cmd_submit(args) -> int:
    key = require_key()
    client = Client(args.base_url, key)
    zip_path = Path(args.zip).expanduser().resolve()
    if not zip_path.is_file():
        die(f"ZIP does not exist: {zip_path}")
    zip_bytes = zip_path.read_bytes()
    zip_sha = sha256_bytes(zip_bytes)

    comp_status, _, comp_raw = client.request(
        "GET", f"/api/v1/competitions/{args.competition_id}"
    )
    competition = decode_json(comp_raw)
    if comp_status != 200 or not isinstance(competition, dict):
        die(f"cannot read competition {args.competition_id} (HTTP {comp_status})")
    game_id = args.game_id or competition.get("game_id")
    if not game_id:
        die("cannot determine the game_id; pass --game-id")

    template_status, _, template_raw = client.request(
        "GET", f"/api/v1/python-submissions/templates/{urllib.parse.quote(str(game_id), safe='')}"
    )
    template = decode_json(template_raw)
    profile_digest = None
    if template_status == 200 and isinstance(template, dict):
        profile = template.get("profile") or {}
        profile_digest = profile.get("profile_digest")
        if profile.get("runtime_id") != "python-agent-v1":
            die(f"unexpected Python runtime: {profile.get('runtime_id')!r}")
        if profile.get("contract_id") != competition.get("rules_version"):
            die(
                "template contract does not match the competition rules_version "
                f"({profile.get('contract_id')} != {competition.get('rules_version')})"
            )
        files = template.get("files") or []
        entries = [f.get("path") for f in files if isinstance(f, dict)]
        if "agent.py" not in entries:
            die("live Python template does not list agent.py as an entry")
    else:
        print(f"warning: Python template unavailable (HTTP {template_status}); continuing", file=sys.stderr)

    reg_path = f"/api/v1/python-submissions/competitions/{urllib.parse.quote(str(args.competition_id), safe='')}/registration"
    reg_status, _, reg_raw = client.request("GET", reg_path)
    registration = decode_json(reg_raw) if reg_status == 200 else {}
    registered = isinstance(registration, dict) and registration.get("registered") is True
    agent_id = args.agent_id or os.environ.get("RSI_AGENT_ID") or (
        registration.get("agent_id") if isinstance(registration, dict) else None
    )
    if not agent_id:
        id_status, _, id_raw = client.request(
            "POST", "/api/v1/python-submissions/agents", body={"game_id": game_id}
        )
        identity = decode_json(id_raw)
        if id_status not in {200, 201} or not isinstance(identity, dict) or not identity.get("id"):
            die(f"cannot create/resolve the Python submission identity (HTTP {id_status})")
        agent_id = identity["id"]

    quoted_agent = urllib.parse.quote(str(agent_id), safe="")
    quoted_comp = urllib.parse.quote(str(args.competition_id), safe="")
    upload_path = f"/api/v1/python-submissions/agents/{quoted_agent}/bundles"
    idempotency_key = args.idempotency_key or str(uuid.uuid4())

    print(json.dumps({
        "competition_id": args.competition_id,
        "game_id": game_id,
        "rules_version": competition.get("rules_version"),
        "agent_id": str(agent_id),
        "registered": registered,
        "profile_digest": profile_digest,
        "zip": str(zip_path),
        "zip_sha256": zip_sha,
        "idempotency_key": idempotency_key,
    }, ensure_ascii=False, indent=2))
    if not args.yes:
        print("\nDry run only. Re-run with --yes to upload and activate this bundle.")
        return 0

    if not registered:
        status, _, raw = client.request(
            "POST", reg_path, body={"agent_id": str(agent_id)}
        )
        show(f"POST {reg_path}", status, decode_json(raw))
        if status not in {200, 201, 204, 409}:
            return 2

    status, headers, raw = client.request(
        "POST",
        upload_path,
        body=zip_bytes,
        headers={"Content-Type": "application/zip", "Idempotency-Key": idempotency_key},
        attempts=5,
    )
    receipt = decode_json(raw)
    show(f"POST {upload_path}", status, receipt)
    if status in {401, 403}:
        die("authentication/permission failure; ask the user for a new account key", 3)
    if status == 409:
        history_path = f"/api/v1/python-submissions/agents/{quoted_agent}/bundles"
        hist_status, _, hist_raw = client.request("GET", history_path)
        show(f"GET {history_path}", hist_status, decode_json(hist_raw))
        print("409: reuse the existing bundle/version; do not bypass idempotency.")
        return 2
    if status not in {200, 201, 202}:
        return 2

    receipt = validate_python_receipt(receipt, zip_sha, profile_digest)
    bundle_id = receipt["id"]
    admission = receipt["admission"]
    status_path = f"/api/v1/python-submissions/bundles/{urllib.parse.quote(str(bundle_id), safe='')}"
    deadline = time.monotonic() + args.poll_timeout
    while admission in {"queued", "running"}:
        if time.monotonic() >= deadline:
            print(
                f"admission still {admission}; keep the idempotency key and poll "
                f"{status_path} later.",
                file=sys.stderr,
            )
            return 2
        time.sleep(2)
        poll_status, poll_headers, poll_raw = client.request("GET", status_path)
        receipt = decode_json(poll_raw)
        show(f"GET {status_path}", poll_status, receipt)
        if poll_status != 200:
            return 2
        receipt = validate_python_receipt(receipt, zip_sha, profile_digest)
        admission = receipt["admission"]

    if admission != "passed":
        print(f"admission {admission}; bundle {bundle_id} is not active.", file=sys.stderr)
        return 2

    activation = None
    if not args.no_activate:
        activation_path = f"/api/v1/python-submissions/competitions/{quoted_comp}/versions"
        act_status, _, act_raw = client.request(
            "POST",
            activation_path,
            body={"submission_id": bundle_id, "auto_match": True},
            attempts=5,
        )
        activation = decode_json(act_raw)
        show(f"POST {activation_path}", act_status, activation)
        if act_status not in {200, 201}:
            return 2

    for path in (
        f"/api/v1/python-submissions/agents/{quoted_agent}/bundles",
        f"/api/v1/me/competitions/{quoted_comp}/versions",
    ):
        try:
            info_status, _, info_raw = client.request("GET", path)
            show(f"GET {path}", info_status, decode_json(info_raw), limit=8000)
        except Exception as exc:
            print(f"verification lookup failed for {path}: {type(exc).__name__}", file=sys.stderr)

    print(json.dumps({
        "bundle_id": bundle_id,
        "admission": admission,
        "activated": not args.no_activate,
        "idempotency_key": idempotency_key,
        "activation": activation,
    }, ensure_ascii=False, indent=2))
    print("\nUpload/admission/activation success is not a full match, score, or win.")
    return 0


def cmd_archive(args) -> int:
    repo_root = Path(args.repo_root).resolve()
    submission_root = Path(args.submission_dir).resolve()
    files = gather_submission(submission_root, args.include)
    assert_no_key(files)
    base = repo_root / "docs" / "submissions"
    base.mkdir(parents=True, exist_ok=True)

    existing: list[tuple[int, int]] = []
    for path in base.iterdir():
        match = re.match(r"\d{4}-v(\d+)\.(\d+)", path.name)
        if match and path.is_dir():
            existing.append((int(match.group(1)), int(match.group(2))))
    if args.version:
        raw = args.version.strip().lower()
        if raw.startswith("v"):
            raw = raw[1:]
        try:
            major_s, minor_s = raw.split(".", 1)
            major, minor = int(major_s), int(minor_s)
        except (ValueError, AttributeError):
            die("--version must look like v0.02")
    else:
        if existing:
            major, minor = max(existing)
            minor += 1
        else:
            major, minor = 0, 1
    version = f"v{major}.{minor:02d}"
    date_prefix = args.date or datetime.now().strftime("%m%d")
    if not re.fullmatch(r"\d{4}", date_prefix):
        die("--date must be MMDD (for example 1112)")
    folder = f"{date_prefix}-{version}"
    target = base / folder
    if target.exists():
        die(f"{target} already exists; choose a new --version or inspect it first")

    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text()
    if not notes:
        die("provide --notes or --notes-file for the change note")

    target.mkdir(parents=True)
    file_hashes = {}
    for rel, path in files:
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        file_hashes[rel.as_posix()] = sha256_file(destination)

    api_result = None
    if args.api_result:
        api_result = json.loads(Path(args.api_result).read_text())
    metadata = {
        "version": folder,
        "date": utc_date(),
        "competition_id": args.competition_id,
        "contract": args.contract,
        "status": args.status,
        "files": file_hashes,
        "change_note": "README.md",
        "related_specs": [],
    }
    if api_result is not None:
        metadata["api_result"] = api_result
    (target / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    readme = f"""# {folder}

- **日期**：{utc_date()}
- **比赛 ID**：`{args.competition_id}`
- **合同**：{args.contract}
- **状态**：{args.status}
- **快照**：{', '.join(file_hashes)}（见同目录文件）

## 改动说明

{notes.strip()}

## 对应规范

TODO: 在受影响的 `docs/spec/*.md` 中加入本版本引用，并在
`docs/spec/README.md` 的版本表登记本版本。

## 验证情况

见 `metadata.json` 的 `status` 与 `api_result`；不要仅凭上传或准入成功声称完整对局通过。
"""
    (target / "README.md").write_text(readme)
    print(json.dumps({
        "created": str(target),
        "version": folder,
        "files": file_hashes,
        "next": "add the version to docs/spec/README.md and backlink from the affected spec",
    }, ensure_ascii=False, indent=2))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="read-only game/competition/OpenAPI discovery")
    discover.add_argument("--base-url", default=os.environ.get("RSI_URL"))
    discover.add_argument("--competition-id", default=os.environ.get("RSI_COMPETITION_ID", DEFAULT_COMPETITION_ID))
    discover.add_argument("--save-openapi", default="/tmp/agx-openapi.json")
    discover.set_defaults(func=cmd_discover)

    build = sub.add_parser("build", help="build a submission ZIP and print its manifest")
    build.add_argument("--submission-dir", default=".")
    build.add_argument("--output", default="/tmp/agx-agent.zip")
    build.add_argument("--include", action="append", default=[])
    build.set_defaults(func=cmd_build)

    submit = sub.add_parser("submit", help="upload a ZIP to the Python bundle endpoint")
    submit.add_argument("--base-url", default=os.environ.get("RSI_URL"))
    submit.add_argument("--competition-id", default=os.environ.get("RSI_COMPETITION_ID", DEFAULT_COMPETITION_ID))
    submit.add_argument("--game-id")
    submit.add_argument("--zip", required=True)
    submit.add_argument("--agent-id", default=os.environ.get("RSI_AGENT_ID"))
    submit.add_argument("--idempotency-key")
    submit.add_argument("--poll-timeout", type=float, default=600)
    submit.add_argument("--no-activate", action="store_true", help="upload and admit without selecting the version")
    submit.add_argument("--yes", action="store_true")
    submit.set_defaults(func=cmd_submit)

    archive = sub.add_parser("archive", help="create a docs/submissions/MMDD-vX.YY snapshot")
    archive.add_argument("--repo-root", default=".")
    archive.add_argument("--submission-dir", default=".")
    archive.add_argument("--include", action="append", default=[])
    archive.add_argument("--notes", default="")
    archive.add_argument("--notes-file")
    archive.add_argument("--version", help="optional next version, e.g. v0.02")
    archive.add_argument("--date", help="optional MMDD prefix; defaults to today")
    archive.add_argument("--competition-id", default=os.environ.get("RSI_COMPETITION_ID", DEFAULT_COMPETITION_ID))
    archive.add_argument("--contract", default="unknown")
    archive.add_argument("--status", default="submitted")
    archive.add_argument("--api-result")
    archive.set_defaults(func=cmd_archive)

    return parser


def main() -> int:
    load_dotenv()
    parser = make_parser()
    args = parser.parse_args()
    if getattr(args, "base_url", None) is not None and not getattr(args, "base_url").strip():
        die("--base-url/RSI_URL is required; do not guess the AGX instance")
    if args.command in {"discover", "submit"} and not getattr(args, "base_url", None):
        die("--base-url/RSI_URL is required; do not guess the AGX instance")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

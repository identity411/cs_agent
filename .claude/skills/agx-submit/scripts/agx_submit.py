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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_COMPETITION_ID = "2a97f94f-816a-52b7-b4b8-5925db160245"
DEFAULT_ACCOUNT_NAME = "main"
ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ACCOUNT_VAR_RE = re.compile(
    r"^RSI_ACCOUNT_([A-Za-z][A-Za-z0-9_]*)_(API_KEY|AGENT_ID|URL|COMPETITION_ID)$"
)
NUMBERED_ACCOUNT_VAR_RE = re.compile(
    r"^RSI_ACCOUNT_(API_KEY|AGENT_ID|URL|COMPETITION_ID)_([0-9]+)$"
)
NUMBERED_AGENT_ID_RE = re.compile(r"^RSI_AGENT_ID_([0-9]+)$")
TRANSIENT = {429, 502, 503, 504}
EXCLUDED_DIRS = {
    ".git", ".claude", ".venv", "venv", "node_modules",
    "docs", "data", "__pycache__", "build", "dist", "output",
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
    if os.environ.get("AGX_NO_DOTENV", "").strip().lower() not in {
            "", "0", "false", "no"}:
        return
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


class AccountError(RuntimeError):
    """A multi-account configuration or selection problem."""


class AccountFailure(RuntimeError):
    """A per-account API operation failed; batch mode records and continues."""

    def __init__(self, message: str, auth: bool = False,
                 partial: dict | None = None):
        super().__init__(message)
        self.auth = auth
        self.partial = partial or {}


@dataclass(frozen=True)
class Account:
    name: str
    key: str = field(default="", repr=False, compare=False)
    key_source: str = "missing"
    base_url: str | None = None
    competition_id: str | None = None
    agent_id: str | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.key)

    @property
    def fingerprint(self) -> str | None:
        return key_fingerprint(self.key) if self.key else None


def key_fingerprint(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return "sha256:" + digest


def normalize_account_name(name: str) -> str:
    value = str(name).strip().lower()
    if not value:
        raise AccountError("account name is empty")
    if not ACCOUNT_NAME_RE.fullmatch(value):
        raise AccountError(
            f"invalid account name {name!r}; use letters, digits and "
            "underscores, starting with a letter"
        )
    return value


def parse_account_names(raw: str | None) -> list[str]:
    names: list[str] = []
    if not raw:
        return names
    for part in re.split(r"[\s,;]+", raw.strip()):
        if not part:
            continue
        name = normalize_account_name(part)
        if name not in names:
            names.append(name)
    return names


def env_value(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def keychain_key(service: str) -> str | None:
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def _numbered_account_name(number: str) -> str:
    # RSI_ACCOUNT_API_KEY_2 and RSI_AGENT_ID_2 are the legacy numbered form
    # of the second account; expose it as "account2".
    return f"account{int(number)}"


def _match_account_env_var(env_name: str) -> tuple[str, str] | None:
    match = ACCOUNT_VAR_RE.match(env_name)
    if match:
        return normalize_account_name(match.group(1)), match.group(2)
    match = NUMBERED_ACCOUNT_VAR_RE.match(env_name)
    if match:
        return _numbered_account_name(match.group(2)), match.group(1)
    match = NUMBERED_AGENT_ID_RE.match(env_name)
    if match:
        return _numbered_account_name(match.group(1)), "AGENT_ID"
    return None


def _scan_named_env(
        environ: Mapping[str, str]) -> dict[str, dict[str, tuple[str, str]]]:
    fields: dict[str, dict[str, tuple[str, str]]] = {}
    for env_name in sorted(environ):
        matched = _match_account_env_var(env_name)
        if not matched:
            continue
        name, suffix = matched
        value = env_value(environ, env_name)
        if not value:
            continue
        current = fields.setdefault(name, {})
        if suffix in current and current[suffix][0] != value:
            raise AccountError(
                f"account {name!r} defines {suffix} twice with different "
                f"values ({current[suffix][1]} and {env_name})"
            )
        current[suffix] = (value, env_name)
    return fields


def discover_accounts(
        environ: Mapping[str, str] | None = None,
        keychain_lookup: Callable[[str], str | None] | None = None,
) -> list[Account]:
    """Discover accounts from the environment.

    The legacy RSI_ACCOUNT_API_KEY / RSI_AGENT_ID pair is the default
    account "main".  Additional accounts use RSI_ACCOUNT_<NAME>_*.
    Only key names that match the documented schema are considered.
    """
    env = os.environ if environ is None else environ
    lookup = keychain_lookup or keychain_key
    shared_url = env_value(env, "RSI_URL")
    shared_comp = env_value(env, "RSI_COMPETITION_ID")
    legacy_key = env_value(env, "RSI_ACCOUNT_API_KEY")
    legacy_agent = env_value(env, "RSI_AGENT_ID")
    legacy_defined = bool(legacy_key or legacy_agent)
    named = _scan_named_env(env)
    declared = parse_account_names(env_value(env, "RSI_ACCOUNTS"))

    if legacy_defined and DEFAULT_ACCOUNT_NAME in named:
        raise AccountError(
            "account 'main' is defined both by RSI_ACCOUNT_API_KEY/"
            "RSI_AGENT_ID and by RSI_ACCOUNT_MAIN_*; keep only one form"
        )

    names: list[str] = []

    def add_name(name: str) -> None:
        if name not in names:
            names.append(name)

    if legacy_defined:
        add_name(DEFAULT_ACCOUNT_NAME)
    for name in declared:
        add_name(name)
    for name in sorted(named):
        add_name(name)

    accounts: list[Account] = []
    for name in names:
        fields = named.get(name, {})
        is_main = name == DEFAULT_ACCOUNT_NAME
        key, source = "", "missing"
        candidates: list[tuple[str, str]] = []
        if is_main and legacy_key:
            candidates.append((legacy_key, "env:RSI_ACCOUNT_API_KEY"))
        env_key = fields.get("API_KEY")
        if env_key:
            candidates.append((env_key[0], f"env:{env_key[1]}"))
        for value, label in candidates:
            if value:
                key, source = value, label
                break
        if not key:
            services = [f"agx-api-key-{name}"]
            if is_main:
                services.insert(0, "agx-api-key")
            for service in services:
                value = lookup(service)
                if value:
                    key, source = value.strip(), f"keychain:{service}"
                    break
        url_field = fields.get("URL")
        comp_field = fields.get("COMPETITION_ID")
        agent_field = fields.get("AGENT_ID")
        agent_id = agent_field[0] if agent_field else None
        if is_main and not agent_id:
            agent_id = legacy_agent
        accounts.append(Account(
            name=name,
            key=key,
            key_source=source,
            base_url=(url_field[0] if url_field else None) or shared_url,
            competition_id=(comp_field[0] if comp_field else None) or shared_comp,
            agent_id=agent_id,
        ))

    if not accounts:
        # Preserve the old Keychain-only setup: no env account at all, but
        # the account API key is stored as the default Keychain item.
        value = lookup("agx-api-key")
        if value:
            accounts.append(Account(
                name=DEFAULT_ACCOUNT_NAME,
                key=value.strip(),
                key_source="keychain:agx-api-key",
                base_url=shared_url,
                competition_id=shared_comp,
            ))
    return accounts


def duplicate_key_groups(accounts: list[Account]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for account in accounts:
        if account.key:
            groups.setdefault(key_fingerprint(account.key), []).append(
                account.name)
    return {fingerprint: names for fingerprint, names in groups.items()
            if len(names) > 1}


def default_account_name(
        accounts: list[Account],
        environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    selector = env_value(env, "RSI_ACCOUNT")
    if selector:
        name = normalize_account_name(selector)
        if not any(account.name == name for account in accounts):
            raise AccountError(
                f"RSI_ACCOUNT selects unknown account {name!r}; configured: "
                + ", ".join(account.name for account in accounts)
            )
        return name
    main = next((account.name for account in accounts
                 if account.name == DEFAULT_ACCOUNT_NAME), None)
    if main:
        return main
    if len(accounts) == 1:
        return accounts[0].name
    if not accounts:
        raise AccountError(
            "no AGX accounts configured; set RSI_ACCOUNT_API_KEY or "
            "RSI_ACCOUNT_<NAME>_API_KEY"
        )
    raise AccountError(
        "multiple accounts configured ("
        + ", ".join(account.name for account in accounts)
        + "); pass --account NAME or set RSI_ACCOUNT"
    )


def select_account(accounts: list[Account], name: str | None = None,
                   environ: Mapping[str, str] | None = None) -> Account:
    target = (default_account_name(accounts, environ) if name is None
              else normalize_account_name(name))
    for account in accounts:
        if account.name == target:
            return account
    raise AccountError(
        f"unknown account {target!r}; configured: "
        + ", ".join(account.name for account in accounts)
    )


def require_account_key(account: Account,
                        competition_id: str | None = None) -> Account:
    if not account.key:
        env_name = ("RSI_ACCOUNT_API_KEY" if account.name == DEFAULT_ACCOUNT_NAME
                    else f"RSI_ACCOUNT_{account.name.upper()}_API_KEY")
        aliases = [env_name]
        if account.name.startswith("account"):
            number = account.name[len("account"):]
            if number.isdigit():
                aliases.append(f"RSI_ACCOUNT_API_KEY_{number}")
        services = [f"agx-api-key-{account.name}"]
        if account.name == DEFAULT_ACCOUNT_NAME:
            services.insert(0, "agx-api-key")
        raise AccountError(
            f"account {account.name!r} has no API key; set "
            + " or ".join(aliases)
            + " or Keychain item "
            + " / ".join(f"'{service}'" for service in services)
        )
    competition = (competition_id or account.competition_id
                   or DEFAULT_COMPETITION_ID)
    if account.key.strip() == competition:
        raise AccountError(
            f"account {account.name!r} key equals the competition ID, not "
            "an API key"
        )
    return account


def resolve_account(
        name: str | None = None,
        environ: Mapping[str, str] | None = None,
        keychain_lookup: Callable[[str], str | None] | None = None,
        require_key: bool = True,
) -> Account:
    accounts = discover_accounts(environ=environ,
                                 keychain_lookup=keychain_lookup)
    account = select_account(accounts, name=name, environ=environ)
    if require_key:
        require_account_key(account)
    return account


def select_accounts_for_cli(
        accounts: list[Account],
        *,
        account: str | None = None,
        accounts_arg: str | None = None,
        all_accounts: bool = False,
        default_all: bool = False,
        environ: Mapping[str, str] | None = None,
        require_keys: bool = True,
) -> list[Account]:
    if account is not None and accounts_arg is not None:
        raise AccountError("use only one of --account and --accounts")
    if all_accounts and (account is not None or accounts_arg is not None):
        raise AccountError(
            "use only one of --account/--accounts and --all-accounts")
    if all_accounts or (default_all and account is None and accounts_arg is None):
        selected = list(accounts)
    elif accounts_arg is not None:
        names = parse_account_names(accounts_arg)
        if not names:
            raise AccountError("--accounts is empty")
        selected = []
        for name in names:
            candidate = select_account(accounts, name=name, environ={})
            if candidate not in selected:
                selected.append(candidate)
    else:
        selected = [select_account(accounts, name=account, environ=environ)]
    if not selected:
        raise AccountError("no AGX accounts configured")
    if require_keys:
        for candidate in selected:
            require_account_key(candidate)
    return selected


def public_account(account: Account) -> dict:
    return {
        "name": account.name,
        "base_url": account.base_url,
        "competition_id": account.competition_id,
        "agent_id": account.agent_id,
        "has_key": account.has_key,
        "key_fingerprint": account.fingerprint,
        "key_source": account.key_source,
    }


def effective_base_url(account: Account, override: str | None = None) -> str:
    value = (override or account.base_url or "").strip()
    if not value:
        raise AccountError(
            f"account {account.name!r} has no base URL; set RSI_URL or "
            f"RSI_ACCOUNT_{account.name.upper()}_URL"
        )
    if not value.startswith(("http://", "https://")):
        raise AccountError(
            f"account {account.name!r} base URL must start with "
            "http:// or https://"
        )
    return value


def competition_aliases(
        environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Map game ids to competition ids from RSI_COMPETITION_<GAME>.

    Both RSI_COMPETITION_FPS and RSI_COMPETITION_ID_FPS are accepted; the
    shorter spelling wins when both define the same game.
    """
    env = os.environ if environ is None else environ
    aliases: dict[str, str] = {}
    for env_name, value in env.items():
        if not env_name.startswith("RSI_COMPETITION_"):
            continue
        game = env_name[len("RSI_COMPETITION_"):].strip().lower()
        if not game or game == "id":
            continue
        if game.startswith("id_"):
            game = game[len("id_"):]
        value = (value or "").strip()
        if game and value:
            aliases.setdefault(game, value)
    return aliases


def resolve_competition_id(
        override: str | None = None,
        *,
        account: Account | None = None,
        game_id: str | None = None,
        environ: Mapping[str, str] | None = None) -> str:
    """Resolve a competition UUID from a UUID or a game alias.

    Precedence: explicit override (UUID or alias) > explicit game id >
    the account's configured competition > shared RSI_COMPETITION_ID >
    the built-in default.
    """
    env = os.environ if environ is None else environ
    aliases = competition_aliases(env)
    if override is not None and override.strip():
        value = override.strip()
        return aliases.get(value.lower(), value)
    if game_id is not None and str(game_id).strip():
        mapped = aliases.get(str(game_id).strip().lower())
        if mapped:
            return mapped
    if account is not None and account.competition_id:
        value = account.competition_id.strip()
        return aliases.get(value.lower(), value)
    shared = env_value(env, "RSI_COMPETITION_ID")
    if shared:
        return aliases.get(shared.lower(), shared)
    return DEFAULT_COMPETITION_ID


def effective_competition_id(
        account: Account,
        override: str | None = None,
        game_id: str | None = None,
        environ: Mapping[str, str] | None = None) -> str:
    return resolve_competition_id(
        override, account=account, game_id=game_id, environ=environ)


def _lenient_account_keys(
        keychain_lookup: Callable[[str], str | None] | None = None,
) -> list[tuple[str, str]]:
    """Scan keys without requiring a valid account configuration."""
    lookup = keychain_lookup or keychain_key
    env = os.environ
    pairs: list[tuple[str, str]] = []

    def add(name: str, value: str | None) -> None:
        value = (value or "").strip()
        if value and all(value != existing for _, existing in pairs):
            pairs.append((name, value))

    add(DEFAULT_ACCOUNT_NAME, env.get("RSI_ACCOUNT_API_KEY"))
    names: set[str] = set()
    for env_name, value in env.items():
        matched = _match_account_env_var(env_name)
        if not matched:
            continue
        name, suffix = matched
        names.add(name)
        if suffix == "API_KEY":
            add(name, value)
    try:
        names.update(parse_account_names(env.get("RSI_ACCOUNTS")))
    except AccountError:
        pass
    for name in sorted(names):
        if not any(existing == name for existing, _ in pairs):
            add(name, lookup(f"agx-api-key-{name}"))
    if not any(existing == DEFAULT_ACCOUNT_NAME for existing, _ in pairs):
        add(DEFAULT_ACCOUNT_NAME, lookup("agx-api-key"))
    return pairs


def all_account_keys() -> list[tuple[str, str]]:
    """Return (account name, key) pairs; never print or serialize them."""
    try:
        accounts = discover_accounts()
    except AccountError:
        return _lenient_account_keys()
    pairs: list[tuple[str, str]] = []
    for account in accounts:
        if account.key and all(account.key != value for _, value in pairs):
            pairs.append((account.name, account.key))
    return pairs or _lenient_account_keys()


def write_json_file(path: Path, data, mode: int = 0o600) -> None:
    """Atomically write JSON with restrictive permissions."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, mode)
    except OSError:
        pass
    os.replace(temporary, path)


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


def fetch_paged_items(client: Client, path: str,
                      limit: int = 100) -> tuple[int, list]:
    """Fetch all pages of an entries/leaderboard-style list.

    The live deployment defaults to 30 items without an explicit limit, which
    can push the current account's `is_mine` entry onto a later page.  Query
    params such as `mine`/`agent_id` return 404, but `limit`/`offset` work.
    """
    items: list = []
    offset = 0
    while True:
        url = f"{path}?limit={limit}&offset={offset}"
        status, _, raw = client.request("GET", url)
        data = decode_json(raw)
        if status != 200 or not isinstance(data, dict):
            if offset == 0:
                status, _, raw = client.request("GET", path)
                data = decode_json(raw)
                if status != 200 or not isinstance(data, dict):
                    return status, []
                return status, list(data.get("items", []))
            return status, items
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
    return status, items


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
    pairs = all_account_keys()
    if not pairs:
        return
    for rel, path in files:
        data = path.read_bytes()
        for name, key in pairs:
            if key.encode("utf-8") in data:
                die(
                    "refusing to package: the API key for account "
                    f"{name!r} appears in {rel.as_posix()}"
                )
    if zip_path and zip_path.exists():
        data = zip_path.read_bytes()
        for name, key in pairs:
            if key.encode("utf-8") in data:
                die(
                    "refusing to package: the API key for account "
                    f"{name!r} appears in the ZIP"
                )


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
    account = resolve_account(name=args.account)
    competition_id = effective_competition_id(
        account, args.competition_id, args.game_id)
    client = Client(effective_base_url(account, args.base_url), account.key)
    print(
        f"account: {account.name} ({account.fingerprint})",
        file=sys.stderr,
    )
    endpoints = [
        "/api/v1/games",
        f"/api/v1/competitions/{competition_id}",
        f"/api/v1/me/competitions/{competition_id}/versions",
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
        raise AccountFailure("invalid Python receipt: expected a JSON object")
    for field in ("id", "bundle_sha256", "runtime_id", "profile_digest"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise AccountFailure(f"invalid Python receipt: missing {field}")
    if data["bundle_sha256"] != zip_sha:
        raise AccountFailure(
            "invalid Python receipt: bundle_sha256 does not match the ZIP "
            f"({data['bundle_sha256']} != {zip_sha})"
        )
    if data["runtime_id"] != "python-agent-v1":
        raise AccountFailure(
            f"invalid Python receipt: unexpected runtime_id "
            f"{data['runtime_id']!r}"
        )
    if profile_digest and data["profile_digest"] != profile_digest:
        raise AccountFailure(
            "invalid Python receipt: profile_digest does not match the live "
            f"template ({data['profile_digest']} != {profile_digest})"
        )
    if data.get("admission") not in {"queued", "running", "passed", "failed"}:
        raise AccountFailure(
            f"invalid Python receipt: unexpected admission "
            f"{data.get('admission')!r}"
        )
    return data


@dataclass
class PreparedSubmission:
    account: Account
    client: Client = field(repr=False)
    base_url: str = ""
    competition_id: str = ""
    game_id: str = ""
    rules_version: str | None = None
    profile_digest: str | None = None
    registered: bool = False
    agent_id: str | None = None
    idempotency_key: str = ""

    @property
    def agent_action(self) -> str:
        return "use" if self.agent_id else "create"

    def plan(self, zip_path: Path, zip_sha: str) -> dict:
        return {
            "account": self.account.name,
            "key_fingerprint": self.account.fingerprint,
            "base_url": self.base_url,
            "competition_id": self.competition_id,
            "game_id": self.game_id,
            "rules_version": self.rules_version,
            "agent_id": self.agent_id,
            "agent_action": self.agent_action,
            "registered": self.registered,
            "profile_digest": self.profile_digest,
            "zip": str(zip_path),
            "zip_sha256": zip_sha,
            "idempotency_key": self.idempotency_key,
        }


def _entry_summary(entry: dict | None) -> dict | None:
    if not isinstance(entry, dict):
        return None
    version = entry.get("version")
    if isinstance(version, dict):
        number = version.get("number")
        code_hash = version.get("code_hash_short")
        version_id = version.get("id")
    else:
        number = entry.get("version_number")
        code_hash = entry.get("code_hash_short")
        version_id = entry.get("version_id")
    return {
        "id": entry.get("id"),
        "agent_id": entry.get("agent_id"),
        "version_id": version_id,
        "version_number": number,
        "code_hash_short": code_hash,
    }


def prepare_submission(account: Account, args, zip_sha: str,
                       idempotency_key: str) -> PreparedSubmission:
    """Read-only planning for one account; never issues a POST."""
    base_url = effective_base_url(account, args.base_url)
    competition_id = effective_competition_id(
        account, args.competition_id, args.game_id)
    require_account_key(account, competition_id)
    client = Client(base_url, account.key)
    comp_path = (
        "/api/v1/competitions/"
        + urllib.parse.quote(competition_id, safe="")
    )
    comp_status, _, comp_raw = client.request("GET", comp_path)
    competition = decode_json(comp_raw)
    if comp_status != 200 or not isinstance(competition, dict):
        raise AccountFailure(
            f"cannot read competition {competition_id} (HTTP {comp_status})",
            auth=comp_status in {401, 403},
        )
    game_id = args.game_id or competition.get("game_id")
    if not game_id:
        raise AccountFailure("cannot determine the game_id; pass --game-id")

    template_path = (
        "/api/v1/python-submissions/templates/"
        + urllib.parse.quote(str(game_id), safe="")
    )
    template_status, _, template_raw = client.request("GET", template_path)
    template = decode_json(template_raw)
    profile_digest = None
    if template_status == 200 and isinstance(template, dict):
        profile = template.get("profile") or {}
        profile_digest = profile.get("profile_digest")
        if profile.get("runtime_id") != "python-agent-v1":
            raise AccountFailure(
                f"unexpected Python runtime: "
                f"{profile.get('runtime_id')!r}"
            )
        if profile.get("contract_id") != competition.get("rules_version"):
            raise AccountFailure(
                "template contract does not match the competition "
                "rules_version "
                f"({profile.get('contract_id')!r} != "
                f"{competition.get('rules_version')!r})"
            )
        files = template.get("files") or []
        entries = [item.get("path") for item in files
                   if isinstance(item, dict)]
        if "agent.py" not in entries:
            raise AccountFailure(
                "live Python template does not list agent.py as an entry")
    elif template_status in {401, 403}:
        raise AccountFailure(
            f"Python template authentication failed (HTTP {template_status})",
            auth=True,
        )
    else:
        print(
            f"warning: [{account.name}] Python template unavailable "
            f"(HTTP {template_status}); continuing",
            file=sys.stderr,
        )

    reg_path = (
        "/api/v1/python-submissions/competitions/"
        + urllib.parse.quote(competition_id, safe="")
        + "/registration"
    )
    reg_status, _, reg_raw = client.request("GET", reg_path)
    if reg_status in {401, 403}:
        raise AccountFailure(
            f"registration lookup failed (HTTP {reg_status})", auth=True)
    registration = decode_json(reg_raw) if reg_status == 200 else {}
    if reg_status != 200:
        print(
            f"warning: [{account.name}] registration lookup returned "
            f"HTTP {reg_status}; will try to register",
            file=sys.stderr,
        )
    registered = (
        isinstance(registration, dict)
        and registration.get("registered") is True
    )
    registration_agent = (
        registration.get("agent_id")
        if isinstance(registration, dict) else None
    )
    agent_id = args.agent_id or account.agent_id or registration_agent
    if (registration_agent and agent_id
            and str(registration_agent) != str(agent_id)):
        print(
            f"warning: [{account.name}] configured agent_id {agent_id} "
            f"differs from the live registration {registration_agent}; "
            "using the configured one",
            file=sys.stderr,
        )
    return PreparedSubmission(
        account=account,
        client=client,
        base_url=base_url,
        competition_id=competition_id,
        game_id=str(game_id),
        rules_version=competition.get("rules_version"),
        profile_digest=profile_digest,
        registered=registered,
        agent_id=str(agent_id) if agent_id else None,
        idempotency_key=idempotency_key,
    )


def execute_submission(prepared: PreparedSubmission, args,
                       zip_bytes: bytes, zip_sha: str,
                       verbose: bool) -> dict:
    """Register, upload, admit, activate, and verify one account."""
    account = prepared.account
    client = prepared.client
    competition_id = prepared.competition_id
    quoted_comp = urllib.parse.quote(str(competition_id), safe="")
    reg_path = (
        "/api/v1/python-submissions/competitions/"
        + quoted_comp
        + "/registration"
    )
    agent_id = prepared.agent_id
    agent_created = False
    partial: dict = {}
    if not agent_id:
        id_status, _, id_raw = client.request(
            "POST",
            "/api/v1/python-submissions/agents",
            body={"game_id": prepared.game_id},
        )
        identity = decode_json(id_raw)
        if id_status in {401, 403}:
            raise AccountFailure(
                "cannot create the Python submission identity "
                f"(HTTP {id_status})", auth=True)
        if (id_status not in {200, 201}
                or not isinstance(identity, dict)
                or not identity.get("id")):
            raise AccountFailure(
                "cannot create/resolve the Python submission identity "
                f"(HTTP {id_status})")
        agent_id = str(identity["id"])
        agent_created = True
        partial["agent_id"] = agent_id
    quoted_agent = urllib.parse.quote(str(agent_id), safe="")
    if not prepared.registered:
        status, _, raw = client.request(
            "POST", reg_path, body={"agent_id": str(agent_id)})
        if verbose:
            show(f"POST {reg_path}", status, decode_json(raw))
        else:
            print(f"[{account.name}] registration -> HTTP {status}")
        if status in {401, 403}:
            raise AccountFailure(
                f"registration failed (HTTP {status})",
                auth=True, partial=partial)
        if status not in {200, 201, 204, 409}:
            raise AccountFailure(
                f"registration failed (HTTP {status})", partial=partial)
    upload_path = (
        "/api/v1/python-submissions/agents/"
        + quoted_agent
        + "/bundles"
    )
    status, headers, raw = client.request(
        "POST",
        upload_path,
        body=zip_bytes,
        headers={
            "Content-Type": "application/zip",
            "Idempotency-Key": prepared.idempotency_key,
        },
        attempts=5,
    )
    receipt = decode_json(raw)
    if verbose:
        show(f"POST {upload_path}", status, receipt)
    else:
        print(f"[{account.name}] upload -> HTTP {status}")
    if status in {401, 403}:
        raise AccountFailure(
            "authentication/permission failure; use a valid key for "
            f"account {account.name!r}", auth=True, partial=partial)
    if status == 409:
        history_path = (
            "/api/v1/python-submissions/agents/"
            + quoted_agent
            + "/bundles"
        )
        try:
            hist_status, _, hist_raw = client.request("GET", history_path)
            if verbose:
                show(f"GET {history_path}", hist_status,
                     decode_json(hist_raw))
        except Exception:
            pass
        raise AccountFailure(
            "409: reuse the existing bundle/version; do not bypass "
            "idempotency", partial=partial)
    if status not in {200, 201, 202}:
        detail = (
            json.dumps(receipt, ensure_ascii=False)[:1000]
            if isinstance(receipt, (dict, list)) else str(receipt)[:1000]
        )
        raise AccountFailure(
            f"upload failed (HTTP {status}): {detail}", partial=partial)
    receipt = validate_python_receipt(
        receipt, zip_sha, prepared.profile_digest)
    bundle_id = receipt["id"]
    admission = receipt["admission"]
    partial.update({
        "agent_id": str(agent_id),
        "bundle_id": bundle_id,
        "admission": admission,
    })
    status_path = (
        "/api/v1/python-submissions/bundles/"
        + urllib.parse.quote(str(bundle_id), safe="")
    )
    deadline = time.monotonic() + args.poll_timeout
    while admission in {"queued", "running"}:
        if time.monotonic() >= deadline:
            raise AccountFailure(
                f"admission still {admission}; keep idempotency key "
                f"{prepared.idempotency_key} and poll {status_path} later",
                partial=partial,
            )
        time.sleep(2)
        poll_status, _, poll_raw = client.request("GET", status_path)
        receipt = decode_json(poll_raw)
        if verbose:
            show(f"GET {status_path}", poll_status, receipt)
        if poll_status in {401, 403}:
            raise AccountFailure(
                f"admission poll failed (HTTP {poll_status})",
                auth=True, partial=partial)
        if poll_status != 200:
            raise AccountFailure(
                f"admission poll failed (HTTP {poll_status})",
                partial=partial)
        receipt = validate_python_receipt(
            receipt, zip_sha, prepared.profile_digest)
        admission = receipt["admission"]
        partial["admission"] = admission
    if admission != "passed":
        raise AccountFailure(
            f"admission {admission}; bundle {bundle_id} is not active",
            partial=partial)
    activation = None
    if not args.no_activate:
        activation_path = (
            "/api/v1/python-submissions/competitions/"
            + quoted_comp
            + "/versions"
        )
        act_status, _, act_raw = client.request(
            "POST",
            activation_path,
            body={"submission_id": bundle_id, "auto_match": True},
            attempts=5,
        )
        activation = decode_json(act_raw)
        if verbose:
            show(f"POST {activation_path}", act_status, activation)
        else:
            print(f"[{account.name}] activation -> HTTP {act_status}")
        if act_status in {401, 403}:
            raise AccountFailure(
                f"activation failed (HTTP {act_status})",
                auth=True, partial=partial)
        if act_status not in {200, 201}:
            raise AccountFailure(
                f"activation failed (HTTP {act_status})",
                partial=partial)
    verification = []
    version_id = None
    version_number = None
    bundles_path = (
        "/api/v1/python-submissions/agents/" + quoted_agent + "/bundles")
    versions_path = (
        "/api/v1/me/competitions/" + quoted_comp + "/versions")
    for path in (bundles_path, versions_path):
        try:
            info_status, _, info_raw = client.request("GET", path)
            info_data = decode_json(info_raw)
            if verbose:
                show(f"GET {path}", info_status, info_data, limit=8000)
            verification.append({"path": path, "status": info_status})
            if (path == bundles_path and info_status == 200
                    and isinstance(info_data, dict)):
                for item in info_data.get("items", []):
                    if (isinstance(item, dict)
                            and item.get("id") == bundle_id):
                        version_id = item.get("version_id")
                        version_number = item.get("number")
                        break
        except Exception as exc:
            verification.append({
                "path": path,
                "error": type(exc).__name__,
            })
    if version_id is None and isinstance(activation, dict):
        version_id = activation.get("version_id")
    entry = None
    entries_path = (
        "/api/v1/competitions/" + quoted_comp + "/entries"
    )
    try:
        entries_status, entries = fetch_paged_items(client, entries_path)
        if entries_status == 200:
            mine = next(
                (item for item in entries
                 if isinstance(item, dict) and item.get("is_mine")),
                None,
            )
            entry = _entry_summary(mine)
        else:
            verification.append({
                "path": entries_path,
                "status": entries_status,
            })
    except Exception as exc:
        verification.append({
            "path": entries_path,
            "error": type(exc).__name__,
        })
    return {
        "account": account.name,
        "key_fingerprint": account.fingerprint,
        "base_url": prepared.base_url,
        "competition_id": competition_id,
        "game_id": prepared.game_id,
        "agent_id": str(agent_id),
        "agent_created": agent_created,
        "registered": prepared.registered,
        "bundle_id": bundle_id,
        "admission": admission,
        "activated": not args.no_activate,
        "version_id": version_id,
        "version_number": version_number,
        "zip_sha256": zip_sha,
        "idempotency_key": prepared.idempotency_key,
        "activation": activation,
        "entry": entry,
        "verification": verification,
    }


def _compact_submit_plan(plan: dict) -> dict:
    return {
        key: plan.get(key) for key in (
            "account", "key_fingerprint", "base_url", "competition_id",
            "game_id", "rules_version", "agent_id", "agent_action",
            "registered", "profile_digest", "idempotency_key",
        )
    }


def _write_submit_receipt(path: Path | None, receipt: dict) -> None:
    if path is not None:
        write_json_file(path, receipt)


def cmd_submit(args) -> int:
    zip_path = Path(args.zip).expanduser().resolve()
    if not zip_path.is_file():
        die(f"ZIP does not exist: {zip_path}")
    zip_bytes = zip_path.read_bytes()
    zip_sha = sha256_bytes(zip_bytes)

    accounts = discover_accounts()
    batch = args.all_accounts or args.accounts is not None
    if batch and args.agent_id:
        die(
            "--agent-id is account-scoped; set RSI_ACCOUNT_<NAME>_AGENT_ID "
            "or omit it so each account discovers its own agent"
        )
    if batch and args.idempotency_key:
        die(
            "--idempotency-key cannot be shared across accounts; batch "
            "mode derives one per account"
        )
    targets = select_accounts_for_cli(
        accounts,
        account=args.account,
        accounts_arg=args.accounts,
        all_accounts=args.all_accounts,
        environ=os.environ,
        require_keys=True,
    )
    duplicates = duplicate_key_groups(targets)
    if batch and duplicates:
        detail = "; ".join(
            f"{', '.join(names)} share {fingerprint}"
            for fingerprint, names in duplicates.items()
        )
        die(
            "selected accounts share an API key "
            f"({detail}); fix .env before submitting"
        )
    if len(targets) > 1:
        batch = True

    plans: list[PreparedSubmission] = []
    try:
        for account in targets:
            if batch:
                idempotency_key = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"agx-submit:{account.name}:{zip_sha}",
                ))
            else:
                idempotency_key = (
                    args.idempotency_key or str(uuid.uuid4()))
            plans.append(prepare_submission(
                account, args, zip_sha, idempotency_key))
    except (AccountFailure, AccountError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "batch aborted before any upload; fix the account and retry.",
            file=sys.stderr,
        )
        return 2

    verbose = len(plans) == 1
    plan_entries = [plan.plan(zip_path, zip_sha) for plan in plans]
    if len(plan_entries) == 1:
        print(json.dumps(plan_entries[0], ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "zip": str(zip_path),
            "zip_sha256": zip_sha,
            "accounts": plan_entries,
        }, ensure_ascii=False, indent=2))

    receipt_path = (
        Path(args.receipt_out).expanduser()
        if args.receipt_out else None
    )
    receipt = {
        "schema_version": 1,
        "command": "submit",
        "zip": str(zip_path),
        "zip_sha256": zip_sha,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "accounts": [
            {**entry, "status": "dry_run" if not args.yes else "planned"}
            for entry in plan_entries
        ],
        "ok": False,
    }
    _write_submit_receipt(receipt_path, receipt)
    if not args.yes:
        print(
            "\nDry run only. Re-run with --yes to upload and activate "
            "these bundles."
        )
        return 0

    results = []
    exit_code = 0
    for index, plan in enumerate(plans):
        entry = plan.plan(zip_path, zip_sha)
        try:
            result = execute_submission(
                plan, args, zip_bytes, zip_sha, verbose)
            result["status"] = (
                "activated" if result.get("activated") else "admitted")
            results.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except AccountFailure as exc:
            failed = {
                **_compact_submit_plan(entry),
                **exc.partial,
                "zip_sha256": zip_sha,
                "status": "failed",
                "error": str(exc),
                "auth_error": exc.auth,
            }
            results.append(failed)
            exit_code = 2
            print(
                f"[{plan.account.name}] failed: {exc}",
                file=sys.stderr,
            )
        except Exception as exc:
            failed = {
                **_compact_submit_plan(entry),
                "zip_sha256": zip_sha,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "auth_error": False,
            }
            results.append(failed)
            exit_code = 2
            print(
                f"[{plan.account.name}] failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        receipt["accounts"] = results + [
            {**remaining, "status": "skipped"}
            for remaining in plan_entries[index + 1:]
        ]
        _write_submit_receipt(receipt_path, receipt)

    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    receipt["ok"] = exit_code == 0
    receipt["accounts"] = results
    _write_submit_receipt(receipt_path, receipt)
    if len(results) > 1:
        print(json.dumps({
            "accounts": [
                {
                    "account": result.get("account"),
                    "status": result.get("status"),
                    "agent_id": result.get("agent_id"),
                    "bundle_id": result.get("bundle_id"),
                    "admission": result.get("admission"),
                    "activated": result.get("activated"),
                    "version_id": result.get("version_id"),
                    "version_number": result.get("version_number"),
                    "entry": result.get("entry"),
                    "error": result.get("error"),
                }
                for result in results
            ],
            "ok": exit_code == 0,
        }, ensure_ascii=False, indent=2))
    print(
        "\nUpload/admission/activation success is not a full match, "
        "score, or win."
    )
    if exit_code:
        print(
            "Some accounts failed; successful accounts are listed above. "
            "Use --receipt-out for evidence.",
            file=sys.stderr,
        )
    return exit_code


def _find_competition_item(items, competition_id: str):
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if (item.get("competition") or {}).get("id") == competition_id:
            return item
    return None


def _check_account(account: Account,
                   competition_id_override: str | None = None) -> dict:
    if not account.key:
        return {"ok": False, "error": "missing API key"}
    try:
        base_url = effective_base_url(account)
    except AccountError as exc:
        return {"ok": False, "error": str(exc)}
    competition_id = effective_competition_id(account, competition_id_override)
    client = Client(base_url, account.key)
    result = {
        "ok": True,
        "competition_id": competition_id,
        "warnings": [],
        "errors": [],
    }
    try:
        status, _, raw = client.request("GET", "/api/v1/me/competitions")
        data = decode_json(raw)
        if status == 200 and isinstance(data, dict):
            item = _find_competition_item(
                data.get("items", []), competition_id)
            result["me"] = {
                "standing": (item or {}).get("standing"),
                "round_match": (item or {}).get("round_match"),
                "next_round": (item or {}).get("next_round"),
                "current_version": (item or {}).get("current_version"),
            }
        else:
            result["errors"].append(
                f"GET /api/v1/me/competitions -> HTTP {status}")
    except Exception as exc:
        result["errors"].append(
            "GET /api/v1/me/competitions: " + type(exc).__name__)

    reg_path = (
        "/api/v1/python-submissions/competitions/"
        + urllib.parse.quote(competition_id, safe="")
        + "/registration"
    )
    try:
        status, _, raw = client.request("GET", reg_path)
        data = decode_json(raw)
        if status == 200 and isinstance(data, dict):
            result["registered"] = data.get("registered") is True
            result["registration_agent_id"] = data.get("agent_id")
        elif status in {401, 403}:
            result["errors"].append(
                f"GET {reg_path} -> HTTP {status} (auth)")
        else:
            result["registered"] = False
            result["warnings"].append(
                f"GET {reg_path} -> HTTP {status}")
    except Exception as exc:
        result["errors"].append(
            f"GET {reg_path}: {type(exc).__name__}")

    entries_path = (
        "/api/v1/competitions/"
        + urllib.parse.quote(competition_id, safe="")
        + "/entries"
    )
    try:
        status, entries = fetch_paged_items(client, entries_path)
        if status == 200:
            mine = next(
                (item for item in entries
                 if isinstance(item, dict) and item.get("is_mine")),
                None,
            )
            result["entry"] = _entry_summary(mine)
        else:
            result["errors"].append(
                f"GET {entries_path} -> HTTP {status}")
    except Exception as exc:
        result["errors"].append(
            f"GET {entries_path}: {type(exc).__name__}")
    result["ok"] = not result["errors"]
    return result


def cmd_accounts(args) -> int:
    accounts = discover_accounts()
    duplicates = duplicate_key_groups(accounts)
    payload = {
        "accounts": [],
        "duplicate_keys": duplicates,
    }
    try:
        payload["default"] = default_account_name(accounts)
    except AccountError:
        payload["default"] = None
    override = args.competition_id
    if override is None and args.game_id:
        override = resolve_competition_id(None, game_id=args.game_id)
    failed = False
    for account in accounts:
        item = public_account(account)
        if args.check:
            check = _check_account(account, override)
            item.update(check)
            if not check.get("ok"):
                failed = True
        payload["accounts"].append(item)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not accounts:
            print("no AGX accounts configured")
        for item in payload["accounts"]:
            agent = (item.get("agent_id")
                     or item.get("registration_agent_id")
                     or "(auto)")
            print(
                f"{item['name']}: {item['key_fingerprint'] or '(missing key)'}"
                f"  source={item['key_source']}"
                f"  url={item['base_url'] or '(none)'}"
                f"  competition={item['competition_id'] or '(default)'}"
                f"  agent={agent}"
            )
            if args.check:
                if item.get("errors"):
                    for error in item["errors"]:
                        print(f"  error: {error}")
                else:
                    me = item.get("me") or {}
                    print(
                        "  checked: "
                        f"registered={item.get('registered')} "
                        f"standing={me.get('standing')} "
                        f"version={(item.get('entry') or {}).get('version_number')}"
                    )
                for warning in item.get("warnings") or []:
                    print(f"  warning: {warning}")
        if payload["default"]:
            print(f"default account: {payload['default']}")
    if duplicates:
        print(
            "warning: accounts share an API key: " + "; ".join(
                f"{', '.join(names)} -> {fingerprint}"
                for fingerprint, names in duplicates.items()
            ),
            file=sys.stderr,
        )
    return 2 if failed else 0


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


def add_account_selector(parser: argparse.ArgumentParser,
                         *, multi: bool = False) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--account", default=None,
        help="account name (default: RSI_ACCOUNT or main)")
    if multi:
        group.add_argument(
            "--accounts", default=None,
            help="comma-separated account names")
        group.add_argument(
            "--all-accounts", action="store_true",
            help="use every configured account")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser(
        "discover", help="read-only game/competition/OpenAPI discovery")
    add_account_selector(discover)
    discover.add_argument("--base-url", default=None)
    discover.add_argument("--competition-id", default=None)
    discover.add_argument(
        "--game-id", default=None,
        help="game id; resolves RSI_COMPETITION_<GAME> when no competition id")
    discover.add_argument("--save-openapi", default="/tmp/agx-openapi.json")
    discover.set_defaults(func=cmd_discover)

    build = sub.add_parser(
        "build", help="build a submission ZIP and print its manifest")
    build.add_argument("--submission-dir", default=".")
    build.add_argument("--output", default="/tmp/agx-agent.zip")
    build.add_argument("--include", action="append", default=[])
    build.set_defaults(func=cmd_build)

    submit = sub.add_parser(
        "submit", help="upload a ZIP to the Python bundle endpoint")
    add_account_selector(submit, multi=True)
    submit.add_argument("--base-url", default=None)
    submit.add_argument("--competition-id", default=None)
    submit.add_argument("--game-id")
    submit.add_argument("--zip", required=True)
    submit.add_argument("--agent-id", default=None)
    submit.add_argument("--idempotency-key")
    submit.add_argument("--poll-timeout", type=float, default=600)
    submit.add_argument(
        "--no-activate", action="store_true",
        help="upload and admit without selecting the version")
    submit.add_argument(
        "--receipt-out",
        help="write a per-account submission receipt JSON (no keys)")
    submit.add_argument("--yes", action="store_true")
    submit.set_defaults(func=cmd_submit)

    accounts = sub.add_parser(
        "accounts", help="list configured AGX accounts")
    accounts.add_argument(
        "--check", action="store_true",
        help="read-only GET checks for registration, standing, version")
    accounts.add_argument(
        "--competition-id", default=None,
        help="override the competition checked; UUID or fps/racing alias")
    accounts.add_argument(
        "--game-id", default=None,
        help="game alias; resolves RSI_COMPETITION_<GAME>")
    accounts.add_argument("--json", action="store_true")
    accounts.set_defaults(func=cmd_accounts)

    archive = sub.add_parser(
        "archive", help="create a docs/submissions/MMDD-vX.YY snapshot")
    archive.add_argument("--repo-root", default=".")
    archive.add_argument("--submission-dir", default=".")
    archive.add_argument("--include", action="append", default=[])
    archive.add_argument("--notes", default="")
    archive.add_argument("--notes-file")
    archive.add_argument("--version", help="optional next version, e.g. v0.02")
    archive.add_argument("--date", help="optional MMDD prefix; defaults to today")
    archive.add_argument(
        "--competition-id",
        default=os.environ.get(
            "RSI_COMPETITION_ID", DEFAULT_COMPETITION_ID))
    archive.add_argument("--contract", default="unknown")
    archive.add_argument("--status", default="submitted")
    archive.add_argument("--api-result")
    archive.set_defaults(func=cmd_archive)

    return parser


def main() -> int:
    load_dotenv()
    parser = make_parser()
    args = parser.parse_args()
    if (getattr(args, "base_url", None) is not None
            and not args.base_url.strip()):
        die("--base-url/RSI_URL is required; do not guess the AGX instance")
    try:
        return args.func(args)
    except AccountError as exc:
        die(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

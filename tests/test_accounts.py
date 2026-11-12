"""Multi-account configuration and batch submission tests.

Run with: python3 -m unittest discover -s tests -v
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / ".claude/skills/agx-submit/scripts/agx_submit.py"
SPEC = importlib.util.spec_from_file_location("agx_submit_for_tests", HELPER)
AGX = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AGX
SPEC.loader.exec_module(AGX)


def discover(environ, keychain=None):
    return AGX.discover_accounts(
        environ=environ,
        keychain_lookup=keychain or (lambda service: None),
    )


def opaque_id(prefix, token):
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
    return prefix + digest


class AccountConfigTests(unittest.TestCase):
    def test_legacy_only_is_main(self):
        accounts = discover({
            "RSI_URL": "https://agx.invalid",
            "RSI_COMPETITION_ID": "comp-1",
            "RSI_ACCOUNT_API_KEY": "key-main",
            "RSI_AGENT_ID": "agent-main",
        })
        self.assertEqual([account.name for account in accounts], ["main"])
        self.assertEqual(accounts[0].key, "key-main")
        self.assertEqual(accounts[0].key_source, "env:RSI_ACCOUNT_API_KEY")
        self.assertEqual(accounts[0].agent_id, "agent-main")
        self.assertEqual(
            AGX.select_account(accounts, environ={}).name, "main")

    def test_legacy_main_remains_default_with_named_accounts(self):
        accounts = discover({
            "RSI_ACCOUNT_API_KEY": "key-main",
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_URL": "https://agx.invalid",
        })
        self.assertEqual([account.name for account in accounts],
                         ["main", "alice"])
        self.assertEqual(
            AGX.default_account_name(accounts, environ={}), "main")

    def test_single_named_account_is_default(self):
        accounts = discover({"RSI_ACCOUNT_ALICE_API_KEY": "key-alice"})
        self.assertEqual([account.name for account in accounts], ["alice"])
        self.assertEqual(
            AGX.default_account_name(accounts, environ={}), "alice")

    def test_ambiguous_named_accounts_fail(self):
        accounts = discover({
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        })
        with self.assertRaises(AGX.AccountError) as caught:
            AGX.default_account_name(accounts, environ={})
        self.assertIn("alice", str(caught.exception))
        self.assertIn("bob", str(caught.exception))

    def test_selector_and_cli_precedence(self):
        accounts = discover({
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        })
        self.assertEqual(
            AGX.select_account(
                accounts, environ={"RSI_ACCOUNT": "ALICE"}).name,
            "alice",
        )
        self.assertEqual(
            AGX.select_account(accounts, name="Bob", environ={}).name,
            "bob",
        )
        with self.assertRaises(AGX.AccountError):
            AGX.select_account(accounts, name="carol", environ={})
        with self.assertRaises(AGX.AccountError):
            AGX.select_account(
                accounts, environ={"RSI_ACCOUNT": "carol"})

    def test_accounts_list_controls_order(self):
        accounts = discover({
            "RSI_ACCOUNT_API_KEY": "key-main",
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
            "RSI_ACCOUNTS": "bob, alice, BOB",
        })
        self.assertEqual([account.name for account in accounts],
                         ["main", "bob", "alice"])

    def test_per_account_overrides_and_shared_fallback(self):
        accounts = discover({
            "RSI_URL": "https://shared.invalid",
            "RSI_COMPETITION_ID": "comp-shared",
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_ALICE_URL": "https://alice.invalid",
            "RSI_ACCOUNT_ALICE_COMPETITION_ID": "comp-alice",
            "RSI_ACCOUNT_ALICE_AGENT_ID": "agent-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        })
        by_name = {account.name: account for account in accounts}
        self.assertEqual(by_name["alice"].base_url,
                         "https://alice.invalid")
        self.assertEqual(by_name["alice"].competition_id, "comp-alice")
        self.assertEqual(by_name["alice"].agent_id, "agent-alice")
        self.assertEqual(by_name["bob"].base_url, "https://shared.invalid")
        self.assertEqual(by_name["bob"].competition_id, "comp-shared")

    def test_numbered_account_key_alias(self):
        accounts = discover({
            "RSI_ACCOUNT_API_KEY": "key-main",
            "RSI_ACCOUNT_API_KEY_2": "key-two",
            "RSI_ACCOUNT_AGENT_ID_2": "agent-two",
            "RSI_ACCOUNT_URL_2": "https://racing.invalid",
            "RSI_ACCOUNT_COMPETITION_ID_2": "comp-two",
        })
        by_name = {account.name: account for account in accounts}
        self.assertEqual(sorted(by_name), ["account2", "main"])
        second = by_name["account2"]
        self.assertEqual(second.key, "key-two")
        self.assertEqual(second.key_source, "env:RSI_ACCOUNT_API_KEY_2")
        self.assertEqual(second.agent_id, "agent-two")
        self.assertEqual(second.base_url, "https://racing.invalid")
        self.assertEqual(second.competition_id, "comp-two")

    def test_legacy_numbered_agent_id_alias(self):
        accounts = discover({
            "RSI_ACCOUNT_API_KEY_2": "key-two",
            "RSI_AGENT_ID_2": "agent-two",
        })
        self.assertEqual([account.name for account in accounts], ["account2"])
        self.assertEqual(accounts[0].agent_id, "agent-two")

    def test_competition_aliases_and_account_override(self):
        env = {
            "RSI_COMPETITION_ID": "cs-uuid",
            "RSI_COMPETITION_FPS": "cs-uuid",
            "RSI_COMPETITION_RACING": "racing-uuid",
            "RSI_ACCOUNT_API_KEY": "key-main",
            "RSI_ACCOUNT_API_KEY_2": "key-two",
            "RSI_ACCOUNT_COMPETITION_ID_2": "racing-uuid",
        }
        accounts = discover(env)
        by_name = {account.name: account for account in accounts}
        self.assertEqual(by_name["account2"].competition_id, "racing-uuid")
        self.assertEqual(
            AGX.competition_aliases(env),
            {"fps": "cs-uuid", "racing": "racing-uuid"},
        )
        self.assertEqual(
            AGX.resolve_competition_id("racing", environ=env),
            "racing-uuid",
        )
        self.assertEqual(
            AGX.resolve_competition_id("fps", environ=env), "cs-uuid")
        self.assertEqual(
            AGX.resolve_competition_id(
                None, game_id="racing", environ=env),
            "racing-uuid",
        )
        self.assertEqual(
            AGX.resolve_competition_id(
                None, account=by_name["account2"], environ=env),
            "racing-uuid",
        )
        self.assertEqual(
            AGX.resolve_competition_id("raw-uuid", environ=env),
            "raw-uuid",
        )
        self.assertEqual(
            AGX.competition_aliases(
                {"RSI_COMPETITION_ID_FPS": "cs-uuid"}),
            {"fps": "cs-uuid"},
        )

    def test_numbered_alias_conflicts_with_named_account(self):
        with self.assertRaises(AGX.AccountError):
            discover({
                "RSI_ACCOUNT_API_KEY_2": "key-two",
                "RSI_ACCOUNT_ACCOUNT2_API_KEY": "key-other",
            })

    def test_assert_no_key_scans_numbered_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.py"
            path.write_text("value = 'key-two'\n")
            files = [(Path("agent.py"), path)]
            env = {
                "AGX_NO_DOTENV": "1",
                "RSI_ACCOUNT_API_KEY": "key-main",
                "RSI_ACCOUNT_API_KEY_2": "key-two",
            }
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(AGX, "keychain_key",
                                      return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    AGX.assert_no_key(files)

    def test_main_legacy_and_named_definition_conflict(self):
        with self.assertRaises(AGX.AccountError):
            discover({
                "RSI_ACCOUNT_API_KEY": "key-main",
                "RSI_ACCOUNT_MAIN_API_KEY": "key-main-2",
            })

    def test_case_colliding_named_variables_conflict(self):
        with self.assertRaises(AGX.AccountError):
            discover({
                "RSI_ACCOUNT_ALICE_API_KEY": "key-one",
                "RSI_ACCOUNT_Alice_API_KEY": "key-two",
            })

    def test_missing_key_is_reported_when_selected(self):
        accounts = discover({"RSI_ACCOUNTS": "alice"})
        self.assertEqual([account.name for account in accounts], ["alice"])
        self.assertFalse(accounts[0].has_key)
        with self.assertRaises(AGX.AccountError):
            AGX.require_account_key(accounts[0])
        with self.assertRaises(AGX.AccountError):
            AGX.resolve_account(
                name="alice",
                environ={"RSI_ACCOUNTS": "alice"},
                keychain_lookup=lambda service: None,
            )

    def test_key_equal_to_competition_id_is_rejected(self):
        account = AGX.Account(
            name="main",
            key="comp-1",
            key_source="env:RSI_ACCOUNT_API_KEY",
            competition_id="comp-1",
        )
        with self.assertRaises(AGX.AccountError):
            AGX.require_account_key(account)

    def test_fingerprint_and_public_view_hide_key(self):
        account = AGX.Account(
            name="alice",
            key="super-secret-key",
            key_source="env:RSI_ACCOUNT_ALICE_API_KEY",
            base_url="https://agx.invalid",
        )
        self.assertNotIn("super-secret-key", repr(account))
        public = AGX.public_account(account)
        serialized = json.dumps(public)
        self.assertNotIn("super-secret-key", serialized)
        self.assertEqual(public["key_fingerprint"], account.fingerprint)
        self.assertTrue(public["key_fingerprint"].startswith("sha256:"))
        self.assertEqual(account.fingerprint, AGX.key_fingerprint(
            "super-secret-key"))
        other = AGX.Account(name="bob", key="other-secret")
        self.assertNotEqual(account.fingerprint, other.fingerprint)

    def test_keychain_fallback(self):
        keys = {
            "agx-api-key": "key-main",
            "agx-api-key-alice": "key-alice",
        }
        accounts = discover(
            {"RSI_ACCOUNTS": "alice,main"},
            keychain=lambda service: keys.get(service),
        )
        by_name = {account.name: account for account in accounts}
        self.assertEqual(by_name["alice"].key, "key-alice")
        self.assertEqual(by_name["alice"].key_source,
                         "keychain:agx-api-key-alice")
        self.assertEqual(by_name["main"].key, "key-main")
        self.assertEqual(by_name["main"].key_source,
                         "keychain:agx-api-key")

    def test_keychain_only_default_main(self):
        accounts = discover(
            {},
            keychain=lambda service: (
                "key-main" if service == "agx-api-key" else None),
        )
        self.assertEqual([account.name for account in accounts], ["main"])
        self.assertEqual(accounts[0].key, "key-main")

    def test_duplicate_key_detection(self):
        accounts = discover({
            "RSI_ACCOUNT_API_KEY": "same-key",
            "RSI_ACCOUNT_ALICE_API_KEY": "same-key",
        })
        groups = AGX.duplicate_key_groups(accounts)
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(next(iter(groups.values()))),
                         ["alice", "main"])

    def test_parse_account_names(self):
        self.assertEqual(
            AGX.parse_account_names("alice, bob; alice\ncarol"),
            ["alice", "bob", "carol"],
        )
        self.assertEqual(AGX.parse_account_names(""), [])
        with self.assertRaises(AGX.AccountError):
            AGX.parse_account_names("1alice")

    def test_select_accounts_for_cli(self):
        accounts = discover({
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        })
        selected = AGX.select_accounts_for_cli(
            accounts, accounts_arg="alice,bob,ALICE",
            environ={}, require_keys=True)
        self.assertEqual([account.name for account in selected],
                         ["alice", "bob"])
        selected_all = AGX.select_accounts_for_cli(
            accounts, all_accounts=True, environ={}, require_keys=True)
        self.assertEqual([account.name for account in selected_all],
                         ["alice", "bob"])
        with self.assertRaises(AGX.AccountError):
            AGX.select_accounts_for_cli(
                accounts, default_all=False, environ={},
                require_keys=True)

    def test_ambiguous_default_all_uses_every_account(self):
        accounts = discover({
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        })
        selected = AGX.select_accounts_for_cli(
            accounts, default_all=True, environ={}, require_keys=True)
        self.assertEqual([account.name for account in selected],
                         ["alice", "bob"])

    def test_fetch_paged_items_reads_all_pages(self):
        class FakeClient:
            def __init__(self):
                self.urls = []

            def request(self, method, url, **kwargs):
                self.urls.append(url)
                if "offset=0" in url:
                    body = {"items": [{"id": 1}, {"id": 2}], "total": 3}
                else:
                    body = {"items": [{"id": 3}], "total": 3}
                return 200, {}, json.dumps(body).encode()

        client = FakeClient()
        status, items = AGX.fetch_paged_items(client, "/entries")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in items], [1, 2, 3])
        self.assertEqual(len(client.urls), 2)

    def test_assert_no_key_scans_all_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.py"
            path.write_text("value = 'key-bob'\n")
            files = [(Path("agent.py"), path)]
            env = {
                "AGX_NO_DOTENV": "1",
                "RSI_ACCOUNT_API_KEY": "key-main",
                "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
            }
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(AGX, "keychain_key",
                                      return_value=None), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    AGX.assert_no_key(files)
            # Also assert the safe case does not fail.
            path.write_text("value = 1\n")
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(AGX, "keychain_key",
                                      return_value=None):
                AGX.assert_no_key(files)


class RecordingHandler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *args):
        pass

    def _send(self, status, data=None):
        body = b"" if data is None else json.dumps(data).encode()
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _auth_token(self):
        value = self.headers.get("Authorization") or ""
        return value[len("Bearer "):] if value.startswith("Bearer ") else ""

    def do_GET(self):
        self.state["requests"].append({
            "method": "GET",
            "path": self.path,
            "auth": self._auth_token(),
            "idempotency": self.headers.get("Idempotency-Key"),
        })
        path = self.path.split("?", 1)[0]
        if path == "/api/v1/competitions/comp-1":
            self._send(200, {
                "id": "comp-1",
                "game_id": "fps",
                "rules_version": "rsi-fps-5.5",
            })
        elif path == "/api/v1/python-submissions/templates/fps":
            self._send(200, {
                "profile": {
                    "runtime_id": "python-agent-v1",
                    "contract_id": "rsi-fps-5.5",
                    "profile_digest": "digest-1",
                },
                "files": [{"path": "agent.py"}],
            })
        elif path.endswith("/registration"):
            self._send(200, {"registered": False, "agent_id": None})
        elif path.endswith("/bundles"):
            self._send(200, {"items": []})
        elif path == "/api/v1/competitions/comp-1/entries":
            token = self._auth_token()
            self._send(200, {
                "items": [{
                    "id": "entry-1",
                    "is_mine": True,
                    "agent_id": opaque_id("agent-", token),
                    "version": {
                        "number": 1,
                        "code_hash_short": "abc123",
                    },
                }],
            })
        elif path.startswith("/api/v1/me/competitions/"):
            self._send(200, {"items": []})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        body = self._body()
        token = self._auth_token()
        self.state["requests"].append({
            "method": "POST",
            "path": self.path,
            "auth": token,
            "idempotency": self.headers.get("Idempotency-Key"),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        })
        path = self.path.split("?", 1)[0]
        if path == "/api/v1/python-submissions/agents":
            self._send(200, {"id": opaque_id("agent-", token)})
        elif path.endswith("/registration"):
            self._send(204)
        elif path.endswith("/bundles"):
            if token == self.state["fail_token"]:
                self._send(401, {"error": "bad key"})
                return
            self._send(201, {
                "id": opaque_id("bundle-", token),
                "bundle_sha256": hashlib.sha256(body).hexdigest(),
                "runtime_id": "python-agent-v1",
                "profile_digest": "digest-1",
                "admission": "passed",
            })
        elif path == "/api/v1/python-submissions/competitions/comp-1/versions":
            self._send(200, {
                "version_id": opaque_id("version-", token),
                "number": 1,
            })
        else:
            self._send(404, {"error": "not found"})


class BatchSubmitTests(unittest.TestCase):
    def setUp(self):
        self.state = {"requests": [], "fail_token": None}
        handler = type("BoundRecordingHandler", (RecordingHandler,),
                       {"state": self.state})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = (
            f"http://127.0.0.1:{self.server.server_address[1]}")
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tempdir.cleanup()

    def _zip(self):
        path = Path(self.tempdir.name) / "agent.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("agent.py", "def act(observation):\n"
                                        "    return {}\n")
        return path

    def _args(self, zip_path, receipt_path, yes, accounts="alice,bob"):
        return SimpleNamespace(
            base_url=self.base_url,
            competition_id="comp-1",
            game_id=None,
            zip=str(zip_path),
            agent_id=None,
            idempotency_key=None,
            poll_timeout=5,
            no_activate=False,
            receipt_out=str(receipt_path),
            yes=yes,
            account=None,
            accounts=accounts,
            all_accounts=False,
        )

    def _env(self):
        return {
            "AGX_NO_DOTENV": "1",
            "RSI_ACCOUNT_ALICE_API_KEY": "key-alice",
            "RSI_ACCOUNT_BOB_API_KEY": "key-bob",
        }

    def _run(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self._env(), clear=True), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = AGX.cmd_submit(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dry_run_is_read_only(self):
        zip_path = self._zip()
        receipt_path = Path(self.tempdir.name) / "receipt.json"
        code, stdout, _ = self._run(
            self._args(zip_path, receipt_path, yes=False))
        self.assertEqual(code, 0)
        self.assertEqual(
            [request for request in self.state["requests"]
             if request["method"] == "POST"],
            [],
        )
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(len(receipt["accounts"]), 2)
        self.assertEqual(
            {item["status"] for item in receipt["accounts"]},
            {"dry_run"},
        )
        self.assertIn("Dry run only", stdout)
        self.assertNotIn("key-alice", receipt_path.read_text())
        self.assertNotIn("key-bob", receipt_path.read_text())

    def test_batch_submit_uses_per_account_keys_and_agent_ids(self):
        zip_path = self._zip()
        receipt_path = Path(self.tempdir.name) / "receipt.json"
        code, stdout, stderr = self._run(
            self._args(zip_path, receipt_path, yes=True))
        self.assertEqual(code, 0, stderr)
        posts = [request for request in self.state["requests"]
                 if request["method"] == "POST"]
        uploads = [request for request in posts
                   if request["path"].endswith("/bundles")]
        self.assertEqual(len(uploads), 2)
        self.assertEqual(
            {request["auth"] for request in uploads},
            {"key-alice", "key-bob"},
        )
        alice_agent = opaque_id("agent-", "key-alice")
        bob_agent = opaque_id("agent-", "key-bob")
        self.assertEqual(
            {request["path"] for request in uploads},
            {
                f"/api/v1/python-submissions/agents/{alice_agent}/bundles",
                f"/api/v1/python-submissions/agents/{bob_agent}/bundles",
            },
        )
        keys = [request["idempotency"] for request in uploads]
        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(keys))
        receipt = json.loads(receipt_path.read_text())
        self.assertTrue(receipt["ok"])
        self.assertEqual(
            {item["status"] for item in receipt["accounts"]},
            {"activated"},
        )
        self.assertEqual(
            {item["agent_id"] for item in receipt["accounts"]},
            {alice_agent, bob_agent},
        )
        text = receipt_path.read_text()
        self.assertNotIn("key-alice", text)
        self.assertNotIn("key-bob", text)
        self.assertNotIn("key-alice", stdout)
        self.assertNotIn("key-bob", stdout)

    def test_one_auth_failure_does_not_stop_the_batch(self):
        self.state["fail_token"] = "key-bob"
        zip_path = self._zip()
        receipt_path = Path(self.tempdir.name) / "receipt.json"
        code, _, stderr = self._run(
            self._args(zip_path, receipt_path, yes=True))
        self.assertEqual(code, 2)
        receipt = json.loads(receipt_path.read_text())
        by_name = {item["account"]: item for item in receipt["accounts"]}
        self.assertEqual(by_name["alice"]["status"], "activated")
        self.assertEqual(by_name["bob"]["status"], "failed")
        self.assertTrue(by_name["bob"]["auth_error"])
        self.assertIn("failed", stderr)


if __name__ == "__main__":
    unittest.main()

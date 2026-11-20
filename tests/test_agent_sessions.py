"""Synthetic SQLite fixtures only; never access the application's databases."""
from dataclasses import replace
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from core.agent.contracts import ConversationState
from core.agent.session_codec import SessionCodec, SessionError
from core.agent.sessions import SessionStore


@contextmanager
def database(path):
    with closing(sqlite3.connect(path)) as connection, connection:
        yield connection


def reference(resource_id="b", position=2):
    return {"set_id": "results-1", "position": position, "resource_id": resource_id,
            "scope": "synthetic", "tool": "lookup", "tool_version": "1",
            "source_revision": "v1", "label": "Example item " + resource_id}


def sample(session_id="example"):
    return ConversationState(session_id=session_id, messages=[
        {"role": "user", "content": "Show examples"},
        {"role": "assistant", "content": "First a, second b"}], data={
            "goal": "Review examples", "draft": {"intent": "edit", "revision": 2,
                "fields": {"title": "Updated example"}, "reference_ids": ["b"]},
            "references": [reference("a", 1), reference()]})


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="viernes-sessions-")
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "sessions.sqlite3"
        self.codec = SessionCodec(secrets=("fixture-secret-123",))
        self.store = SessionStore(self.path, codec=self.codec)
        self.addCleanup(self.store.close)

    def error(self, code, action):
        with self.assertRaises(SessionError) as caught:
            action()
        self.assertEqual(caught.exception.as_dict()["code"], code)
        self.assertNotIn("fixture-secret", json.dumps(caught.exception.as_dict()))

    def test_create_reopen_restore_structured_context_and_order(self):
        created = self.store.create(sample())
        self.assertEqual(created.state.revision, 0)
        with SessionStore(self.path, codec=self.codec) as reopened:
            record = reopened.load("example")
            self.assertEqual(record.state.data, sample().data)
            self.assertEqual(record.state.messages, sample().messages)
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.state.data["references"][1]["resource_id"], "b")
            self.assertEqual([r["session_id"] for r in reopened.list()], ["example"])
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_revision_conflict_structured_no_merge_and_current_load(self):
        old = self.store.create(sample()).state
        current = self.store.save(old, expected_revision=0)
        self.assertEqual(current.state.revision, 1)
        before = self.path.read_bytes()
        self.error("REVISION_CONFLICT", lambda: self.store.save(old, expected_revision=0))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.load("example").state.revision, 1)
        self.assertEqual(old.revision, 0)
        self.error("REVISION_CONFLICT", lambda: self.store.save(current.state, expected_revision=0))

    def test_explicit_turn_lifecycle_and_token_binding(self):
        state = self.store.create(sample()).state
        started = self.store.begin_turn(state.session_id, 0)
        self.assertEqual(started.status, "started")
        self.error("TURN_ACTIVE", lambda: self.store.begin_turn(state.session_id, 1))
        self.error("INVALID_TURN", lambda: self.store.finish_turn(
            started.state, 1, "foreign-token"))
        done = self.store.finish_turn(started.state, 1, started.turn_id)
        self.assertEqual((done.status, done.state.revision), ("completed", 2))
        started = self.store.begin_turn(state.session_id, 2)
        interrupted = self.store.interrupt(state.session_id, started.state.revision)
        self.assertEqual(interrupted.status, "interrupted")
        self.assertEqual(interrupted.state.messages, sample().messages)

    def test_tool_exchanges_and_authority_not_persisted(self):
        state = sample()
        state.messages[1:1] = [
            {"role": "assistant", "content": "", "tool_calls": [{"function": {
                "name": "lookup", "arguments": {"token": "fixture-secret-123"}}}]},
            {"role": "tool", "tool_name": "lookup", "content": "UNNECESSARY_TOOL_PAYLOAD"}]
        state.data.update(grants=["write"], policy={"allow": True}, raw_result="UNNECESSARY")
        state.data["draft"]["fields"]["password"] = "another-secret"
        state.messages[0]["content"] = "token=hidden-credential fixture-secret-123"
        saved = self.store.create(state)
        exported = self.store.export("example")
        for excluded in ("fixture-secret-123", "hidden-credential", "another-secret",
                         "UNNECESSARY", "tool_calls", "grants", "password"):
            self.assertNotIn(excluded, exported)
            self.assertNotIn(excluded.encode(), self.path.read_bytes())
        self.assertEqual([m["role"] for m in saved.state.messages], ["user", "assistant"])
        self.assertEqual(saved.state.data["references"][1]["position"], 2)

    def test_strict_deserialization_versions_sizes_types_and_privilege(self):
        raw = json.loads(self.codec.encode(sample()))
        mutations = [lambda d: d.update(version=999), lambda d: d.update(approved=True),
                     lambda d: d["state"].update(revision=True),
                     lambda d: d["state"]["data"].update(grants=["write"]),
                     lambda d: d["state"]["messages"][0].update(role="system"),
                     lambda d: d["state"]["data"]["references"][0].update(position=True),
                     lambda d: d["state"]["data"]["references"][1].update(position=1),
                     lambda d: d["state"]["data"]["draft"].update(authorized=True)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = json.loads(json.dumps(raw))
                mutation(value)
                self.error("INVALID_SNAPSHOT", lambda: self.codec.decode(json.dumps(value), "example"))
        self.error("INVALID_SNAPSHOT", lambda: self.codec.decode('{"version":1,"version":1}', "example"))
        self.error("INVALID_SNAPSHOT", lambda: self.codec.decode("[" * 1000, "example"))
        self.error("INVALID_SNAPSHOT", lambda: self.codec.decode("x" * 65537, "example"))
        self.error("INVALID_SNAPSHOT", lambda: self.codec.decode(self.codec.encode(sample()), "foreign"))

    def test_corruption_and_message_snapshot_mismatch_fail_closed(self):
        self.store.create(sample())
        with database(self.path) as connection:
            connection.execute("UPDATE snapshots SET payload='{}'")
        self.error("INVALID_SNAPSHOT", lambda: self.store.load("example"))

    def test_recomputed_checksum_does_not_bypass_schema_checks(self):
        self.store.create(sample())
        with database(self.path) as connection:
            raw = json.loads(connection.execute("SELECT payload FROM snapshots").fetchone()[0])
            raw["state"]["messages"][0]["role"] = "system"
            payload = json.dumps(raw)
            connection.execute("UPDATE snapshots SET payload=?, digest=?", (
                payload, hashlib.sha256(payload.encode()).hexdigest()))
        self.error("INVALID_SNAPSHOT", lambda: self.store.load("example"))

    def test_history_mismatch_and_foreign_session_rejected(self):
        self.store.create(sample())
        with database(self.path) as connection:
            connection.execute("UPDATE messages SET content='modified' WHERE ordinal=0")
        self.error("INVALID_SNAPSHOT", lambda: self.store.load("example"))

    def test_busy_error_has_no_partial_write_or_sensitive_error(self):
        self.store.create(sample())
        with database(self.path) as other:
            other.execute("BEGIN IMMEDIATE")
            self.error("STORAGE_ERROR", lambda: self.store.save(sample(), 0))
        self.assertEqual(self.store.load("example").state.revision, 0)

    def test_trigger_failure_rolls_back_snapshot_messages_and_revision(self):
        self.store.create(sample())
        with database(self.path) as connection:
            connection.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON messages "
                               "BEGIN SELECT RAISE(ABORT, 'fixture-secret-123'); END")
        changed = sample()
        changed.data["goal"] = "Must roll back"
        self.error("STORAGE_ERROR", lambda: self.store.save(changed, 0))
        self.assertEqual(self.store.load("example").state.data, sample().data)
        self.assertEqual(self.store.load("example").state.revision, 0)

    def test_process_exit_before_commit_rolls_back(self):
        self.store.create(sample())
        program = "import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1]); c.execute('BEGIN IMMEDIATE'); c.execute('DELETE FROM messages'); os._exit(7)"
        result = subprocess.run([sys.executable, "-c", program, str(self.path)], check=False)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.store.load("example").state.messages, sample().messages)

    def test_deletion_and_delete_all_remove_derived_records_not_other_tables(self):
        self.store.create(sample())
        self.store.create(sample("other"))
        self.assertTrue(self.store.delete("example"))
        self.error("NOT_FOUND", lambda: self.store.load("example"))
        self.assertEqual(len(self.store.list()), 1)
        with database(self.path) as connection:
            connection.execute("CREATE TABLE commitments (id INTEGER)")
            connection.execute("INSERT INTO commitments VALUES (1)")
        self.assertEqual(self.store.delete_all(), 1)
        self.assertEqual(self.store.list(), [])
        with database(self.path) as connection:
            for table in ("messages", "snapshots", "sessions"):
                self.assertEqual(connection.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM commitments").fetchone()[0], 1)

    def test_retention_default_none_and_explicit_configured_prune(self):
        self.store.create(sample())
        with database(self.path) as connection:
            connection.execute("UPDATE sessions SET updated_at=1")
        self.assertEqual(self.store.prune(now=999999), 0)
        with SessionStore(self.path, retention_seconds=100) as finite:
            self.assertEqual(len(finite.list()), 1)
            self.assertEqual(finite.prune(now=101), 0)
            self.assertEqual(finite.prune(now=102), 1)
        self.error("NOT_FOUND", lambda: self.store.load("example"))

    def test_export_import_and_sqlite_backup_round_trip(self):
        self.store.create(sample())
        exported = self.store.export("example")
        with SessionStore(Path(self.scratch.name) / "import.sqlite3", codec=self.codec) as target:
            restored = target.import_session(exported)
            self.assertEqual(restored.state.data, sample().data)
            self.error("REVISION_CONFLICT", lambda: target.import_session(exported))
        backup = Path(self.scratch.name) / "backup.sqlite3"
        with database(self.path) as source, database(backup) as destination:
            source.backup(destination)
        with SessionStore(backup) as restored:
            self.assertEqual(restored.load("example").state.data, sample().data)

    def test_unknown_database_version_or_corrupt_database_never_reinitialized(self):
        self.store.close()
        with database(self.path) as connection:
            connection.execute("PRAGMA user_version=999")
        before = self.path.read_bytes()
        self.error("INCOMPATIBLE_STORE", lambda: SessionStore(self.path))
        self.assertEqual(self.path.read_bytes(), before)
        corrupt = Path(self.scratch.name) / "broken.sqlite3"
        corrupt.write_bytes(b"Not SQLite")
        self.error("STORAGE_ERROR", lambda: SessionStore(corrupt))
        self.assertEqual(corrupt.read_bytes(), b"Not SQLite")

    def test_invalid_state_never_creates_a_session(self):
        for state in (replace(sample(), messages=[{"role": "user", "content": "unfinished"}]),
                      replace(sample(), revision=True)):
            self.error("INVALID_SNAPSHOT", lambda: self.store.create(state))
        self.assertEqual(self.store.list(), [])

    def test_secret_identifiers_are_rejected_not_redacted_into_new_identities(self):
        state = sample("fixture-secret-123")
        self.error("INVALID_SNAPSHOT", lambda: self.store.create(state))
        state = sample()
        state.data["references"][0]["resource_id"] = "fixture-secret-123"
        self.error("INVALID_SNAPSHOT", lambda: self.store.create(state))
        self.assertEqual(self.store.list(), [])

    def test_disk_full_rolls_back_actual_save(self):
        self.store.create(sample())
        pages = self.store.connection.execute("PRAGMA page_count").fetchone()[0]
        self.store.connection.execute("PRAGMA max_page_count=" + str(pages))
        state = sample()
        state.messages = [{"role": role, "content": "x" * 1500}
                          for _ in range(16) for role in ("user", "assistant")]
        self.error("STORAGE_ERROR", lambda: self.store.save(state, 0))
        self.assertEqual(self.store.load("example").state.messages, sample().messages)
        self.assertEqual(self.store.load("example").state.revision, 0)

    def test_active_turn_not_pruned_or_exported_and_import_keeps_interruption(self):
        self.store.create(sample())
        begun = self.store.begin_turn("example", 0)
        self.error("TURN_ACTIVE", lambda: self.store.export("example"))
        with SessionStore(self.path, retention_seconds=1) as finite:
            self.assertEqual(finite.prune(now=999999999999), 0)
        self.store.interrupt("example", begun.state.revision)
        exported = self.store.export("example")
        with SessionStore(Path(self.scratch.name) / "import.sqlite3") as target:
            restored = target.import_session(exported)
            self.assertEqual(restored.status, "interrupted")
            self.assertEqual(restored.state.revision, 2)
            self.assertEqual(json.loads(target.export("example")), json.loads(exported))

    def test_near_limit_snapshot_and_export_remain_round_trippable(self):
        state = ConversationState(session_id="near-limit", data={"references": [
            reference(str(i), i + 1) for i in range(64)]}, messages=[
                {"role": role, "content": "x"} for _ in range(16) for role in ("user", "assistant")])
        overhead = len(self.codec.encode(state).encode())
        padding = (self.codec.max_bytes - overhead) // 32
        for message in state.messages:
            message["content"] += "x" * padding
        self.assertGreater(len(self.codec.encode(state).encode()), 65000)
        self.assertEqual(self.codec.decode(self.codec.encode(state)).messages, state.messages)
        self.store.create(state)
        exported = self.store.export(state.session_id)
        with SessionStore(Path(self.scratch.name) / "near-limit-import.sqlite3", codec=self.codec) as target:
            imported = target.import_session(exported)
            self.assertEqual(imported.state, state)
            malformed = json.loads(exported)
            malformed["snapshot"]["state"]["data"]["goal"] = float("nan")
            self.error("INVALID_SNAPSHOT", lambda: target.import_session(json.dumps(malformed)))

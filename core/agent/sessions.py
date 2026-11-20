"""Local single-owner SQLite sessions. No domain writes, tool replay or authority."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import math
import os
import sqlite3
import time
from uuid import uuid4

from .contracts import AgentError, ConversationState, json_bytes
from .session_codec import (SessionCodec, SessionError, SessionRecord, integer, require,
                            text, unique_object)


class SessionStore:
    def __init__(self, path, *, codec=None, retention_seconds=None):
        if retention_seconds is not None and (type(retention_seconds) is not int or retention_seconds <= 0):
            raise ValueError("Retention must be positive seconds or None.")
        self.codec = codec if codec is not None else SessionCodec()
        if not isinstance(self.codec, SessionCodec):
            raise ValueError("An explicit SessionCodec is required.")
        self.retention_seconds = retention_seconds
        self.connection = None
        try:
            # Caller must supply a trusted local directory. Refuse final-component symlinks.
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
            self.connection = sqlite3.connect(path, timeout=0.1, isolation_level=None)
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA trusted_schema=OFF")
            self.connection.execute("PRAGMA secure_delete=ON")
            self.connection.execute("PRAGMA synchronous=FULL")
            with self._transaction():
                version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise SessionError("INCOMPATIBLE_STORE")
                if version == 0:
                    if self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                        raise SessionError("INCOMPATIBLE_STORE")
                    for statement in (
                        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                        "created_at REAL NOT NULL, updated_at REAL NOT NULL, status TEXT NOT NULL, turn_id TEXT)",
                        "CREATE TABLE snapshots (session_id TEXT PRIMARY KEY REFERENCES sessions ON DELETE CASCADE, "
                        "payload TEXT NOT NULL, digest TEXT NOT NULL)",
                        "CREATE TABLE messages (session_id TEXT REFERENCES sessions ON DELETE CASCADE, "
                        "ordinal INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, "
                        "PRIMARY KEY (session_id, ordinal))",
                        "PRAGMA user_version=1"):
                        self.connection.execute(statement)
        except (sqlite3.Error, OSError) as exc:
            self.close()
            raise SessionError("STORAGE_ERROR") from exc
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def _transaction(self, write=True):
        try:
            if self.connection is None:
                raise SessionError("STORAGE_ERROR")
            self.connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise
        except sqlite3.Error as exc:
            raise SessionError("STORAGE_ERROR") from exc

    def _read(self, session_id):
        require(text(session_id, 128))
        row = self.connection.execute(
            "SELECT revision,substr(status,1,12),substr(turn_id,1,129) FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise SessionError("NOT_FOUND")
        revision, status, turn_id = row
        require(integer(revision) and status in ("started", "completed", "interrupted"))
        require((status == "started" and text(turn_id, 128)) or (status != "started" and turn_id is None))
        snapshot = self.connection.execute(
            "SELECT substr(payload,1,65537),substr(digest,1,65) FROM snapshots WHERE session_id=?", (session_id,)).fetchone()
        require(snapshot is not None)
        payload, digest = snapshot
        require(type(payload) is str and hashlib.sha256(payload.encode("utf-8")).hexdigest() == digest)
        state = self.codec.decode(payload, session_id)
        require(state.revision == revision)
        rows = self.connection.execute(
            "SELECT ordinal,role,substr(content,1,4097) FROM messages WHERE session_id=? ORDER BY ordinal LIMIT 33",
            (session_id,)).fetchall()
        # Compare original persisted values before current-policy redaction on recovery.
        persisted = state.messages
        require(len(rows) == len(persisted))
        for ordinal, (row_ordinal, role, content) in enumerate(rows):
            require(row_ordinal == ordinal and {"role": role, "content": self.codec.clean(content)} == persisted[ordinal])
        return SessionRecord(state, status, turn_id)

    def load(self, session_id):
        with self._transaction(write=False):
            return self._read(session_id)

    def _put(self, state, status, turn_id):
        payload = self.codec.encode(state)
        projected = self.codec.decode(payload, state.session_id)
        self.connection.execute("UPDATE sessions SET revision=?,updated_at=?,status=?,turn_id=? WHERE session_id=?",
            (state.revision, time.time(), status, turn_id, state.session_id))
        self.connection.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)", (
            state.session_id, payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
        self.connection.execute("DELETE FROM messages WHERE session_id=?", (state.session_id,))
        self.connection.executemany("INSERT INTO messages VALUES (?,?,?,?)", [
            (state.session_id, index, message["role"], message["content"])
            for index, message in enumerate(projected.messages)])
        return SessionRecord(projected, status, turn_id)

    def _create(self, projected, status="completed", timestamps=None):
        with self._transaction():
            if self.connection.execute("SELECT 1 FROM sessions WHERE session_id=?", (projected.session_id,)).fetchone():
                raise SessionError("REVISION_CONFLICT")
            now = time.time()
            created, updated = timestamps if timestamps is not None else (now, now)
            self.connection.execute("INSERT INTO sessions VALUES (?,0,?,?,'completed',NULL)",
                                    (projected.session_id, created, updated))
            record = self._put(projected, status, None)
            self.connection.execute("UPDATE sessions SET updated_at=? WHERE session_id=?", (updated, projected.session_id))
            return record

    def create(self, state=None):
        state = state if state is not None else ConversationState()
        # Validate and minimize before opening the write transaction.
        projected = self.codec.decode(self.codec.encode(state), state.session_id)
        require(projected.revision == 0)
        return self._create(projected)

    def _expected(self, session_id, expected_revision):
        require(integer(expected_revision))
        record = self._read(session_id)
        if record.state.revision != expected_revision:
            raise SessionError("REVISION_CONFLICT")
        return record

    def save(self, state, expected_revision):
        projected = self.codec.decode(self.codec.encode(state), state.session_id)
        if projected.revision != expected_revision:
            raise SessionError("REVISION_CONFLICT")
        with self._transaction():
            old = self._expected(state.session_id, expected_revision)
            if old.status == "started":
                raise SessionError("TURN_ACTIVE")
            return self._put(replace(projected, revision=expected_revision + 1), "completed", None)

    def begin_turn(self, session_id, expected_revision):
        with self._transaction():
            old = self._expected(session_id, expected_revision)
            if old.status == "started":
                raise SessionError("TURN_ACTIVE")
            return self._put(replace(old.state, revision=expected_revision + 1), "started", str(uuid4()))

    def finish_turn(self, state, expected_revision, turn_id):
        projected = self.codec.decode(self.codec.encode(state), state.session_id)
        if projected.revision != expected_revision:
            raise SessionError("REVISION_CONFLICT")
        with self._transaction():
            old = self._expected(state.session_id, expected_revision)
            if old.status != "started" or turn_id != old.turn_id:
                raise SessionError("INVALID_TURN")
            return self._put(replace(projected, revision=expected_revision + 1), "completed", None)

    def interrupt(self, session_id, expected_revision):
        """Explicit host abandonment, never an automatic resume or replay."""
        with self._transaction():
            old = self._expected(session_id, expected_revision)
            if old.status != "started":
                raise SessionError("INVALID_TURN")
            return self._put(replace(old.state, revision=expected_revision + 1), "interrupted", None)

    def list(self, limit=100, offset=0):
        require(integer(limit, 100) and limit > 0 and integer(offset))
        with self._transaction(write=False):
            rows = self.connection.execute("SELECT substr(session_id,1,129),revision,substr(status,1,12),updated_at FROM sessions "
                "ORDER BY updated_at DESC,session_id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            for session_id, revision, status, updated in rows:
                require(text(session_id, 128) and self.codec.clean(session_id) == session_id
                        and integer(revision) and status in ("started", "completed", "interrupted")
                        and type(updated) in (int, float) and math.isfinite(updated))
            return [dict(zip(("session_id", "revision", "status", "updated_at"), row)) for row in rows]

    def delete(self, session_id):
        require(text(session_id, 128))
        with self._transaction():
            return self.connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,)).rowcount == 1

    def delete_all(self):
        with self._transaction():
            return self.connection.execute("DELETE FROM sessions").rowcount

    def prune(self, now=None):
        now = time.time() if now is None else now
        require(type(now) in (int, float) and math.isfinite(now))
        if self.retention_seconds is None:
            return 0
        with self._transaction():
            return self.connection.execute("DELETE FROM sessions WHERE updated_at < ? AND status != 'started'",
                (now - self.retention_seconds,)).rowcount

    def export(self, session_id):
        with self._transaction(write=False):
            record = self._read(session_id)
            if record.status == "started":
                raise SessionError("TURN_ACTIVE")
            timestamps = self.connection.execute(
                "SELECT created_at,updated_at FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            require(all(type(t) in (int, float) and math.isfinite(t) and t >= 0 for t in timestamps)
                    and timestamps[0] <= timestamps[1])
            return json_bytes({"export_version": 1, "status": record.status,
                "created_at": timestamps[0], "updated_at": timestamps[1],
                "snapshot": json.loads(self.codec.encode(record.state))}).decode("utf-8")

    def import_session(self, raw):
        try:
            require(type(raw) is str and len(raw.encode("utf-8")) <= self.codec.max_bytes + 1024)
            value = json.loads(raw, object_pairs_hook=unique_object,
                               parse_constant=lambda _: require(False))
            require(type(value) is dict and set(value) == {
                "export_version", "status", "created_at", "updated_at", "snapshot"})
            require(type(value["export_version"]) is int and value["export_version"] == 1
                    and value["status"] in ("completed", "interrupted"))
            created, updated = value["created_at"], value["updated_at"]
            require(all(type(t) in (int, float) and math.isfinite(t) and t >= 0 for t in (created, updated))
                    and created <= updated)
            state = self.codec.decode(json_bytes(value["snapshot"]).decode("utf-8"))
        except (AgentError, ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
            raise SessionError("INVALID_SNAPSHOT") from exc
        return self._create(state, value["status"], (created, updated))

# PR3: local sessions without restored execution authority

PR3 adds an explicitly composed SQLite session store around the PR2 runtime.
Once composed, sessions are recorded automatically. It does not change the default
Viernes entrypoint, legacy planner, PR1 evaluator, or tool permissions. No semantic
memory, domain tools, migrations of existing databases, or live-model claims are included.

## Quick path

Supply an existing trusted local directory and a separate sessions database:

```python
from core.agent import ConversationState, PersistentRuntime, SessionCodec, SessionStore

# runtime is the host-created PR2 Runtime, with explicit read/prepare-only policy.
# known_secrets is a host-owned tuple; never load it from a conversation.
with SessionStore("/trusted/private-directory/sessions.sqlite3",
                  codec=SessionCodec(secrets=known_secrets)) as store:
    session = store.create(ConversationState())
    agent = PersistentRuntime(runtime, store)
    result = agent.handle_turn("A new question", session.state)
    if result.error:
        print(result.error["code"])  # Do not claim the answer was saved.
```

No separate recording opt-in is required inside this composition. Merely importing
these classes does not create a database or activate persistence in the application.
Session deletion and import/export are backend APIs, not model tools.

After restart, create a new runtime with trusted host policy and call
`agent.recover(session_id)`. Recovery never invokes a tool or model. A started turn
is explicitly abandoned as interrupted; therefore only call recover after ensuring
the previous owner is no longer active. The returned state can be passed to a new
`handle_turn`. An old user message, `/confirm`, or tool call is never executable input.

## Store and concurrency contract

| API | Result and boundary |
| --- | --- |
| `create(state=None)` | `SessionRecord`; new UUID by default, initial revision zero; duplicate ID conflicts. |
| `load(session_id)` | Validated `SessionRecord(state, status, turn_id)`; read-only, no replay or takeover. |
| `save(state, expected_revision)` | Atomic snapshot/history save; returns incremented revision; input revision must match expected revision. |
| `begin_turn(id, expected_revision)` | Atomically increments revision, records `started` and a random turn token before any model/tool call. |
| `finish_turn(state, expected_revision, turn_id)` | Checks current revision and active token, atomically saves minimized state and `completed`. |
| `interrupt(id, expected_revision)` | Explicit abandonment of a started turn; preserves last durable conversation and increments revision. |
| `list(limit=100, offset=0)` | Bounded session metadata, newest first; no content search. |
| `delete(id)` / `delete_all()` | Remove session rows and cascade messages/snapshots; never delete domain tables. |
| `prune(now=None)` | Explicit retention operation; default retention `None` deletes nothing. |
| `export(id)` / `import_session(raw)` | Bounded versioned plain JSON, timestamps, revision, provenance and completed/interrupted status; no active turn token. |

Use returned revisions, not guessed counters. Begin and completion each increment
the storage revision; it is not a count of model turns. `REVISION_CONFLICT` is a
structured `SessionError.as_dict()`; load the current state and make an explicit
decision. There is no retry, merge or overwrite of divergent states. The wrapper
returns errors in `TurnResult.error`. It reloads canonical data in the same write
transaction as turn admission, so editing a returned object cannot bypass refresh.

SQLite transactions cover sessions, minimized ordered messages and the current
snapshot. Previous snapshots are replaced, not accumulated indefinitely. Reads use
a consistent transaction; writes use `BEGIN IMMEDIATE`, bounded lock waits,
foreign keys and full synchronous writes. No transaction spans a model/tool call.
The supported deployment is one active owner per session on a local filesystem;
this is not a distributed lease or a workflow engine. Explicit interruption can
invalidate a live owner's token, so callers must enforce the single-owner rule.

## Turn lifecycle and failures

| Boundary | Durable state and recovery |
| --- | --- |
| Session created / successful standalone save | `completed`, no active token. |
| Before inference or reference refresh | `started`, previous snapshot, new revision/token. Input and partial model/tool data are not journaled. |
| Successful turn | `completed`, minimized user/final-assistant pair and structured context saved together. |
| Runtime or refresh failure | `interrupted`, previous messages/context retained; partial exchanges discarded. |
| Completion persistence fails or its outcome is uncertain | No retry; return error and no answer claiming durability. Load/recover the durable boundary explicitly. |
| Process stops with a started turn | `load` still reports `started`; explicit `recover` marks it `interrupted`, with no tool/model call. |

Failures marking an interruption are also returned as storage errors. The previously
committed SQLite boundary remains the recovery source. Unknown database versions,
invalid snapshots and corrupt data fail closed; no silent database reinitialization
or speculative state repair occurs. Tests cover actual SQLite full/locked errors,
transaction aborts and a subprocess exiting before commit.

## Minimal structured context and reference continuity

Persistence format version 1 wraps PR2 ConversationState version 1. Only complete
user/final-assistant pairs are stored, up to 16 recent pairs, within 64 KiB total.
Each text field is bounded to 4,096 characters. Native assistant tool calls,
arguments, intermediate assistant content and full tool messages are omitted.
Recovery therefore produces valid PR2 messages without simulating old executions.
Oversized state fails explicitly rather than silently truncating text or drafts.

The context allowlist is:

- `goal`: bounded text.
- `draft`: `intent`, integer `revision`, flat bounded scalar `fields`, and
  `reference_ids`. Sensitive field names are excluded before writing. Draft fields
  do not create application operations or permission.
- `references`: up to 64 ordered records containing `set_id`, one-based `position`,
  `resource_id`, `scope`, `tool`, `tool_version`, `source_revision`, and short `label`.
  Positions start at one within each set, so “the second” retains its identity.
  Labels support contextual references without retaining complete result objects.

The host may supply `project_context(completed_state)` to the wrapper. It inspects
actual completed tool outcomes and returns only this allowlisted context. There is
no generic extraction of arbitrary tool payloads: a capability must explicitly
declare which result IDs, ordering, provenance and short labels matter. Existing
structured context is retained when no projector is installed. Projectors must
generate stable result-set IDs, preserve relevant references and treat their input
as data; they are trusted application code, not serialized callbacks.

Every reference is historical on load, regardless of stored labels or revisions.
Before **every** subsequent turn, the wrapper requires a host-registered
`ReferenceReader` for each scope. It runs an explicitly read-only `ToolSpec` through
the existing ToolExecutor, current Policy and shared turn Budget. Its argument
builder selects actual IDs; its result projector returns the same reference with
only `label` and `source_revision` updated. Missing, ambiguous, unauthorized or
identity-substituted results block inference with `REVALIDATION_REQUIRED`.

Fresh goals/draft/reference context enters a user-role block explicitly labeled
untrusted, never the system prompt. The original user input, not this synthetic
block, is persisted. No stored boolean can skip the read or enable a capability.
PR3 ships no real commitment readers; until PR4 supplies them, such references
cannot be used operationally. Fresh reads do not authorize a later domain write;
PR6 must additionally enforce transactional domain conflicts at confirmation.

## Privacy, deletion, retention and portability

- Known host-supplied secret strings and common credential/private-key patterns are
  redacted from persisted text. Sensitive draft keys, unknown context fields,
  grants, policies and complete tool exchanges are not persisted. Secret-bearing
  identifiers are rejected rather than redacted into a different identity.
- Arbitrary free-text secrets cannot be recognized universally. These filters are
  defense in depth, not a guarantee for unknown credentials or safe handling of
  arbitrary private conversations. Configure known secrets before using real data.
- Errors use fixed messages/codes, never raw SQLite exception text, payloads or
  filesystem paths. Runtime traces are not stored in the session database.
- The database file is restricted to mode 0600; the caller must secure the parent
  directory. Standard SQLite is not encrypted. This is not a filesystem sandbox.
- Deletion removes active session storage and derived rows. Secure-delete is
  enabled, but backups, filesystem snapshots, journals and device remnants prevent
  any forensic-erasure guarantee. Manage backup retention separately.
- `retention_seconds=None` is the default. Finite positive seconds require explicit
  configuration and `prune`; nothing is deleted on open, load or save. Pruning uses
  `updated_at < now - retention_seconds`, excluding active started turns.
- Export/import retains minimized state, timestamps, provenance and interruption
  status. Import never overwrites an existing ID, accepts active execution, or
  restores authority. Use SQLite's backup API for a consistent database backup;
  copying a live database file is not the backup contract.

## Guarantees deliberately not claimed

The SHA-256 snapshot digest detects accidental corruption; schema, ID, revision
and history checks reject detectable manipulation. An attacker able to rewrite
the database and digest consistently can forge contextual facts. This is not
authenticated storage, and a hash/fingerprint is not anonymization. Recovered data
never grants privileges even when structurally valid.

Session persistence and external/domain effects are different transactions. A crash
after an effect but before completion may leave an uncertain result. PR3 does not
replay it and does not claim exactly-once execution. Durable operation identity and
domain-result reconciliation belong to PR6, not this database. A new explicit user
turn may choose another read/prepare call; historical call IDs are not deduplication
keys or reusable grants.

## Offline verification

Focused regression command:

```bash
python -B -m unittest tests.test_agent_sessions tests.test_agent_recovery tests.test_pr3_independent_verifier tests.test_pr3_targeted_portability
```

Run the existing agent, planner, store and evaluation unittest modules as the
compatibility suite. Exclude service-connectivity, audio and OS integration probes;
no live inference is authorized. Independent verification must exercise restart,
forged authority, reference freshness, revision conflicts, interrupted transactions,
privacy and deletion in isolated synthetic state against the PR29 baseline.

The retained independent probes include cross-store byte-preserving conflicts,
interrupted transactions and Unicode snapshots near the 64 KiB boundary. Encoding,
decoding and export/import use the same compact JSON representation; adding
whitespace or Unicode escaping must not make a valid stored snapshot unrecoverable.

Rollback removes the three new implementation modules, additive package exports,
tests and this guide. The separate session database is never a commitments database;
removing PR3 does not require changing or deleting existing domain records.

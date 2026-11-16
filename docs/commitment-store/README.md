# Validated commitment storage

[English](README.md) | [Español](README.es.md)

`core.commitments` is a SQLite storage library, independent of AI, audio and
configuration. It validates titles, areas, projects, ISO dates and integer IDs.
`create_many` validates the complete batch before writing; records retain source
text and support area filtering, editing and completion across restarts.

This library writes when explicitly called. It does not implement user-facing
proposal confirmation; that belongs to the next planner CLI unit. These API
examples/tests are not a workaround for broken conversational acceptance.

```bash
python -B -m unittest tests.test_commitment_store
```

Tests use only new temporary synthetic databases. No schema migration, default
database access, model calls or configuration imports are included. Rollback
removes this library, its isolated tests and these guides before any integration.

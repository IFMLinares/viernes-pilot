# Minimal reusable agent runtime (PR2)

[English](README.md) | [Español](README.es.md)

This is an opt-in Python API, not a replacement for `main.py --planner`. It has
no application tools, persistence, framework, automatic service startup, or CLI
activation. PR3 session persistence is out of scope.

## State and contracts

`ConversationState` contains versioned JSON messages/data, a session ID and a
revision. `to_json()` / `from_json()` are in-memory serialization, not storage or
secret redaction. Only completed user/assistant/tool exchanges restore; system
instructions, extra authority fields and unfinished calls are rejected. A known
session ID can be checked explicitly. Restored data grants no tool permissions.

`ModelAdapter.next(messages, tool_specs, budget)` is the model boundary. `Limits`
and the process-local `Budget` bound requests, iterations, tool calls, time,
context bytes and response bytes; no execution budget/authority is serialized.
Sizes are UTF-8 JSON bytes, not token counts. Unsupported limits fail explicitly.

```bash
python -B -m unittest tests.test_agent_state
```

All fixtures are synthetic. No live-model behavior is claimed by these tests.

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

## Tool boundary

`ToolSpec` requires explicit effects and scope, input/result schemas and a trusted
host handler. `Policy` defaults to empty grants; both name and scope must match.
Only `read`/`prepare` effects can be advertised or executed. `write` and `external`
are denied even when their names are granted. There is no confirmation tool.

Schemas support `type`, `description`, `enum`, closed object properties/required,
array items/minItems/maxItems, string minLength/maxLength, and numeric minimum/
maximum. Supported types: object, array, string, integer, number, boolean, null.
Unsupported types/keywords fail registration; no `$ref`, unions or regex are
silently ignored. Booleans are not integers. Arguments/results are JSON-copied.

Handlers receive only validated arguments, not state, grants or execution context.
They are trusted application code, **not sandboxed Python**; falsely labeling a
dangerous host function as read-only cannot be made safe by metadata. No built-in
OS/external/domain handlers exist. Hard handler deadlines fail closed if unsupported.
Trace events expose known tool names, outcome/error codes, sizes and fingerprints,
never raw argument/result/exception text. Fingerprints are not anonymization.

```bash
python -B -m unittest tests.test_agent_state tests.test_agent_tools
```

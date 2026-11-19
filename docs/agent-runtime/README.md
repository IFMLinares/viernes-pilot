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

## Native model boundary and turns

`Runtime(adapter, executor, policy, limits).handle_turn(input, state, context=None)`
creates a fresh process-local budget by default. An optional host-created
`ExecutionContext` must carry this runtime's policy and matching limits; state
JSON cannot create one. Generic `state.data` is preserved but never promoted to
system instructions or policy. System instructions belong to runtime configuration.

`OllamaModelAdapter(url, model)` requires an explicit loopback endpoint and model.
It sends `/api/chat` with native `tools`, `stream=false` and `think=false`; there
is no action-classification JSON schema. HTTP response reading is streamed only
to enforce the response-byte cap, not to publish partial model tokens. Every POST
is reserved before sending. Redirects/proxies/retries are disabled/not added.
The API uses `assistant.tool_calls` followed by `role=tool`, `tool_name` and a
JSON `ok/data/error/meta` result. Multiple calls execute in order, never in parallel.

Unknown tools, invalid arguments/results and ordinary handler failures can return
recoverable errors to the model. Permission denial, exhausted budgets, unavailable
deadlines and incomplete/malformed model responses terminate the turn. A model
timeout/connection error is returned to the caller, not automatically retried.
Only successful completed turns advance the revision; terminal failures return
the input state without a queued call. This does not undo a falsely labeled
handler's external side effect: register only trusted pure read/preparation code.

`TurnResult.answer` is model text, not proof of a committed operation. No write,
confirmation, saved-record result, or persistence capability exists in PR2.
The pure POSIX timer is shared with PR1 through its unchanged `hard_timeout`
interface; runtime does not import evaluation modules or SQLite.

```bash
python -B -m unittest tests.test_agent_state tests.test_agent_tools tests.test_agent_runtime
```

These tests use synthetic native envelopes and forbid real network requests.
Local model capability/quality remains unverified: no live probe was authorized.

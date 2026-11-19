# Interpreter evaluation tools

[English](README.md) | [Español](README.es.md)

This experimental candidate includes the strict evaluator, offline rescoring tool and synthetic
corpus. Historical run reports and private execution notes remain excluded.
The corpus retains its original fixed-date/year-required assumptions; it is not
a new benchmark proving the current Caracas/current-year policy works.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

These checks mock model transport and use temporary data. Live evaluation requires
a separately authorized model, endpoint, request count and elapsed-time budget.
Inspect `python -m tools.evaluate_interpreter --help` before any real run; do not
run connectivity/audio checks or regenerate historical reports automatically.

Offline rescoring consumes an existing report and writes a distinct output; it
does not establish that the current model generates the expected actions. Keep
failed, partial, mocked and actual live evidence separate. See
[acceptance issue #6](https://github.com/IFMLinares/viernes-pilot/issues/6).

## HTTP accounting

The legacy evaluator now counts each actual planner POST, including tool
continuations and explicitly repeated failed attempts, not interpreter invocations.
No automatic retries are added. `requests` has no retry adapter here and planner
redirects remain disabled. A reservation is committed before sending; it proves
budget consumption, not that Ollama received the request.

`--output` has a companion `<output>.attempts.sqlite3` ledger containing only the
budget, expiry, endpoint/model/mode binding, and attempt count. Reusing it cannot
extend its deadline or reset its count. Use a new output for a separately approved
new run. `--request-timeout` defaults to 90 seconds and is capped by the remaining
global time; hard HTTP wall-time enforcement requires POSIX timers on the main
thread and otherwise fails closed. Interrupted reservations are not refunded.
Keep reports/ledgers outside the checkout. Zero requests still produces a partial
report without sending. Old report keys remain, with corrected per-case `requests`
and an additive `http_attempts` total; historical reports are not rewritten.

## PR1 complete-conversation baseline

```bash
python -B -m unittest tests.test_evaluation_http tests.test_conversation_evaluation
python -B -m tools.evaluate_conversations --output /tmp/viernes-baseline.json
```

The second command is offline by default. Its six synthetic conversations retain
one Planner and an isolated temporary SQLite store across 16 turns. They cover
clarification/confirmation, pending correction, cancellation/reference, inferred
area/lost online detail, date metadata/continuation faults, and query/completion.
No planner rules or production storage change. Date fault injections are rejected
wire shapes, not a diagnosis or recording of the original #5 live failure.

`expect` pins observed host behavior under scripted responses; `acceptance` records
the desired outcome separately. Output/state/fields/source, actual date-tool calls,
POST attempts and stored records are checked before redaction. Non-confirmation
turns must leave stored records unchanged. Reports retain check results and state,
response and record hashes, not raw conversations/model replies. They are not
production session storage or a claim that secret filtering is implemented.

The shipped baseline exits **1**: `completed=true` and `baseline_matches=true`
coexist with `acceptance_passed=false`. Known missing behavior and injected failure
conditions are visible, not converted into a model PASS. Unexpected baseline
changes stop with `baseline_mismatch`. Reports distinguish `http_attempts` from
`simulated_attempts`; deterministic/replay runs perform zero HTTP requests.

`--mode replay --replay <recording.json>` requires caller-declared provenance
(`source=recorded-synthetic`, `model`, `digest`) and `cases[case_id]`: one response
list per turn, each entry containing `status_code` and the raw Ollama `body`.
It consumes these exact envelopes, never falls back to network, and records the
recording hash. No real-model recordings are shipped; synthetic tests of this
path do not establish recorded or live model acceptance.

Live runs require separate authorization and explicit `--mode live --url --model
--max-requests --max-seconds --request-timeout --output`. Caps are at most 60 POSTs
and 900 seconds. Empty/whitespace-only live endpoints or model names are rejected
before creating a ledger, sending, or overwriting a report; they never select
defaults. Example **configuration only, not authorization to execute**:
`--mode live --url http://127.0.0.1:11434 --model qwen3.5:9b --max-requests 12
--max-seconds 120 --request-timeout 30 --output /tmp/viernes-approved-live.json`.
Live stops on the first error or acceptance failure and preserves a partial
report. Budgets cover continuations and failed sends; automatic retries are not
introduced. This PR ran only deterministic tests and synthetic replay.

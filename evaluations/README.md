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

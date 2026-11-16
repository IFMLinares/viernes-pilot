# Interpreter evaluation tools

[English](README.md) | [Español](README.es.md)

This snapshot includes the strict evaluator, offline rescoring tool and synthetic
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

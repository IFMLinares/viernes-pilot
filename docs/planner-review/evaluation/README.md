# Bounded interpreter evaluation CLI

[English](README.md) | [Español](README.es.md)

The evaluator supports direct and planner-path checks against synthetic cases,
with bounded requests/time and explicit partial/error outcomes. Reports contain
reviewed metadata, not private conversation dumps. No historical run is regenerated
by this publication. Live evaluation requires a separately authorized budget.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

These commands mock transport. CLI availability is not consent to run a model.

# Caller-scoped parse metadata

[English](README.md) | [Español](README.es.md)

Parse diagnostics belong to the calling planner, not a mutated shared interpreter
closure. Metadata describes type, emptiness and completion/JSON parse status;
prompt, answer and record contents are not diagnostic payloads. Disabled callers
must not inherit another caller's sink.

```bash
python -B -m unittest tests.test_planner_diagnostics tests.test_offline_evaluation
```

Checks use synthetic envelopes and mocks, not the live model or private logs.

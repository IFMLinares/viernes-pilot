# Opt-in request diagnostics

[English](README.md) | [Español](README.es.md)

The CLI accepts diagnostics only with planner mode. Enabled diagnostics emit
allowlisted route/outcome/error/timing metadata to stderr, not record text or
prompts. This port changes only the final CLI dispatch, retaining the legacy body.
No default log file or service is created by this publication.

```bash
python -B -m unittest tests.test_planner_diagnostics tests.test_planner_entrypoint
```

Use external temporary HOME/data/tmp for tests. Detailed tool-failure diagnosis
is still an open issue; this historical import does not claim to solve it.

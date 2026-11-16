# Strict offline report rescoring

[English](README.md) | [Español](README.es.md)

Offline rescoring validates an existing report and writes a distinct derived
output without model calls or input mutation. Invalid/private metadata and unsafe
output targets are rejected. Reinterpreting a historical report does not measure
the current model. Existing historical run reports remain outside this chain.

```bash
python -B -m unittest tests.test_offline_evaluation
```

Reports and generated test files belong in external temporary directories.

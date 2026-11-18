# Typed comparison oracle and corpus

[English](README.md) | [Español](README.es.md)

This unit imports typed public-action comparison and a synthetic case corpus.
Comparison rules and safe metadata must not turn an interpreter error into a
correct result. The corpus uses its historical fixed reference/year assumptions;
it is not proof of the later Caracas/current-year policy. CLI execution follows.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

Tests supply model outputs. They do not prove the model generates those outputs.

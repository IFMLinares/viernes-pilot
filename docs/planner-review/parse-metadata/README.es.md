# Metadatos de parseo por llamador

[English](README.md) | [Español](README.es.md)

Los diagnósticos pertenecen al planner que llama, no a una clausura compartida
modificada. Describen tipo, vacío y resultado de finalización/parseo JSON; no
incluyen prompts, respuestas ni registros. Un llamador deshabilitado no debe
heredar el destino de otro.

```bash
python -B -m unittest tests.test_planner_diagnostics tests.test_offline_evaluation
```

Usan sobres sintéticos y mocks, no el modelo real ni registros privados.

# Consultas acotadas y fundamentadas

[English](README.md) | [Español](README.es.md)

SQL aplica área/fechas antes de recuperar registros. El alcance actual incluye
fechas recientes/futuras, pendientes vencidos anteriores y pendientes sin fecha.
El historial completo incluye todas las fechas/estados; los rangos son inclusivos.
Un alcance vacío no demuestra ausencia global. La salida procede del almacenamiento,
no de una afirmación del modelo. La fecha de referencia es inyectable en pruebas.

```bash
python -B -m unittest tests.test_planner_queries tests.test_commitments
```

No requiere modelo real ni bases del usuario. Los fallos de captura siguen abiertos.

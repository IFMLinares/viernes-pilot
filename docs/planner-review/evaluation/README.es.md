# CLI acotado de evaluación del intérprete

[English](README.md) | [Español](README.es.md)

El evaluador comprueba casos sintéticos de forma directa o mediante el planner,
con límites y resultados parciales/errores explícitos. Los informes contienen
metadatos revisados, no conversaciones privadas. No se regeneran informes al
publicar. Una evaluación real requiere presupuesto autorizado por separado.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

Estas órdenes simulan transporte. Tener el CLI no autoriza ejecutar el modelo.

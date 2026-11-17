# Recálculo estricto de informes sin modelo

[English](README.md) | [Español](README.es.md)

El recálculo valida un informe y genera otro archivo, sin modelo ni cambios del
original. Rechaza metadatos inválidos/privados y destinos inseguros. Reinterpretar
un informe histórico no mide el modelo actual. Los informes de ejecuciones
históricas quedan fuera de esta cadena.

```bash
python -B -m unittest tests.test_offline_evaluation
```

Los informes de prueba deben permanecer en temporales externos.

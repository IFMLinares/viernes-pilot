# Biblioteca pura de reloj y fechas

[English](README.md) | [Español](README.es.md)

El registro puro expone inicialmente resolve_date. Recibe un instante confiable
de America/Caracas, resuelve referencias y devuelve fecha, invalidez o conflicto.
Sin año se usa el actual de Caracas; el próximo día semanal es estrictamente
futuro. No llama a modelo, almacenamiento ni red. La base de zonas del sistema
debe contener America/Caracas.

```bash
python -B -m unittest tests.test_planner_tools
```

La selección de herramientas e integración de captura llega después.

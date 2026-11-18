# Almacenamiento validado de compromisos

[English](README.md) | [Español](README.es.md)

`core.commitments` es una biblioteca SQLite independiente de IA, audio y
configuración. Valida títulos, áreas, proyectos, fechas ISO e IDs enteros.
`create_many` valida todo el lote antes de escribir; conserva la procedencia y
permite filtrar por área, editar y completar registros entre reinicios.

La biblioteca escribe cuando se invoca explícitamente. No implementa confirmación
de propuestas; corresponde a la siguiente unidad del CLI. Sus pruebas no son una
alternativa para dar por correcta una captura conversacional que todavía falla.

```bash
python -B -m unittest tests.test_commitment_store
```

Las pruebas usan solo bases sintéticas temporales. No se incluyen migraciones,
acceso a la base habitual, llamadas al modelo ni importación de configuración.
Antes de integrar, la reversión elimina biblioteca, pruebas y estas guías.

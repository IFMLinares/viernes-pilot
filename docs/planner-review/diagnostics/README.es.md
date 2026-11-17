# Diagnósticos opcionales de solicitudes

[English](README.md) | [Español](README.es.md)

El CLI admite diagnósticos solo con el planner. Emite a stderr metadatos limitados
de ruta, resultado, error y tiempo, no registros ni prompts. El portado solo cambia
el selector final y conserva el cuerpo anterior. No crea un archivo de registro
predeterminado ni inicia servicios durante esta publicación.

```bash
python -B -m unittest tests.test_planner_diagnostics tests.test_planner_entrypoint
```

Usa HOME/datos/temporales aislados. El diagnóstico concreto de fallos de herramientas
sigue abierto; importar esta versión histórica no lo resuelve.

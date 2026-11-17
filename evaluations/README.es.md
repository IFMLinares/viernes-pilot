# Herramientas de evaluación del intérprete

[English](README.md) | [Español](README.es.md)

Esta candidata incluye evaluador estricto, recálculo sin modelo y corpus sintético.
Se excluyen informes históricos y notas privadas de ejecución. El corpus conserva
sus supuestos originales de fecha fija y año explícito; no demuestra la nueva
política de Caracas y año actual.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

Estas comprobaciones simulan el transporte y usan datos temporales. Evaluar el
modelo real requiere autorizar modelo, destino, cantidad y tiempo por separado.
Consulta `python -m tools.evaluate_interpreter --help` antes de una prueba real;
no ejecutes conectividad/audio ni regeneres informes automáticamente.

El recálculo usa un informe existente y escribe otro archivo; no demuestra que
el modelo actual genere acciones correctas. Separa fallos, evidencia parcial,
simulada y real. Consulta la
[issue de aceptación #6](https://github.com/IFMLinares/viernes-pilot/issues/6).

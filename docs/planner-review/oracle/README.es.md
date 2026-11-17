# Oráculo de comparación y corpus tipados

[English](README.md) | [Español](README.es.md)

Esta unidad importa comparación de acciones públicas y casos sintéticos. Sus
reglas y metadatos no deben convertir un error del intérprete en un acierto.
El corpus conserva fecha/año históricos; no valida la política posterior de
Caracas y año actual. La ejecución CLI llega en la siguiente unidad.

```bash
python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation
```

Las pruebas suministran salidas; no prueban que el modelo las genere.

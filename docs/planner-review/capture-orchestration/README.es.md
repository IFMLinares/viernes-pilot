# Captura y herramientas de la candidata consolidadas

[English](README.md) | [Español](README.es.md)

Esta unidad importa el controlador acoplado actual, no cada parche fallido. El
borrador conserva valores validados; responder un área con datos completos puede
producir una propuesta local. Las herramientas de creación conservan título,
el bucle es limitado y las respuestas públicas mantienen tres claves. Se permite
cambiar fecha explícitamente; solo la confirmación exacta persiste registros.

```bash
python -B -m unittest tests.test_planner_capture tests.test_planner_tool_loop tests.test_planner_intent tests.test_planner_clarification tests.test_planner_generation
```

Son comprobaciones simuladas/reproducidas. Los errores reales de herramientas,
áreas inferidas, límites de corrección y aceptación pendiente siguen en #3–#6.
Importar la candidata no corrige ni cierra esos informes.

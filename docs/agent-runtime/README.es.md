# Runtime reutilizable mínimo del agente (PR2)

[English](README.md) | [Español](README.es.md)

API Python opcional; no reemplaza `main.py --planner`. No incluye herramientas
de aplicación, persistencia, framework, arranque automático de servicios ni
activación por CLI. La persistencia de sesiones de PR3 queda fuera de alcance.

`ConversationState` conserva mensajes/datos JSON versionados, ID y revisión.
Serializar no equivale a persistir ni a filtrar secretos. Se rechazan instrucciones
de sistema importadas, campos de autoridad y llamadas sin terminar. Restaurar
datos no concede permisos; se puede comprobar un ID de sesión esperado.

`ModelAdapter.next(messages, tool_specs, budget)` delimita el acceso al modelo.
`Limits` y `Budget` acotan solicitudes, iteraciones, herramientas, tiempo y bytes
JSON UTF-8 de contexto/respuesta. Los presupuestos son locales al proceso y no
se restauran como autoridad. Las pruebas usan exclusivamente datos sintéticos.

```bash
python -B -m unittest tests.test_agent_state
```

`ToolSpec` exige efectos, alcance, esquemas y handler explícitos. `Policy` deniega
por defecto y comprueba nombre/alcance; solo permite `read` y `prepare`. Ni una
concesión de nombre permite `write` o `external`. No existe herramienta de confirmación.

El subconjunto de esquemas admite tipos JSON, objetos cerrados, campos requeridos,
arrays con límites, tamaños de texto, rangos numéricos y enum. Las restricciones no
soportadas se rechazan, no se ignoran. No admite `$ref`, uniones ni regex. Se validan
argumentos/resultados y se copian como JSON; los booleanos no son enteros.

Los handlers son código confiable de la aplicación, no Python aislado en sandbox.
No reciben estado ni permisos; no hay herramientas reales de dominio ni de sistema.
Las trazas contienen códigos, tamaños y fingerprints, nunca argumentos/resultados
o excepciones crudas. Los fingerprints no equivalen a anonimización.

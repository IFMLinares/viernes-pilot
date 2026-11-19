# Issue #26 — PR2 minimal reusable runtime
Branch: `feat/issue-26-agent-runtime`; base: `ef0d9d44cc093eb02469b0890a5300f920e0fa08` (merged PR28).
Delivery: one independent PR to main, size exception approved; offline unittest only; inline implementation.

## Specs

- S1: "Primero verifica que PR #28 esté integrado en main. Lee el diseño aprobado en `docs/issue-26-agent-architecture.md` y la infraestructura de evaluación incorporada en PR1." "Crea una branch nueva para este 2do PR".
- S2: "Implementar los contratos mínimos de ModelAdapter, ToolSpec, ToolExecutor, Policy, ConversationState y Runtime.handle_turn definidos en el RFC."
- S3: "Utilizar el protocolo nativo de herramientas de Ollama, con mensajes assistant.tool_calls y resultados role=\"tool\"."
- S4: "Mantener el runtime independiente de CommitmentStore, SQLite y reglas específicas de pendientes." "Mantener el estado conversacional serializable, sin implementar todavía persistencia entre reinicios."
- S5: "Permitir múltiples llamadas secuenciales a herramientas, con límites explícitos de iteraciones, solicitudes, tiempo y tamaño de contexto."
- S6: "Validar nombres, argumentos y resultados de herramientas." "Clasificar efectos como read, prepare, write y external." "Permitir inicialmente solo herramientas autorizadas de lectura y preparación."
- S7: "Devolver errores estructurados y permitir recuperación controlada ante fallos recuperables." "Incorporar trazas sanitizadas para evaluar selección de herramientas, argumentos, resultados y presupuestos."
- S8: "No modificar el comportamiento del planner actual." "No implementar todavía las herramientas reales de pendientes." "No crear persistencia de sesiones; corresponde a PR3." "No introducir un framework sin justificación." "No habilitar herramientas de sistema operativo ni operaciones externas." "No permitir que el LLM confirme o ejecute escrituras persistentes." "No generar un catálogo de regex para interpretar intenciones."
- S9: "Tool calling nativo simulado." "Llamadas secuenciales." "Herramienta inexistente." "Argumentos inválidos." "Resultado malformado." "Rechazo de permisos." "Presupuesto agotado." "Interrupción del modelo." "Serialización y restauración segura del estado." "Ausencia de efectos de escritura."
- S10: "Antes de implementar, presenta el diseño concreto de archivos, contratos y criterios de aceptación." "Después implementa exclusivamente PR2, ejecuta las pruebas offline correspondientes y prepara un PR independiente hacia main, vinculado al issue #26." "No avances a PR3 ni actives el runtime como comportamiento predeterminado."

## Tasks

- T1 [S2,S4,S9] inline — checked locally: JSON contracts/state and limits, six offline tests/docs. Schema validation belongs to T2's tool boundary. Risk: item 2 (safe state admission). Commit: first unit; final verification pending.
- T2 [S2,S6,S7,S8,S9] inline — pending: explicit registration, deny-by-default policy, bounded executor, sanitized traces, tests/docs. Risk: item 2 (tool execution permissions). Commit: pending.
- T3 [S3,S5,S7,S8,S9] inline — pending: native Ollama adapter, bounded turn loop and timer reuse, tests/docs. Risk: items 2 and 3 (execution guards; compatibility of PR1 timer). Commit: pending.
- T4 [S1,S8,S10] inline plus independent verifier — pending: full offline checks, scoped security verification, old planner/evaluator compatibility, publish one independent PR. No live inference or PR3.

## Log

L1 — Original request (verbatim):

> Vamos a comenzar PR2 del issue #26: runtime reutilizable mínimo del agente.
>
> Primero verifica que PR #28 esté integrado en main. Lee el diseño aprobado en `docs/issue-26-agent-architecture.md` y la infraestructura de evaluación incorporada en PR1.
>
> Crea una branch nueva para este 2do PR
> Objetivo: implementar un runtime genérico y limitado, capaz de interactuar con Ollama mediante tool calling nativo, sin reemplazar todavía el planner actual.
>
> Requisitos:
>
> 1. Implementar los contratos mínimos de ModelAdapter, ToolSpec, ToolExecutor, Policy, ConversationState y Runtime.handle_turn definidos en el RFC.
> 2. Utilizar el protocolo nativo de herramientas de Ollama, con mensajes assistant.tool_calls y resultados role="tool".
> 3. Mantener el runtime independiente de CommitmentStore, SQLite y reglas específicas de pendientes.
> 4. Permitir múltiples llamadas secuenciales a herramientas, con límites explícitos de iteraciones, solicitudes, tiempo y tamaño de contexto.
> 5. Validar nombres, argumentos y resultados de herramientas.
> 6. Clasificar efectos como read, prepare, write y external.
> 7. Permitir inicialmente solo herramientas autorizadas de lectura y preparación.
> 8. Mantener el estado conversacional serializable, sin implementar todavía persistencia entre reinicios.
> 9. Devolver errores estructurados y permitir recuperación controlada ante fallos recuperables.
> 10. Incorporar trazas sanitizadas para evaluar selección de herramientas, argumentos, resultados y presupuestos.
>
> Restricciones:
>
> - No modificar el comportamiento del planner actual.
> - No implementar todavía las herramientas reales de pendientes.
> - No crear persistencia de sesiones; corresponde a PR3.
> - No introducir un framework sin justificación.
> - No habilitar herramientas de sistema operativo ni operaciones externas.
> - No permitir que el LLM confirme o ejecute escrituras persistentes.
> - No generar un catálogo de regex para interpretar intenciones.
>
> Pruebas:
>
> - Tool calling nativo simulado.
> - Llamadas secuenciales.
> - Herramienta inexistente.
> - Argumentos inválidos.
> - Resultado malformado.
> - Rechazo de permisos.
> - Presupuesto agotado.
> - Interrupción del modelo.
> - Serialización y restauración segura del estado.
> - Ausencia de efectos de escritura.
>
> Antes de implementar, presenta el diseño concreto de archivos, contratos y criterios de aceptación.
>
> Después implementa exclusivamente PR2, ejecuta las pruebas offline correspondientes y prepara un PR independiente hacia main, vinculado al issue #26.
>
> No avances a PR3 ni actives el runtime como comportamiento predeterminado.

L2 — Delivery decision (verbatim): "Un PR con excepción". Applies to PR2 only; no protected label mutation inferred. Forecast 900–1,300 authored changed lines including tests/docs; advisory forecast, not a reason to omit coverage.

L3 — GitHub PR28 verified MERGED; local main fast-forwarded to origin/main. New branch created at `ef0d9d4`; local RFC inputs preserved. No live inference authorized. Parent read RFC contracts and PR1 transport; official Ollama documentation confirms native assistant/tool messages. CodeGraph previously unavailable for this workspace; no index initialization.

L4 — Route: inline because the units share contracts and are dependent; no parallel writer trigger. Runtime must not import PR1 Budget (SQLite/mock patching). Only its pure hard deadline mechanism may be shared, preserving old exception semantics with differential checks. Host handlers are trusted application code, not a sandbox. Terminal turn failure returns the input state; recoverable tool errors may continue within limits.

L5 — T1 RED: `python -B -m unittest tests.test_agent_state` failed because the module did not exist. GREEN: six tests passed after implementation. State serialization includes explicit version admission and completed native-call ordering, and excludes system/grant fields; no persistence. The initial serializer omitted the init-disabled version field; round-trip tests caught it and explicit serialization fixed it. Schema validation remains at T2's tool boundary, avoiding a separate schema framework.

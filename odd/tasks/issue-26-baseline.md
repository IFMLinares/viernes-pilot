# Issue #26 — PR1 conversational baseline
Branch: `test/issue-26-agent-baseline`; base: `899d840f4a5e679db3201c6766aa98ba331400b1`.
Delivery: one PR to main; user accepted the over-400-line exception. Runner: Python unittest, no live inference.

## Specs

- S1: "Lee `docs/issue-26-agent-architecture.md` desde main y respeta el plan aprobado." Main, origin/main and this branch were verified equal after fetch; PR27 is merged.
- S2: "Crear un corpus reproducible de conversaciones completas basado en los defectos de los issues #3, #4, #5 y #6." "Evaluar resultados, estado conversacional, llamadas a herramientas y efectos persistidos, no únicamente texto de respuesta."
- S3: "Contabilizar todas las peticiones HTTP reales realizadas al modelo, incluidas continuaciones y reintentos." Count durable reservations before every actual planner POST; failed attempts consume budget. No new automatic retry policy.
- S4: "Diferenciar claramente tests deterministas, replay y evaluaciones con el modelo real." "Introducir presupuestos configurables y mecanismos de parada para evaluaciones live." Live is not run in this delivery; deterministic synthetic wire data is never labeled recorded model evidence.
- S5: "Registrar los fallos reproducibles del planner actual como baseline, sin alterar su comportamiento." "No implementar todavía el nuevo runtime." "No modificar las reglas de decisión del planner." "No agregar regex para resolver los casos fallidos."
- S6: "No incorporar nuevas dependencias salvo necesidad justificada." "No ejecutar evaluaciones live sin definir previamente sus presupuestos." "No utilizar datos personales reales en los fixtures." "Mantener los cambios centrados en infraestructura de evaluación, pruebas y documentación."
- S7: "Antes de implementar, inspecciona el evaluador existente y presenta un plan concreto con archivos afectados, riesgos y criterios de aceptación." "Después implementa únicamente PR1, ejecuta las pruebas locales que no requieran inferencia y prepara un PR hacia main vinculado al issue #26." "No comiences PR2 ni fases posteriores."

## Tasks

- T1 [S3,S4,S6] inline — checked locally: durable evaluation-only HTTP accounting, caps/deadlines, legacy evaluator compatibility, tests/docs. Risk: item 2 (live execution guard and budget enforcement). Commit: `1d93a3d`; independent feature-end verification pending.
- T2 [S2,S4,S5,S6] inline — checked locally: synthetic multi-turn corpus, observation/assertions, separate evidence modes, replay and baseline failure reports, tests/docs. Commit: `45a2299`; independent feature-end verification pending.
- T3 [S1,S5,S7] inline + independent verification for item 2 — pending: offline suite and differential checks, scope review, one linked PR. Commit/PR: pending.

## Log

L1 — Original request (verbatim):

> Ahora revisa que esta branch issue-26-aggent-baseline este actualizada con main (y que main este actualizada) y inicia esto
>
> Vamos a comenzar la primera fase de implementación del issue #26 de Viernes Pilot.
>
> Lee `docs/issue-26-agent-architecture.md` desde main y respeta el plan aprobado.
>
> Trabaja exclusivamente en PR1: baseline conversacional y contabilidad real de solicitudes HTTP a Ollama.
>
> Objetivos:
>
> 1. Crear un corpus reproducible de conversaciones completas basado en los defectos de los issues #3, #4, #5 y #6.
> 2. Evaluar resultados, estado conversacional, llamadas a herramientas y efectos persistidos, no únicamente texto de respuesta.
> 3. Contabilizar todas las peticiones HTTP reales realizadas al modelo, incluidas continuaciones y reintentos.
> 4. Diferenciar claramente tests deterministas, replay y evaluaciones con el modelo real.
> 5. Introducir presupuestos configurables y mecanismos de parada para evaluaciones live.
> 6. Registrar los fallos reproducibles del planner actual como baseline, sin alterar su comportamiento.
>
> Restricciones:
>
> - No implementar todavía el nuevo runtime.
> - No modificar las reglas de decisión del planner.
> - No agregar regex para resolver los casos fallidos.
> - No incorporar nuevas dependencias salvo necesidad justificada.
> - No ejecutar evaluaciones live sin definir previamente sus presupuestos.
> - No utilizar datos personales reales en los fixtures.
> - Mantener los cambios centrados en infraestructura de evaluación, pruebas y documentación.
>
> Antes de implementar, inspecciona el evaluador existente y presenta un plan concreto con archivos afectados, riesgos y criterios de aceptación.
>
> Después implementa únicamente PR1, ejecuta las pruebas locales que no requieran inferencia y prepara un PR hacia main vinculado al issue #26.
>
> No comiences PR2 ni fases posteriores.

L2 — User delivery decision (verbatim): "Un PR con excepción". One PR1 delivery, not PR2; no protected-label mutation inferred.

L3 — Exploration: legacy evaluator counts interpreter invocations, while `core/planner.py:422-428` sends every continuation separately. Exact boundary is evaluation-scoped wrapping of `requests.post`; core source stays unchanged. Existing focused runner: `python -B -m unittest tests.test_interpreter_evaluation tests.test_offline_evaluation`.

L4 — Route: parent writes inline; no independent parallel writer units or context-backstop trigger. Separate read-only explorer supplied a routing map. Expected files: evaluation tools, synthetic corpus, tests, evaluation docs, this logbook. Temporary state remains outside the workspace. Synthetic transport failures model error classes, not proof of the original live model's root cause.

L5 — T1 RED: `python -B -m unittest tests.test_evaluation_http` failed on the missing transport module. GREEN: `python -B -m unittest tests.test_evaluation_http tests.test_interpreter_evaluation` passed 34 tests. First combined check found legacy zero-request reporting incompatible with rejecting zero; retained its no-send partial report. Seven new tests cover durable count-before-send, reopen, retries/continuations, hard timeout and budget binding. No inference. SQLite holds only evaluation accounting, not production sessions.

L6 — T2 RED: `python -B -m unittest tests.test_conversation_evaluation` failed on the missing runner. GREEN: the new conversation/HTTP tests passed 17 tests. Six conversations, 16 turns, nine simulated POSTs and zero actual HTTP requests reproduce host behavior; acceptance remains false intentionally. The two date-wire injections are not asserted as the original live failure's root cause. Replay provenance is caller-declared; no real recordings are shipped. An initially assumed natural-query fast path required a model response; the query/complete scenario uses explicit `/list` to isolate confirmed store behavior instead of inventing model output.

L7 — Offline applicable suite: `python -B -m unittest tests.test_evaluation_http tests.test_conversation_evaluation tests.test_interpreter_evaluation tests.test_offline_evaluation tests.test_commitment_store tests.test_ollama_runtime tests.test_planner_entrypoint tests.test_planner_queries tests.test_planner_conversation tests.test_planner_clarification tests.test_planner_diagnostics tests.test_planner_generation tests.test_planner_intent tests.test_planner_presentation tests.test_planner_tool_loop tests.test_planner_tools tests.test_planner_capture` passed 230 tests. Connectivity/audio/OS integration checks and live inference were not run. RDD remains disabled by clone-local preference; no review transaction was started. Independent guard/compatibility verification is still pending.

L8 — Independent verification passed 108 focused tests and differential checks of all three legacy evaluator modes plus the rescoring sibling. Core/requirements bytes are unchanged. One blocker B1: explicit empty live endpoint/model silently selected defaults. Its committed regression observed RED (exit 0 instead of 2 for empty endpoint/model and whitespace model); the guard now rejects empty/whitespace configuration before reservation/send/output mutation. Three targeted guard/missing-budget/mocked-valid-path tests passed. One correction batch only; independent B1 recheck pending. Initial verifier launch produced no verdict due to usage limit; user said "continua" before the successful launch. No inference occurred.

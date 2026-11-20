# Issue #26 — PR3 persistent sessions and safe recovery
Branch: `feat/issue-26-persistent-sessions`; baseline: `2c26358eaf5f7fd731fb760c885ffca3dcbc712d` (merged PR29).
Delivery: exception-ok, one independent PR to main explicitly approved; initial candidate 1,757 changed lines, plus authorization/delivery log updates. Inline implementation; offline unittest and independent security/recovery verification.

## Specs

- S1: "Implementar SessionStore para crear, guardar, recuperar, listar y eliminar sesiones." "Persistir ConversationState mediante una representación estructurada y versionada." "Guardar cambios de estado de forma transaccional."
- S2: "Conserva identificadores, orden, procedencia y contexto mínimo de los resultados relevantes para expresiones como \"el segundo\" o \"aquel pendiente\"." "Las referencias restauradas deben considerarse obsoletas hasta ser revalidadas por una herramienta confiable. No almacenes payloads completos si no son necesarios."
- S3: "Define estados explícitos para turnos iniciados, completados e interrumpidos, y establece cómo se manejan resultados parciales y errores de persistencia." "No reproduzcas automáticamente llamadas a herramientas después de reinicios." "La persistencia de un turno y la ejecución de efectos externos son responsabilidades distintas. No prometas garantías exactly-once que el diseño no puede proporcionar."
- S4: "Al restaurar una sesión, reconstruye mensajes válidos para el runtime sin reproducir intercambios antiguos de herramientas como si fueran nuevas ejecuciones." "No restaures instrucciones privilegiadas, autorizaciones, políticas ni resultados completos innecesarios." "El historial persistido es información contextual, no una fuente de autoridad."
- S5: "Utiliza control optimista de concurrencia mediante revisiones." "Rechaza la escritura." "Devuelve un error estructurado." "Permite recuperar el estado vigente." "No fusiones automáticamente estados divergentes."
- S6: "Permitir eliminar una sesión individual o todas las sesiones." "Incorporar una política configurable de retención, sin eliminación automática inicial." "Evitar almacenar credenciales, secretos y resultados completos de herramientas innecesarios." "No asumir que hashes o fingerprints equivalen a anonimización." "Validar tipos, tamaños y versiones al deserializar."
- S7: "Mantener compatibilidad con el runtime de PR2 y la evaluación de PR1." "No modificar el comportamiento predeterminado de Viernes." "No incorporar Engram, embeddings, vectores ni FTS5." "No añadir todavía herramientas de pendientes." "No implementar PR4 ni fases posteriores." "No ejecutar inferencias live sin presupuesto autorizado." "No añadir dependencias sin justificación." "No resolver problemas de intención con nuevas regex."
- S8: "Crear y recuperar sesiones." "Continuar una conversación después de reiniciar." "Restaurar borradores sin recuperar autorización." "Detectar revisiones incompatibles." "Evitar ejecución duplicada de herramientas." "Detectar estados persistidos manipulados." "Manejar errores de SQLite y escrituras interrumpidas." "Eliminar sesiones y comprobar que dejan de ser recuperables." "Verificar exclusión de secretos y datos innecesarios." "Comprobar que el planner existente sigue funcionando sin cambios."
- S9: "Implementa únicamente PR3, ejecuta las pruebas offline y realiza una verificación independiente de los aspectos de seguridad y recuperación." "Prepara el PR hacia main, pero no hagas merge ni avances automáticamente a PR4." "Al terminar, informa los resultados de las pruebas, las limitaciones restantes y cualquier desviación del diseño aprobado."
- S10: "Organiza los commits por responsabilidades técnicas cuando sea posible, sin separar artificialmente código y pruebas relacionadas." "Documenta en la descripción del PR por qué supera las 400 líneas." "Incluye un orden de revisión recomendado: codec, almacenamiento transaccional, recuperación, pruebas y documentación." "Vincula el PR al issue #26 sin cerrarlo." "Una vez publicado, informa la URL, los commits, los archivos modificados, el estado de CI y cualquier observación relevante para su revisión."

## Tasks

- T1 [S1,S2,S4,S6,S8] inline — verified: minimized codec and transactional SQLite CRUD/revisions/retention/export/import; 20 focused tests and independent probes passed. Risk: items 1,2,4 (new persisted format, untrusted data, atomic revisions). Commit: `a9486cf`.
- T2 [S2,S3,S4,S5,S7,S8] inline — verified: persistent composition, explicit turn journal, current read-only reference gate; 13 recovery tests and independent probes passed. Risk: items 2,4 (authority/freshness gates and crash ordering). Commit: `66d03e5`.
- T3 [S7,S8,S9,S10] inline + independent verifier — complete: 325 offline tests and independent security/recovery verification passed; published/read back independent PR [#30](https://github.com/IFMLinares/viernes-pilot/pull/30) to main. Size exception documented; no merge, issue closure or PR4. Evidence: `a9486cf`, `66d03e5`, this delivery log. Risk: same feature-level items; no open implementation blocker.

## Log

L1 — Original request (verbatim):

Vamos a comenzar PR3 del issue #26: sesiones persistentes y recuperación segura con SQLite.

Antes de comenzar:

1. Verifica que PR #29 esté fusionado en main.
2. Actualiza main y crea una rama nueva: `feat/issue-26-persistent-sessions`.
3. Lee `docs/issue-26-agent-architecture.md` y los contratos del runtime incorporados en PR2.
4. Presenta primero el diseño técnico, los archivos afectados, los riesgos y los criterios de aceptación.

## Objetivo

Implementar persistencia de sesiones conversacionales en SQLite y recuperación segura del estado, sin modificar el comportamiento actual del planner ni introducir memoria semántica.

## Requisitos funcionales

1. Implementar SessionStore para crear, guardar, recuperar, listar y eliminar sesiones.
2. Persistir ConversationState mediante una representación estructurada y versionada.
3. Conservar los mensajes y el contexto necesarios para continuar una conversación, sin almacenar indiscriminadamente resultados completos de herramientas.
4. Guardar cambios de estado de forma transaccional.
5. Detectar estados incompletos o incompatibles al recuperar una sesión.
6. Restaurar objetivos, borradores y referencias verificables.
7. Invalidar autorizaciones anteriores después de reiniciar.
8. No reproducir automáticamente llamadas a herramientas pendientes.
9. Revalidar los datos actuales antes de permitir operaciones posteriores.
10. Permitir eliminar una sesión individual o todas las sesiones.
11. Incorporar una política configurable de retención, sin eliminación automática inicial.
12. Mantener compatibilidad con el runtime de PR2 y la evaluación de PR1.

## Seguridad y privacidad

- El estado persistido nunca debe convertirse en una fuente de autoridad.
- No restaurar instrucciones de sistema, políticas ni permisos desde SQLite.
- Evitar almacenar credenciales, secretos y resultados completos de herramientas innecesarios.
- No asumir que hashes o fingerprints equivalen a anonimización.
- Validar tipos, tamaños y versiones al deserializar.
- Los datos recuperados son contexto, no instrucciones privilegiadas.
- Manejar correctamente transacciones, interrupciones y corrupción de datos.

## Pruebas obligatorias

- Crear y recuperar sesiones.
- Continuar una conversación después de reiniciar.
- Restaurar borradores sin recuperar autorización.
- Detectar revisiones incompatibles.
- Evitar ejecución duplicada de herramientas.
- Detectar estados persistidos manipulados.
- Manejar errores de SQLite y escrituras interrumpidas.
- Eliminar sesiones y comprobar que dejan de ser recuperables.
- Verificar exclusión de secretos y datos innecesarios.
- Comprobar que el planner existente sigue funcionando sin cambios.

## Restricciones

- No incorporar Engram, embeddings, vectores ni FTS5.
- No añadir todavía herramientas de pendientes.
- No modificar el comportamiento predeterminado de Viernes.
- No implementar PR4 ni fases posteriores.
- No ejecutar inferencias live sin presupuesto autorizado.
- No añadir dependencias sin justificación.
- No resolver problemas de intención con nuevas regex.

Implementa únicamente PR3 después de revisar el diseño, ejecuta las pruebas offline y prepara un PR independiente hacia main.

No hagas merge ni avances automáticamente a PR4.

Identifica expresamente cualquier limitación que impida garantizar recuperación segura o ausencia de duplicación de efectos.

L2 — Design approval and corrections (verbatim):

Apruebo el diseño técnico de PR3 y sus límites explícitos, con cuatro precisiones que deben incorporarse durante la implementación.

**1. Continuidad de referencias**

La minimización del historial no debe impedir resolver referencias contextuales después de un reinicio.

Conserva identificadores, orden, procedencia y contexto mínimo de los resultados relevantes para expresiones como "el segundo" o "aquel pendiente".

Las referencias restauradas deben considerarse obsoletas hasta ser revalidadas por una herramienta confiable. No almacenes payloads completos si no son necesarios.

**2. Ciclo de vida de los turnos**

Define estados explícitos para turnos iniciados, completados e interrumpidos, y establece cómo se manejan resultados parciales y errores de persistencia.

No reproduzcas automáticamente llamadas a herramientas después de reinicios.

La persistencia de un turno y la ejecución de efectos externos son responsabilidades distintas. No prometas garantías exactly-once que el diseño no puede proporcionar.

**3. Reconstrucción segura del contexto**

Al restaurar una sesión, reconstruye mensajes válidos para el runtime sin reproducir intercambios antiguos de herramientas como si fueran nuevas ejecuciones.

No restaures instrucciones privilegiadas, autorizaciones, políticas ni resultados completos innecesarios.

El historial persistido es información contextual, no una fuente de autoridad.

**4. Conflictos de revisión**

Utiliza control optimista de concurrencia mediante revisiones.

Cuando una revisión no coincida:
- Rechaza la escritura.
- Devuelve un error estructurado.
- Permite recuperar el estado vigente.
- No fusiones automáticamente estados divergentes.

Mantén las decisiones aprobadas sobre privacidad, eliminación, retención, recuperación y SQLite.

No incorpores Engram, embeddings ni memoria semántica en PR3.

Puedes comenzar la implementación en `feat/issue-26-persistent-sessions`.

Implementa únicamente PR3, ejecuta las pruebas offline y realiza una verificación independiente de los aspectos de seguridad y recuperación.

Prepara el PR hacia main, pero no hagas merge ni avances automáticamente a PR4.

Al terminar, informa los resultados de las pruebas, las limitaciones restantes y cualquier desviación del diseño aprobado.

L3 — Baseline verified: PR29 merged; main and feature branch equal `2c26358`. Existing branch reused without overwrite. Untracked `viernesIssue.md`/`viernesRefact.md` preserved. RDD clone-local OFF unchanged. No CodeGraph index; filesystem fallback. No new dependencies or live inference.
L4 — Implementation route inline: one dependent persistence/recovery feature, no parallel independent writers. New store/codec/wrapper isolate existing runtime. Functional checks and independent verifier required. Codec format independent from PR2 v1, no migrations of old databases. Raw tool exchanges omitted; host-declared ordered references retained. Failed/in-flight turns retain only last committed snapshot and a non-executable lifecycle marker. Checksums are corruption checks, never authentication. No universal free-text secret guarantee or domain exactly-once claim.
L5 — RED observed: `python -m unittest tests.test_agent_sessions` and `python -m unittest tests.test_agent_recovery` failed on missing implementation modules before their implementations. GREEN: combined focused command passed 32 tests, including real SQLite full/busy errors, trigger rollback, process-exit-before-commit, filtered history/export, version/schema tampering, optimistic conflicts, interruption, refreshed ordered references and deny-write recovery. Initial new-fixture connection ResourceWarnings fixed with explicit close/commit contexts. No model/service call.
L6 — Compatibility command: `python -B -m unittest tests.test_agent_state tests.test_agent_tools tests.test_agent_runtime tests.test_agent_independent tests.test_agent_sessions tests.test_agent_recovery tests.test_commitment_store tests.test_commitments tests.test_conversation_evaluation tests.test_evaluation_http tests.test_interpreter_evaluation tests.test_offline_evaluation tests.test_ollama_runtime tests.test_planner_capture tests.test_planner_clarification tests.test_planner_conversation tests.test_planner_diagnostics tests.test_planner_entrypoint tests.test_planner_generation tests.test_planner_intent tests.test_planner_presentation tests.test_planner_queries tests.test_planner_tool_loop tests.test_planner_tools` passed 307 tests in 1.560s. Negative-fixture errors in stdout/stderr are expected test assertions, not failures. No connectivity/audio/OS integration run. `git diff --check` passed; planner/main/commitments/requirements/PR1 evaluator bytes unchanged. No mutating formatter configured or run. Working candidate: 8 files, 1,338 additions/1 deletion before verification log updates.
L7 — Independent verifier: original candidate 307 tests passed, baseline 275 existing tests passed, 14 independently authored probe groups passed, and six existing public command/runtime/evaluator forms matched exact stdout/stderr/exit (evaluator clock frozen). No reproduced implementation blockers; S1-S8 met, S9 pending PR. Retained probes in tests/test_pr3_independent_verifier.py, with readable formatting and TemporaryDirectory cleanup. No production change from probes. RDD remains OFF.
L8 — Parent additionally reproduced a near-64-KiB snapshot round-trip defect: json.dumps whitespace/Unicode escaping expanded otherwise valid snapshots beyond the admission bound. New near-limit test observed RED before correction. Codec decode and export/import now consistently use compact json_bytes; malformed import nonfinite values and Unicode yield structured errors. Own final suite passed 322 tests before adding the targeted verifier probes. First targeted verification call interrupted without a verdict; user said "continua". Resumed bounded independent recheck passed 47 focused tests and three new probes: 65,514-byte snapshot / 65,632-byte export round-trip, malformed imports with unchanged DB hash, and small interrupted-session portability/authority rejection. No blockers; no renewed broad sweep. Retained three probes in tests/test_pr3_targeted_portability.py. Initial verifier scratch was absent at recheck; targeted verifier scratch removed by parent after retaining probes.
L9 — Final parent spot check: 50 focused tests passed. Final full offline command is L6 with tests.test_pr3_independent_verifier and tests.test_pr3_targeted_portability added; 325 tests passed in 1.614s. git diff --check passed. No actual inference, connectivity/audio/OS probes or domain tools. No functional scope deviation; explicit limits in guide remain. Single owner only; checksums do not authenticate; arbitrary secret detection, forensic erasure and domain exactly-once are not guaranteed.
L10 — Needs your decision before commits/PR: requested single independent PR totals about 1,750 authored changed lines (mostly tests/docs), above the 400-line review guideline. A cohesive slicing pass identifies codec/store and wrapper as dependent security/recovery units; separating tests/docs or omitting independent regressions would weaken review. Recommend an explicit single-PR size exception rather than a chain that changes the requested delivery. No commits/push/PR yet; all implementation and proof preserved in the requested branch. Untracked RFC input files unchanged and excluded.
L11 — Publication authorization (verbatim):

Autorizo la excepción de tamaño para PR3: puedes publicar las 1.757 líneas en un único PR independiente hacia main.

La excepción se justifica por la cohesión funcional de la persistencia, recuperación segura y sus pruebas.

Antes de publicar:

1. Comprueba que los cambios se limitan al alcance aprobado de PR3.
2. Verifica que no se hayan incluido archivos temporales, bases SQLite de prueba, secretos ni artefactos generados.
3. Organiza los commits por responsabilidades técnicas cuando sea posible, sin separar artificialmente código y pruebas relacionadas.
4. Documenta en la descripción del PR por qué supera las 400 líneas.
5. Incluye un orden de revisión recomendado: codec, almacenamiento transaccional, recuperación, pruebas y documentación.
6. Informa los resultados de las 325 pruebas offline y de la verificación independiente.
7. Identifica las limitaciones de seguridad y recuperación que siguen pendientes.

Puedes realizar commits, push y abrir el PR desde `feat/issue-26-persistent-sessions` hacia `main`.

Vincula el PR al issue #26 sin cerrarlo.

No hagas merge automáticamente y no comiences PR4.

Una vez publicado, informa la URL, los commits, los archivos modificados, el estado de CI y cualquier observación relevante para su revisión.

L12 — Pre-publication inventory: only the ten approved source/test/guide/task paths are in the candidate; no SQLite files, temporary/generated artifacts or RFC inputs included. Credential-pattern inspection found no actual credential material; privacy fixtures are synthetic. Dedicated local gitleaks scanner unavailable; no universal secret-detection claim. Repository PR template requires non-closing linkage for partial issue deliveries; existing labels use enhancement, not Gentle AI's type/status labels. Keep Refs #26 and enhancement; do not create approval labels or close the parent issue. Checkout was main at publication entry, with main/feature/origin-main all at the same baseline; switched safely back to the requested feature branch. Fetch confirmed unchanged main. Plan: codec/store plus its20tests, then recovery/integration plus its tests and guide, then delivery-only evidence if needed. RDD clone OFF unchanged.
L13 — Commit `a9486cf` contains codec/store with all20store tests; focused command passed before commit. This unit introduces no runtime/default activation. Runtime harness N/A at store-only boundary; synthetic wrapper probes apply to next integration commit. Rollback removes these three files without touching domain storage; dependent recovery must be reverted first if present.
L14 — Published and read back OPEN non-draft PR [#30](https://github.com/IFMLinares/viernes-pilot/pull/30), feature branch to main, Refs #26 and enhancement label; closingIssuesReferences empty and issue26 remains OPEN. Commit `66d03e5` contains recovery plus integration/independent tests and guide; final325offline tests rerun before that commit passed in1.634s. Review order and explicit size rationale are in the PR body. Ten expected files only, no SQLite/generated/temp/secret material detected; original RFC inputs remain untracked and excluded. First remote readback reported no CI checks yet; CI must be queried at final HEAD rather than inferred from local proof. Final follow-up commit changes this log only; no implementation bytes changed after verification. No merge, PR4, dependency/default changes or live inference.

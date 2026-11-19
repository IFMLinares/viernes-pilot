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

## Contabilidad HTTP y baseline conversacional del PR1

El evaluador contabiliza cada POST del planner antes del envío, incluidas las
continuaciones y los intentos fallidos repetidos explícitamente. No agrega
reintentos automáticos ni modifica las decisiones del planner. El archivo
`<output>.attempts.sqlite3` conserva el contador, vencimiento y configuración;
reabrirlo no reinicia el cupo ni extiende el tiempo. Una reserva no demuestra que
Ollama haya recibido la petición. `--request-timeout` limita cada intento y se
acota al tiempo global restante; exige temporizadores POSIX en el hilo principal.
Sin esa capacidad, el envío se rechaza. Los reportes históricos no se reescriben.

```bash
python -B -m unittest tests.test_evaluation_http tests.test_conversation_evaluation
python -B -m tools.evaluate_conversations --output /tmp/viernes-baseline.json
```

El segundo comando no utiliza red por defecto. Recorre seis conversaciones
sintéticas y 16 turnos con un Planner por conversación y SQLite temporal aislado:
aclaración/confirmación, corrección pendiente, cancelación/referencia, área inferida
y detalle online omitido, fallos de fecha y consulta/finalización. Los errores de
fechas se inyectan como salidas malformadas; no prueban la causa del fallo real #5.

`expect` registra el comportamiento actual con respuestas simuladas; `acceptance`
registra por separado el resultado deseado. Se verifican respuesta, estado,
campos/procedencia, herramientas, intentos y registros persistidos. Ningún turno
sin `/confirm` puede alterar registros. El reporte conserva resultados y hashes,
no conversaciones ni respuestas crudas. No implementa persistencia de sesiones.

El baseline distribuido termina con código **1**: puede estar completo y coincidir
con el comportamiento actual, pero `acceptance_passed=false` deja visibles los
fallos. No equivale a aceptación del modelo. Una diferencia inesperada detiene
la ejecución con `baseline_mismatch`. `http_attempts` y `simulated_attempts` se
informan por separado: las pruebas deterministas y replay no hacen solicitudes HTTP.

`--mode replay --replay <recording.json>` requiere procedencia declarada
(`source=recorded-synthetic`, `model`, `digest`) y `cases[case_id]`, con una lista
por turno de envelopes `{status_code, body}` de Ollama. Nunca recurre a la red.
No se distribuyen grabaciones de modelo real; probar esta ruta con datos simulados
no constituye evidencia real.

El modo live requiere autorización separada y los argumentos explícitos
`--mode live --url --model --max-requests --max-seconds --request-timeout --output`.
Máximos: 60 POST y 900 segundos. Se detiene ante el primer error o fallo de
aceptación y conserva un reporte parcial. Los ejemplos de presupuesto de la guía
en inglés no autorizan ejecutarlos. Este PR solo ejecuta pruebas sin inferencia.
Un destino o modelo live vacío o compuesto solo por espacios se rechaza antes
de crear el contador, enviar o sobrescribir el reporte; no selecciona valores
predeterminados.

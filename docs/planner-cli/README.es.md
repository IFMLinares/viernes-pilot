# Base del CLI del planner de texto

[English](README.md) | [Español](README.es.md)

Esta unidad conecta el motor histórico con `main.py` sin copiar cambios posteriores
de voz ni binarios. Conserva el arranque anterior sin opciones. Es una base
experimental, no la versión más reciente de conversación o herramientas de fechas.

```bash
python main.py --planner
```

Dentro del planner, `/help` explica `/new`, `/list`, `/edit`, `/done`, `/confirm`,
`/cancel` y `/quit`. Los cambios son propuestas hasta `/confirm`; `/cancel` los
descarta. Los comandos explícitos funcionan sin Ollama. Las áreas son `university`,
`work` y `personal`; las fechas de comandos JSON usan formato ISO.
En una propuesta pendiente con un solo compromiso nuevo, una corrección explícita
como `El area es para la universidad, no personal` cambia solo su área y agrega la
corrección a la fuente. Revisa la propuesta actualizada antes de `/confirm` exacto.
Las demás solicitudes siguen bloqueadas; la corrección no elige implícitamente
entre varios compromisos ni modifica propuestas sobre registros guardados.
Para registros guardados, usa `/edit ID`.
Cancelar descarta el borrador y su fuente. Una referencia al borrador cancelado
explica que ya no está disponible y pide repetir la solicitud completa; nunca
restaura ni guarda el contenido descartado.
Usa una base sintética nueva para probar. `.env` puede sobrescribir su ruta;
exportar solo una variable en la terminal no garantiza aislamiento.

```bash
python -B -m unittest tests.test_planner_entrypoint tests.test_commitments
```

Las pruebas simulan modelo y enrutamiento, y usan almacenamiento temporal. No son
aceptación conversacional real. Las issues #3–#6 siguen abiertas. Interfaz bilingüe,
consultas acotadas, conversación, diagnósticos y fechas llegan en unidades posteriores.

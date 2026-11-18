# Probar Viernes manualmente

[English](README.md) | [Español](README.es.md)

Guía de arranque, pruebas y diagnóstico del **organizador de texto**. Primero
comprueba almacenamiento y confirmaciones sin generar respuestas de IA; después,
si lo deseas, prueba la interpretación con Ollama. Utiliza únicamente datos ficticios.

## Ruta rápida

1. Abre Bash en la raíz del repositorio y activa Python: [preparación](#1-preparar-python).
2. Crea una carpeta temporal y define el arranque protegido: [aislamiento](#2-crear-un-entorno-de-prueba-aislado).
3. Ejecuta `viernes_manual` y sigue la [prueba determinista](#3-prueba-determinista-paso-a-paso).
4. Comprueba reinicio y persistencia; luego prueba [Ollama](#5-pruebas-opcionales-con-ollama).
5. Si algo falla, consulta [diagnósticos](#6-diagnósticos-y-problemas-frecuentes).

Los comandos `bash` se escriben en la **terminal del sistema**. Los comandos
`text` que empiezan por `/` se escriben **dentro de Viernes**, en `tú:` o `you:`.
Para volver a la terminal, utiliza `/quit`.

### Qué se está probando

| Incluido | Fuera de esta guía |
| --- | --- |
| Crear, confirmar, consultar, editar y completar compromisos | Voz, Whisper, Piper y acciones del escritorio |
| Áreas, fechas, persistencia e idioma | Jira, Engram y memoria entre proyectos |
| Consultas locales y conversación con Ollama | Web, teléfono, sincronización y nube |

No se necesita OpenCode, Gentle AI ni una suscripción a ChatGPT para ejecutar
este organizador. Los modelos Sol/Luna del entorno de desarrollo son independientes
del modelo local que utiliza Viernes.

## 1. Preparar Python

Esta receta está pensada para Bash en Linux o WSL. Trabaja en el directorio que
contiene `main.py`, `config.py` y `core/`.

```bash
pwd
python3 --version
```

El proyecto declara Python 3.12 o superior. Si ya tienes el entorno del proyecto:

```bash
source .venv/bin/activate
```

Si necesitas un entorno independiente para esta prueba, créalo fuera del repositorio:

```bash
python3 -m venv "$HOME/.local/share/venvs/viernes-manual"
source "$HOME/.local/share/venvs/viernes-manual/bin/activate"
python -m pip install 'requests==2.34.2'
```

Si ese entorno ya existe, actívalo; no utilices `--clear`. La instalación de `requests`
descarga paquetes Python, no modelos. El pin corresponde a `requirements.txt`.
La receta protegida siguiente importa solo el organizador: requiere `requests`
y la biblioteca estándar, incluido SQLite; no requiere `faster-whisper` ni embeddings.
La instalación completa del asistente anterior se explica en el [README general](../../README.es.md).

```bash
python --version
python -m pip --version
python -c 'import requests, sqlite3; print("Planner dependencies available")'
```

## 2. Crear un entorno de prueba aislado

La base normal contiene datos personales. Además, `config.py` carga `.env`
sobrescribiendo variables de la terminal. **Exportar solamente `VIERNES_DB_PATH`
no garantiza el aislamiento** si `.env` define la misma variable.

Esta receta fija la base **después** de cargar la configuración y solo acepta
el directorio temporal de esta guía. No modifica `.env`, `config.py` ni tus datos.

```bash
export VIERNES_MANUAL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/viernes-manual.XXXXXX")"
export VIERNES_MANUAL_DB="$VIERNES_MANUAL_DIR/commitments.sqlite3"
printf 'Carpeta de prueba: %s\n' "$VIERNES_MANUAL_DIR"
```

La carpeta se crea bajo `TMPDIR`, o `/tmp` si no está definido. Copia esta función
completa en la misma terminal:

```bash
viernes_manual() {
  if [ "$#" -ne 0 ]; then
    printf 'Usage: viernes_manual (no arguments)\n' >&2
    return 2
  fi
  python -c '
import os
import sys
import tempfile
from pathlib import Path

database = Path(sys.argv[1]).resolve()
if not (
    database.parent.parent == Path(tempfile.gettempdir()).resolve()
    and database.parent.name.startswith("viernes-manual.")
    and database.parent.is_dir()
    and database.name == "commitments.sqlite3"
):
    raise SystemExit("Expected viernes-manual.*/commitments.sqlite3 under the system temporary directory; run setup first.")

import config
config.OLLAMA_URL = "http://127.0.0.1:11434"
config.OLLAMA_MODEL = "qwen3.5:9b"
os.environ["VIERNES_DB_PATH"] = str(database)
os.environ["VIERNES_OLLAMA_AUTOSTART"] = "false"
os.environ["VIERNES_OLLAMA_STARTUP_TIMEOUT"] = "10"

from core.diagnostics import Diagnostics
from core.planner import main
print(f"Test database: {database}")
raise SystemExit(main(diagnostics=Diagnostics()))
' "${VIERNES_MANUAL_DB:-}" 2>> "${VIERNES_MANUAL_DIR:?Create the test directory first}/diagnostics.jsonl"
}
```

```bash
viernes_manual
```

`viernes_manual` es un **ayudante de esta terminal**, no un comando nuevo de la
aplicación, y no acepta argumentos. Llama al mismo `core.planner.main` que utiliza `--planner`, conserva
la entrada interactiva con `python -c`, desactiva el autoarranque y guarda los
diagnósticos en la carpeta temporal. No cambia la configuración del siguiente proceso.

Comprueba que `Test database:` señala la carpeta recién creada. Si Ollama no está
disponible, se mostrará un aviso y los comandos explícitos seguirán funcionando.
El arranque puede consultar disponibilidad/modelos locales; esta primera prueba
**no genera inferencias**. No detengas un servidor existente para hacerla.

Conserva esta terminal y la ruta impresa: reiniciar con otra carpeta significa
abrir otra base. `/tmp` puede limpiarse al reiniciar el sistema; no utilices este
almacenamiento temporal para compromisos reales.

## 3. Prueba determinista paso a paso

Empieza con una carpeta nueva. El primer registro normalmente tendrá ID `1`;
si se muestra otro, sustituye `1` por ese ID en los pasos siguientes.
Los mensajes pueden aparecer en inglés o español según el idioma inicial.

### A. Ayuda y base vacía

```text
/help
/list --all
```

Esperado: ayuda y ningún compromiso guardado. `/list` no es un comando de Bash.

### B. Propuesta, confirmación y entrada vacía

```text
/new {"title":"MANUAL - Informe de prueba","area":"university","project":"manual-test","due_date":"2099-12-31"}
/help
/list --all
sí
```

Esperado: propuesta marcada como no guardada; el listado continúa vacío.
`sí` no guarda: se recuerda utilizar `/confirm` o `/cancel`. Presiona Enter
vacío: no debe guardar, cancelar ni activar el micrófono.

```text
/confirm
/list university --all
```

Esperado: un registro persistido, con título, área, proyecto y fecha solicitados.
Anota su ID. La fecha lejana mantiene el ejemplo independiente del día de la prueba.

### C. Cancelar una creación

```text
/new {"title":"MANUAL - No guardar","area":"work"}
/cancel
/list work --all
```

Esperado: ningún registro de trabajo. El registro de universidad debe seguir existiendo.

### D. Editar sin guardar automáticamente

```text
/edit 1 {"title":"MANUAL - Informe actualizado","due_date":"2099-12-30"}
/list university --all
/confirm
/list university --all
```

Esperado: antes de confirmar, el listado conserva los valores anteriores;
después, muestra el título y la fecha actualizados. Un listado no confirma una propuesta.

### E. Quitar fecha y completar

```text
/edit 1 {"due_date":null}
/confirm
/list university
/done 1
/list university --all
/confirm
/list university
/list university --all
```

Esperado: `null` elimina la fecha. El registro pendiente sin fecha aparece en el
listado normal; `/done` solo propone completarlo. Después de `/confirm`, queda
completado. Un **completado sin fecha se excluye del listado normal**, pero sigue
en `/list university --all`: no fue borrado.

### F. Rechazar entradas inválidas

```text
/new not-json
/new {"title":"MANUAL - Área inválida","area":"school"}
/new {"title":"MANUAL - Fecha inválida","area":"work","due_date":"2099-02-30"}
/edit 999999 {"title":"MANUAL - ID inexistente"}
/edit 1 {"status":"pending"}
/list --pending
/confirm
/list --all
```

Esperado: errores para JSON/campos/ID/opción inválidos; ninguna propuesta válida que
confirmar; el único registro guardado sigue siendo el de universidad.
`--pending` no está implementado. Los errores no deben convertirse en respuestas
generales de IA ni en escrituras.

### G. Persistencia y salida con una propuesta pendiente

```text
/new {"title":"MANUAL - Descartar al salir","area":"personal"}
/quit
```

Ya en Bash, vuelve a ejecutar **sin recrear las variables ni la carpeta**:

```bash
viernes_manual
```

```text
/list university --all
/list personal --all
```

Esperado: el registro completado de universidad persiste; el de personal nunca
se guardó. También se puede salir con Ctrl+C o fin de entrada (Ctrl+D en Bash).
Salir no elimina registros confirmados ni detiene automáticamente Ollama.

## 4. Referencia de comandos y alcance

| Dentro de Viernes | Efecto | ¿Necesita IA? |
| --- | --- | --- |
| `/help` | Muestra ayuda; disponible con propuesta pendiente | No |
| `/new {"title":"…","area":"personal"}` | Propone crear; título y área obligatorios | No |
| `/list` | Consulta todos los ámbitos dentro del alcance habitual | No |
| `/list work` | Filtra por área | No |
| `/list --all` / `/list work --all` | Incluye historial completo, pendientes y completados | No |
| `/edit ID {"project":"demo"}` | Propone cambios parciales de campos | No |
| `/done ID` | Propone marcar como completado | No |
| `/confirm` | Aplica exactamente la propuesta pendiente | No |
| `/cancel` | Descarta propuesta y contexto de aclaración | No |
| `/quit` | Sale descartando lo no confirmado | No |

- Áreas exactas: `university`, `work`, `personal`; no se traducen en JSON.
- Campos de creación/edición: `title`, `area`, `project`, `due_date`; fechas ISO
  `YYYY-MM-DD`. `project` y `due_date` son opcionales; `null` puede quitar una fecha.
- Los títulos guardados no se traducen al cambiar el idioma de la conversación.
- Los IDs son enteros positivos existentes. Los estados almacenados son `pending`
  y `completed`; `status` no es un campo editable mediante `/edit`.
- Alcance normal: fechas desde hace siete días inclusive y todo el futuro,
  más pendientes antiguos vencidos y pendientes sin fecha, en secciones separadas.
  No es un filtro de «solo pendientes».
- Semanas: lunes a domingo; meses: límites reales del calendario. Los rangos
  explícitos excluyen elementos fuera del período, incluidos los que no tienen fecha.
- No hay comandos `/delete`, `/reset`, `/undo` ni para reabrir completados.
  No edites SQLite directamente para simular comandos inexistentes.
- Para repetir desde cero, sal y crea **otra carpeta temporal** con el paso 2;
  no borres ni reemplaces la base real.

Estas consultas claras también se reconocen localmente, sin generación de IA:

```text
Show all my university commitments.
muestrame mis comprimisos del trabajo
Muéstrame mis compromisos de esta semana.
```

Después del recorrido anterior: la primera incluye el completado; trabajo sigue
vacío; la semana no incluye el completado sin fecha. En diagnósticos deben aparecer
como `fast_path`. Otra redacción puede necesitar el modelo: no todas las frases son atajos.

## 5. Pruebas opcionales con Ollama

Estas pruebas sí consumen recursos de inferencia local. No son necesarias para
validar SQLite. El modelo utilizado por el ayudante es `qwen3.5:9b` y debe estar
instalado; no se descarga automáticamente. Si falta, elige/instala un modelo compatible
como un paso separado y adapta la línea `config.OLLAMA_MODEL` del ayudante.

### Preparar el servidor

En otra terminal, comprueba el servidor local y sus modelos:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama ls
```

Si el servidor no está ejecutándose, puedes iniciarlo en esa terminal:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

Mantén esa terminal abierta y repite `ollama ls` desde otra. Si el puerto ya está
ocupado, comprueba el servidor existente; no mates procesos ni cambies servicios.
No uses `ollama run` como prueba de Viernes: es otra conversación y puede descargar
un modelo ausente. Opcionalmente, consulta la API sin generar texto:

```bash
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:11434/api/tags
```

Sal de Viernes con `/quit` y vuelve a ejecutar `viernes_manual` en la terminal
original. Si se abrió sin modelo disponible, hay que reiniciarlo para habilitar
la interpretación; iniciar Ollama después no actualiza esa sesión automáticamente.

### Casos de IA: expectativas, no garantías

| Escribe dentro de Viernes | Resultado buscado | Qué registrar si falla |
| --- | --- | --- |
| `Tengo que entregar MANUAL - Informe del trabajo el 31 de diciembre de 2099.` | Propuesta de trabajo con fecha `2099-12-31`; nada guardado todavía | Área/fecha inventada o respuesta general en lugar de propuesta |
| `/cancel` | Descarta la propuesta anterior | No confirmar una propuesta incorrecta |
| `Tengo un parcial el 23.` | Aclara el mes ausente; el año omitido usa el actual de Caracas | La interpretación es fallible; cancelar si propone datos no indicados |
| `/cancel` | Limpia la aclaración antes de otro caso | El caso siguiente comienza sin esa aclaración |
| `¿Qué es una derivada?` | Respuesta etiquetada como información general, no consulta de compromisos | Error de parseo o acción equivocada; no exigir una frase exacta |
| `¿Puedes dar un ejemplo?` | Seguimiento con contexto breve de la sesión | Respuesta irrelevante o pérdida de contexto |
| `Explain the difference between a task and an event.` | Respuesta general en inglés | Idioma incorrecto o escritura inesperada |
| `/list --all` | Continúan los mismos datos confirmados si cancelaste las propuestas | No debe haber tareas creadas por una explicación general |

Un fallo aquí no demuestra un fallo de SQLite. Una etiqueta de información general
tampoco garantiza que el modelo no invente hechos. Para comprobar datos personales,
utiliza los listados. La medición histórica fue parcial; las pruebas unitarias
no garantizan la precisión real de Ollama ni su velocidad.

La petición estructurada ahora usa `think: false`, también para conversación
general. Si el modelo vuelve a terminar por longitud sin contenido final, aparecerá
un aviso específico y el código `generation_limit`, sin guardar ni reintentar.
Reinicia Viernes para cargar cambios de código; conserva la misma ruta de prueba.

### Continuidad de una aclaración de área

Si Viernes pregunta el área, responde `Universidad`, `trabajo` o `personal`.
También reconoce las etiquetas inglesas, mayúsculas, `UNIVERSIDAD!` y
`Del área de la universidad`. Conserva la solicitud original y aplica esa elección
al borrador; no debería volver a pedir el mismo campo. Si falta el año se usa el
actual de Caracas; los datos de mes/día ausentes o contradictorios requieren aclaración.

Comprueba que `/help` o `/list --all` no pierden la selección, que una propuesta
sigue necesitando `/confirm` y que `/cancel` permite empezar una solicitud distinta
sin heredar el área. No se corrigen localmente negaciones, áreas mezcladas ni
`uiniversidad`. Si el modelo insiste en pedir el área resuelta o contradice la
selección, aparecerá `clarification_conflict`; no hay reintentos ni guardado implícito.

### Conservar un compromiso nuevo entre turnos

En una base sintética, comienza con:

```text
Hola viernes, tenemos un conversatorio para el jueves 19 de noviembre, sobre sistemas digitales 3 el tema 1
```

Si solicita el área, responde `Universidad`. El año omitido usa el actual de
Caracas; aclara una fecha contradictoria solo si hace falta. Debe proponer crear el evento conservando
sus detalles, no consultar registros existentes ni pedir sus IDs o alcance del
historial. Una explicación como `No entiendo eso` no debe descartar el borrador.
Una deriva de operación produce `intent_conflict`, sin reintentos. No se guarda
nada antes de `/confirm`; `/cancel` abandona la captura.

Si la primera respuesta del modelo declara creación pero devuelve texto de
conversación, la aplicación presenta una aclaración fija y conserva solo los
campos validados del borrador. No muestra afirmaciones del modelo de haber
guardado el evento ni inventa una fecha.

La eliminación no está implementada. Una solicitud interpretada como eliminación
recibe un aviso de operación no disponible, no una pregunta de ID ni una afirmación
de haber eliminado datos. Estas son expectativas de aceptación, no una afirmación
de éxito con el modelo real; registra los turnos y fallos observados por separado
de los resultados de pruebas simuladas.

### Reloj de Caracas y herramientas de fechas

Cada turno proporciona fecha y hora de Venezuela (`America/Caracas`). Una fecha
como `19 de septiembre` usa el año actual de Caracas sin pedirlo solo porque se
omitió, incluso si septiembre ya pasó. La propuesta sigue requiriendo revisión
y el comando exacto `/confirm`.

En una captura sintética nueva, prueba `Informe de universidad para dentro de 3 dias`.
La fecha esperada es tres días de calendario después de la fecha de referencia,
calculada por `resolve_date` cuando el modelo selecciona esa herramienta de solo
lectura. El próximo día de la semana es estrictamente posterior a hoy. Para
`el jueves que viene 19 de septiembre`, una contradicción debe mostrar ambas
fechas calculadas y preguntar cuál usar.

El registro privado solo expone fechas; no concede acceso a terminal, red ni
escrituras. Un turno puede usar hasta dos solicitudes de herramientas y tres
peticiones al modelo, por lo que las pruebas reales necesitan un presupuesto
explícito suficiente. La selección de herramienta y la extracción de la frase
siguen dependiendo del modelo. Esta extensión tiene pruebas deterministas; la
captura real exitosa anterior no equivale a una prueba real de herramientas.
Después de resolver una fecha de creación, la continuación debe avanzar la
creación o preguntar por campos realmente ausentes, no afirmar que el evento ya
está guardado. Su esquema excluye respuestas conversacionales y preguntas
repetidas sobre la fecha; una salida inválida se rechaza en vez de convertirse
en una pregunta genérica de crear/consultar. Las preguntas generales sobre la
fecha pueden seguir recibiendo respuestas normales de IA.

Para la captura entre turnos reportada, reinicia la sesión aislada para cargar
el código nuevo y usa esta secuencia exacta:

```text
Tengo que entregar el informe del laboratorio de instrumentacion industrial el proximo sabado
universidad
```

Se espera una resolución de fecha y una propuesta sin guardar después de elegir
el área, no otra pregunta de operación o fecha. Con referencia de Caracas del
15 de noviembre de 2026, la fecha es el 21 de noviembre de 2026. La solicitud de
herramienta de creación ahora conserva el título; una respuesta de área con el
borrador completo se procesa localmente, sin otra inferencia. Detén la prueba en
el primer error y repórtalo. Es una candidata probada, no una garantía general de
estabilidad con el modelo real. No sigas respondiendo preguntas repetidas.

## 6. Diagnósticos y problemas frecuentes

Después de salir de Viernes, revisa el archivo del ayudante:

```bash
tail -n 20 "$VIERNES_MANUAL_DIR/diagnostics.jsonl"
```

| Campo | Interpretación |
| --- | --- |
| `route` | `command`, `fast_path` o `interpreter` |
| `outcome` | Acción/resultado; `create` es una propuesta y `confirm` una confirmación |
| `error_code` | Por ejemplo `clarification_conflict`, `generation_limit`, `invalid_json`, `invalid_structure`, `invalid_fields`, `connection`, `timeout` |
| `filter_scope`, `filter_area`, `count` | Alcance real consultado; `count: 0` no es un error |
| `duration_ms` | Duración observada; no un objetivo de rendimiento |
| `parse_stage`, `content_type`, `content_length` | Metadatos de parseo, no el texto del modelo |

Una interacción con IA puede producir una línea de parseo y otra de `respond`;
**más líneas no significa más inferencias**. Los eventos de la aplicación no
incluyen prompts, títulos, respuestas ni cuerpos HTTP. El archivo captura stderr,
por lo que un fallo de arranque de Python también puede producir texto no JSON.
Revísalo antes de compartirlo.

| Síntoma | Comprobación o acción |
| --- | --- |
| `ModuleNotFoundError: requests` | Activa el entorno correcto; instala con `python -m pip`, no con otro intérprete |
| No aparece el prompt después de configurar | Revisa mensajes de arranque y dependencias; comprueba que estás en la raíz |
| Ollama/modelo no disponible | Revisa `ollama ls` contra `127.0.0.1:11434`; conserva los comandos sin IA y reinicia Viernes tras corregirlo |
| Se recuerda `/confirm` | Hay una propuesta pendiente; revisarla y confirmar o cancelar |
| No aparece algo que ya completaste | Consulta `/list --all`; puede quedar fuera del alcance habitual |
| Datos distintos al reiniciar | Compara la ruta `Test database:`; una carpeta nueva es otra base |
| El ayudante rechaza la ruta | Ejecuta el paso 2; no apuntes el ayudante a una base personal o a un enlace hacia ella |
| Error de JSON/fecha/área | Usa comillas dobles, `null`, áreas exactas y fechas reales ISO |
| La IA tarda o responde mal | Anota entrada sintética, resultado y diagnóstico; no repitas peticiones en bucle. Ctrl+C cierra Viernes, no el servicio Ollama |

La conexión del intérprete usa timeouts de 3 segundos para conexión y 90 para
lectura; no constituyen una garantía de duración total. No atribuyas todos los
errores `invalid_json` a una causa específica sin evidencia.

## 7. Referencia técnica y uso habitual

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | Selección `--planner`/`--diagnostics` frente al asistente anterior |
| `core/planner.py` | Bucle, propuestas, confirmación, conversación y petición estructurada a Ollama |
| `core/commitments.py` | Validación, SQLite y consultas por área/fecha |
| `core/queries.py` | Atajos locales y tolerancia limitada a errores en nombres de tareas |
| `core/presentation.py` | Mensajes bilingües y presentación, sin traducir registros |
| `core/ollama_runtime.py` | Disponibilidad local, modelo y autoarranque opcional acotado |
| `core/diagnostics.py` | Eventos con campos permitidos y metadatos sin contenido privado |
| `config.py` | Carga de `.env` y valores de configuración; puede sobrescribir variables de la terminal |

Flujo: entrada → comando/atajo local o intérprete Ollama → validación → propuesta
o lectura/respuesta general. **Solo `/confirm` aplica la propuesta en SQLite.**
El modelo no escribe directamente en la base ni ejecuta herramientas del sistema.
El chat general conserva como máximo tres pares y 4000 caracteres en memoria;
desaparece al salir y no recibe automáticamente todos los registros guardados.

### Arranque normal: no es la base temporal protegida

Cuando decidas utilizar datos reales y hayas revisado tu configuración:

```bash
python main.py --planner
```

Para diagnósticos normales: `python main.py --planner --diagnostics`.
`--diagnostics` sin `--planner` devuelve un error. El ayudante anterior no es
necesario en el uso habitual: se utiliza aquí para proteger tus pruebas.

| Variable | Valor habitual / efecto |
| --- | --- |
| `OLLAMA_URL` | HTTP local en puerto `11434`; no se admiten endpoints remotos en el organizador |
| `OLLAMA_MODEL` | `qwen3.5:9b` por defecto; debe estar instalado |
| `VIERNES_DB_PATH` | Ruta elegida; por defecto `$XDG_DATA_HOME/viernes/commitments.sqlite3` o `~/.local/share/viernes/commitments.sqlite3` |
| `VIERNES_OLLAMA_AUTOSTART` | `false` por defecto; `true` permite intentar iniciar `ollama serve` |
| `VIERNES_OLLAMA_STARTUP_TIMEOUT` | `10` por defecto; ventana de disponibilidad entre 0 y 120 segundos, con tiempo adicional de sondeo/limpieza |

El autoarranque no instala Ollama ni descarga modelos; un servidor que arrancó
correctamente puede seguir activo después de salir. El ayudante de prueba lo
desactiva expresamente. La base almacena títulos y texto de origen: es privada,
no está cifrada ni sincronizada con una nube. Conserva respaldos antes de trabajar
con datos importantes. `python main.py` sin `--planner` ejecuta el asistente
anterior, con otras dependencias y herramientas; no es el modo de esta prueba.

### Inspección de SQLite: opcional y solo de lectura

Sal primero de Viernes. Este comando no crea una base vacía si la ruta es incorrecta:

```bash
python -c '
import sqlite3
import sys
from pathlib import Path
uri = Path(sys.argv[1]).resolve().as_uri() + "?mode=ro"
connection = sqlite3.connect(uri, uri=True)
try:
    for row in connection.execute("SELECT id, title, area, project, due_date, status FROM commitments ORDER BY id"):
        print(row)
finally:
    connection.close()
' "$VIERNES_MANUAL_DB"
```

No hace falta instalar el ejecutable `sqlite3` para esta comprobación. No utilices
SQL de escritura para saltar las reglas de confirmación de la aplicación.

## 8. Pruebas automáticas y registro de resultados

La [guía del organizador](../../PLANNER.md#verify-without-running-models-or-desktop-tools)
contiene la suite explícita de unidades. La referencia histórica de entrega fue
190 pruebas; la suite dirigida de herramientas de fechas pasó **221 pruebas en
una copia aislada**, sin las pruebas heredadas de configuración, voz y sistema.
El número puede variar con cambios locales. No ejecutes
`tests/test_conectividad.py` ni un descubrimiento indiscriminado para esta rutina:
las pruebas de conectividad utilizan servicios/audio reales.

Los ejecutores `tools.evaluate_interpreter` y `tools.rescore_interpreter` son
herramientas separadas, no pasos obligatorios de esta guía. Una evaluación real
puede consumir hasta 60 intentos/900 segundos y necesita un presupuesto deliberado.
No vuelvas a generar los archivos históricos `local-baseline*.json`.
Consulta [la documentación de evaluación](../../evaluations/README.md).

| Caso | Entrada | Esperado | Observado | Diagnóstico / tiempo |
| --- | --- | --- | --- | --- |
| A–G / IA | Solo datos ficticios | Estado/área/fecha, sin exigir prosa exacta | Completar manualmente | Ruta, código de error y duración |

Antes de avanzar a otra interfaz, comprueba:

- [ ] Crear/editar/completar requiere `/confirm`.
- [ ] Cancelar, rechazar y salir sin confirmar no cambia los datos guardados.
- [ ] Reiniciar con la misma ruta conserva lo confirmado.
- [ ] `--all` explica las diferencias frente al alcance normal.
- [ ] Consultas de trabajo no muestran registros de universidad.
- [ ] La conversación general no crea tareas ni sustituye una consulta fallida.
- [ ] Los fallos de IA quedan registrados por separado de las pruebas deterministas.

Referencias externas de Ollama: [CLI](https://github.com/ollama/ollama/blob/main/docs/cli.mdx)
y [API local](https://github.com/ollama/ollama/blob/main/docs/api.md).

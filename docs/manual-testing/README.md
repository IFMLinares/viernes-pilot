# Test Viernes manually

[English](README.md) | [Español](README.es.md)

Startup, testing, and troubleshooting for the **text planner**. First verify
storage and confirmations without generating AI responses; then optionally test
interpretation with Ollama. Use synthetic data only.

## Quick path

1. Open Bash in the repository root and activate Python: [setup](#1-prepare-python).
2. Create a temporary directory and define the protected launcher: [isolation](#2-create-an-isolated-test-environment).
3. Run `viernes_manual` and follow the [deterministic walkthrough](#3-step-by-step-deterministic-test).
4. Check restart persistence, then optionally test [Ollama](#5-optional-ollama-tests).
5. If something fails, see [diagnostics](#6-diagnostics-and-troubleshooting).

Run `bash` commands in the **system terminal**. Run `text` commands starting with
`/` **inside Viernes**, at `you:` or `tú:`. Use `/quit` to return to the terminal.

### Scope

| Included | Outside this guide |
| --- | --- |
| Create, confirm, list, edit, and complete commitments | Voice, Whisper, Piper, desktop actions |
| Areas, dates, persistence, and language | Jira, Engram, cross-project memory |
| Local queries and Ollama conversation | Web, phone access, synchronization, cloud |

The planner does not require OpenCode, Gentle AI, or a ChatGPT subscription.
The development environment's Sol/Luna models are separate from Viernes's local model.

## 1. Prepare Python

This recipe targets Bash on Linux or WSL. Work in the directory containing
`main.py`, `config.py`, and `core/`.

```bash
pwd
python3 --version
```

The project specifies Python 3.12 or newer. If the project environment already exists:

```bash
source .venv/bin/activate
```

For a separate test environment, create one outside the repository:

```bash
python3 -m venv "$HOME/.local/share/venvs/viernes-manual"
source "$HOME/.local/share/venvs/viernes-manual/bin/activate"
python -m pip install 'requests==2.34.2'
```

Activate an existing environment instead of recreating it; do not use `--clear`.
Installing `requests` downloads Python packages, not models. The version matches
`requirements.txt`. The protected recipe below imports only the planner: it needs
`requests` and the standard library, including SQLite, not `faster-whisper` or
embeddings. See the [main README](../../README.md) for the complete legacy installation.

```bash
python --version
python -m pip --version
python -c 'import requests, sqlite3; print("Planner dependencies available")'
```

## 2. Create an isolated test environment

The normal database contains personal data. Also, `config.py` loads `.env` by
overwriting terminal environment variables. **Exporting only `VIERNES_DB_PATH`
does not guarantee isolation** if `.env` defines the same variable.

This recipe sets the database **after** loading configuration and accepts only
this guide's temporary workspace. It does not modify `.env`, `config.py`, or your data.

```bash
export VIERNES_MANUAL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/viernes-manual.XXXXXX")"
export VIERNES_MANUAL_DB="$VIERNES_MANUAL_DIR/commitments.sqlite3"
printf 'Test directory: %s\n' "$VIERNES_MANUAL_DIR"
```

The directory is created under `TMPDIR`, or `/tmp` if unset. Copy this entire
function into the same terminal:

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

`viernes_manual` is a **helper for this terminal**, not a new application command;
it takes no arguments.
It calls the same `core.planner.main` as `--planner`, keeps stdin available through
`python -c`, disables autostart, and writes diagnostics into the temporary directory.
It does not change configuration for the next process.

Check that `Test database:` points to the directory you just created. If Ollama
is unavailable, a notice appears and explicit commands remain usable. Startup may
probe local server/model availability; this first test **does not generate inference**.
Do not stop an existing server for this test.

Keep this terminal and the printed path: choosing a new directory opens another
database. `/tmp` may be cleaned at reboot; do not use this temporary storage for real commitments.

## 3. Step-by-step deterministic test

Start with a fresh directory. The first saved ID will normally be `1`; substitute
the actual displayed ID for `1` below if it differs. Messages may initially be in
English or Spanish depending on the operating-system language.

### A. Help and an empty database

```text
/help
/list --all
```

Expected: help and no saved commitments. `/list` is not a Bash command.

### B. Proposal, confirmation, and empty input

```text
/new {"title":"MANUAL - Informe de prueba","area":"university","project":"manual-test","due_date":"2099-12-31"}
/help
/list --all
sí
```

Expected: a proposal marked not yet saved; the list remains empty. `sí` does not
save: the application asks for `/confirm` or `/cancel`. Press Enter on an empty
line: it must not save, cancel, or activate a microphone.

```text
/confirm
/list university --all
```

Expected: one persisted record with the requested title, area, project, and date.
Record its ID. The distant date keeps this example independent of the test day.

### C. Cancel creation

```text
/new {"title":"MANUAL - No guardar","area":"work"}
/cancel
/list work --all
```

Expected: no work records. The university record must still exist.

### D. Edit without automatically saving

```text
/edit 1 {"title":"MANUAL - Informe actualizado","due_date":"2099-12-30"}
/list university --all
/confirm
/list university --all
```

Expected: before confirmation, listing keeps the previous values; afterward, it
shows the changed title and date. Listing does not confirm a proposal.

### E. Clear the deadline and complete

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

Expected: `null` removes the date. An undated pending record appears in the normal
list; `/done` only proposes completion. After `/confirm`, it is completed.
An **undated completed record is excluded from the normal list**, but remains
in `/list university --all`: it was not deleted.

### F. Reject invalid input

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

Expected: invalid JSON/fields/ID/option produce errors, with no valid proposal to
confirm; the university record is still the only saved record. `--pending` is
not implemented. Errors must not turn into general AI replies or writes.

### G. Persistence and exiting with a pending proposal

```text
/new {"title":"MANUAL - Descartar al salir","area":"personal"}
/quit
```

Back in Bash, run again **without recreating the variables or directory**:

```bash
viernes_manual
```

```text
/list university --all
/list personal --all
```

Expected: the completed university record persists; the personal record was never
saved. Ctrl+C and EOF (Ctrl+D in Bash) also exit. Exiting neither removes confirmed
records nor automatically stops Ollama.

## 4. Command reference and query scope

| Inside Viernes | Effect | Needs AI? |
| --- | --- | --- |
| `/help` | Shows help; available with a pending proposal | No |
| `/new {"title":"…","area":"personal"}` | Proposes creation; title and area are required | No |
| `/list` | Reads all areas within the normal scope | No |
| `/list work` | Filters by area | No |
| `/list --all` / `/list work --all` | Includes full history, pending and completed | No |
| `/edit ID {"project":"demo"}` | Proposes partial field changes | No |
| `/done ID` | Proposes completion | No |
| `/confirm` | Applies exactly the pending proposal | No |
| `/cancel` | Discards proposal and clarification context | No |
| `/quit` | Exits, discarding unconfirmed work | No |

- Exact areas: `university`, `work`, `personal`; do not translate JSON tokens.
- Create/edit fields: `title`, `area`, `project`, `due_date`; dates use ISO
  `YYYY-MM-DD`. `project` and `due_date` are optional; `null` can remove a deadline.
- Stored titles are not translated when conversation language changes.
- IDs are existing positive integers. Stored statuses are `pending` and
  `completed`; `status` is not an editable `/edit` field.
- Normal scope: dated records from seven days ago inclusive and all future dates,
  plus older overdue pending and undated pending records in separate sections.
  This is not a pending-only filter.
- Weeks run Monday–Sunday; months use actual calendar boundaries. Explicit ranges
  exclude out-of-period records, including undated records.
- No `/delete`, `/reset`, `/undo`, or reopen-completed command exists. Do not write
  SQL directly to simulate unsupported application commands.
- To start over, exit and create **another temporary directory** using step 2;
  do not delete or replace the real database.

These clear requests also use local recognition without generating AI text:

```text
Show all my university commitments.
muestrame mis comprimisos del trabajo
Muéstrame mis compromisos de esta semana.
```

After the walkthrough: the first includes the completed record; work is empty;
the week excludes the undated completed record. Diagnostics should show `fast_path`.
Other wording may require the model: not every phrase is a shortcut.

## 5. Optional Ollama tests

These tests consume local inference resources and are not needed to verify SQLite.
The helper uses `qwen3.5:9b`, which must already be installed; there is no automatic
download. If it is missing, choose/install a compatible model separately and adapt
the helper's `config.OLLAMA_MODEL` line.

### Prepare the server

In another terminal, check the local server and its models:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama ls
```

If the server is not running, you can start it in that terminal:

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

Keep that terminal open and repeat `ollama ls` in another. If the address is already
in use, inspect the existing server; do not kill processes or change services.
Do not use `ollama run` as a Viernes test: it is a separate conversation and can
download a missing model. Optionally inspect the API without generating text:

```bash
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:11434/api/tags
```

Exit Viernes with `/quit` and run `viernes_manual` again in the original terminal.
If it opened without an available model, restart it to enable interpretation;
starting Ollama later does not automatically update the existing session.

### AI cases: expectations, not guarantees

| Enter inside Viernes | Intended result | What to record if it fails |
| --- | --- | --- |
| `Tengo que entregar MANUAL - Informe del trabajo el 31 de diciembre de 2099.` | Work proposal dated `2099-12-31`; nothing saved yet | Invented area/date or a general reply instead of a proposal |
| `/cancel` | Discards the previous proposal | Do not confirm an incorrect proposal |
| `Tengo un parcial el 23.` | Clarifies the missing month; an omitted year uses the current Caracas year | Interpretation can fail; cancel unrequested fields |
| `/cancel` | Clears clarification before another case | The next case starts without that clarification |
| `¿Qué es una derivada?` | Reply labeled as general information, not a commitment lookup | Parse error or incorrect action; do not require exact prose |
| `¿Puedes dar un ejemplo?` | Follow-up using bounded session context | Irrelevance or lost context |
| `Explain the difference between a task and an event.` | General reply in English | Incorrect language or an unexpected write |
| `/list --all` | Same confirmed data if all proposals were cancelled | Explanations must not create commitments |

A failure here does not prove a SQLite failure. A general-information label also
does not guarantee that the model avoids invented facts. Use lists to check stored
data. The historical measurement was partial; unit tests do not guarantee
Ollama's real accuracy or speed.

The shared structured request now uses `think: false`, including general replies.
If the model again reaches its length limit without final content, a specific
message and `generation_limit` code appear without saving or retrying. Restart
Viernes to load code changes; keep the same test database path.

### Continuing an area clarification

If Viernes asks for the area, answer `university`, `work`, or `personal`. It also
recognizes Spanish labels, uppercase input, `UNIVERSIDAD!`, and
`Del área de la universidad`. It retains the original request and applies that
choice to the draft; it should not request the same field again. A missing year
uses the current Caracas year; missing or conflicting month/day details still need clarification.

Check that `/help` or `/list --all` preserves the selection, a proposal still needs
`/confirm`, and `/cancel` starts a different request without inheriting the area.
Negative, mixed, and misspelled labels such as `uiniversidad` are not guessed
locally. If the model still asks for the resolved area or contradicts it,
`clarification_conflict` appears without retries or implicit saves.

### Preserving a new commitment across turns

In a synthetic database, start with:

```text
Hola viernes, tenemos un conversatorio para el jueves 19 de noviembre, sobre sistemas digitales 3 el tema 1
```

Answer a requested area with `Universidad`. The omitted year uses the current
Caracas year; clarify a conflicting date only if needed. Expect a create proposal retaining the event details,
not a query about existing records or a request for their IDs/history scope.
An explanation such as `No entiendo eso` must not discard the draft. Operation
drift produces `intent_conflict` without retries. Nothing is saved before
`/confirm`; `/cancel` abandons the capture.

If the first model response declares creation but returns reply prose, the
application asks a fixed clarification and retains only validated draft fields.
It does not show a model claim that the event was already saved or invent a date.

Deletion is not implemented. A request interpreted as deletion receives an
unsupported-operation notice, not an ID question or a claim of deletion.
These are acceptance expectations, not a claim of real-model success; record
the actual turns and failures separately from mocked test results.

### Caracas clock and date tools

Each turn supplies Venezuela date/time (`America/Caracas`). A date such as
`19 de septiembre` uses the current Caracas year without asking for it merely
because it was omitted, even if September has already passed. A proposal still
requires review and exact `/confirm`.

In a fresh synthetic capture, try `Informe de universidad para dentro de 3 dias`.
The expected deadline is three calendar days after the displayed reference date,
calculated by the read-only `resolve_date` tool when the model selects it. Next
weekday is strictly after today. For `el jueves que viene 19 de septiembre`, any
contradiction should show both computed dates and ask which one to use.

The private tool registry currently exposes only dates; it grants no terminal,
network or write access. One turn can use up to two tool requests and three model
requests, so real tests need an explicit sufficient call budget. Tool selection
and phrase extraction still depend on the model. This extension has deterministic
tests; do not treat the earlier successful live capture as a live test of tools.
After a tool resolves a creation deadline, the continuation must advance creation
or ask for genuinely missing fields, not claim the event is saved. Its schema
excludes conversational replies and repeat date questions; invalid model output
is rejected rather than turned into a generic create/list question. General
questions about the date may still receive normal AI replies.

For the reported cross-turn capture, restart the isolated session to load the
new code and use this exact sequence:

```text
Tengo que entregar el informe del laboratorio de instrumentacion industrial el proximo sabado
universidad
```

Expect one date resolution followed by an unsaved proposal after selecting the
area, not another operation/date question. At a Caracas reference of November 15,
2026, the deadline is November 21, 2026. The create-tool request now retains the
task title; a complete area answer is handled locally without another inference.
Stop at the first error and report it. This is a tested candidate, not a blanket
claim of real-model stability. Do not keep answering repeated questions.

## 6. Diagnostics and troubleshooting

After exiting Viernes, inspect the helper's log:

```bash
tail -n 20 "$VIERNES_MANUAL_DIR/diagnostics.jsonl"
```

| Field | Meaning |
| --- | --- |
| `route` | `command`, `fast_path`, or `interpreter` |
| `outcome` | Action/result; `create` is a proposal, `confirm` is confirmation |
| `error_code` | For example `clarification_conflict`, `generation_limit`, `invalid_json`, `invalid_structure`, `invalid_fields`, `connection`, `timeout` |
| `filter_scope`, `filter_area`, `count` | Actual query scope; `count: 0` is not an error |
| `duration_ms` | Observed duration, not a performance target |
| `parse_stage`, `content_type`, `content_length` | Parsing metadata, not model text |

An AI interaction can emit both a parse line and a `respond` line; **more log lines
do not imply more inference calls**. Application events omit prompts, titles,
answers, and HTTP bodies. The file captures stderr, so Python startup failures can
also produce non-JSON text. Inspect it before sharing.

| Symptom | Check or action |
| --- | --- |
| `ModuleNotFoundError: requests` | Activate the correct environment; install with the matching `python -m pip` |
| No prompt after setup | Inspect startup messages/dependencies and confirm the repository root |
| Ollama/model unavailable | Check `ollama ls` against `127.0.0.1:11434`; keep using non-AI commands and restart Viernes after fixing it |
| Repeated `/confirm` reminder | A proposal is pending; inspect, confirm, or cancel it |
| A completed record is missing | Use `/list --all`; it may be outside normal scope |
| Different data after restart | Compare `Test database:` paths; a new directory is another database |
| Helper rejects the path | Run step 2; never point it to a personal database or a symlink to one |
| Invalid JSON/date/area | Use double quotes, `null`, exact area tokens, and real ISO dates |
| Slow or incorrect AI | Record synthetic input, result, and diagnostics; do not retry in a loop. Ctrl+C exits Viernes, not the Ollama service |

Interpreter timeouts are 3 seconds for connection and 90 for reading, not a
guaranteed total duration. Do not attribute every `invalid_json` error to a specific
cause without evidence.

## 7. Technical reference and normal use

| File | Responsibility |
| --- | --- |
| `main.py` | Selects `--planner`/`--diagnostics` versus the legacy assistant |
| `core/planner.py` | Loop, proposals, confirmation, conversation, structured Ollama request |
| `core/commitments.py` | Validation, SQLite, area/date queries |
| `core/queries.py` | Local shortcuts and limited task-noun typo tolerance |
| `core/presentation.py` | Bilingual messages/display, without translating stored records |
| `core/ollama_runtime.py` | Local readiness/model checks and bounded optional autostart |
| `core/diagnostics.py` | Allowlisted events and metadata without private content |
| `config.py` | `.env` loading/configuration; may overwrite terminal variables |

Flow: input → local command/shortcut or Ollama interpretation → validation →
proposal, lookup, or general reply. **Only `/confirm` applies a proposal to SQLite.**
The model does not write the database directly or execute system tools. General
chat retains at most three pairs/4000 characters in memory; it disappears on exit
and does not automatically receive all stored records.

### Normal startup is not the protected temporary database

When you decide to use real data and have reviewed configuration:

```bash
python main.py --planner
```

For normal diagnostics: `python main.py --planner --diagnostics`.
`--diagnostics` without `--planner` returns an error. The helper above is not needed
for normal use; it exists here to protect manual tests.

| Variable | Usual value/effect |
| --- | --- |
| `OLLAMA_URL` | Local HTTP on port `11434`; remote planner endpoints are unsupported |
| `OLLAMA_MODEL` | Defaults to `qwen3.5:9b`; must be installed |
| `VIERNES_DB_PATH` | Selected path; defaults to `$XDG_DATA_HOME/viernes/commitments.sqlite3` or `~/.local/share/viernes/commitments.sqlite3` |
| `VIERNES_OLLAMA_AUTOSTART` | Defaults to `false`; `true` allows attempting `ollama serve` |
| `VIERNES_OLLAMA_STARTUP_TIMEOUT` | Defaults to `10`; readiness window 0–120 seconds, plus probe/cleanup overhead |

Autostart does not install Ollama or download models; a successfully started server
can remain active after exit. The test helper explicitly disables it. The database
contains titles and original source text: it is private, unencrypted, and not
cloud-synchronized. Keep backups before using important data. `python main.py`
without `--planner` runs the legacy assistant with other dependencies/tools; it
is not this guide's test mode.

### Optional read-only SQLite inspection

Exit Viernes first. This command cannot create an empty database if the path is wrong:

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

The separate `sqlite3` executable is not required. Do not use SQL writes to bypass
the application's confirmation rules.

## 8. Automated checks and recording results

The [planner guide](../../PLANNER.md#verify-without-running-models-or-desktop-tools)
contains the explicit unit suite. The historical delivery reference was 190 tests;
the date-tool targeted suite passed **221 tests in an isolated copy**, excluding
legacy config/voice/system tests. Counts can differ with local changes. Do not run
`tests/test_conectividad.py` or indiscriminate discovery for this routine:
connectivity checks access real services/audio.

`tools.evaluate_interpreter` and `tools.rescore_interpreter` are separate tools,
not required steps here. A live evaluation can consume up to 60 attempts/900
seconds and needs a deliberate budget. Do not regenerate historical
`local-baseline*.json` files. See the [evaluation guide](../../evaluations/README.md).

| Case | Input | Expected | Observed | Diagnostics/time |
| --- | --- | --- | --- | --- |
| A–G / AI | Synthetic data only | State/area/date, not exact prose | Fill in manually | Route, error code, duration |

Before moving to another interface, check:

- [ ] Creating/editing/completing requires `/confirm`.
- [ ] Cancelling, rejecting, or exiting unconfirmed does not change saved data.
- [ ] Restarting with the same path preserves confirmed records.
- [ ] `--all` explains differences from normal scope.
- [ ] Work queries do not show university records.
- [ ] General conversation creates no tasks and does not replace a failed query.
- [ ] AI failures are recorded separately from deterministic checks.

External Ollama references: [CLI](https://github.com/ollama/ollama/blob/main/docs/cli.mdx)
and [local API](https://github.com/ollama/ollama/blob/main/docs/api.md).

# Use Viernes to track personal commitments

The opt-in planner supports general conversation alongside capturing, confirming,
listing, editing and completing university, work and personal commitments. It
uses SQLite for records and local Ollama for interpretation and general answers.
Obsidian versus a local web interface is still undecided; this terminal interface
validates the underlying workflow.

For an isolated, step-by-step walkthrough, see the
[manual testing guide](docs/manual-testing/README.md)
([Español](docs/manual-testing/README.es.md)).

## Quick start

Activate the existing virtual environment, then run:

```bash
python main.py --planner
```

When the configured local model is available, describe a commitment:

```text
Tengo que entregar el informe de física el 23 de noviembre de 2026.
```

Review the proposed fields, then type `/confirm` to save or `/cancel` to discard.
Missing or contradictory date details should trigger a clarification; an omitted
year uses the current Caracas year. Only the exact `/confirm`
command applies a displayed change; ordinary conversational agreement does not.
The model can still misunderstand a date or intent: review the proposal.

## General conversation

Ask questions directly, without changing mode:

```text
¿Qué es una derivada?
Explain the difference between a task and an event.
How can I prepare for an exam?
```

General answers are labeled **AI reply · General information (no commitment
lookup)**, or the Spanish equivalent. Ordinary replies use one structured Ollama
request, without a separate routing agent. A model-selected date tool can require
follow-up requests within the bounded loop described below. The reply action
cannot contain task-operation fields, create a proposal, confirm a change, call
OS tools or write Engram. Malformed interpreter output and failed queries remain
errors/clarifications; they are never automatically replaced with a chat answer.
Every public reply must contain exactly `action`, `language` (`en` or `es`) and `answer`;
missing or mixed fields are rejected before storing any session history.
The model's wire schema additionally carries operation intent and an optional
partial draft; the adapter removes these from public action/report dictionaries.

The shared structured request explicitly sets `think: false`, including for general
replies, to prioritize the final JSON answer over separate extended reasoning.
This can affect complex general-answer quality. The date-tool extension keeps the
configured model, context window and per-request transport timeout; it extends
the prompt and private wire schema and can make up to three requests per turn.
Historical baseline reports were captured before this setting and are not new
measurements of the current request configuration.

General replies are model knowledge/advice, not verified personal-data or current
web results. The prompt directs stored-commitment questions to query/clarification
actions, and supported local queries still bypass the model. However, model
intent classification and factual accuracy are fallible: a general-information
label is not proof that a statement about your records is true. Use `/list` for
a deterministic check and report any misrouted personal-data question.

Follow-up general questions receive limited session context: at most three
user/assistant pairs and 4000 characters total, trimmed as complete pairs. Each
retained user message is capped at 1000 characters and answer at 3000. Full
displayed answers are limited to 8000 characters. General history is not stored
in SQLite/Engram and disappears on exit. Query results and stored records are
not automatically inserted into this history. General conversation does not
become the source of a later task. During a declared commitment capture, replies
preserve its operation and draft; use `/cancel` to abandon it before switching
record operations. A pending proposal still requires `/confirm` or `/cancel` first.

## Conversation language and presentation

Write in English or Spanish. Ollama reports the message language in the same
structured interpretation request, and application replies follow that language.
Commands such as `/confirm`, `/list` and `/help` retain the current conversation
language; they are not translated. Stored titles, source text, area tokens and
dates are never translated or rewritten by the presentation layer.

Before the first message, the terminal uses `LC_ALL`, then `LC_MESSAGES`, then
`LANG` (Spanish for `es*`, otherwise English). If Ollama is unavailable or fails,
lightweight word hints select the language for clear messages; ambiguous input
keeps the previous language. This fallback is not a general language detector.
The model can also misidentify a language; language classification is not a
guarantee of interpretation accuracy. No extra AI request is made for translation.

Proposals, saved records and lists are displayed with readable labels and dates:

```text
Propuesta · Todavía no guardada
Crear
Informe de física
Área: Universidad
Fecha límite: 23 de noviembre de 2026
/confirm para guardar · /cancel para descartar
```

An edit proposal shows the resulting record; a completion proposal shows the
completed status before confirmation. Neither changes storage until `/confirm`.
Empty input is ignored, including while a proposal is pending. It neither saves
nor cancels the proposal. Validation, connection and storage errors use localized
application messages rather than raw internal exceptions.

## Commands, including offline use

```text
/new {"title":"Physics report","area":"university","due_date":"2026-11-23"}
/confirm
/list university
/list university --all
/edit 1 {"due_date":"2026-11-24"}
/confirm
/done 1
/confirm
/list
/help
/quit
```

Use the actual ID returned by your own `/list`, not necessarily `1`.
Areas are `university`, `work` and `personal`. `project` and `due_date` are
optional. A null date removes a deadline. Query results include pending and
completed records within the chosen date scope. Status-only filters, reminders,
calendar blocks and automatic scheduling are not implemented yet.

### Continuing an area clarification

While an area clarification is pending, clear English/Spanish answers such as
`Universidad`, `UNIVERSIDAD!`, `Del área de la universidad`, `university`, `trabajo`,
`work` and `personal` are normalized into an application-owned, session-only area.
Negative/mixed answers and fuzzy spellings such as `uiniversidad` are not locally
resolved. Original input and accepted
answers remain in the eventual confirmed record's source text, once per accepted turn.

The interpreter receives explicit continuation context. Once the area is selected,
the per-call clarification schema no longer permits asking for it again; answering
the area question is not treated as a new general-chat request. The global schema
and other Planner instances are unchanged. The selected area fills omitted areas
in create proposals and interpreted queries; contradictory create/query areas are
rejected, not silently overwritten. Existing edit fields are not changed by this selection.

`/help`, blank input and explicit `/list` commands preserve the unfinished capture.
`/cancel` and a completed proposal clear its area state. General replies and
independent local queries preserve an unfinished create/edit/complete capture.
Clear independent local queries keep their own area filters. If the
model ignores the continuation constraints, `clarification_conflict` explains that
the area is already selected; there is no automatic retry or invented next field.
Dates still require normal interpretation/validation, and nothing is written
until `/confirm`. The existing clarification bound also limits accepted sources.

### Preserving the operation and draft

Creating a new commitment cannot turn into a stored-record lookup during an
area/date clarification. The application retains validated partial fields and
rejects operation drift as `intent_conflict`, without querying or saving records.
Create clarifications cannot ask for an existing ID or history scope. Rejected
model output cannot replace retained draft fields. A reply explaining a question
does not discard the capture; `/cancel` explicitly abandons it.

If the first response declares create intent but supplies general-answer prose
instead of a create/clarify action, a well-formed reply is converted into a fixed
clarification. The application retains validated draft fields, asks for area only
when a title is present and area is absent, and otherwise requests clarification
of the request. It does not display that prose, infer missing fields, or propose a
write. Malformed replies still fail validation.

Deleting records is not implemented. An interpretation classified as unsupported
receives an application-owned notice, not an ID question or a deletion claim.
Intent classification is still model-dependent; these safeguards are not proof
that every real-model request will be interpreted correctly.

## Query scope and grounded answers

### Trusted clock and model-selected date tools

Every planner turn receives one trusted date/time snapshot in `America/Caracas`.
The interpreter, local query fast path and store query use that same local date.
No model call is needed to read the clock. A yearless calendar date means the
current Caracas year, even when already past; it never silently rolls forward.
"Next Thursday" means the next Thursday strictly after today, including a full
week later when today is Thursday.

The extensible registry in `core/planner_tools.py` initially exposes only the
read-only `resolve_date` tool. Its description and argument schema tell the model
when to request calendar, relative-day or next-weekday calculations. Python does
the calculation; multiple references to the same event are checked together.
Conflicts show the computed alternatives in a fixed localized question; invalid
calendar dates request clarification rather than rolling to another year.

Tool selection uses private structured JSON (`action=tool`, name and arguments),
not an assumed combination of Ollama native tool calls and `format`. The host
validates the registered name and arguments before execution, then supplies the
result for continuation. At most two tools and three model requests are allowed
per turn; exhaustion fails without retries or writes. Unknown tools and a final
deadline contradicting a computed date are rejected. Ordinary replies still
expose exactly three public keys. Tool requests/results are not source text,
public action metadata, or diagnostics payloads.
If an edit continuation omits the computed deadline, the host retains that
deadline alongside the other proposed fields rather than silently losing it.
After a tool declares a record operation, the next schema permits only that
operation, valid missing-field clarification, or another bounded tool request.
Conversational `reply`/`answer` and operation switches are excluded. A successfully
resolved date cannot be requested again in that continuation. The host also
validates these transitions: out-of-contract output fails without retries,
saved claims, or conversion into a generic operation question. General date
questions with reply intent still support ordinary three-field replies.

### Cross-turn capture candidate

Validated draft values, not only field names, are supplied to each continuation.
A create date-tool request must carry `draft.title` from the original task;
the private schema has separate final-action, create-tool and other-tool branches.
Incomplete create-tool requests are rejected before execution, not repeatedly
resolved while losing the task. This private grammar change still needs actual
model acceptance; passing mocked tests is not a guarantee of tool selection.

When a dated draft already has its title and the user answers the pending area
question, the application validates the complete draft and renders a proposal
locally. It does not invoke the model or date tool again. A genuine date change
can still be interpreted and resolved before the area answer. Generic create
clarifications ask for missing commitment details, never the known operation.
An initial reply claiming persistence cannot be promoted to a proposal.

Registry extensions are developer-owned Python `Tool` entries; each pure handler
must validate its own arguments. No dynamic imports, shell, database-write or
network tools are registered. Date extraction and tool selection remain model
decisions: deterministic tests do not prove that every real-model phrase calls
the tool correctly. Existing historical evaluation reports/corpus retain their
original year-required policy; they are not a new benchmark of this policy.

By default, `/list` and general natural-language queries retrieve dated records
from seven days before the Caracas current date (inclusive) onward, without a future
cutoff. Older overdue pending records and pending records without a deadline are
included in separate sections. Old completed records and completed records
without dates are excluded from that default, not deleted.

Use `/list --all`, `/list university --all`, or explicitly request full history to
include all dates and statuses. A model-proposed full-history query is not run
unless the user explicitly requests it. For explicit periods, dates are inclusive
and records outside the period (including undated records) are not included:

```text
Muéstrame mis compromisos de la universidad.
que compromisos tengo registrados?
Show my university commitments.
Show all my university commitments.
Muéstrame mis compromisos de esta semana.
Show my commitments this month.
Consulta del 1 al 30 de noviembre de 2026.
```

Clear supported general/week/month/history queries are handled locally without
calling the model, including offline. Weeks run Monday through Sunday; months
use actual calendar boundaries. Other phrasing and explicit custom date ranges
use structured interpretation and may require clarification. Unrecognized
modifiers are not discarded by the local recognizer. SQL applies date and area
filters before retrieving records; the planner does not load all history into
Python or send the database contents to the model for filtering.

The local recognizer tolerates one unambiguous insertion, deletion, substitution
or adjacent transposition in long task nouns (at least eight characters), such as
`comprimisos` for `compromisos`. It does not autocorrect areas, dates, negations,
history flags or short words, and never rewrites stored titles or source text.
Other unrecognized wording still goes to structured interpretation.

Every list states its area and date scope. An empty result means no records in
that scope, not necessarily no records anywhere. Only SQLite query results
determine empty-state messages. The model's clarification output is restricted
to a reason (`area`, `date`, `id`, `scope`, `request`); the application renders a
fixed localized question. Free-form model claims about stored data are never
displayed as clarifications.

All changes require confirmation. A pending proposal blocks new requests until
confirmed or cancelled, but `/list` and `/help` remain available. `/cancel` also
clears clarification context. Exiting discards unconfirmed proposals.

The planner has no Engram writes, arbitrary shell tools, audio initialization or
automatic model downloads. The older assistant remains available with
`python main.py`; it retains its existing behavior and permissions.

## Configuration

Set these environment variables before launching (existing configuration loading
also supports local environment-file values):

| Variable | Default | Meaning |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Only loopback HTTP on port 11434 is supported by the planner. No remote endpoint is probed. |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Must already be installed. No automatic download or update. |
| `VIERNES_DB_PATH` | `$XDG_DATA_HOME/viernes/commitments.sqlite3` | Database path; data home defaults to `~/.local/share`. |
| `VIERNES_OLLAMA_AUTOSTART` | `false` | Set exactly `true` to allow `ollama serve` when the local server is unavailable. |
| `VIERNES_OLLAMA_STARTUP_TIMEOUT` | `10` | Readiness polling window in seconds, from 0 to 120; a probe may add up to one second and child cleanup up to four seconds. |

For example, after installing Ollama and your chosen model yourself:

```bash
export VIERNES_OLLAMA_AUTOSTART=true
python main.py --planner
```

Existing environment-file values may override shell values under the legacy
configuration loader. This delivery does not change that loader.

A running server is reused. Startup uses a fixed argv (`ollama serve`), never
`sudo`, a shell string or system-service changes, and binds the child to the
configured loopback address. A successfully started server remains running after
the planner exits so other local clients can use it. On readiness timeout only
the child started by this invocation is terminated. Startup/inference failures
do not prevent deterministic commands from being used. Restart the planner after
fixing an unavailable server/model to enable natural-language input.

Records live outside the repository by default. They contain the original input
as source text; treat the database and backups as private. This first version
has no encryption or cloud synchronization. It does not read tasks into model
context automatically: for natural-language edits/completion, specify the ID
shown by `/list`.

## Diagnostics

Add `--diagnostics` to `--planner` to emit one JSON line per request to stderr
with bounded, non-private fields:

```bash
python main.py --planner --diagnostics 2> diagnostics.jsonl
```

Diagnostic events include route (`command`, `fast_path`, `interpreter`), outcome,
stage, stable error code, elapsed milliseconds and, for queries, validated
filters and row count. Error codes distinguish connection, timeout, invalid JSON,
invalid fields, invalid scope, invalid structure and storage issues. They never
contain raw prompts, general answers, stored records, exception bodies,
credentials or environment values. `--diagnostics` without `--planner` is rejected.

If Ollama ends with `done_reason: length` and empty final content, diagnostics
report `generation_limit` and the terminal explains the generation cutoff instead
of blaming the input. No changes are saved and no automatic retry is made.
Other malformed JSON keeps its existing `invalid_json` classification.

When diagnostics are enabled, the interpreter can also emit privacy-safe parse
metadata for the model response: parse stage (`envelope`/`content`), whether the
content field exists, its sanitized type/length/empty flag, JSON decode error
position, and known completion signals (`stop`, `length`, `tool_calls`). This
metadata is optional and depends on what the response envelope provides; it
cannot explain historical raw failures that were recorded before the metadata
was available. Parse metadata is attached to exceptions so error events include
safe context, but raw response bodies, message content and prompts are never
logged.

## Evaluate interpretation quality

Run the synthetic corpus against the local interpreter and/or full planner:

```bash
python -m tools.evaluate_interpreter \
  --url http://127.0.0.1:11434 --model qwen3.5:9b \
  --mode both --max-requests 60 --max-seconds 900 \
  --output evaluations/reports/new-baseline.json
```

See `evaluations/README.md` for the report schema and how to interpret results.
Choose an unused output path: the evaluator can overwrite an existing file.
The retained `local-baseline*.json` files are historical artifacts, not scratch output.

## Verify without running models or desktop tools

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_planner_capture tests.test_planner_tools tests.test_planner_tool_loop tests.test_planner_intent tests.test_planner_clarification tests.test_planner_generation tests.test_interpreter_evaluation tests.test_offline_evaluation tests.test_planner_diagnostics tests.test_planner_conversation tests.test_planner_queries tests.test_planner_presentation tests.test_commitments tests.test_ollama_runtime tests.test_planner_entrypoint tests.test_config tests.test_voice tests.test_sistema
```

Tests use isolated temporary databases and mocked HTTP/processes. Do not run
`tests/test_conectividad.py` as a unit test: it accesses real services/audio.

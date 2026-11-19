# Text planner CLI foundation

[English](README.md) | [Español](README.es.md)

This review boundary wires the historical planner engine into `main.py` without
copying later voice changes or model binaries. The legacy default entry is retained.
It is an experimental foundation, not the latest date-tool/conversation version.

```bash
python main.py --planner
```

Inside the planner, `/help` lists `/new`, `/list`, `/edit`, `/done`, `/confirm`,
`/cancel` and `/quit`. Changes are proposals until exact `/confirm`; `/cancel`
discards them. Offline explicit commands remain available when Ollama is unavailable.
Areas are `university`, `work`, and `personal`; deadlines use ISO dates in JSON commands.
For a pending proposal containing one new commitment, an explicit area correction
such as `the area is university, not personal` or
`El area es para la universidad, no personal` updates only its area and appends the
correction to its source. Review the revised proposal before exact `/confirm`.
Other requests remain blocked; multi-item and saved-record proposals are not
implicitly targeted by area corrections. Use `/edit ID` for saved records.
Cancellation discards the draft and its source. A reference to the cancelled draft
explains that it is unavailable and asks for the full request again; it never
restores or saves discarded contents.
Use only a fresh synthetic database for tests. Configuration may override the
database path through `.env`; do not assume a shell export alone isolates it.

```bash
python -B -m unittest tests.test_planner_entrypoint tests.test_commitments
```

Tests mock routing/model calls and use temporary storage. They do not prove real
conversational acceptance. Known defects remain in issues #3–#6. Bilingual UI,
scoped queries, general conversation, diagnostics and date tools follow separately.

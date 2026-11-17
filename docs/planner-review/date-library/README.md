# Pure clock and date library

[English](README.md) | [Español](README.es.md)

The pure registry initially exposes only resolve_date. It receives a trusted
America/Caracas instant, resolves calendar/relative-day/weekday references and
returns resolved, invalid or conflicting results. Omitted year means the current
Caracas year; next weekday is strictly future. It performs no model/storage/network
calls. The OS timezone database must include America/Caracas.

```bash
python -B -m unittest tests.test_planner_tools
```

Planner tool selection and capture integration follow in the next unit.

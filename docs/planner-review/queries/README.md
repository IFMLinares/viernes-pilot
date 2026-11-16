# Scoped grounded queries

[English](README.md) | [Español](README.es.md)

SQL applies area/date scope before retrieving records. Current scope includes
recent/upcoming dates, older overdue pending records and undated pending records.
Explicit full history includes all dates/statuses; ranges are inclusive. An empty
scope is not evidence that no records exist elsewhere. Query output comes from
storage, not a model claim. The date reference is injectable for deterministic tests.

```bash
python -B -m unittest tests.test_planner_queries tests.test_commitments
```

No live model or existing user database is required. Capture defects remain open.

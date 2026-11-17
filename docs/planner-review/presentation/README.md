# Bilingual terminal presentation

[English](README.md) | [Español](README.es.md)

This unit imports readable proposals, records, dates and English/Spanish UI.
Commands retain the conversation language; stored titles/source are not translated.
Only exact confirmation writes a proposal. Presentation is not proof that the
model selected correct fields or that a personal-data answer was grounded.

```bash
python -B -m unittest tests.test_planner_presentation tests.test_commitments
```

These are mocked/synthetic checks. Known capture and inference defects stay open.
Rollback is this unit's presentation, engine wiring, tests and guide delta.

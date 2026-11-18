# Bounded task-noun typo handling

[English](README.md) | [Español](README.es.md)

The local query recognizer tolerates one unambiguous edit in supported long task
nouns. It does not fuzzy-match areas, dates, negations or history modifiers, and
does not rewrite stored text. Unsupported wording returns to structured interpretation.

```bash
python -B -m unittest tests.test_planner_queries
```

This historical recognizer boundary does not fix unrelated capture or tool failures.

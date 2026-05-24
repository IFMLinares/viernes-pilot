# Tests Module

[English](#) | [Español](README.es.md)

The `tests` module provides validation scripts to ensure system tools, path mappings, and connectivity to local services are operating correctly.

## File Breakdown

### test_conectividad.py

This file performs integration checks to confirm local services are active and reachable.

- Verifies connection to the local **Ollama** API (port 11434) and checks model availability for `qwen3.5:9b` and `nomic-embed-text`.
- Verifies connection to the local **Engram** server (port 7437) and checks memory persistence.

### test_sistema.py

This file contains unit tests for the core utilities inside `tools/sistema.py`.

- **test_normalizacion_texto**: Validates cleaning rules for text input (accents, casing, special symbols).
- **test_buscar_coincidencias_exactas_y_fuzzy**: Simulates and asserts accurate resolution of friendly app queries (e.g. typos, substring queries, exact matches).
- **test_to_windows_path**: Assures relative and absolute WSL path mappings convert correctly to Windows UNC paths under WSL environments.

## Running the Tests

Ensure your virtual environment is active:
```bash
source .venv/bin/activate
```

To execute all tests in the suite:
```bash
python3 -m unittest discover -s tests
```

To run a specific test file:
```bash
python3 -m unittest tests/test_sistema.py
```

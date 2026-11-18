# Local Ollama runtime foundation

[English](README.md) | [Español](README.es.md)

This review unit adds `core.ollama_runtime.ensure_ollama` without changing the
legacy assistant or introducing the planner CLI yet. It is not a stability release.

- Only loopback HTTP on port 11434 is accepted; remote endpoints are not probed.
- Existing servers are reused. The selected model must already be installed.
- Autostart requires explicit `autostart=True`; it uses fixed `ollama serve` argv.
- Readiness waiting is bounded. Timeout cleanup targets only the child created
  by this invocation, never an existing shared server.
- No models, packages or services are installed or downloaded.

## Verification

```bash
python -B -m unittest tests.test_ollama_runtime
```

The tests mock HTTP/processes and exercise endpoint rejection, missing models,
disabled startup, reuse and owned-child cleanup. No live model call is required.
Rollback removes only this module, its tests and these two guides. See
[publication issue #7](https://github.com/IFMLinares/viernes-pilot/issues/7).

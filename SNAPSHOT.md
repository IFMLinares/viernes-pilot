# Experimental snapshot / Snapshot experimental

This branch preserves the later planner candidate for browsing and reproduction.
It is not a review unit, stable release, or replacement for the dependent PR chain
under [tracker #8](https://github.com/IFMLinares/viernes-pilot/pull/8).
Known failures [#3](https://github.com/IFMLinares/viernes-pilot/issues/3),
[#4](https://github.com/IFMLinares/viernes-pilot/issues/4),
[#5](https://github.com/IFMLinares/viernes-pilot/issues/5) and
[#6](https://github.com/IFMLinares/viernes-pilot/issues/6) remain open.

Esta rama conserva la candidata posterior para consulta y reproducción. No es una
unidad de revisión, versión estable ni reemplazo de la cadena bajo el PR #8.
Los fallos #3–#6 permanecen abiertos. No debe integrarse directamente en main.

Planner modules, tests and the synthetic corpus are copied from the development
candidate. Root startup retains the remote legacy body and imports only the
candidate's final planner/diagnostics dispatch. Voice changes, model binaries,
personal configuration, databases, private task logs and historical run reports
are excluded. Earlier foundation guides describe their own review boundaries.

Los módulos, pruebas y corpus sintético proceden de la candidata de desarrollo.
El arranque conserva el cuerpo anterior y solo incorpora el selector final del
planner/diagnósticos. Se excluyen voz, binarios, configuración personal, bases,
registros internos e informes históricos. Las guías base describen sus propios cortes.

Use [PLANNER.md](PLANNER.md) and the isolated
[manual guide](docs/manual-testing/README.md)
([Español](docs/manual-testing/README.es.md)). No new inference budget is granted
by this archive; mocked test success is not live conversational acceptance.

Consulta las guías antes de probar. Este archivo no concede presupuesto nuevo de
inferencia; los resultados simulados no equivalen a aceptación conversacional real.

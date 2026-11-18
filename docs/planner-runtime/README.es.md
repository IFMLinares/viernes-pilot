# Base de runtime local de Ollama

[English](README.md) | [Español](README.es.md)

Esta unidad agrega `core.ollama_runtime.ensure_ollama` sin cambiar el asistente
anterior ni introducir todavía el CLI del planner. No es una versión estable.

- Solo acepta HTTP de loopback en el puerto 11434; no consulta destinos remotos.
- Reutiliza servidores existentes. El modelo seleccionado debe estar instalado.
- El inicio requiere `autostart=True` explícito y argumentos fijos `ollama serve`.
- La espera está acotada. Al vencer, solo limpia el proceso creado por esta
  invocación, nunca un servidor compartido que ya existía.
- No instala ni descarga modelos, paquetes o servicios.

## Verificación

```bash
python -B -m unittest tests.test_ollama_runtime
```

Las pruebas simulan HTTP y procesos: destinos inválidos, modelos ausentes,
inicio deshabilitado, reutilización y limpieza propia. No requieren inferencias.
La reversión elimina solo este módulo, sus pruebas y estas dos guías. Consulta
la [issue de publicación #7](https://github.com/IFMLinares/viernes-pilot/issues/7).

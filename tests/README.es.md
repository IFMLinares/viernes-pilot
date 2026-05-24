# Módulo de Pruebas

[Español](#) | [English](README.md)

El módulo `tests` proporciona los scripts de validación necesarios para asegurar el correcto funcionamiento de las herramientas del sistema, el mapeo de rutas y la conectividad con los servicios locales.

## Desglose de Archivos

### test_conectividad.py

Este archivo realiza comprobaciones de integración para verificar que los servicios locales se encuentran activos y accesibles.

- Valida la conexión con la API de **Ollama** (puerto 11434) y comprueba la disponibilidad de los modelos `qwen3.5:9b` y `nomic-embed-text`.
- Valida la conexión con el servidor local de **Engram** (puerto 7437) y la persistencia de las observaciones en base de datos.

### test_sistema.py

Este archivo contiene las pruebas unitarias para las utilidades del núcleo en `tools/sistema.py`.

- **test_normalizacion_texto**: Valida las reglas de limpieza aplicadas al texto de entrada (eliminación de acentos, conversión de mayúsculas y caracteres especiales).
- **test_buscar_coincidencias_exactas_y_fuzzy**: Simula y comprueba la resolución correcta de nombres de aplicaciones en búsquedas aproximadas, parciales o exactas.
- **test_to_windows_path**: Asegura que las rutas relativas y absolutas de WSL se traduzcan correctamente a rutas UNC de Windows cuando se ejecuta dentro de entornos WSL.

## Ejecución de Pruebas

Asegúrate de tener activo tu entorno virtual:
```bash
source .venv/bin/activate
```

Para ejecutar todas las pruebas del proyecto:
```bash
python3 -m unittest discover -s tests
```

Para ejecutar un archivo de pruebas específico:
```bash
python3 -m unittest tests/test_sistema.py
```

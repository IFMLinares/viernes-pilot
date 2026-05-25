# Viernes Pilot

[Español](#) | [English](README.md)

Viernes Pilot es un asistente de desarrollo y orquestador de espacios de trabajo local y enfocado en la privacidad. Integra WSL con el sistema operativo Windows para automatizar la preparación de entornos de desarrollo, lanzar aplicaciones mediante búsqueda difusa (fuzzy-launch) y configurar pestañas interactivas de terminal.

## Requisitos Previos

- **Python**: Versión 3.12 o superior.
- **Ollama**: Ejecutándose localmente con un modelo que tenga soporte nativo de Tool Calling (ej. `qwen3.5:9b`, que fue el usado en desarrollo) y el modelo de embeddings `nomic-embed-text`.
- **Engram**: Activo en el puerto 7437 (base de datos vectorial local para la memoria).

## Instalación

No instales paquetes directamente en el Python del sistema. Se debe utilizar obligatoriamente un entorno virtual.

1. Clona el repositorio:
   ```bash
   git clone https://github.com/ifmlinares/viernes-pilot.git
   cd viernes-pilot
   ```

2. Crea un entorno virtual de Python:
   ```bash
   python3 -m venv .venv
   ```

3. Activa el entorno virtual:
   - **Linux / macOS / WSL**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows (Símbolo del sistema - CMD)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```

4. Instala las dependencias dentro del entorno activo:
   ```bash
   pip install -r requirements.txt
   ```

5. Configura las variables de entorno:
   Copia la plantilla de configuración `.env.example` como `.env` y personaliza los valores (como el nombre del modelo, la URL de Ollama o la de Engram):
   ```bash
   cp .env.example .env
   ```

## Ejecución

Asegúrate de que tu entorno virtual esté activo antes de iniciar la aplicación:

```bash
python3 main.py
```

## Documentación Modular

Para obtener información detallada sobre cada componente del sistema, consulta la documentación específica de cada módulo:

- **Módulo Core**: Detalles sobre el cliente de Ollama y la integración de memoria con Engram.
  - [Español](core/README.es.md) | [English](core/README.md)
- **Módulo de Herramientas**: Detalles sobre el lanzador difuso de aplicaciones y la integración de terminales.
  - [Español](tools/README.es.md) | [English](tools/README.md)
- **Módulo de Pruebas**: Instrucciones para ejecutar las pruebas unitarias y de conectividad.
  - [Español](tests/README.es.md) | [English](tests/README.md)

## Estándares del Proyecto

Para conocer las pautas de formato de documentación y estándares del código en este repositorio, consulta el [Estándar de Documentación](skills/documentacion.md).

## Licencia

Distribuido bajo la Licencia MIT. Consulta el archivo LICENSE para más detalles.

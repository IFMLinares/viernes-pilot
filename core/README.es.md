# Módulo Core

[Español](#) | [English](README.md)

El módulo `core` gestiona todas las comunicaciones con los servicios locales de inteligencia artificial y almacenamiento de memoria. Contiene los clientes principales para interactuar con Ollama y Engram.

## Desglose de Archivos

### brain.py

Este archivo sirve de interfaz para **Ollama**, comunicándose con la instancia local en el puerto 11434.

- **chat(model, messages, format, tools)**: Envía el historial de la conversación, el prompt del sistema y la lista de herramientas dinámicas a la API de chat de Ollama. La transmisión por flujo (stream) está desactivada para poder manejar las ejecuciones de herramientas de manera secuencial.
- **embed(model, text)**: Genera la representación vectorial de un texto dado utilizando el modelo de embeddings configurado (`nomic-embed-text` por defecto).

### memory.py

Este archivo gestiona la conexión con **Engram**, la base de datos vectorial de memoria a largo plazo que se ejecuta en el puerto 7437.

- **save(title, content, mem_type, topic_key)**: Guarda y persiste una observación, preferencia o detalle de configuración en la base de datos vectorial.
- **search(query, limit)**: Realiza una consulta semántica en Engram para recuperar los recuerdos guardados más relevantes.
- **search_expanded(query, limit)**: Mejora la búsqueda semántica estándar mediante consultas de respaldo con palabras individuales (excluyendo conectores y palabras vacías comunes en español). Devuelve una lista depurada y sin duplicados de los recuerdos relevantes.

## Flujo de Ejecución

1. El usuario introduce una consulta en `main.py`.
2. El sistema realiza una consulta en `memory.py` mediante `search_expanded`.
3. Las observaciones recuperadas se inyectan en el contexto del prompt del sistema en forma de bloque de "Memoria a largo plazo".
4. El prompt de sistema, el contexto, el historial y las herramientas disponibles se envían a `brain.py`.
5. Ollama procesa la información y decide si responder directamente al usuario o solicitar la ejecución de una herramienta en formato JSON.

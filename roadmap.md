# Viernes Pilot - Roadmap

Asistente de IA local, personal, no-code. Basado en Ollama + Engram.

---

## Estado Actual

- [x] Proyecto estructurado con entorno virtual (venv)
- [x] Ollama + qwen3.5:9b (o modelos compatibles con Tool Calling) funcionando
- [x] Engram conectado (proyecto: "viernes")
- [x] Tests de conectividad pasando y funcionando
- [x] Integración nativa de herramientas del sistema (WSL y Windows)
- [x] Configuración de control de versiones Git y acceso vía SSH
- [x] Estándar de documentación modular y bilingüe completo

---

## Fases

### Fase 1 - Fundación (Completado)
- [x] Estructura del proyecto
- [x] Tests de conectividad
- [x] main.py con REPL interactivo
- [x] Primera conversación funcional

### Fase 2 - Core Features (En Progreso)
- [x] Loop interactivo: entrada -> contexto -> respuesta
- [x] Soporte nativo para Tool Calling con Ollama y mapeo dinámico de funciones
- [x] tools/sistema.py: abrir aplicaciones (antigravity, opencode, etc.) en WSL y Windows
- [x] Integración de múltiples terminales (abrir_terminal) y compatibilidad con Windows Terminal y WSL-Terminal
- [x] Conversión dinámica de rutas (WSL a Windows UNC)
- [x] Notificaciones de escritorio (Toast en Windows/WSL y notify-send en Linux)
- [ ] tools/buscar.py: web scraping básico y búsqueda web minimalista
- [ ] Monitor: "avísame cuando termine X" (monitoreo asíncrono de procesos)

### Fase 3 - Inteligencia (Próximos Pasos)
- [ ] RAG mejorado (mejor segmentación / chunking y embeddings avanzados)
- [x] Contexto acumulativo (memoria de conversación a largo plazo con Engram)
- [ ] Macros de entorno y perfiles de espacio de trabajo configurables
- [ ] Herramientas de sistema adicionales (búsqueda rápida de archivos locales, control de energía, etc.)
- [x] Soporte de documentación bilingüe (ES/EN) de alta calidad

### Fase 4 - Voz (Futuro)
- [ ] Speech-to-text (STT) con Faster-Whisper local
- [ ] Text-to-speech (TTS) con Piper o Kokoro-82M local
- [ ] Modo hands-free y control por voz

---

## Comandos Principales

```bash
# Activar entorno virtual (Linux / WSL)
source .venv/bin/activate

# Correr tests de conectividad
python tests/test_conectividad.py

# Iniciar el asistente
python main.py
```

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| LLM | qwen3.5:9b u otros compatibles con Tool Calling nativo (Ollama) |
| Embeddings | nomic-embed-text (Ollama) |
| Memoria | Engram (localhost:7437) |
| Lenguaje | Python 3.12 |

---

## Ideas y Pautas de Desarrollo

### Tool Calling Nativo (Fase 2)
- Utilizar el soporte nativo de Tool Calling de Ollama. Pasar la descripción de las herramientas en formato JSON Schema para que el modelo elija cuándo llamar a funciones como abrir apps o buscar información.

### Monitoreo Asíncrono (Fase 2)
- Para comandos del tipo "Avísame cuando termine X", utilizar hilos (threading) o tareas asíncronas (asyncio) junto con psutil (o pgrep a través de subprocess) para monitorear el estado del proceso en segundo plano sin bloquear el REPL interactivo.
- Usar notify-send para notificaciones nativas en el sistema Linux, o llamadas Powershell a través de WSL para mostrar notificaciones flotantes (toast) en Windows.

### Web Scraping Inteligente (Fase 2)
- Empezar con un buscador simplificado y requests + BeautifulSoup para la extracción de texto simple en webs estáticas.
- Considerar Playwright (en modo headless) para el futuro si es necesario extraer información de sitios web dinámicos.

### Perfiles de Entorno y Orquestación (Fase 3)
- Implementar "comandos macro" o perfiles de espacio de trabajo que preparen entornos específicos. Por ejemplo, al decir "prepara el entorno de desarrollo", el asistente abrirá el editor en la carpeta correspondiente, levantará servicios locales, activará entornos virtuales y abrirá pestañas en el navegador.
- Los perfiles pueden guardarse en un archivo JSON o gestionarse de forma semántica a través de recuerdos persistentes en Engram.

### Voz Local (Fase 4)
- STT (Speech-to-Text): Implementar Faster-Whisper para transcripción rápida fuera de la nube.
- TTS (Text-to-Speech): Utilizar Piper o Kokoro-82M para síntesis de voz local de excelente calidad en español con bajo consumo de recursos.

---

*Última actualización: 2026-05-24*
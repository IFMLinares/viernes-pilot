# Viernes — Roadmap

> Asistente de IA local, personal, no-code. Basado en Ollama + Engram.

---

## Estado Actual

- ✅ Proyecto structurado con venv
- ✅ Ollama + qwen3.5:9b funcionando
- ✅ Engram conectado (project: "viernes")
- ✅ Tests de conectividad pasando

---

## Fases

### Fase 1 — Fundación *(hoy)*
- [x] Estructura del proyecto
- [x] Tests de conectividad
- [ ] **main.py con REPL interactivo** ← siguiente paso
- [ ] Primera conversación funcional

### Fase 2 — Core Features *(esta semana)*
- [ ] Loop interactivo: entrada → contexto → respuesta
- [ ] `tools/sistema.py`: abrir apps (antigravity, opencode, etc)
- [ ] `tools/buscar.py`: web scraping básico
- [ ] Monitor: "avisame cuando termine X"

### Fase 3 — Inteligencia *(próximo mes)*
- [ ] RAG mejorado (better embeddings, chunking)
- [ ] Contexto acumulativo (memoria de conversación)
- [ ] Más herramientas de sistema

### Fase 4 — Voz *(futuro)*
- [ ] Speech-to-text
- [ ] Text-to-speech
- [ ] Modo hands-free

---

## Comandos Principales

```bash
# Activar entorno
source .venv/bin/activate

# Correr tests
python tests/test_conectividad.py

# Próximo paso
python main.py
```

---

## Stack

| Componente | Tecnología |
|---|---|
| LLM | qwen3.5:9b (Ollama) |
| Embeddings | nomic-embed-text (Ollama) |
| Memoria | Engram (localhost:7437) |
| Lenguaje | Python 3.12 |

---

## Ideas y Pautas de Desarrollo

### 🛠️ Tool Calling Nativo (Fase 2)
- Utilizar el soporte nativo de **Tool Calling** de `qwen3.5` en Ollama. Pasar la descripción de las herramientas en formato JSON Schema para que el modelo elija cuándo llamar a funciones como abrir apps o buscar información.

### 🔄 Monitoreo Asíncrono (Fase 2)
- Para comandos del tipo *"Avísame cuando termine X"*, utilizar hilos (`threading`) o tareas asíncronas (`asyncio`) junto con `psutil` (o `pgrep` a través de subprocess) para monitorear el estado del proceso en segundo plano sin bloquear el REPL interactivo.
- Usar `notify-send` para notificaciones nativas en el sistema Linux.

### 🌐 Web Scraping Inteligente (Fase 2)
- Empezar con `requests` + `BeautifulSoup` para la extracción de texto simple en webs estáticas.
- Considerar `Playwright` (en modo headless) para el futuro si es necesario extraer información de sitios web dinámicos.

### 🚀 Perfiles de Entorno / Orquestación (Fase 3)
- Implementar "comandos macro" para preparar espacios de trabajo (ej. *"Prepara el entorno de desarrollo"* abre OpenCode, activa el entorno virtual de Python, levanta servicios locales y abre el navegador).

### 🎙️ Voz Local (Fase 4)
- **STT (Speech-to-Text):** Implementar **Faster-Whisper** para transcripción rápida fuera de la nube.
- **TTS (Text-to-Speech):** Utilizar **Piper** o **Kokoro-82M** para síntesis de voz local de excelente calidad en español con bajo consumo de recursos.

---

*Última actualización: 2026-05-22*
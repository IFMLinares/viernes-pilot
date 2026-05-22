# Jarvis Local - Diseño y Planificación

## Contexto

El usuario quiere crear su propio asistente de IA local, inspirado en una estructura propuesta por Gemini. Gemini generó un plan de 4 fases con la siguiente estructura:

```
jarvis_local/
├── config.py          # Configuración de puertos (Ollama, Engram) y prompts del sistema.
├── main.py            # Punto de entrada. Inicializa los hilos (Terminal y Background).
├── core/
│   ├── __init__.py
│   ├── brain.py       # Cliente de Ollama (Manejo de chat y embeddings).
│   ├── memory.py      # Cliente de Engram (Conexión HTTP local y búsquedas).
│   └── enrutador.py   # Lógica que decide qué herramienta usar basado en el JSON de la IA.
├── tools/
│   ├── __init__.py
│   ├── sistema.py     # Funciones nativas: abrir programas, scripts de tus proyectos.
│   └── alertas.py     # Lógica de notificaciones (notify-send).
└── workers/
    ├── __init__.py
    └── monitor.py     # Hilo secundario que vigila procesos o eventos en segundo plano.
```

## Las 4 fases propuestas

### Fase 1: El Sistema Nervioso (Conexión Local e Infraestructura)
- Paso 1.1: Levantar segunda instancia de Engram en puerto 8081 con base de datos exclusiva.
- Paso 1.2: Descargar qwen2.5:7b y nomic-embed-text en Ollama.
- Paso 1.3: Desarrollar core/brain.py y core/memory.py con scripts de prueba.

### Fase 2: La Interfaz y el "Sándwich de Contexto"
- Paso 2.1: Bucle interactivo en main.py para capturar entrada de texto.
- Paso 2.2: Lógica del "Sándwich": consulta Engram + contexto + pregunta -> Ollama.
- Paso 2.3: Formateador de salida legible para terminal.

### Fase 3: El Enrutador de Herramientas y Control de PC
- Paso 3.1: System Prompt en config.py para responder en JSON estructurado.
- Paso 3.2: tools/sistema.py para lanzar apps y notify-send.
- Paso 3.3: core/enrutador.py para parsear JSON y ejecutar funciones.

### Fase 4: Concurrencia y Proactividad (Background Worker)
- Paso 4.1: threading/asyncio en main.py para separar terminal del monitor.
- Paso 4.2: workers/monitor.py para vigilan proceso simulado.
- Paso 4.3: Conectar monitor con tools/alertas.py para notificaciones.

## Feedback provisto

### Lo que está bien
- Fases progresivas con prueba en cada paso ✅
- Separación clara de concerns (brain/memory/enrutador) ✅
- Apuntar a servicios locales (Ollama + Engram) ✅

### Lo que se revisaría
1. **"Sándwich de Contexto" es RAG sin llamarlo por su nombre** — Es Retrieval Augmented Generation. Buscar "RAG tutorial" sería más útil.
2. **Fase 4 (threading) es premature optimization** — Sin caso concreto de necesidad, agrega complejidad sin beneficio inmediato.
3. **No reinventar el enrutador de herramientas** — Es el patrón de tool calling. Frameworks como LangChain o LlamaIndex lo resuelven bien.
4. **Segunda instancia de Engram en puerto 8081** — Separar bases de datos baja la eficiencia de búsqueda vectorial. Se puede usar la misma con namespace.

## Recomendación

Arrancar más simple, sin threading, sin monitor, sin workers:

```
jarvis_local/
├── config.py
├── main.py
├── core/
│   ├── brain.py      # Ollama
│   └── memory.py     # Engram
└── tools/
    └── sistema.py     # abrir apps, notify-send
```

Solo Fase 1 + 2 + 3 funcional reducido. Probar que funciona, después agregar complejidad solo si se necesita.

## Estado actual

**Pendiente:** confirmar si el usuario ya tiene Ollama y Engram corriendo, o si se empieza de cero.
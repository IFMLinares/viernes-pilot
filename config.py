"""Configuración centralizada de Viernes."""
import os

# Intentar cargar el archivo .env si existe localmente
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

# Conectividad
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
ENGRAM_URL = os.getenv("ENGRAM_URL", "http://localhost:7437")

# Modelos
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_EMBED = os.getenv("OLLAMA_EMBED", "nomic-embed-text")

# Proyecto
ENGRAM_PROJECT = os.getenv("ENGRAM_PROJECT", "viernes")

SYSTEM_PROMPT = """Sos Viernes, un asistente de IA local. Respondés de forma clara, directa y en español rioplatense (usando voseo: "vos", "sos", "hacés", etc.).
Tenés acceso a una base de datos de memoria persistente a largo plazo llamada Engram.
Cuando el usuario te pregunte cosas sobre el pasado, sobre interacciones previas o sobre qué tenés guardado en memoria, debés usar obligatoria y explícitamente los recuerdos provistos en la sección "Memoria a largo plazo recuperada" para responderle con precisión.
Si no hay recuerdos relevantes en esa sección, podés decírselo de forma amable.
Cuando te pidan abrir un programa o aplicación, usá la herramienta `abrir_programa` pasándole el nombre amigable (ej: "calculadora", "spotify", "bloc de notas"). El sistema resolverá la coincidencia e indicará si es ambiguo o exitoso."""
"""Cliente Engram para memoria persistente."""
import requests
import json

ENGRAM_URL = "http://localhost:7437"
PROJECT = "viernes"


def search(query: str, limit: int = 5) -> list[dict]:
    """Busca recuerdos relevantes en Engram."""
    response = requests.get(
        f"{ENGRAM_URL}/search",
        params={"q": query, "project": PROJECT, "limit": limit},
    )
    response.raise_for_status()
    return response.json()


def save(title: str, content: str, mem_type: str = "manual", topic_key: str = None):
    """Guarda un recuerdo en Engram."""
    payload = {
        "session_id": f"manual-save-{PROJECT}",
        "type": mem_type,
        "title": title,
        "content": content,
        "project": PROJECT,
    }
    if topic_key:
        payload["topic_key"] = topic_key
        
    response = requests.post(
        f"{ENGRAM_URL}/observations",
        json=payload,
    )
    response.raise_for_status()
    return response.json()


def search_expanded(query: str, limit: int = 5) -> list[dict]:
    """Busca recuerdos en Engram con expansión de palabras clave individuales para búsquedas parciales."""
    # Intentar primero con la query completa
    search_results = search(query, limit=limit)
    if not search_results:
        search_results = []

    # Extraer palabras clave de más de 3 letras ignorando conectores comunes
    stop_words = {"para", "como", "pero", "este", "esta", "con", "del", "las", "los", "que", "una", "uno", "unos", "unas", "sobre"}
    words = [
        w.lower().strip(".,!?\"()'") 
        for w in query.split() 
        if len(w) > 3 and w.lower() not in stop_words
    ]
    
    # Hacer búsquedas individuales para cada palabra clave (máximo 3)
    if words:
        for word in words[:3]:
            extra_results = search(word, limit=limit)
            if extra_results:
                search_results.extend(extra_results)

    # Eliminar duplicados por ID
    seen_ids = set()
    unique_results = []
    for item in search_results:
        if item and item.get("id") not in seen_ids:
            seen_ids.add(item.get("id"))
            unique_results.append(item)
    return unique_results


def delete_observation(obs_id: int):
    """Borra un recuerdo en Engram por ID."""
    response = requests.delete(f"{ENGRAM_URL}/observations/{obs_id}")
    response.raise_for_status()
    return response.json()


def extract_json(text: str) -> dict:
    """Extrae un objeto JSON de una cadena de texto, soportando bloques markdown y texto extra."""
    text = text.strip()
    if not text:
        return {}

    # Intentar parsear directo
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Intentar buscar bloques de código markdown ```json ... ``` o ``` ... ```
    import re
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Buscar el primer '{' y el último '}'
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    return {}


def learn_from_interaction(user_input: str, response: str):
    """Analiza la interacción actual para extraer y actualizar hechos clave en Engram."""
    from core.brain import chat
    from config import OLLAMA_MODEL

    # 1. Buscar memorias relevantes usando búsqueda expandida
    search_results = search_expanded(user_input, limit=5)
    
    # 2. Filtrar estrictamente para proteger las configuraciones de OpenCode
    relevant_memories = [
        item for item in search_results 
        if item.get("type") in ["conversacion", "manual"]
    ]

    mem_list_str = ""
    if relevant_memories:
        for m in relevant_memories:
            mem_list_str += f"- ID: {m.get('id')} | topic_key: '{m.get('topic_key')}' | Título: '{m.get('title')}' | Contenido: '{m.get('content')}'\n"
    else:
        mem_list_str = "No hay memorias previas relevantes encontradas."

    system_prompt = """Sos el Gestor de Memoria a largo plazo de Viernes. Tu única tarea es analizar la última interacción entre el usuario (Vos) y el asistente (Viernes), evaluar las memorias existentes relevantes de la base de datos de Engram, y decidir qué cambios deben realizarse.

Reglas críticas de extracción:
1. Buscá hechos permanentes, decisiones importantes, soluciones de problemas, configuraciones de sistema o preferencias explícitas reveladas en la conversación.
2. NO guardes conversaciones triviales, saludos, preguntas genéricas de relleno, chistes ni emociones pasajeras.
3. Si el hecho revelado es nuevo, creá un `topic_key` único y descriptivo (usando letras, números y guiones, ej. 'ciudad-natal-miguel', 'resolucion-error-firewall') y asigná `action: "save"`.
4. Si la interacción actual actualiza, complementa o corrige una memoria existente (por ejemplo, el usuario cambia su nombre o la solución de un problema cambia), usá el `topic_key` de la memoria existente y asigná `action: "save"`. Esto actualizará el contenido de forma automática.
5. Si la interacción contradice o anula por completo una memoria existente (por ejemplo, el usuario dice que ya no tiene un perro), asigná `action: "delete"` e indica el `id` numérico de la memoria existente.

Debés responder exclusivamente con un objeto JSON válido con la siguiente estructura (si querés podés envolver el JSON en bloques de código markdown ```json ... ```):
{
  "updates": [
    {
      "action": "save",
      "topic_key": "clave-unica-descriptiva",
      "title": "Título corto y claro",
      "content": "El hecho o conocimiento detallado (ej. 'A Miguel le gusta programar en Python')"
    },
    {
      "action": "delete",
      "id": 123
    }
  ]
}"""

    user_message = f"""Última interacción:
Vos (Usuario): {user_input}
Viernes (Asistente): {response}

Memorias existentes relevantes recuperadas de la base de datos (pueden ser vacías):
{mem_list_str}

Decidí qué actualizaciones realizar en la memoria persistente."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        reply = chat(OLLAMA_MODEL, messages)
        data = extract_json(reply)
        updates = data.get("updates", [])
        
        if updates:
            print("\n--- PROCESO DE APRENDIZAJE (Gestor de Memoria) ---")
            for update in updates:
                action = update.get("action")
                if action == "save":
                    topic_key = update.get("topic_key")
                    title = update.get("title")
                    content = update.get("content")
                    if topic_key and title and content:
                        save(title, content, mem_type="conversacion", topic_key=topic_key)
                        print(f"[Aprendido/Actualizado] Clave: '{topic_key}' -> '{content}'")
                elif action == "delete":
                    obs_id = update.get("id")
                    if obs_id:
                        delete_observation(obs_id)
                        print(f"[Olvidado/Eliminado] Memoria ID: {obs_id}")
            print("--------------------------------------------------\n")
    except Exception as e:
        print(f"\n[Warning] No se pudo procesar el aprendizaje de memoria: {e}\n")
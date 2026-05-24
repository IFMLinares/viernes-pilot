"""REPL interactivo para Viernes."""
import sys
sys.path.insert(0, ".")

from core.brain import chat
from core.memory import search, save, learn_from_interaction, search_expanded
from config import OLLAMA_MODEL, SYSTEM_PROMPT

# Mapeo y esquemas de herramientas para Tool Calling
from tools.sistema import abrir_programa, mostrar_notificacion, abrir_terminal

FUNCIONES_MAP = {
    "abrir_programa": abrir_programa,
    "mostrar_notificacion": mostrar_notificacion,
    "abrir_terminal": abrir_terminal
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "abrir_programa",
            "description": (
                "Abre un programa o aplicación en el sistema (ej. bloc de notas, "
                "editor de código, navegador, explorador, opencode, antigravity)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "programa": {
                        "type": "string",
                        "description": "El nombre o alias del programa a abrir."
                    },
                    "ruta": {
                        "type": "string",
                        "description": "Opcional. La ruta absoluta de la carpeta o archivo a abrir con el programa (ej: abrir un proyecto en el editor)."
                    }
                },
                "required": ["programa"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_terminal",
            "description": (
                "Abre una nueva pestaña o ventana de terminal en un directorio específico, "
                "pudiendo ejecutar opcionalmente un comando de forma interactiva."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "carpeta": {
                        "type": "string",
                        "description": "La ruta absoluta de la carpeta donde se iniciará la terminal."
                    },
                    "comando": {
                        "type": "string",
                        "description": "Opcional. El comando a ejecutar automáticamente en la terminal (ej: 'python manage.py runserver')."
                    }
                },
                "required": ["carpeta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mostrar_notificacion",
            "description": (
                "Muestra una notificación emergente (alerta de sistema) en el escritorio del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "El título de la notificación."
                    },
                    "mensaje": {
                        "type": "string",
                        "description": "El contenido o texto del mensaje de la notificación."
                    }
                },
                "required": ["titulo", "mensaje"]
            }
        }
    }
]


def build_messages(history: list[dict], contexto: str) -> list[dict]:
    """Arma el historial de mensajes para enviar a Ollama."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if contexto:
        messages.append({
            "role": "system",
            "content": f"Memoria a largo plazo recuperada de Engram:\n{contexto}"
        })
    messages.extend(history)
    return messages


def main():
    print("Viernes activo. Escribí tu mensaje (Ctrl+C para salir).\n")

    history = []

    while True:
        try:
            user_input = input("vos: ").strip()
            if not user_input:
                continue

            # Armar contexto con búsqueda en memoria y depuración
            memoria = search_expanded(user_input, limit=3)
            if not memoria:
                memoria = []
            
            print("\n--- DEBUG MEMORIA (Resultados de search()) ---")
            if memoria:
                for idx, item in enumerate(memoria):
                    print(f"[{idx+1}] ID: {item.get('id')} | Título: '{item.get('title')}'")
                    print(f"    Contenido: {item.get('content')}")
                    print(f"    Rank/Score: {item.get('rank')}")
            else:
                print("No se encontraron recuerdos relevantes.")
            print("---------------------------------------------\n")

            contexto = ""
            if memoria:
                contexto_list = []
                for item in memoria:
                    content = item.get("content", "")
                    if content:
                        contexto_list.append(f"- {content}")
                contexto = "\n".join(contexto_list)

            # Agregar mensaje del usuario al historial
            history.append({"role": "user", "content": user_input})

            # Enviar a Ollama con las herramientas disponibles
            messages = build_messages(history, contexto)

            print("viernes: ", end="", flush=True)
            response_msg = chat(OLLAMA_MODEL, messages, tools=TOOLS)
            
            # Bucle de orquestación de Tool Calling
            tool_calls = response_msg.get("tool_calls", [])
            
            while tool_calls:
                # Añadir respuesta del asistente (que contiene tool_calls) al historial
                history.append(response_msg)
                
                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"]["arguments"]
                    
                    print(f"\n[Ejecutando herramienta] {func_name}({func_args})...")
                    
                    func_to_call = FUNCIONES_MAP.get(func_name)
                    if func_to_call:
                        try:
                            result = func_to_call(**func_args)
                        except Exception as err:
                            result = f"Error ejecutando función: {err}"
                    else:
                        result = f"Error: La función '{func_name}' no está registrada."
                        
                    print(f"[Resultado] {result}\n")
                    
                    # Añadir el resultado del tool al historial
                    history.append({
                        "role": "tool",
                        "name": func_name,
                        "content": result
                    })
                
                # Volver a invocar el chat con el historial que ya incluye el resultado de las herramientas
                messages = build_messages(history, contexto)
                print("viernes: ", end="", flush=True)
                response_msg = chat(OLLAMA_MODEL, messages, tools=TOOLS)
                tool_calls = response_msg.get("tool_calls", [])
            
            # Una vez terminadas las herramientas, imprimir la respuesta final de texto
            respuesta = response_msg.get("content", "")
            if respuesta:
                print(respuesta)
                print()

            # Agregar respuesta final del asistente al historial
            history.append(response_msg)

            # Limitar el historial para no saturar el contexto
            if len(history) > 20:
                history = history[-20:]

            # Guardar/Actualizar hechos de forma autónoma en la memoria a largo plazo
            learn_from_interaction(user_input, respuesta)

        except KeyboardInterrupt:
            print("\n\nChau!")
            break


if __name__ == "__main__":
    main()
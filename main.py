"""REPL interactivo para Viernes."""
import sys
sys.path.insert(0, ".")

from core.brain import chat
from core.memory import search, save, learn_from_interaction, search_expanded
from config import OLLAMA_MODEL, SYSTEM_PROMPT


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

            # Enviar a Ollama
            messages = build_messages(history, contexto)

            print("viernes: ", end="", flush=True)
            respuesta = chat(OLLAMA_MODEL, messages)
            print(respuesta)
            print()

            # Agregar respuesta del asistente al historial
            history.append({"role": "assistant", "content": respuesta})

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
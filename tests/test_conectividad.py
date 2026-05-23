"""Test de conectividad con servicios externos."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# from core.brain import chat, embed
from core.brain import chat, embed
from core.memory import search, save


def test_ollama_embed():
    """Embedding debería funcionar rápido."""
    print("Test: Ollama Embed...")
    vec = embed("nomic-embed-text", "test query")
    print(f"  OK — {len(vec)} dims")
    return True


def test_ollama_chat():
    """Chat con modelo pequeño primero."""
    print("Test: Ollama Chat (qwen3.5:9b)...")
    resp = chat("qwen3.5:9b", [{"role": "user", "content": "Hola"}])
    print(f"  OK — {resp[:50]}...")
    return True


def test_engram():
    """Engram save + search."""
    print("Test: Engram Save/Search...")
    save("test connectivity", "Esto es una prueba de memoria")
    resultados = search("prueba")
    print(f"  OK — {len(resultados)} resultados")
    return True


if __name__ == "__main__":
    ok = True
    for test in [test_ollama_chat, test_ollama_embed, test_engram]:
        try:
            ok = test() and ok
        except Exception as e:
            print(f"  FAIL — {e}")
            ok = False
    print(f"\n{'All OK' if ok else 'Some failed'}")
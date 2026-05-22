"""Cliente Ollama para chat y embeddings."""
import requests

OLLAMA_URL = "http://localhost:11434"


def chat(model: str, messages: list[dict]) -> str:
    """Envía un mensaje al modelo y devuelve la respuesta."""
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def embed(model: str, text: str) -> list[float]:
    """Genera embeddings de un texto."""
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": model, "prompt": text},
    )
    response.raise_for_status()
    return response.json()["embedding"]
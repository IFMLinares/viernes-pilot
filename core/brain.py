"""Cliente Ollama para chat y embeddings."""
import requests

OLLAMA_URL = "http://localhost:11434"


def chat(model: str, messages: list[dict], format: str = None, tools: list[dict] = None) -> dict:
    """Envía un mensaje al modelo y devuelve el objeto del mensaje de respuesta."""
    payload = {"model": model, "messages": messages, "stream": False}
    if format:
        payload["format"] = format
    if tools:
        payload["tools"] = tools
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
    )
    response.raise_for_status()
    return response.json()["message"]


def embed(model: str, text: str) -> list[float]:
    """Genera embeddings de un texto."""
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": model, "prompt": text},
    )
    response.raise_for_status()
    return response.json()["embedding"]
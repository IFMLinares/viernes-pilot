"""Cliente Engram para memoria persistente."""
import requests

ENGRAM_URL = "http://localhost:7437"
PROJECT = "viernes"


def search(query: str, limit: int = 5) -> list[dict]:
    """Busca recuerdos relevantes en Engram."""
    response = requests.post(
        f"{ENGRAM_URL}/mcp/v1/search",
        json={"query": query, "project": PROJECT, "limit": limit},
    )
    response.raise_for_status()
    return response.json().get("results", [])


def save(title: str, content: str, mem_type: str = "manual"):
    """Guarda un recuerdo en Engram."""
    response = requests.post(
        f"{ENGRAM_URL}/mcp/v1/memories",
        json={"title": title, "content": content, "project": PROJECT, "type": mem_type},
    )
    response.raise_for_status()
    return response.json()
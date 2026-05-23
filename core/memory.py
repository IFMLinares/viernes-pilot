"""Cliente Engram para memoria persistente."""
import requests

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


def save(title: str, content: str, mem_type: str = "manual"):
    """Guarda un recuerdo en Engram."""
    response = requests.post(
        f"{ENGRAM_URL}/observations",
        json={
            "session_id": f"manual-save-{PROJECT}",
            "type": mem_type,
            "title": title,
            "content": content,
            "project": PROJECT,
        },
    )
    response.raise_for_status()
    return response.json()
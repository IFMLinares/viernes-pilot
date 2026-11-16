"""Recognize only clear, supported read requests; defer other text to interpretation."""
import calendar
import re
import unicodedata
from datetime import date, timedelta

WORDS = set((
    "muestrame mostrame muestra mostrar lista listar que cuales tengo registrados registradas hay "
    "mis los las de del la el universidad trabajo personal personales compromisos tareas "
    "todos todas todo historial completo esta este semana mes por favor "
    "show me my the list what which do i have registered all history full university work personal "
    "commitments tasks assignments this week month please for"
).split())


def _words(value):
    normalized = "".join(char for char in unicodedata.normalize("NFKD", value.lower())
                         if not unicodedata.combining(char))
    return re.findall(r"\w+", normalized)


def history_requested(value):
    tokens = set(_words(value))
    return (bool(tokens & {"all", "history", "todos", "todas", "todo", "historial"})
            and not tokens & {"not", "no", "without", "except", "sin", "excepto"})


def listing_request(value, today=None):
    words = _words(value)
    if words[:2] == ["por", "favor"]:
        words = words[2:]
    elif words[:1] == ["please"]:
        words = words[1:]
    if not words or not set(words) <= WORDS:
        return None
    spanish = words[0] in ("muestrame", "mostrame", "muestra", "mostrar", "lista", "listar", "que", "cuales")
    if not spanish and words[0] not in ("show", "list", "what", "which"):
        return None
    tokens = set(words)
    if not tokens & {"compromisos", "tareas", "commitments", "tasks", "assignments"}:
        return None
    areas = [area for area, names in (("university", {"universidad", "university"}),
             ("work", {"trabajo", "work"}), ("personal", {"personal", "personales"})) if tokens & names]
    if len(areas) > 1:
        return None
    result = {"action": "list", "language": "es" if spanish else "en",
              "area": areas[0] if areas else None, "scope": "current"}
    week = bool(tokens & {"semana", "week"})
    month = bool(tokens & {"mes", "month"})
    if week and month:
        return None
    if week or month:
        if not tokens & {"this", "esta", "este"}:
            return None
        today = today or date.today()
        if week:
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        else:
            start = today.replace(day=1)
            end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        result.update(scope="range", start_date=start.isoformat(), end_date=end.isoformat())
    elif tokens & {"all", "history", "full", "todos", "todas", "todo", "historial", "completo"}:
        result["scope"] = "all"
    return result

"""Recognize only clear, supported read requests; defer other text to interpretation."""
import calendar
import re
import unicodedata
from datetime import date, timedelta

TASK_WORDS = {"compromisos", "tareas", "commitments", "tasks", "assignments"}
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


def _one_edit_apart(value, target):
    """One insertion, deletion, substitution or adjacent transposition only."""
    if abs(len(value) - len(target)) > 1:
        return False
    if len(value) == len(target):
        differences = [index for index, (left, right) in enumerate(zip(value, target)) if left != right]
        if len(differences) == 1:
            return True
        if len(differences) == 2:
            first, second = differences
            return (second == first + 1 and value[first] == target[second]
                    and value[second] == target[first])
        return False
    short, long = (value, target) if len(value) < len(target) else (target, value)
    return any(short == long[:index] + long[index + 1:] for index in range(len(long)))


def _query_words(value):
    words = _words(value)
    corrections = {}
    for word in set(words) - WORDS:
        matches = [target for target in TASK_WORDS if len(target) >= 8 and _one_edit_apart(word, target)]
        if len(matches) != 1:
            return None
        corrections[word] = matches[0]
    return [corrections.get(word, word) for word in words]


def listing_request(value, today=None):
    words = _query_words(value)
    if not words:
        return None
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
    if not tokens & TASK_WORDS:
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

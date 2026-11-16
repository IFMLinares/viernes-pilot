"""Typed comparison oracle for synthetic interpreter evaluation."""
from datetime import date
from core.commitments import AREAS, validate_fields


REFERENCE_DATE = date(2026, 11, 23)



COMPARISON_FIELDS = {
    "create": ["action", "language", "items"],
    "list": ["action", "language", "area", "scope", "start_date", "end_date"],
    "edit": ["action", "language", "id", "fields"],
    "complete": ["action", "language", "id"],
    "clarify": ["action", "language", "clarification"],
    "reply": ["action", "language", "answer"],
}



def normalize_action(action):
    """Keep whitelisted structured fields for in-memory comparison."""
    if not isinstance(action, dict):
        return None
    name = action.get("action")
    if name not in COMPARISON_FIELDS:
        return None
    result = {"action": name}
    if "language" in action:
        result["language"] = action["language"]
    if name == "create":
        items = action.get("items")
        if isinstance(items, list):
            result["items"] = [{k: item.get(k) for k in ("title", "area", "project", "due_date")} for item in items]
    elif name == "list":
        for k in ("area", "scope", "start_date", "end_date"):
            if k in action:
                result[k] = action[k]
        # Canonical documented default: an omitted list scope means current.
        result.setdefault("scope", "current")
    elif name in ("edit", "complete"):
        result["id"] = action.get("id")
        if name == "edit":
            result["fields"] = action.get("fields")
    elif name == "clarify":
        result["clarification"] = action.get("clarification")
    elif name == "reply":
        result["answer"] = action.get("answer")
    return result



def validate_action_contract(action):
    """Validate a proposed action using production rules; raise ValueError if invalid."""
    if not isinstance(action, dict):
        raise ValueError("Expected a structured proposal.")
    name = action.get("action")
    if name not in COMPARISON_FIELDS:
        raise ValueError("Unsupported proposal action.")
    language = action.get("language")
    if language not in ("en", "es"):
        raise ValueError("Language must be en or es.")
    if "answer" in action and name != "reply":
        raise ValueError("General answers cannot be combined with commitment operations.")

    if name == "reply":
        if set(action) != {"action", "language", "answer"}:
            raise ValueError("General replies require exactly action, language and answer.")
        answer = action.get("answer")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
            raise ValueError("Expected a nonempty general answer of at most 8000 characters.")
        return

    if name == "create":
        items = action.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ValueError("Expected between 1 and 20 commitments.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each commitment must be an object.")
            validate_fields(item)
        return

    if name == "list":
        area = action.get("area")
        if area is not None and area not in AREAS:
            raise ValueError("Unknown area.")
        scope = action.get("scope", "current")
        if scope not in ("current", "all", "range"):
            raise ValueError("Unknown query scope.")
        if scope == "range":
            validate_fields({"due_date": action.get("start_date")}, partial=True)
            validate_fields({"due_date": action.get("end_date")}, partial=True)
        return

    if name == "edit":
        task_id = action.get("id")
        if not isinstance(task_id, int) or task_id <= 0:
            raise ValueError("Expected a positive integer commitment ID.")
        fields = action.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("Expected title, area, project and/or due_date fields only.")
        validate_fields(fields, partial=True)
        return

    if name == "complete":
        task_id = action.get("id")
        if not isinstance(task_id, int) or task_id <= 0:
            raise ValueError("Expected a positive integer commitment ID.")
        return

    if name == "clarify":
        reason = action.get("clarification", "request")
        if reason not in ("area", "date", "id", "scope", "request"):
            raise ValueError("Unsupported clarification reason.")
        return



def actions_equal(actual, expected):
    """Lenient equality: actual title/answer must be present; expected constrains typed fields."""
    a = normalize_action(actual)
    e = normalize_action(expected)
    if a is None or e is None:
        return False
    if a.get("action") != e.get("action"):
        return False
    if a.get("language") != e.get("language"):
        return False
    action = a["action"]
    if action == "create":
        a_items = a.get("items", [])
        e_items = e.get("items", [])
        if len(a_items) != len(e_items):
            return False
        for ai, ei in zip(a_items, e_items):
            if not ai.get("title"):
                return False
            if ai.get("area") != ei.get("area"):
                return False
            if ai.get("due_date") != ei.get("due_date"):
                return False
            if ai.get("project") != ei.get("project"):
                return False
        return True
    if action == "list":
        return (a.get("area") == e.get("area")
                and a.get("scope") == e.get("scope")
                and a.get("start_date") == e.get("start_date")
                and a.get("end_date") == e.get("end_date"))
    if action == "edit":
        return a.get("id") == e.get("id") and a.get("fields") == e.get("fields")
    if action == "complete":
        return a.get("id") == e.get("id")
    if action == "clarify":
        return a.get("clarification") == e.get("clarification")
    if action == "reply":
        answer = a.get("answer")
        return isinstance(answer, str) and bool(answer.strip())
    return False

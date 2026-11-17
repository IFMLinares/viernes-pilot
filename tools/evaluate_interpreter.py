"""Evaluate interpreter quality against synthetic cases without touching user data.

Example:
    python -m tools.evaluate_interpreter \
        --url http://127.0.0.1:11434 --model qwen3.5:9b \
        --mode both --max-requests 60 --max-seconds 900 \
        --output evaluations/reports/local-baseline.json
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.commitments import AREAS, CommitmentStore, validate_fields
from core.diagnostics import Diagnostics
from core.ollama_runtime import local_url
from core.planner import Planner, ollama_interpreter


class BudgetExceeded(RuntimeError):
    """Raised when the shared request/time budget is exhausted."""
    pass


REFERENCE_DATE = date(2026, 11, 23)
DEFAULT_MAX_REQUESTS = 60
DEFAULT_MAX_SECONDS = 900

# Full structured action used for in-memory comparison.
COMPARISON_FIELDS = {
    "create": ["action", "language", "items"],
    "list": ["action", "language", "area", "scope", "start_date", "end_date"],
    "edit": ["action", "language", "id", "fields"],
    "complete": ["action", "language", "id"],
    "clarify": ["action", "language", "clarification"],
    "reply": ["action", "language", "answer"],
}

# Safe field allowlists for persisted reports.
SAFE_ITEM_FIELDS = {"area", "project", "due_date"}
SAFE_EDIT_FIELDS = {"area", "project", "due_date"}

INFRA_CODES = {500, 502, 503, 504, 404}


def load_cases(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_fixtures(store, case):
    """Populate isolated store with synthetic fixtures for a case."""
    for item in case.get("fixtures", []):
        action = item.get("action", "create")
        if action == "create":
            store.create_many([{
                "title": item["title"],
                "area": item["area"],
                "project": item.get("project"),
                "due_date": item.get("due_date"),
            }], "synthetic fixture")
        elif action == "complete":
            rows = store.create_many([{
                "title": item["title"],
                "area": item["area"],
                "project": item.get("project"),
                "due_date": item.get("due_date"),
            }], "synthetic fixture")
            for row in rows:
                store.complete(row["id"])


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


def _is_valid_date(value):
    try:
        validate_fields({"due_date": value}, partial=True)
        return True
    except (TypeError, ValueError):
        return False


def _safe_int(value, positive=True):
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if positive and value <= 0:
        return None
    return value


def _safe_area(value):
    if value is None:
        return None
    return value if value in AREAS else None


def _safe_scope(value):
    return value if value in ("current", "all", "range") else None


def _safe_clarification(value):
    return value if value in ("area", "date", "id", "scope", "request") else None


def sanitize_action(action):
    """Return a privacy-safe, metadata-only representation for the JSON report."""
    if not isinstance(action, dict):
        return None
    name = action.get("action")
    if name not in COMPARISON_FIELDS:
        return None
    result = {"action": name}
    language = action.get("language")
    if language in ("en", "es"):
        result["language"] = language
    if name == "create":
        items = action.get("items")
        if isinstance(items, list):
            safe_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                safe = {}
                area = _safe_area(item.get("area"))
                if area is not None:
                    safe["area"] = area
                due_date = item.get("due_date")
                if due_date is not None and _is_valid_date(due_date):
                    safe["due_date"] = due_date
                project = item.get("project")
                safe["project_present"] = isinstance(project, str) and bool(project.strip())
                title = item.get("title")
                safe["title_present"] = isinstance(title, str) and bool(title.strip())
                if isinstance(title, str):
                    safe["title_length"] = len(title)
                safe_items.append(safe)
            result["items"] = safe_items
    elif name == "list":
        area = _safe_area(action.get("area"))
        if "area" in action:
            result["area"] = area
        scope = _safe_scope(action.get("scope"))
        if scope is not None:
            result["scope"] = scope
        for k in ("start_date", "end_date"):
            value = action.get(k)
            if value is not None and _is_valid_date(value):
                result[k] = value
    elif name in ("edit", "complete"):
        task_id = _safe_int(action.get("id"))
        if task_id is not None:
            result["id"] = task_id
        if name == "edit":
            fields = action.get("fields") or {}
            safe = {}
            if isinstance(fields, dict):
                area = _safe_area(fields.get("area"))
                if area is not None:
                    safe["area"] = area
                due_date = fields.get("due_date")
                if due_date is not None and _is_valid_date(due_date):
                    safe["due_date"] = due_date
                project = fields.get("project")
                safe["project_present"] = isinstance(project, str) and bool(project.strip())
                title = fields.get("title")
                safe["title_present"] = isinstance(title, str) and bool(title.strip())
                if isinstance(title, str):
                    safe["title_length"] = len(title)
            result["fields"] = safe
    elif name == "clarify":
        clarification = _safe_clarification(action.get("clarification", "request"))
        if clarification is not None:
            result["clarification"] = clarification
    elif name == "reply":
        answer = action.get("answer")
        result["answer_present"] = isinstance(answer, str) and bool(answer.strip())
        if isinstance(answer, str):
            result["answer_length"] = len(answer)
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


def _extract_http_code(message):
    for token in message.split():
        try:
            code = int(token.rstrip("."))
            if 100 <= code <= 599:
                return code
        except ValueError:
            continue
    return None


def classify_http_error(code):
    if code in INFRA_CODES:
        return "infrastructure"
    return "service_error"


class Budget:
    def __init__(self, max_requests, deadline):
        self.max_requests = max_requests
        self.deadline = deadline
        self.requests = 0

    def check(self):
        if self.requests >= self.max_requests:
            raise BudgetExceeded("max_requests")
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded("deadline")

    def remaining_seconds(self):
        return max(0, self.deadline - time.monotonic())


class BudgetedInterpreter:
    """Central wrapper: counts attempts before the call, enforces budget/timeout, classifies errors."""

    def __init__(self, url, model, budget):
        self.url = url
        self.model = model
        self.budget = budget

    def _timeout(self):
        remaining = self.budget.remaining_seconds()
        return (min(3, remaining), remaining)

    def call(self, text, history):
        self.budget.check()
        self.budget.requests += 1
        try:
            interpreter = ollama_interpreter(self.url, self.model, today=REFERENCE_DATE, timeout=self._timeout())
            return interpreter(text, history)
        except ValueError as exc:
            message = str(exc)
            code = _extract_http_code(message)
            if code is not None:
                raise RuntimeError(classify_http_error(code)) from exc
            raise
        except requests.Timeout as exc:
            raise RuntimeError("timeout") from exc
        except requests.ConnectionError as exc:
            raise RuntimeError("connection") from exc
        except requests.RequestException as exc:
            raise RuntimeError("network") from exc


def evaluate_direct(case, interpreter):
    """Run a single case through the production interpreter (one attempt always consumed)."""
    start = time.perf_counter()
    try:
        actual = interpreter.call(case["input"], [])
        validate_action_contract(actual)
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": sanitize_action(actual),
            "route": "interpreter",
            "verdict": "correct" if actions_equal(actual, case["expected"]) else "incorrect",
            "reason_code": None,
            "requests": 1,
            "elapsed_ms": elapsed_ms,
        }
    except RuntimeError as exc:
        if isinstance(exc, BudgetExceeded):
            raise
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        reason = str(exc)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": reason,
            "requests": 1,
            "elapsed_ms": elapsed_ms,
            "stop": reason in ("infrastructure", "connection", "timeout", "network", "service_error", "max_requests", "deadline"),
        }
    except json.JSONDecodeError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": "invalid_json",
            "requests": 1,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": _error_code_from_exception(exc),
            "requests": 1,
            "elapsed_ms": elapsed_ms,
        }


def _error_code_from_exception(exc):
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "connection"
    if isinstance(exc, requests.RequestException):
        return "network"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        message = str(exc).lower()
        if "area must be" in message or "due_date must be" in message or "title must be" in message:
            return "invalid_fields"
        if "unknown query scope" in message:
            return "invalid_scope"
        return "invalid_structure"
    return "unexpected"


def evaluate_end_to_end(case, interpreter):
    """Run a single case through Planner.respond with isolated fixtures and DB-state checks."""
    start = time.perf_counter()
    events = []
    diag = Diagnostics(output=type("Sink", (), {"write": lambda _, s: events.append(json.loads(s)), "flush": lambda _: None})())
    temp = tempfile.TemporaryDirectory(prefix="viernes-eval-")
    try:
        path = Path(temp.name) / "tasks.sqlite3"
        store = CommitmentStore(path)
        try:
            setup_fixtures(store, case)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            planner = Planner(store, interpreter.call, today=REFERENCE_DATE, diagnostics=diag)
            response = planner.respond(case["input"])
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            actual = planner._last_action
            route = planner._last_route or "interpreter"
            if actual is not None:
                validate_action_contract(actual)
            if before != after:
                return {
                    "expected": sanitize_action(case["expected"]),
                    "actual": None,
                    "route": route,
                    "verdict": "error",
                    "reason_code": "storage_changed",
                    "requests": 1 if route == "interpreter" else 0,
                    "elapsed_ms": elapsed_ms,
                }
            return {
                "expected": sanitize_action(case["expected"]),
                "actual": sanitize_action(actual),
                "route": route,
                "verdict": "correct" if actions_equal(actual, case["expected"]) else "incorrect",
                "reason_code": None,
                "requests": 1 if route == "interpreter" else 0,
                "elapsed_ms": elapsed_ms,
            }
        finally:
            store.close()
    except RuntimeError as exc:
        if isinstance(exc, BudgetExceeded):
            raise
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        reason = str(exc)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": reason,
            "requests": 1,
            "elapsed_ms": elapsed_ms,
            "stop": reason in ("infrastructure", "connection", "timeout", "network", "service_error", "max_requests", "deadline"),
        }
    except json.JSONDecodeError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": "invalid_json",
            "requests": 1,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "expected": sanitize_action(case["expected"]),
            "actual": None,
            "route": "interpreter",
            "verdict": "error",
            "reason_code": _error_code_from_exception(exc),
            "requests": 1,
            "elapsed_ms": elapsed_ms,
        }
    finally:
        temp.cleanup()


def summarize(results):
    total = len(results)
    correct = sum(1 for r in results if r["verdict"] == "correct")
    errors = sum(1 for r in results if r["verdict"] == "error")
    total_ms = sum(r["elapsed_ms"] for r in results)
    by_route = {}
    for r in results:
        by_route[r.get("route", "unknown")] = by_route.get(r.get("route", "unknown"), 0) + 1
    return {
        "evaluated": total,
        "correct": correct,
        "incorrect": total - correct - errors,
        "errors": errors,
        "accuracy": correct / total if total else 0,
        "total_ms": total_ms,
        "avg_ms": round(total_ms / total, 2) if total else 0,
        "routes": by_route,
    }


def build_report(args, cases, direct_results, e2e_results, completed, stopped_reason):
    report = {
        "reference_date": REFERENCE_DATE.isoformat(),
        "url": args.url,
        "model": args.model,
        "mode": args.mode,
        "max_requests": args.max_requests,
        "max_seconds": args.max_seconds,
        "completed": completed,
        "stopped_reason": stopped_reason,
        "summary": {},
        "cases": [],
    }
    if direct_results is not None:
        report["summary"]["direct"] = summarize(direct_results)
    if e2e_results is not None:
        report["summary"]["end_to_end"] = summarize(e2e_results)
    for index, case in enumerate(cases):
        entry = {
            "case_id": case["case_id"],
            "category": case["category"],
        }
        if direct_results is not None and index < len(direct_results):
            entry["direct"] = direct_results[index]
        if e2e_results is not None and index < len(e2e_results):
            entry["end_to_end"] = e2e_results[index]
        report["cases"].append(entry)
    return report


def write_report(report, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate interpreter interpretation quality")
    parser.add_argument("--url", required=True, help="Local Ollama URL (loopback only)")
    parser.add_argument("--model", required=True, help="Local Ollama model name")
    parser.add_argument("--mode", choices=("direct", "end-to-end", "both"), default="both",
                        help="Evaluation mode")
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS,
                        help="Global hard cap on inference attempts (<=60)")
    parser.add_argument("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
                        help="Deadline for the whole evaluation (<=900)")
    parser.add_argument("--cases", default="evaluations/interpreter_cases.json",
                        help="Path to the synthetic case corpus")
    parser.add_argument("--output", required=True, help="Sanitized JSON report path")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.max_requests > DEFAULT_MAX_REQUESTS:
        print(f"--max-requests must be <= {DEFAULT_MAX_REQUESTS}", file=sys.stderr)
        return 2
    if args.max_seconds > DEFAULT_MAX_SECONDS:
        print(f"--max-seconds must be <= {DEFAULT_MAX_SECONDS}", file=sys.stderr)
        return 2

    url = local_url(args.url)
    if url is None:
        print("Only loopback HTTP on port 11434 is supported.", file=sys.stderr)
        return 2

    cases = load_cases(args.cases)
    if not cases:
        print("No cases loaded.", file=sys.stderr)
        return 2

    budget = Budget(args.max_requests, time.monotonic() + args.max_seconds)
    direct_results = [] if args.mode in ("direct", "both") else None
    e2e_results = [] if args.mode in ("end-to-end", "both") else None
    completed = False
    stopped_reason = None
    interpreter = BudgetedInterpreter(url, args.model, budget)

    try:
        for case in cases:
            if direct_results is not None:
                budget.check()
                result = evaluate_direct(case, interpreter)
                direct_results.append(result)
                if result.get("stop"):
                    raise RuntimeError(result["reason_code"])
            if e2e_results is not None:
                budget.check()
                result = evaluate_end_to_end(case, interpreter)
                e2e_results.append(result)
                if result.get("stop"):
                    raise RuntimeError(result["reason_code"])
        if time.monotonic() >= budget.deadline:
            raise RuntimeError("deadline")
        completed = True
    except RuntimeError as exc:
        stopped_reason = str(exc)
    except Exception as exc:
        stopped_reason = f"unexpected: {type(exc).__name__}"

    report = build_report(args, cases, direct_results, e2e_results, completed, stopped_reason)
    write_report(report, args.output)
    print(f"Report written to {args.output}", file=sys.stderr)
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())

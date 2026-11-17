"""Offline re-score for interpreter evaluation reports.

Re-grade a previous sanitized report using corrected semantic-default rules.
No network, model, config or private environment access.

Example:
    python -m tools.rescore_interpreter \
        --input evaluations/reports/local-baseline.json \
        --output evaluations/reports/local-baseline-rescored.json
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.commitments import AREAS, validate_fields
from tools.evaluate_interpreter import actions_equal


SCORING_RULE = "semantic-defaults"
SCORING_RULE_VERSION = "1"

# Top-level keys a sanitized report is expected to carry.
_REQUIRED_TOP_KEYS = {
    "reference_date", "url", "model", "mode", "max_requests", "max_seconds",
    "completed", "stopped_reason", "summary", "cases",
}

# Keys allowed inside a result record. Anything else is treated as unsafe.
_SAFE_RESULT_KEYS = {
    "expected", "actual", "route", "verdict", "reason_code", "requests", "elapsed_ms", "stop",
}

# Raw/private keys that must never appear in a report we are willing to rescore.
_FORBIDDEN_KEYS = {
    "input", "fixtures", "prompt", "messages", "raw", "source", "answer", "title", "project",
}

_VALID_VERDICTS = {"correct", "incorrect", "error"}
_VALID_ROUTES = {"interpreter", "fast_path", "command"}

# Allowed keys per sanitized action type (positive allowlist).
_ACTION_KEYS = {
    "create": {"action", "language", "items"},
    "list": {"action", "language", "area", "scope", "start_date", "end_date"},
    "edit": {"action", "language", "id", "fields"},
    "complete": {"action", "language", "id"},
    "clarify": {"action", "language", "clarification"},
    "reply": {"action", "language", "answer_present", "answer_length"},
}

_SAFE_ITEM_KEYS = {"title_present", "title_length", "project_present", "area", "due_date"}
_SAFE_EDIT_FIELDS_KEYS = {"title_present", "title_length", "project_present", "area", "due_date"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Re-score a sanitized interpreter evaluation report offline")
    parser.add_argument("--input", required=True, help="Path to the original sanitized report")
    parser.add_argument("--output", required=True, help="Path for the derived rescored report")
    return parser.parse_args(argv)


def _has_forbidden_keys(obj):
    """Reject reports that contain raw/private fields at any level."""
    if isinstance(obj, dict):
        for key in obj:
            if key in _FORBIDDEN_KEYS:
                return True
            if _has_forbidden_keys(obj[key]):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_forbidden_keys(item):
                return True
    return False


def _safe_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer.")
    return value


def _validate_presence_metadata(fields):
    for key in ("title_present", "project_present", "answer_present"):
        if key in fields and type(fields[key]) is not bool:
            raise ValueError("Presence metadata must be boolean.")
    for key in ("title_length", "answer_length"):
        if key in fields:
            _safe_int(fields[key], key)


def _validate_date(value):
    """Require a real ISO date or null; raises ValueError otherwise."""
    if value is None:
        return
    try:
        validate_fields({"due_date": value}, partial=True)
    except (TypeError, ValueError):
        raise ValueError("Invalid ISO date metadata.") from None


def _validate_action(action):
    """Positive allowlisted validation for sanitized action metadata."""
    if action is None:
        return None
    if not isinstance(action, dict):
        raise ValueError("Action metadata must be an object or null.")
    name = action.get("action")
    if not isinstance(name, str) or name not in _ACTION_KEYS:
        raise ValueError("Unsupported or missing action.")
    language = action.get("language")
    if language not in ("en", "es"):
        raise ValueError("Invalid action language.")
    extra = set(action) - _ACTION_KEYS[name]
    if extra:
        raise ValueError("Unexpected action metadata keys.")
    if name == "list":
        area = action.get("area")
        if area is not None and area not in AREAS:
            raise ValueError("Invalid list area.")
        scope = action.get("scope", "current")
        if scope not in ("current", "all", "range"):
            raise ValueError("Invalid list scope.")
        for key in ("start_date", "end_date"):
            if key in action:
                _validate_date(action[key])
        start, end = action.get("start_date"), action.get("end_date")
        if scope == "range":
            if start is None or end is None or start > end:
                raise ValueError("Range scope requires ordered, complete dates.")
        elif start is not None or end is not None:
            raise ValueError("Explicit dates require range scope.")
    elif name == "create":
        items = action.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Create items must be a nonempty list.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each create item must be an object.")
            item_extra = set(item) - _SAFE_ITEM_KEYS
            if item_extra:
                raise ValueError("Unexpected create metadata keys.")
            _validate_presence_metadata(item)
            area = item.get("area")
            if area not in AREAS:
                raise ValueError("Invalid create item area.")
            due_date = item.get("due_date")
            if due_date is not None:
                _validate_date(due_date)
    elif name == "edit":
        fields = action.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("Edit fields must be an object.")
        field_extra = set(fields) - _SAFE_EDIT_FIELDS_KEYS
        if field_extra:
            raise ValueError("Unexpected edit metadata keys.")
        _validate_presence_metadata(fields)
        for key in ("area",):
            if key in fields and fields[key] not in AREAS:
                raise ValueError(f"Invalid edit field {key}.")
        if "due_date" in fields and fields["due_date"] is not None:
            _validate_date(fields["due_date"])
        task_id = action.get("id")
        if _safe_int(task_id, "edit id") == 0:
            raise ValueError("Edit id must be positive.")
    elif name == "complete":
        task_id = action.get("id")
        if _safe_int(task_id, "complete id") == 0:
            raise ValueError("Complete id must be positive.")
    elif name == "clarify":
        clarification = action.get("clarification", "request")
        if clarification not in ("area", "date", "id", "scope", "request"):
            raise ValueError("Invalid clarification reason.")
    elif name == "reply":
        _validate_presence_metadata(action)
    return action


def _validate_result(result):
    """Validate a single mode result record."""
    if not isinstance(result, dict):
        raise ValueError("Result must be an object.")
    extra = set(result) - _SAFE_RESULT_KEYS
    if extra:
        raise ValueError("Unexpected result metadata keys.")
    verdict = result.get("verdict")
    if not isinstance(verdict, str) or verdict not in _VALID_VERDICTS:
        raise ValueError("Invalid verdict metadata.")
    route = result.get("route")
    if not isinstance(route, str) or route not in _VALID_ROUTES:
        raise ValueError("Invalid route metadata.")
    _safe_int(result.get("requests"), "requests")
    _safe_int(result.get("elapsed_ms"), "elapsed_ms")
    stop = result.get("stop")
    if stop is not None and not isinstance(stop, bool):
        raise ValueError("stop must be a boolean or absent.")
    reason_code = result.get("reason_code")
    if reason_code is not None and not isinstance(reason_code, str):
        raise ValueError("reason_code must be a string or null.")
    _validate_action(result.get("expected"))
    _validate_action(result.get("actual"))


def _validate_report(report):
    """Sanity-check the input shape and refuse malformed/unsafe reports."""
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object.")
    if _has_forbidden_keys(report):
        raise ValueError("Report contains forbidden raw/private fields.")
    missing = _REQUIRED_TOP_KEYS - set(report)
    if missing:
        raise ValueError(f"Missing required report keys: {sorted(missing)}")
    if not isinstance(report.get("cases"), list):
        raise ValueError("Report cases must be a list.")
    if not isinstance(report.get("completed"), bool):
        raise ValueError("completed must be a boolean.")
    _safe_int(report.get("max_requests"), "max_requests")
    _safe_int(report.get("max_seconds"), "max_seconds")
    for key in ("mode", "url", "model", "reference_date"):
        if not isinstance(report.get(key), str):
            raise ValueError(f"{key} must be a string.")
    if report["mode"] not in ("direct", "end-to-end", "both"):
        raise ValueError("Invalid report mode.")
    _validate_date(report["reference_date"])
    if report["stopped_reason"] is not None and not isinstance(report["stopped_reason"], str):
        raise ValueError("stopped_reason must be a string or null.")
    if not isinstance(report.get("summary"), dict):
        raise ValueError("summary must be an object.")
    for case in report["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Each case must be an object.")
        if "case_id" not in case or "category" not in case:
            raise ValueError("Each case must have case_id and category.")
        for key in ("case_id", "category"):
            value = case[key]
            if not isinstance(value, str) or not value or not value.isprintable():
                raise ValueError("Case identifiers must be nonempty printable strings.")
        for mode in ("direct", "end_to_end"):
            result = case.get(mode)
            if result is None:
                continue
            _validate_result(result)
    return True


def _rescore_result(result):
    """Re-grade a single result under semantic-default rules.

    Returns (new_result_dict, was_changed). Only list actions with omitted scope
    -> current may be corrected. Errors, correct results and non-list actions are
    preserved/annotated but not changed.
    """
    original_verdict = result.get("verdict")
    actual = result.get("actual")
    expected = result.get("expected")
    new_result = dict(result)
    new_result["original_verdict"] = original_verdict

    if original_verdict == "error" or original_verdict is None:
        new_result["rescore_status"] = "preserved"
        return new_result, False

    if original_verdict == "correct":
        new_result["rescore_status"] = "preserved"
        return new_result, False

    # From here on original_verdict == "incorrect".
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        new_result["rescore_status"] = "not_rescorable"
        return new_result, False

    if actual.get("action") != "list" or expected.get("action") != "list":
        new_result["rescore_status"] = "not_rescorable"
        return new_result, False

    normalized_defaults = {}
    # Documented default: omitted list scope means current.
    if expected.get("scope") == "current" and "scope" not in actual:
        normalized_defaults["scope"] = "current"

    if actions_equal(actual, expected):
        new_result["verdict"] = "correct"
        new_result["rescore_status"] = "corrected"
        new_result["normalized_defaults"] = normalized_defaults
        return new_result, True

    new_result["rescore_status"] = "unchanged"
    new_result["normalized_defaults"] = normalized_defaults if normalized_defaults else None
    return new_result, False


def _summarize(case_results, original_mode):
    """Recompute summary preserving coverage, errors, timing and requests."""
    results = [c[original_mode] for c in case_results if original_mode in c]
    total = len(results)
    correct = sum(1 for r in results if r.get("verdict") == "correct")
    errors = sum(1 for r in results if r.get("verdict") == "error")
    total_ms = sum(r.get("elapsed_ms", 0) for r in results)
    total_requests = sum(r.get("requests", 0) for r in results)
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
        "requests": total_requests,
        "routes": by_route,
    }


def rescore(report_bytes):
    """Build the derived rescored report from original report bytes."""
    report = json.loads(report_bytes)
    _validate_report(report)

    case_results = []
    any_changed = False
    for case in report["cases"]:
        entry = {"case_id": case["case_id"], "category": case["category"]}
        for mode in ("direct", "end_to_end"):
            original = case.get(mode)
            if original is None:
                continue
            rescored, changed = _rescore_result(original)
            any_changed = any_changed or changed
            entry[mode] = rescored
        case_results.append(entry)

    derived = {
        "scoring_rule": SCORING_RULE,
        "scoring_rule_version": SCORING_RULE_VERSION,
        "source_report": None,
        "source_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "rescored_at": datetime.now(timezone.utc).isoformat(),
        "note": "Rescore completed. Exit 0 means the offline re-grade finished; the original measurement may still be partial.",
        "reference_date": report["reference_date"],
        "url": report["url"],
        "model": report["model"],
        "mode": report["mode"],
        "max_requests": report["max_requests"],
        "max_seconds": report["max_seconds"],
        "completed": report["completed"],
        "stopped_reason": report["stopped_reason"],
        "summary": {},
        "case_results": case_results,
    }
    for mode in ("direct", "end_to_end"):
        if mode in report.get("summary", {}):
            derived["summary"][mode] = _summarize(case_results, mode)
    derived["any_verdict_changed"] = any_changed
    return derived


def main(argv=None):
    args = parse_args(argv)
    input_path = os.path.realpath(args.input)
    output_path = os.path.realpath(args.output)

    if input_path == output_path:
        print("Error: --output must differ from --input (symlinks are resolved).", file=sys.stderr)
        return 2

    if not os.path.isfile(input_path):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 2

    if os.path.exists(output_path):
        print(f"Error: output already exists: {args.output}", file=sys.stderr)
        return 2

    try:
        report_bytes = Path(input_path).read_bytes()
        derived = rescore(report_bytes)
        derived["source_report"] = os.path.basename(input_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Error: unsupported or unsafe input: {exc}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(derived, f, ensure_ascii=False, indent=2)
    print(f"Derived report written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

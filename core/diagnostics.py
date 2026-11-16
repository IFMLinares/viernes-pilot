"""Opt-in planner diagnostics: route, outcome, stage, error code and duration."""
import json
import sys
import time


ALLOWED_KEYS = {
    "route", "outcome", "stage", "error_code", "duration_ms",
    "filter_area", "filter_scope", "filter_start_date", "filter_end_date", "count",
    "parse_stage", "content_exists", "content_type", "content_length", "content_empty",
    "json_error_line", "json_error_column", "json_error_position",
    "completion_flag", "completion_reason",
}

# Whitelisted completion signals from the Ollama envelope.
_COMPLETION_REASONS = {"stop", "length", "tool_calls"}

_UNSET = object()


def _safe_type_name(value):
    """Sanitized type label for content metadata; never includes value."""
    return type(value).__name__


def _safe_completion_reason(value):
    """Known termination reasons only; unknown strings become 'other'."""
    if not isinstance(value, str):
        return None
    return value if value in _COMPLETION_REASONS else "other"


def _content_metadata(response_json):
    """Return safe content metadata from a parsed envelope, without raw text."""
    meta = {"content_exists": False, "content_type": "null", "content_empty": True}
    message = response_json.get("message") if isinstance(response_json, dict) else None
    if isinstance(message, dict):
        meta["content_exists"] = "content" in message
        content = message.get("content")
        meta["content_type"] = _safe_type_name(content)
        if isinstance(content, (str, list, dict, bytes)):
            meta["content_length"] = len(content)
            meta["content_empty"] = not content
        else:
            meta["content_empty"] = True
    return meta


def parse_metadata(response_json, exc=None):
    """Build privacy-safe parse metadata from an Ollama-style response envelope.

    Returns only primitive, allowlisted fields: stage, content presence/type/length,
    JSON error position, and known completion signals. Raw prompts, answers, message
    content, response bodies and tracebacks are never included.
    """
    meta = {}
    envelope = isinstance(response_json, dict)
    done = response_json.get("done") if envelope else None
    done_reason = response_json.get("done_reason") if envelope else None

    if done is not None or done_reason is not None:
        meta["parse_stage"] = "envelope"
        if isinstance(done, bool):
            meta["completion_flag"] = "done" if done else "not_done"
        reason = _safe_completion_reason(done_reason)
        if reason is not None:
            meta["completion_reason"] = reason
    else:
        meta["parse_stage"] = "content"

    meta.update(_content_metadata(response_json))

    if isinstance(exc, json.JSONDecodeError):
        meta["parse_stage"] = "content"
        meta["json_error_line"] = exc.lineno
        meta["json_error_column"] = exc.colno
        meta["json_error_position"] = exc.pos

    return meta


class Diagnostics:
    """JSON-lines diagnostic emitter writing only bounded, non-private fields."""

    def __init__(self, output=_UNSET):
        if output is _UNSET:
            self.output = sys.stderr
            self.enabled = True
        else:
            self.output = output
            self.enabled = output is not None

    def emit(self, **kwargs):
        if not self.enabled:
            return
        event = {k: v for k, v in kwargs.items() if k in ALLOWED_KEYS and v is not None}
        self.output.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.output.flush()

    def measure(self, start):
        return round((time.perf_counter() - start) * 1000)

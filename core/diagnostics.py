"""Opt-in planner diagnostics: route, outcome, stage, error code and duration."""
import json
import sys
import time


ALLOWED_KEYS = {
    "route", "outcome", "stage", "error_code", "duration_ms",
    "filter_area", "filter_scope", "filter_start_date", "filter_end_date", "count",
}

_UNSET = object()


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

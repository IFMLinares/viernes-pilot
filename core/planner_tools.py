"""Read-only planner tools. No configuration, storage, network or model access."""
import copy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CARACAS = ZoneInfo("America/Caracas")


class ToolError(ValueError):
    """An unregistered tool or invalid invocation was rejected before execution."""


def reference_time(today=None, clock=None):
    """One aware Caracas instant; explicit dates retain the existing test seam."""
    if today is not None:
        return datetime.combine(today, time.min, tzinfo=CARACAS)
    instant = (clock or (lambda: datetime.now(CARACAS)))()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ToolError("The planner clock must return an aware datetime.")
    return instant.astimezone(CARACAS)


class ClockContext(dict):
    """A trusted snapshot shared by the planner, interpreter and tool execution."""

    def __init__(self, instant):
        self.instant = instant
        super().__init__(role="system", content=(
            f"Trusted current datetime: {instant.isoformat()}. Timezone: America/Caracas. "
            f"Current date: {instant.date().isoformat()}. ISO weekday: {instant.isoweekday()}. "
            "A calendar date without a year uses this current year, even if already past. "
            "Never silently move it to next year. Next weekday means strictly after today."
        ))


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    handler: object


class ToolRegistry:
    """Only explicitly registered pure handlers can be invoked by name.

    Each handler owns argument validation; schema is an advertisement, not a
    replacement for host validation. Registry entries are developer-owned.
    """

    def __init__(self, tools):
        self._tools = {}
        for tool in tools:
            if not isinstance(tool, Tool) or not tool.name or tool.name in self._tools or not callable(tool.handler):
                raise ToolError("Invalid or duplicate tool registration.")
            self._tools[tool.name] = tool

    def definitions(self):
        return [{"name": item.name, "description": item.description,
                 "parameters": copy.deepcopy(item.parameters)} for item in self._tools.values()]

    def request_schema(self):
        return {"oneOf": [{"type": "object", "properties": {
            "name": {"const": item.name}, "arguments": copy.deepcopy(item.parameters)},
            "required": ["name", "arguments"], "additionalProperties": False}
            for item in self._tools.values()]}

    def execute(self, name, arguments, instant):
        if not isinstance(name, str) or name not in self._tools:
            raise ToolError("Unknown planner tool.")
        if not isinstance(arguments, dict):
            raise ToolError("Tool arguments must be an object.")
        instant = reference_time(clock=lambda: instant)
        return self._tools[name].handler(copy.deepcopy(arguments), instant)


def _integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ToolError("Invalid integer date argument.")
    return value


def resolve_date(arguments, instant):
    """Resolve model-extracted references to the same event, not model arithmetic."""
    if set(arguments) != {"references"}:
        raise ToolError("Expected date references only.")
    references = arguments["references"]
    if not isinstance(references, list) or not 1 <= len(references) <= 4:
        raise ToolError("Expected between one and four date references.")
    anchor = instant.date()
    dates = []
    for item in references:
        if not isinstance(item, dict):
            raise ToolError("Each date reference must be an object.")
        kind = item.get("kind")
        if kind == "calendar":
            if not {"kind", "day", "month"} <= item.keys() or set(item) - {"kind", "day", "month", "year"}:
                raise ToolError("Calendar references require day and month, with optional year.")
            year = _integer(item.get("year", anchor.year), 1, 9999)
            month = _integer(item["month"], 1, 12)
            day = _integer(item["day"], 1, 31)
            try:
                resolved = date(year, month, day)
            except ValueError:
                return {"status": "invalid", "reference_date": anchor.isoformat(), "timezone": "America/Caracas"}
        elif kind == "relative_days" and set(item) == {"kind", "days"}:
            offset = _integer(item["days"], -36600, 36600)
            try:
                resolved = anchor + timedelta(days=offset)
            except OverflowError as exc:
                raise ToolError("Date calculation exceeds calendar bounds.") from exc
        elif kind == "weekday" and set(item) == {"kind", "weekday"}:
            weekday = _integer(item["weekday"], 1, 7)
            try:
                resolved = anchor + timedelta(days=(weekday - anchor.isoweekday()) % 7 or 7)
            except OverflowError as exc:
                raise ToolError("Date calculation exceeds calendar bounds.") from exc
        else:
            raise ToolError("Invalid date reference kind or fields.")
        dates.append(resolved.isoformat())
    unique = list(dict.fromkeys(dates))
    result = {"reference_date": anchor.isoformat(), "timezone": "America/Caracas"}
    if len(unique) != 1:
        return {**result, "status": "conflict", "dates": unique}
    return {**result, "status": "resolved", "date": unique[0]}


def default_registry():
    reference = {"oneOf": [
        {"type": "object", "properties": {"kind": {"const": "calendar"},
         "day": {"type": "integer", "minimum": 1, "maximum": 31},
         "month": {"type": "integer", "minimum": 1, "maximum": 12},
         "year": {"type": "integer", "minimum": 1, "maximum": 9999}},
         "required": ["kind", "day", "month"], "additionalProperties": False},
        {"type": "object", "properties": {"kind": {"const": "relative_days"},
         "days": {"type": "integer", "minimum": -36600, "maximum": 36600}},
         "required": ["kind", "days"], "additionalProperties": False},
        {"type": "object", "properties": {"kind": {"const": "weekday"},
         "weekday": {"type": "integer", "minimum": 1, "maximum": 7}},
         "required": ["kind", "weekday"], "additionalProperties": False},
    ]}
    return ToolRegistry([Tool("resolve_date", (
        "Resolve a date using the trusted Caracas clock. Use for calendar deadlines (omit year if absent), "
        "relative days (today=0, tomorrow=1, within three days=3), and next weekday (ISO Monday=1). "
        "Include ALL references to the SAME event together to detect contradictions; never choose one silently. "
        "Not for independent events or query ranges. Returns resolved, conflict, or invalid."
    ), {"type": "object", "properties": {"references": {
        "type": "array", "minItems": 1, "maxItems": 4, "items": reference}},
        "required": ["references"], "additionalProperties": False}, resolve_date)])

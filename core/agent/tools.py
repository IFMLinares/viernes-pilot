"""Explicit host registration, strict schema subset and deny-by-default tool execution."""
from dataclasses import dataclass
import hashlib
import math

from core.deadlines import deadline
from .contracts import AgentError, clone, json_bytes, valid_name

EFFECTS = frozenset({"read", "prepare", "write", "external"})


def check_schema(schema):
    if not isinstance(schema, dict) or schema.get("type") not in (
            "object", "array", "string", "integer", "number", "boolean", "null"):
        raise ValueError("Unsupported schema type.")
    kind = schema["type"]
    extra = {"object": {"properties", "required", "additionalProperties"}, "array": {"items", "minItems", "maxItems"},
             "string": {"minLength", "maxLength"}, "integer": {"minimum", "maximum"},
             "number": {"minimum", "maximum"}}.get(kind, set())
    if set(schema) - ({"type", "description", "enum"} | extra):
        raise ValueError("Unsupported schema keyword.")
    if "description" in schema and not isinstance(schema["description"], str):
        raise ValueError("Invalid schema description.")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("Invalid enum.")
    if kind == "object":
        properties, required = schema.get("properties", {}), schema.get("required", [])
        if (not isinstance(properties, dict) or not all(isinstance(key, str) for key in properties)
                or not isinstance(required, list) or not all(isinstance(key, str) for key in required)
                or not set(required) <= set(properties) or schema.get("additionalProperties") is not False):
            raise ValueError("Object schemas must declare closed properties.")
        for child in properties.values():
            check_schema(child)
    if kind == "array":
        check_schema(schema.get("items"))
    for key in ("minItems", "maxItems", "minLength", "maxLength"):
        if key in schema and (type(schema[key]) is not int or schema[key] < 0):
            raise ValueError("Invalid schema size bound.")
    for key in ("minimum", "maximum"):
        if key in schema and (type(schema[key]) not in (int, float) or not math.isfinite(schema[key])):
            raise ValueError("Invalid numeric schema bound.")


def validate(value, schema):
    kind = schema["type"]
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    if kind == "number":
        valid = type(value) in (int, float) and math.isfinite(value)
    else:
        valid = type(value) is types[kind]
    if not valid:
        raise ValueError("Invalid value type.")
    if "enum" in schema and json_bytes(value) not in [json_bytes(item) for item in schema["enum"]]:
        raise ValueError("Value not in enum.")
    if kind == "object":
        properties = schema.get("properties", {})
        if set(value) - set(properties) or not set(schema.get("required", [])) <= set(value):
            raise ValueError("Unknown or missing properties.")
        for key, item in value.items():
            validate(item, properties[key])
    if kind == "array":
        for item in value:
            validate(item, schema["items"])
    if kind in ("array", "string"):
        suffix = "Items" if kind == "array" else "Length"
        if not schema.get("min" + suffix, 0) <= len(value) <= schema.get("max" + suffix, float("inf")):
            raise ValueError("Value exceeds size bounds.")
    if kind in ("integer", "number") and not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
        raise ValueError("Value exceeds numeric bounds.")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    result_schema: dict
    handler: object
    effects: frozenset
    scope: str
    version: str = "1"
    max_result_bytes: int = 4096

    def __post_init__(self):
        if (not valid_name(self.name) or not isinstance(self.description, str) or len(self.description) > 1024
                or not callable(self.handler) or not isinstance(self.scope, str) or not 0 < len(self.scope) <= 128
                or not isinstance(self.version, str) or not self.version
                or type(self.max_result_bytes) is not int or self.max_result_bytes <= 0
                or not isinstance(self.effects, frozenset) or not self.effects or not self.effects <= EFFECTS):
            raise ValueError("Invalid tool registration.")
        for field in ("parameters", "result_schema"):
            copied = clone(getattr(self, field))
            check_schema(copied)
            object.__setattr__(self, field, copied)
        if self.parameters["type"] != "object":
            raise ValueError("Tool parameters must be an object schema.")


@dataclass(frozen=True)
class Policy:
    allowed_tools: frozenset = frozenset()
    allowed_scopes: frozenset = frozenset()

    def __post_init__(self):
        if (not isinstance(self.allowed_tools, frozenset) or not all(valid_name(name) for name in self.allowed_tools)
                or not isinstance(self.allowed_scopes, frozenset)
                or not all(isinstance(scope, str) and scope for scope in self.allowed_scopes)):
            raise ValueError("Policy grants must be explicit immutable sets.")

    def authorize(self, spec, context=None, arguments=None):
        return (spec.name in self.allowed_tools and spec.scope in self.allowed_scopes
                and spec.effects <= {"read", "prepare"})


class ToolExecutor:
    def __init__(self, tools=()):
        self._tools = {}
        for spec in tools:
            if not isinstance(spec, ToolSpec) or spec.name in self._tools:
                raise ValueError("Invalid or duplicate tool registration.")
            # Snapshot schemas so mutating an advertisement cannot change validation.
            self._tools[spec.name] = ToolSpec(**vars(spec))

    def definitions(self, policy):
        return [{"type": "function", "function": {"name": spec.name, "description": spec.description,
                                                    "parameters": clone(spec.parameters)}}
                for spec in self._tools.values() if spec.effects <= {"read", "prepare"} and policy.authorize(spec)]

    def execute(self, call, context):
        tool, metadata = "unknown", {}
        try:
            context.budget.reserve("tool_calls")
            function = call.get("function", {}) if isinstance(call, dict) else {}
            spec = self._tools.get(function.get("name"))
            if spec is None:
                raise AgentError("UNKNOWN_TOOL", recoverable=True)
            tool = spec.name
            if (not spec.effects <= {"read", "prepare"}
                    or not context.policy.authorize(spec, context, function.get("arguments"))):
                raise AgentError("UNAUTHORIZED")
            arguments = function.get("arguments")
            try:
                encoded = json_bytes(arguments)
                metadata = {"args_bytes": len(encoded), "args_sha256": hashlib.sha256(encoded).hexdigest()}
                context.budget.check_context(arguments)
                validate(arguments, spec.parameters)
            except (AgentError, ValueError, TypeError, RecursionError) as exc:
                raise AgentError("INVALID_ARGUMENTS", recoverable=True) from exc
            remaining = context.budget.remaining()
            resource = "time" if remaining <= context.budget.limits.tool_timeout else "tool_time"
            with deadline(min(remaining, context.budget.limits.tool_timeout),
                          lambda: AgentError("BUDGET_EXCEEDED", resource=resource),
                          lambda: AgentError("DEADLINE_UNAVAILABLE")):
                result = spec.handler(**clone(arguments))
            context.budget.check_time()
            try:
                encoded = json_bytes(result)
                metadata.update(result_bytes=len(encoded), result_sha256=hashlib.sha256(encoded).hexdigest())
                validate(result, spec.result_schema)
                if len(encoded) > spec.max_result_bytes:
                    raise ValueError("Tool result too large.")
            except (AgentError, ValueError, TypeError, RecursionError) as exc:
                raise AgentError("INVALID_RESULT", recoverable=True) from exc
            context.emit("tool", tool=tool, outcome="ok", **metadata)
            return {"ok": True, "data": clone(result), "error": None,
                    "meta": {"call_id": f"call-{context.budget.tool_calls}"}}
        except AgentError as exc:
            error = exc
        except Exception:
            error = AgentError("TOOL_FAILED", recoverable=True)
        context.emit("tool", tool=tool, outcome="error", code=error.code, **metadata)
        return {"ok": False, "data": None, "error": error.as_dict(),
                "meta": {"call_id": f"call-{context.budget.tool_calls}"}}

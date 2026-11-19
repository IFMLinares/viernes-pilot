"""Pure in-memory contracts, bounded JSON state and process-local execution data."""
from dataclasses import dataclass, field
import json
import math
import time
from typing import Protocol
from uuid import uuid4

MESSAGES = {
    "INVALID_DATA": "Expected finite JSON data.",
    "INVALID_STATE": "Conversation state is incompatible or incomplete.",
    "MODEL_PROTOCOL": "The model response is malformed.",
    "MODEL_INTERRUPTED": "The model did not complete the request.",
    "MODEL_UNAVAILABLE": "The model request failed.",
    "BUDGET_EXCEEDED": "An execution budget was exhausted.",
    "CONTEXT_LIMIT": "The context or response exceeds its size limit.",
    "UNKNOWN_TOOL": "The requested tool is not registered.",
    "UNAUTHORIZED": "This tool is not authorized.",
    "INVALID_ARGUMENTS": "Tool arguments do not satisfy the declared schema.",
    "INVALID_RESULT": "The tool result does not satisfy the declared schema.",
    "TOOL_FAILED": "The tool could not complete its operation.",
    "DEADLINE_UNAVAILABLE": "A hard execution deadline is unavailable.",
}


class AgentError(Exception):
    def __init__(self, code, recoverable=False, resource=None):
        self.code = code if code in MESSAGES else "TOOL_FAILED"
        self.recoverable, self.resource = bool(recoverable), resource
        super().__init__(MESSAGES[self.code])

    def as_dict(self):
        result = {"code": self.code, "message": MESSAGES[self.code], "recoverable": self.recoverable}
        if self.resource in ("requests", "iterations", "tool_calls", "time", "request_time", "tool_time"):
            result["resource"] = self.resource
        return result


def json_bytes(value):
    try:
        return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise AgentError("INVALID_DATA") from exc


def clone(value):
    return json.loads(json_bytes(value))


def valid_name(name):
    return isinstance(name, str) and 0 < len(name) <= 64 and name.isascii() and name.isidentifier() and not name.startswith("_")


def assistant_message(message):
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise AgentError("MODEL_PROTOCOL")
    content, calls = message.get("content", ""), message.get("tool_calls", [])
    if calls is None:
        calls = []
    if not isinstance(content, str) or not isinstance(calls, list) or not (content.strip() or calls):
        raise AgentError("MODEL_PROTOCOL")
    normalized = {"role": "assistant", "content": content}
    if calls:
        normalized["tool_calls"] = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if (not isinstance(function, dict) or not valid_name(function.get("name"))
                    or not isinstance(function.get("arguments"), dict)
                    or call.get("type", "function") != "function"):
                raise AgentError("MODEL_PROTOCOL")
            normalized["tool_calls"].append({"function": {
                "name": function["name"], "arguments": clone(function["arguments"])}})
    return normalized


@dataclass(frozen=True)
class Limits:
    max_iterations: int = 6
    max_requests: int = 6
    max_tool_calls: int = 6
    max_seconds: float = 30
    request_timeout: float = 10
    tool_timeout: float = 2
    max_context_bytes: int = 32768
    max_response_bytes: int = 16384

    def __post_init__(self):
        for name, value in vars(self).items():
            if name in ("max_seconds", "request_timeout", "tool_timeout"):
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("Time limits must be finite and positive.")
            elif type(value) is not int or value < 0:
                raise ValueError("Count and size limits must be nonnegative integers.")


@dataclass
class Budget:
    limits: Limits
    requests: int = field(default=0, init=False)
    iterations: int = field(default=0, init=False)
    tool_calls: int = field(default=0, init=False)
    deadline: float = field(init=False)

    def __post_init__(self):
        self.deadline = time.monotonic() + self.limits.max_seconds

    def remaining(self):
        return max(0, self.deadline - time.monotonic())

    def check_time(self):
        if self.remaining() <= 0:
            raise AgentError("BUDGET_EXCEEDED", resource="time")

    def reserve(self, resource):
        self.check_time()
        if resource not in ("requests", "iterations", "tool_calls"):
            raise ValueError("Unknown budget resource.")
        if getattr(self, resource) >= getattr(self.limits, "max_" + resource):
            raise AgentError("BUDGET_EXCEEDED", resource=resource)
        setattr(self, resource, getattr(self, resource) + 1)

    def check_context(self, value):
        if len(json_bytes(value)) > self.limits.max_context_bytes:
            raise AgentError("CONTEXT_LIMIT")


class ModelAdapter(Protocol):
    def next(self, messages: list, tool_specs: list, budget: Budget) -> dict:
        """Return one native assistant message; reserve every outbound request."""
        ...


@dataclass
class ConversationState:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    revision: int = 0
    messages: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    version: int = field(default=1, init=False)

    def to_json(self, max_bytes=65536):
        if (type(self.version) is not int or self.version != 1
                or not isinstance(self.session_id, str) or not 0 < len(self.session_id) <= 128
                or type(self.revision) is not int or self.revision < 0
                or not isinstance(self.data, dict) or not isinstance(self.messages, list)):
            raise AgentError("INVALID_STATE")
        expected, pending = "user", []
        for message in self.messages:
            if not isinstance(message, dict) or message.get("role") != expected:
                raise AgentError("INVALID_STATE")
            if expected == "user":
                if set(message) != {"role", "content"} or not isinstance(message["content"], str) or not message["content"].strip():
                    raise AgentError("INVALID_STATE")
                expected = "assistant"
            elif expected == "assistant":
                normalized = assistant_message(message)
                if normalized != message:
                    raise AgentError("INVALID_STATE")
                pending = [call["function"]["name"] for call in normalized.get("tool_calls", [])]
                expected = "tool" if pending else "user"
            else:
                if (set(message) != {"role", "tool_name", "content"}
                        or message["tool_name"] != pending.pop(0) or not isinstance(message["content"], str)):
                    raise AgentError("INVALID_STATE")
                expected = "tool" if pending else "assistant"
        if expected != "user":
            raise AgentError("INVALID_STATE")
        encoded = json_bytes({"version": self.version, "session_id": self.session_id,
                              "revision": self.revision, "messages": self.messages, "data": self.data})
        if len(encoded) > max_bytes:
            raise AgentError("CONTEXT_LIMIT")
        return encoded.decode("utf-8")

    @classmethod
    def from_json(cls, raw, expected_session_id=None, max_bytes=65536):
        try:
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
                raise AgentError("INVALID_STATE")
            value = json.loads(raw)
            if (not isinstance(value, dict) or set(value) != {"version", "session_id", "revision", "messages", "data"}
                    or type(value["version"]) is not int or value.pop("version") != 1
                    or expected_session_id is not None and value["session_id"] != expected_session_id):
                raise AgentError("INVALID_STATE")
            state = cls(**value)
            state.to_json(max_bytes)
            return state
        except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
            raise AgentError("INVALID_STATE") from exc


@dataclass
class TurnResult:
    state: ConversationState
    answer: str = ""
    error: dict | None = None
    traces: list = field(default_factory=list)

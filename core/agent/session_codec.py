"""Minimized session format. Persisted text is context, never execution authority."""
from dataclasses import dataclass
import json
import re

from .contracts import AgentError, ConversationState, clone, json_bytes, valid_name


ERRORS = {
    "INVALID_SNAPSHOT": "The session snapshot is invalid, incompatible or incomplete.",
    "INCOMPATIBLE_STORE": "The session database version is not supported.",
    "REVISION_CONFLICT": "The revision changed; load the current session before retrying.",
    "NOT_FOUND": "The session does not exist.",
    "STORAGE_ERROR": "The session operation could not be persisted or read.",
    "TURN_ACTIVE": "A started turn must be explicitly interrupted before continuing.",
    "INVALID_TURN": "The turn identity or lifecycle transition does not match.",
    "REVALIDATION_REQUIRED": "Recovered references require a trusted current-data read.",
}


class SessionError(Exception):
    def __init__(self, code):
        self.code = code if code in ERRORS else "STORAGE_ERROR"
        super().__init__(ERRORS[self.code])

    def as_dict(self):
        return {"code": self.code, "message": ERRORS[self.code], "recoverable": True}


def require(condition):
    if not condition:
        raise SessionError("INVALID_SNAPSHOT")


def integer(value, maximum=2**63 - 2):
    return type(value) is int and 0 <= value <= maximum


def text(value, limit=4096):
    return type(value) is str and 0 < len(value) <= limit


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


@dataclass
class SessionRecord:
    state: ConversationState
    status: str = "completed"
    turn_id: str | None = None


class SessionCodec:
    """Fixed bounded allowlist; host-supplied known secrets never leave this object.

    Credential-pattern filtering is defense in depth, not universal secret detection.
    No hashes of removed values are retained. Tool arguments/results are omitted.
    """
    max_bytes = 65536
    max_pairs = 16
    sensitive = frozenset({"password", "passwd", "secret", "token", "apikey",
                           "authorization", "credential", "privatekey", "cookie"})
    credential = re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|authorization|credential)"
        r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+|\bbearer\s+[A-Za-z0-9._~+/=-]+")
    private_key = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)", re.S)

    def __init__(self, secrets=()):
        if not isinstance(secrets, tuple) or not all(text(item) for item in secrets):
            raise ValueError("Known secrets must be nonempty strings in a host-owned tuple.")
        self.secrets = secrets

    def clean(self, value):
        require(type(value) is str and len(value) <= 4096)
        for secret in self.secrets:
            value = value.replace(secret, "[redacted]")
        return self.credential.sub("[redacted]", self.private_key.sub("[redacted]", value))

    def sensitive_key(self, key):
        normalized = key.lower().replace("_", "").replace("-", "")
        return any(term in normalized for term in self.sensitive)

    def context(self, data, *, strict=False):
        require(type(data) is dict)
        if strict:
            require(not set(data) - {"goal", "draft", "references"})
        result = {}
        if "goal" in data:
            require(text(data["goal"]))
            result["goal"] = self.clean(data["goal"])
        if "draft" in data:
            draft = data["draft"]
            require(type(draft) is dict and set(draft) == {"intent", "revision", "fields", "reference_ids"})
            require(text(draft["intent"], 64) and integer(draft["revision"]))
            fields, ids = draft["fields"], draft["reference_ids"]
            require(type(fields) is dict and len(fields) <= 32)
            require(type(ids) is list and len(ids) <= 64 and all(
                text(i, 128) and self.clean(i) == i for i in ids))
            cleaned = {}
            for key, value in fields.items():
                require(text(key, 64))
                if self.sensitive_key(key):
                    require(not strict)
                    continue
                require(value is None or type(value) in (str, bool, int))
                if type(value) is int:
                    require(integer(abs(value)))
                require(self.clean(key) == key)
                cleaned[key] = self.clean(value) if type(value) is str else value
            result["draft"] = {"intent": self.clean(draft["intent"]), "revision": draft["revision"],
                               "fields": cleaned, "reference_ids": [self.clean(i) for i in ids]}
        if "references" in data:
            refs, occupied = data["references"], set()
            require(type(refs) is list and len(refs) <= 64)
            result["references"] = []
            keys = {"set_id", "position", "resource_id", "scope", "tool", "tool_version", "source_revision", "label"}
            for ref in refs:
                require(type(ref) is dict and set(ref) == keys)
                require(integer(ref["position"], 64) and ref["position"] > 0)
                require(all(text(ref[key], 128 if key != "label" else 512) for key in keys - {"position"}))
                require(valid_name(ref["tool"]))
                identity = (ref["set_id"], ref["position"])
                require(identity not in occupied)
                occupied.add(identity)
                # Never redact an identifier into a different entity identity.
                require(all(self.clean(ref[key]) == ref[key] for key in keys - {"position", "label"}))
                result["references"].append({**ref, "label": self.clean(ref["label"])})
            positions = {}
            for ref in result["references"]:
                expected = positions.get(ref["set_id"], 0) + 1
                require(ref["position"] == expected)
                positions[ref["set_id"]] = expected
        if "draft" in result:
            require(set(result["draft"]["reference_ids"]) <= {
                ref["resource_id"] for ref in result.get("references", [])})
        return result

    def encode(self, state):
        try:
            require(isinstance(state, ConversationState))
            state.to_json(self.max_bytes)
            require(self.clean(state.session_id) == state.session_id)
            pairs, user = [], None
            for message in state.messages:
                if message["role"] == "user":
                    user = self.clean(message["content"])
                elif message["role"] == "assistant" and not message.get("tool_calls"):
                    pairs.append([{"role": "user", "content": user},
                                  {"role": "assistant", "content": self.clean(message["content"])}])
            projected = ConversationState(session_id=state.session_id, revision=state.revision,
                messages=[m for pair in pairs[-self.max_pairs:] for m in pair], data=self.context(state.data))
            raw = json_bytes({"version": 1, "state": json.loads(projected.to_json(self.max_bytes))})
            require(len(raw) <= self.max_bytes)
            return raw.decode("utf-8")
        except (AgentError, ValueError, TypeError, RecursionError, UnicodeError) as exc:
            raise SessionError("INVALID_SNAPSHOT") from exc

    def decode(self, raw, expected_session_id=None):
        try:
            require(type(raw) is str and len(raw.encode("utf-8")) <= self.max_bytes)
            value = json.loads(raw, object_pairs_hook=unique_object,
                               parse_constant=lambda _: require(False))
            require(type(value) is dict and set(value) == {"version", "state"})
            require(type(value["version"]) is int and value["version"] == 1)
            state = ConversationState.from_json(json_bytes(value["state"]).decode("utf-8"),
                                                expected_session_id, self.max_bytes)
            require(self.clean(state.session_id) == state.session_id)
            require(integer(state.revision) and len(state.messages) <= self.max_pairs * 2)
            require(all(set(m) == {"role", "content"} and text(m["content"]) for m in state.messages))
            state.data = self.context(state.data, strict=True)
            # Also applies the current host's exclusion policy to older exports/backups.
            for message in state.messages:
                message["content"] = self.clean(message["content"])
            return state
        except (AgentError, ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
            raise SessionError("INVALID_SNAPSHOT") from exc

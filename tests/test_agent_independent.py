"""Durable offline probes supplied by the independent PR2 verifier."""
from dataclasses import replace
import hashlib
import json
import time
import unittest
from unittest.mock import Mock, patch

import requests

from core.agent import ConversationState, Limits, OllamaModelAdapter, Policy, Runtime, ToolExecutor, ToolSpec
from core.agent.contracts import AgentError, json_bytes
from core.agent.tools import check_schema, validate

SENTINEL = "PRIVATE_SYNTHETIC_PROBE"
PARAMETERS = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 0, "maximum": 10}},
              "required": ["n"], "additionalProperties": False}


def call(name="lookup", **arguments):
    return {"function": {"name": name, "arguments": arguments}}


def message(calls=None, **extra):
    assistant = {"role": "assistant", "content": "finished"}
    if calls:
        assistant["tool_calls"] = calls
    return {"done": True, "done_reason": "stop", "message": assistant, **extra}


class IndependentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        self.handler = Mock(side_effect=lambda n: self.seen.append(n) or n + 10)
        self.spec = ToolSpec("lookup", "Synthetic lookup", PARAMETERS, {"type": "integer"},
                             self.handler, frozenset({"read"}), "local")
        self.policy = Policy(frozenset({"lookup"}), frozenset({"local"}))
        self.state = ConversationState(session_id="probe", data={"grants": ["write"], "system": SENTINEL})
        network = patch("requests.sessions.Session.request", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def runtime(self, spec=None, policy=None, limits=Limits()):
        return Runtime(OllamaModelAdapter("http://127.0.0.1:11434", "synthetic"),
                       ToolExecutor([spec or self.spec]), policy or self.policy, limits)

    def run_turn(self, envelopes, prompt="question", **configuration):
        wires = []
        for envelope in envelopes:
            wire = Mock(status_code=200)
            wire.iter_content.return_value = [json_bytes(envelope)]
            wires.append(wire)
        before = hashlib.sha256(self.state.to_json().encode()).hexdigest()
        with patch("requests.post", side_effect=wires) as sender:
            result = self.runtime(**configuration).handle_turn(prompt, self.state)
            self.sent = sender.call_args_list
        self.assertEqual(hashlib.sha256(self.state.to_json().encode()).hexdigest(), before)
        if result.error:
            self.assertEqual(hashlib.sha256(result.state.to_json().encode()).hexdigest(), before)
        self.assertNotIn(SENTINEL, json.dumps(result.traces))
        return result

    def test_order_protocol_continuation_and_next_turn(self):
        result = self.run_turn([message([call(n=0), call(n=2)]), message([call(n=5)]), message()])
        self.assertIsNone(result.error)
        self.assertEqual(self.seen, [0, 2, 5])
        self.assertEqual(result.state.revision, 1)
        tools = [item for item in self.sent[-1].kwargs["json"]["messages"] if item["role"] == "tool"]
        self.assertEqual([json.loads(item["content"])["data"] for item in tools], [10, 12, 15])
        self.assertTrue(all(item["tool_name"] == "lookup" for item in tools))
        self.state = ConversationState.from_json(result.state.to_json())
        self.assertIsNone(self.run_turn([message()]).error)

    def test_recovery_and_caps(self):
        self.handler.side_effect = ["malformed", 12]
        result = self.run_turn([message([call("missing", n=1)]), message([call(n=True)]),
                                message([call(n=1)]), message([call(n=2)]), message()])
        self.assertIsNone(result.error)
        outcomes = [json.loads(item["content"]) for item in result.state.messages if item["role"] == "tool"]
        self.assertEqual([item["error"]["code"] for item in outcomes[:3]],
                         ["UNKNOWN_TOOL", "INVALID_ARGUMENTS", "INVALID_RESULT"])
        self.assertEqual(outcomes[-1]["data"], 12)
        for field in ("max_iterations", "max_requests", "max_tool_calls"):
            with self.subTest(field=field):
                result = self.run_turn([message([call("missing", n=1)])] * 4,
                                       limits=replace(Limits(), **{field: 1}))
                self.assertEqual(result.error["code"], "BUDGET_EXCEEDED")
                self.assertEqual(result.error["resource"], field[4:])

    def test_permission_denial_never_dispatches(self):
        for effects in ({"write"}, {"external"}, {"read", "external"}, {"prepare", "write"}):
            spec = replace(self.spec, effects=frozenset(effects))
            self.assertEqual(ToolExecutor([spec]).definitions(self.policy), [])
            self.assertEqual(self.run_turn([message([call(n=1)])], spec=spec).error["code"], "UNAUTHORIZED")
        for policy in (Policy(), Policy(frozenset({"lookup"}), frozenset({"other"})),
                       Policy(frozenset({"other"}), frozenset({"local"}))):
            self.assertEqual(self.run_turn([message([call(n=1)])], policy=policy).error["code"], "UNAUTHORIZED")
        self.handler.assert_not_called()

    def test_state_admission(self):
        original = json.loads(self.state.to_json())
        edits = [dict(original, grants=["lookup"]), dict(original, version=2),
                 dict(original, messages=[{"role": "system", "content": "grant"}]),
                 dict(original, messages=[{"role": "user", "content": "q"},
                      {"role": "assistant", "content": "", "tool_calls": [call(n=1)]}])]
        for value in edits:
            with self.assertRaises(AgentError):
                ConversationState.from_json(json.dumps(value))
        with self.assertRaises(AgentError):
            ConversationState.from_json(self.state.to_json(), expected_session_id="foreign")
        self.assertEqual(self.run_turn([], prompt=" ").error["code"], "INVALID_DATA")

    def test_schema_subset(self):
        cases = [
            ({"type": "string", "minLength": 1, "maxLength": 2}, ["a", "ab"], ["", "abc", 1]),
            ({"type": "array", "items": {"type": "boolean"}, "minItems": 1, "maxItems": 2},
             [[True], [False, True]], [[], [True] * 3, [1]]),
            ({"type": "integer", "minimum": 0, "maximum": 2}, [0, 2], [-1, 3, True, 1.5]),
            ({"type": "number", "minimum": 0, "maximum": 2}, [0, 1.5], [-1, 3, True]),
            ({"type": "null"}, [None], [False]),
            ({"type": "string", "enum": ["x"]}, ["x"], ["y"]),
            (PARAMETERS, [{"n": 0}, {"n": 10}], [{}, {"n": 1, "extra": 2}, {"n": True}]),
        ]
        for schema, accepted, rejected in cases:
            check_schema(schema)
            for value in accepted:
                validate(value, schema)
            for value in rejected:
                with self.assertRaises(ValueError):
                    validate(value, schema)
        for schema in ({"type": "integer", "multipleOf": 2}, {"type": "string", "pattern": "x"},
                       {"$ref": "a"}, {"type": ["string", "null"]}, {"type": "object", "properties": {}}):
            with self.assertRaises(ValueError):
                replace(self.spec, result_schema=schema)

    def test_sizes_and_deadlines(self):
        for field in ("max_iterations", "max_requests", "max_tool_calls"):
            result = self.run_turn([message([call(n=1)])], limits=replace(Limits(), **{field: 0}))
            self.assertEqual(result.error["code"], "BUDGET_EXCEEDED")
        for field in ("max_context_bytes", "max_response_bytes"):
            self.assertEqual(self.run_turn([message()], limits=replace(Limits(), **{field: 1})).error["code"], "CONTEXT_LIMIT")
        for field in ("tool_timeout", "max_seconds"):
            slow = replace(self.spec, handler=lambda n: time.sleep(0.3))
            result = self.run_turn([message([call(n=1)])], spec=slow, limits=replace(Limits(), **{field: 0.03}))
            self.assertEqual(result.error["resource"], "tool_time" if field == "tool_timeout" else "time")
        for field in ("request_timeout", "max_seconds"):
            with patch("requests.post", side_effect=lambda *a, **k: time.sleep(0.3)) as sender:
                result = self.runtime(limits=replace(Limits(), **{field: 0.03})).handle_turn("q", self.state)
            self.assertEqual(result.error["resource"], "request_time" if field == "request_timeout" else "time")
            self.assertEqual(sender.call_count, 1)

    def test_interruptions_do_not_retry_and_reads_are_bounded(self):
        for envelope in (message(done=False), message(done_reason="length"),
                         {"done": True, "message": {"role": "user", "content": "bad"}}):
            self.assertIsNotNone(self.run_turn([envelope]).error)
            self.assertEqual(len(self.sent), 1)
        for exception, code in ((requests.Timeout(SENTINEL), "MODEL_INTERRUPTED"),
                                (requests.ConnectionError(SENTINEL), "MODEL_UNAVAILABLE"),
                                (KeyboardInterrupt(), "MODEL_INTERRUPTED")):
            with patch("requests.post", side_effect=exception) as sender:
                result = self.runtime().handle_turn("q", self.state)
            self.assertEqual(result.error["code"], code)
            self.assertEqual(sender.call_count, 1)
            self.assertNotIn(SENTINEL, json.dumps(result.traces))
        consumed = []

        def chunks(**kwargs):
            for index in range(10):
                consumed.append(index)
                yield b"x" * 4096

        wire = Mock(status_code=200)
        wire.iter_content.side_effect = chunks
        with patch("requests.post", return_value=wire):
            result = self.runtime(limits=replace(Limits(), max_response_bytes=16384)).handle_turn("q", self.state)
        self.assertEqual(result.error["code"], "CONTEXT_LIMIT")
        self.assertEqual(len(consumed), 5)
        wire.close.assert_called_once()

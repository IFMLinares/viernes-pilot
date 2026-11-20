"""Native Ollama protocol and generic orchestration, entirely offline."""
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import Mock, patch

import requests

from core.agent.contracts import ConversationState, Limits
from core.agent.ollama import OllamaModelAdapter
from core.agent.runtime import Runtime
from core.agent.tools import Policy, ToolExecutor, ToolSpec


def response(content="Done", calls=None, **extra):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {"done": True, "done_reason": "stop", "message": message, **extra}


def call(name="increment", arguments=None):
    return {"function": {"name": name, "arguments": {"value": 1} if arguments is None else arguments}}


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.state = ConversationState(session_id="synthetic", data={"goal": "example"})
        self.handler = Mock(side_effect=lambda value: value + 1)
        self.spec = ToolSpec("increment", "Synthetic computation", {
            "type": "object", "properties": {"value": {"type": "integer"}},
            "required": ["value"], "additionalProperties": False}, {"type": "integer"},
            self.handler, frozenset({"read"}), "synthetic")
        self.policy = Policy(frozenset({"increment"}), frozenset({"synthetic"}))
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Real network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def runtime(self, limits=Limits(), spec=None):
        return Runtime(OllamaModelAdapter("http://127.0.0.1:11434", "synthetic"),
                       ToolExecutor([spec or self.spec]), self.policy, limits)

    def run_messages(self, messages, runtime=None):
        responses = []
        for message in messages:
            wire = Mock(status_code=200)
            wire.iter_content.return_value = [json.dumps(message).encode()]
            responses.append(wire)
        with patch("requests.post", side_effect=responses) as sender:
            result = (runtime or self.runtime()).handle_turn("Synthetic question", self.state)
            self.sent = sender.call_args_list
        return result

    def test_native_sequential_calls_use_real_results_in_tool_role(self):
        result = self.run_messages([response("", [call()]), response("", [call(arguments={"value": 2})]), response()])
        self.assertIsNone(result.error)
        self.assertEqual(result.answer, "Done")
        self.assertEqual(self.handler.call_args_list[0].kwargs, {"value": 1})
        self.assertEqual(self.handler.call_args_list[1].kwargs, {"value": 2})
        second = self.sent[1].kwargs["json"]
        self.assertNotIn("format", second)
        self.assertEqual(second["messages"][-2]["tool_calls"], [call()])
        self.assertEqual(second["messages"][-1]["role"], "tool")
        self.assertEqual(second["messages"][-1]["tool_name"], "increment")
        self.assertEqual(json.loads(second["messages"][-1]["content"])["data"], 2)
        self.assertEqual(self.state.messages, [])
        self.assertEqual(ConversationState.from_json(result.state.to_json()).messages, result.state.messages)
        self.assertEqual(result.traces[-1]["requests"], 3)

    def test_unknown_and_invalid_calls_can_recover_within_budget(self):
        result = self.run_messages([response("", [call("missing")]), response("", [call(arguments={"value": True})]),
                                    response("", [call()]), response()])
        self.assertIsNone(result.error)
        self.assertEqual(self.handler.call_count, 1)
        outcomes = [json.loads(item["content"]) for item in result.state.messages if item["role"] == "tool"]
        self.assertEqual([item["error"]["code"] for item in outcomes[:2]], ["UNKNOWN_TOOL", "INVALID_ARGUMENTS"])

    def test_multiple_calls_in_one_message_are_executed_in_order(self):
        result = self.run_messages([response("", [call(), call(arguments={"value": 4})]), response()])
        self.assertIsNone(result.error)
        self.assertEqual([entry.kwargs["value"] for entry in self.handler.call_args_list], [1, 4])

    def test_write_and_external_are_denied_even_with_restored_claims(self):
        self.state.data["grants"] = ["write", "external"]
        self.state = ConversationState.from_json(self.state.to_json())
        for effects in ({"write"}, {"external"}, {"read", "external"}):
            with self.subTest(effects=effects):
                before = self.state.to_json()
                result = self.run_messages([response("", [call()])], self.runtime(spec=replace(self.spec, effects=frozenset(effects))))
                self.assertEqual(result.error["code"], "UNAUTHORIZED")
                self.assertEqual(result.state.to_json(), before)
        self.handler.assert_not_called()

    def test_each_count_limit_stops_before_an_extra_request_or_handler(self):
        for field in ("max_iterations", "max_requests", "max_tool_calls"):
            with self.subTest(field=field):
                runtime = self.runtime(replace(Limits(), **{field: 0}))
                result = self.run_messages([response("", [call()])], runtime)
                self.assertEqual(result.error["code"], "BUDGET_EXCEEDED")
                self.assertEqual(result.error["resource"], field[4:])
                self.assertEqual(len(self.sent), 1 if field == "max_tool_calls" else 0)
                self.assertEqual(result.state.to_json(), self.state.to_json())
        self.handler.assert_not_called()

    def test_context_schema_and_response_limits_prevent_tool_execution(self):
        result = self.run_messages([], self.runtime(replace(Limits(), max_context_bytes=1)))
        self.assertEqual(result.error["code"], "CONTEXT_LIMIT")
        self.assertEqual(self.sent, [])
        result = self.run_messages([response("x" * 1000, [call()])], self.runtime(replace(Limits(), max_response_bytes=100)))
        self.assertEqual(result.error["code"], "CONTEXT_LIMIT")
        self.handler.assert_not_called()

    def test_model_interruptions_and_partial_generation_never_commit_state(self):
        for failure in (requests.Timeout("SENSITIVE"), requests.ConnectionError("SENSITIVE"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), patch("requests.post", side_effect=failure):
                result = self.runtime().handle_turn("SENSITIVE question", self.state)
            self.assertIsNotNone(result.error)
            self.assertNotIn("SENSITIVE", json.dumps(result.traces))
            self.assertEqual(result.state.to_json(), self.state.to_json())
        for envelope in (response(done=False), response(done_reason="length"), response(calls=False)):
            self.assertIsNotNone(self.run_messages([envelope]).error)

    def test_real_wall_timeout_stops_stalled_mock_transport(self):
        with patch("requests.post", side_effect=lambda *a, **k: time.sleep(1)):
            result = self.runtime(replace(Limits(), request_timeout=0.02)).handle_turn("Synthetic", self.state)
        self.assertEqual(result.error["code"], "BUDGET_EXCEEDED")
        self.assertEqual(result.error["resource"], "request_time")

    def test_global_time_and_large_tool_results_stop_without_followup(self):
        with patch("requests.post", side_effect=lambda *a, **k: time.sleep(1)):
            result = self.runtime(replace(Limits(), max_seconds=0.02)).handle_turn("Synthetic", self.state)
        self.assertEqual(result.error["resource"], "time")
        spec = replace(self.spec, result_schema={"type": "string"}, max_result_bytes=6000,
                       handler=lambda **kwargs: "x" * 5000)
        result = self.run_messages([response("", [call()])],
                                   self.runtime(replace(Limits(), max_context_bytes=2000), spec=spec))
        self.assertEqual(result.error["code"], "CONTEXT_LIMIT")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(result.state.to_json(), self.state.to_json())

    def test_http_failure_is_structured_and_response_is_closed(self):
        wire = Mock(status_code=503)
        with patch("requests.post", return_value=wire):
            result = self.runtime().handle_turn("Synthetic", self.state)
        self.assertEqual(result.error["code"], "MODEL_UNAVAILABLE")
        wire.close.assert_called_once()
        self.handler.assert_not_called()

    def test_result_failure_can_recover_but_traces_do_not_leak_payload(self):
        self.handler.side_effect = ["SENSITIVE_RESULT", 2]
        result = self.run_messages([response("", [call()]), response("", [call()]), response()])
        self.assertIsNone(result.error)
        self.assertEqual(json.loads(self.sent[1].kwargs["json"]["messages"][-1]["content"])["error"]["code"], "INVALID_RESULT")
        self.assertNotIn("SENSITIVE_RESULT", json.dumps(result.traces))

    def test_empty_or_remote_model_configuration_is_rejected_without_sending(self):
        for url, model in [("", "synthetic"), ("http://example.com:11434", "synthetic"),
                           ("http://127.0.0.1:11434", " ")]:
            with self.subTest(url=url, model=model), self.assertRaises(ValueError):
                OllamaModelAdapter(url, model)

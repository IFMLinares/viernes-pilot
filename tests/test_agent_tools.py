"""Host policies, not model arguments or restored data, authorize handlers."""
import json
import time
import unittest
from unittest.mock import Mock

from core.agent.contracts import Budget, ExecutionContext, Limits
from core.agent.tools import Policy, ToolExecutor, ToolSpec

PARAMETERS = {"type": "object", "properties": {"value": {"type": "integer", "minimum": 0}},
              "required": ["value"], "additionalProperties": False}
RESULT = {"type": "integer", "minimum": 0}


class ToolExecutionTests(unittest.TestCase):
    def spec(self, handler=None, **kwargs):
        kwargs.setdefault("effects", frozenset({"read"}))
        kwargs.setdefault("scope", "synthetic")
        return ToolSpec("increment", "Synthetic computation", PARAMETERS, RESULT,
                        handler or (lambda value: value + 1), **kwargs)

    def context(self, allowed=True, **limits):
        policy = Policy(frozenset({"increment"}), frozenset({"synthetic"})) if allowed else Policy()
        return ExecutionContext(policy, Budget(Limits(**limits)))

    def execute(self, executor, arguments, context=None, name="increment"):
        return executor.execute({"function": {"name": name, "arguments": arguments}}, context or self.context())

    def test_explicit_read_and_prepare_are_allowed_and_inputs_are_copied(self):
        for effect in ("read", "prepare"):
            with self.subTest(effect=effect):
                executor = ToolExecutor([self.spec(effects=frozenset({effect}))])
                arguments = {"value": 3}
                result = self.execute(executor, arguments)
                self.assertEqual(result["data"], 4)
                self.assertTrue(result["ok"])
                self.assertEqual(arguments, {"value": 3})

    def test_denied_effects_and_scopes_never_invoke_write_handler(self):
        for effects in ({"write"}, {"external"}, {"read", "external"}, {"prepare", "write"}):
            handler = Mock()
            executor = ToolExecutor([self.spec(handler, effects=frozenset(effects))])
            result = self.execute(executor, {"value": 1})
            self.assertEqual(result["error"]["code"], "UNAUTHORIZED")
            handler.assert_not_called()
            self.assertEqual(executor.definitions(self.context().policy), [])
        handler = Mock()
        executor = ToolExecutor([self.spec(handler)])
        self.assertFalse(self.execute(executor, {"value": 1}, self.context(allowed=False))["ok"])
        foreign = ExecutionContext(Policy(frozenset({"increment"}), frozenset({"other"})), Budget(Limits()))
        self.assertFalse(self.execute(executor, {"value": 1}, foreign)["ok"])
        handler.assert_not_called()

    def test_unknown_tool_and_invalid_arguments_are_recoverable_before_handler(self):
        handler = Mock()
        executor = ToolExecutor([self.spec(handler)])
        result = self.execute(executor, {}, name="missing")
        self.assertEqual(result["error"]["code"], "UNKNOWN_TOOL")
        for arguments in [{"value": True}, {"value": -1}, {"value": 1, "grants": ["write"]}, {}, []]:
            result = self.execute(executor, arguments)
            self.assertEqual(result["error"]["code"], "INVALID_ARGUMENTS")
            self.assertTrue(result["error"]["recoverable"])
        handler.assert_not_called()

    def test_result_schema_and_byte_limit_are_enforced(self):
        for returned in ("SENSITIVE_RESULT", True, object()):
            executor = ToolExecutor([self.spec(lambda **kwargs: returned)])
            result = self.execute(executor, {"value": 1})
            self.assertEqual(result["error"]["code"], "INVALID_RESULT")
        executor = ToolExecutor([self.spec(lambda **kwargs: 123, max_result_bytes=1)])
        self.assertEqual(self.execute(executor, {"value": 1})["error"]["code"], "INVALID_RESULT")

    def test_unsupported_schema_and_duplicate_registration_fail_closed(self):
        with self.assertRaises(ValueError):
            ToolExecutor([self.spec(), self.spec()])
        with self.assertRaises(ValueError):
            ToolSpec("x", "Example", {**PARAMETERS, "oneOf": []}, RESULT, lambda: 1,
                     frozenset({"read"}), "synthetic")
        with self.assertRaises(ValueError):
            self.spec(effects=frozenset({"unknown"}))

    def test_handler_exception_is_sanitized_and_tool_timeout_is_terminal(self):
        handler = Mock(side_effect=ValueError("SENSITIVE_EXCEPTION"))
        context = self.context()
        self.execute(ToolExecutor([self.spec(handler)]), {"value": 1}, context)
        self.assertNotIn("SENSITIVE_EXCEPTION", json.dumps(context.traces))
        executor = ToolExecutor([self.spec(lambda **kwargs: time.sleep(1))])
        result = self.execute(executor, {"value": 1}, self.context(tool_timeout=0.02))
        self.assertEqual(result["error"]["code"], "BUDGET_EXCEEDED")
        self.assertFalse(result["error"]["recoverable"])

    def test_traces_contain_fingerprints_and_sizes_not_arguments(self):
        parameters = {"type": "object", "properties": {"value": {"type": "string"}},
                      "required": ["value"], "additionalProperties": False}
        spec = ToolSpec("increment", "Synthetic echo", parameters, {"type": "string"}, lambda value: value,
                        frozenset({"read"}), "synthetic")
        context = self.context()
        self.execute(ToolExecutor([spec]), {"value": "SENSITIVE_ARGUMENT"}, context)
        raw = json.dumps(context.traces)
        self.assertNotIn("SENSITIVE_ARGUMENT", raw)
        self.assertIn("args_sha256", raw)
        self.assertIn("result_bytes", raw)

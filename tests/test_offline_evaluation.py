"""Offline regressions for privacy-safe parse diagnostics and caller isolation."""
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.diagnostics import ALLOWED_KEYS, Diagnostics, _safe_completion_reason, _safe_type_name, parse_metadata
from core.planner import Planner, ollama_interpreter
from tools import evaluate_interpreter


class SemanticDefaultNormalizationTests(unittest.TestCase):
    """S8: omitted list scope means current; explicit invalid/null/wrong filters stay rejected."""

    def test_omitted_list_scope_normalizes_to_current_and_matches_explicit_current(self):
        actual = {"action": "list", "language": "en", "area": "university"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        evaluate_interpreter.validate_action_contract(actual)
        self.assertTrue(evaluate_interpreter.actions_equal(actual, expected))

    def test_omitted_scope_both_ways_is_equivalent(self):
        a = {"action": "list", "language": "es", "area": "work"}
        b = {"action": "list", "language": "es", "area": "work", "scope": "current"}
        self.assertTrue(evaluate_interpreter.actions_equal(a, b))
        self.assertTrue(evaluate_interpreter.actions_equal(b, a))

    def test_explicit_none_scope_is_not_normalized(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": None}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract(actual)
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_invalid_scope_is_not_normalized(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": "invalid"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract(actual)
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_wrong_area_is_not_forgiven(self):
        actual = {"action": "list", "language": "en", "area": "work", "scope": "current"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_wrong_dates_are_not_forgiven(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": "range",
                  "start_date": "2026-11-01", "end_date": "2026-11-15"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "range",
                    "start_date": "2026-11-01", "end_date": "2026-11-30"}
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_non_list_actions_ignore_scope_default(self):
        actual = {"action": "create", "language": "es", "items": [{"title": "X", "area": "university"}]}
        expected = {"action": "create", "language": "es", "items": [{"title": "Y", "area": "university"}]}
        self.assertTrue(evaluate_interpreter.actions_equal(actual, expected))

    def test_validate_action_contract_still_requires_language(self):
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract({"action": "list", "area": "university"})



class ParseMetadataSanitizationTests(unittest.TestCase):
    def test_safe_type_name_allows_primitive_names(self):
        self.assertEqual(_safe_type_name("text"), "str")
        self.assertEqual(_safe_type_name(None), "NoneType")
        self.assertEqual(_safe_type_name(123), "int")
        self.assertEqual(_safe_type_name({}), "dict")

    def test_safe_completion_reason_whitelists_known_values(self):
        for value in ("stop", "length"):
            self.assertEqual(_safe_completion_reason(value), value)

    def test_safe_completion_reason_maps_unknown_to_other(self):
        self.assertEqual(_safe_completion_reason("weird_reason"), "other")

    def test_safe_completion_reason_rejects_non_strings(self):
        self.assertIsNone(_safe_completion_reason(123))

    def test_parse_metadata_captures_content_stage(self):
        response = {"message": {"content": '{"action":"list"}'}}
        meta = parse_metadata(response)
        self.assertEqual(meta["parse_stage"], "content")
        self.assertTrue(meta["content_exists"])
        self.assertEqual(meta["content_type"], "str")
        self.assertEqual(meta["content_length"], len('{"action":"list"}'))
        self.assertFalse(meta["content_empty"])

    def test_parse_metadata_captures_envelope_stage_for_done_reason(self):
        response = {"message": {"content": '{"action":"list"}'}, "done": True, "done_reason": "stop"}
        meta = parse_metadata(response)
        self.assertEqual(meta["parse_stage"], "envelope")
        self.assertEqual(meta["completion_reason"], "stop")

    def test_parse_metadata_handles_missing_content(self):
        response = {"message": {}}
        meta = parse_metadata(response)
        self.assertFalse(meta["content_exists"])
        self.assertEqual(meta["content_type"], "NoneType")
        self.assertTrue(meta["content_empty"])

    def test_parse_metadata_handles_nonstring_content(self):
        response = {"message": {"content": 123}}
        meta = parse_metadata(response)
        self.assertTrue(meta["content_exists"])
        self.assertEqual(meta["content_type"], "int")
        self.assertNotIn("content_length", meta)
        self.assertTrue(meta["content_empty"])

    def test_parse_metadata_handles_json_error_position(self):
        response = {"message": {"content": "not json"}}
        try:
            json.loads(response["message"]["content"])
        except json.JSONDecodeError as exc:
            meta = parse_metadata(response, exc=exc)
        self.assertEqual(meta["json_error_line"], 1)
        self.assertEqual(meta["json_error_column"], 1)
        self.assertEqual(meta["json_error_position"], 0)
        self.assertEqual(meta["parse_stage"], "content")

    def test_parse_metadata_omits_raw_strings_and_bodies(self):
        response = {"message": {"content": '{"action":"list"}', "raw": "secret"}}
        meta = parse_metadata(response)
        for key in ("content", "raw", "prompt", "answer"):
            self.assertNotIn(key, meta)



class InterpreterParseDiagnosticsTests(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_diagnostics_off_emits_no_parse_event(self, post):
        stderr = io.StringIO()
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        interpreter("test", [])
        self.assertEqual(stderr.getvalue().strip(), "")

    @patch("core.planner.requests.post")
    def test_diagnostics_on_emits_content_stage_metadata(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        stderr.seek(0)
        events = [json.loads(line) for line in stderr if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertEqual(len(parse_events), 1)
        event = parse_events[0]
        self.assertEqual(event["parse_stage"], "content")
        self.assertTrue(event["content_exists"])
        self.assertEqual(event["content_type"], "str")
        self.assertGreater(event["content_length"], 0)
        self.assertFalse(event["content_empty"])

    @patch("core.planner.requests.post")
    def test_diagnostics_on_emits_envelope_metadata_for_done_reason(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'},
                                                "done": True, "done_reason": "stop"}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        event = [e for e in events if e.get("parse_stage") == "envelope"][0]
        self.assertEqual(event["completion_reason"], "stop")

    @patch("core.planner.requests.post")
    def test_diagnostics_on_preserves_json_error_type(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": "not json"}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        with self.assertRaises(json.JSONDecodeError):
            interpreter("test", [])
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertEqual(len(parse_events), 1)
        event = parse_events[0]
        self.assertEqual(event["parse_stage"], "content")
        self.assertIn("json_error_line", event)
        self.assertIn("json_error_column", event)

    @patch("core.planner.requests.post")
    def test_diagnostics_never_leaks_raw_content_or_prompts(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"synthetic-secret"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        raw = stderr.getvalue()
        self.assertNotIn("synthetic-secret", raw)
        self.assertNotIn("prompt", raw)

    @patch("core.planner.requests.post")
    def test_nonstring_content_preserves_typeerror_with_safe_metadata(self, post):
        cases = [None, {}, [], 42, True]
        for content in cases:
            with self.subTest(content=content):
                stderr = io.StringIO()
                diag = Diagnostics(output=stderr)
                post.return_value.status_code = 200
                post.return_value.json.return_value = {"message": {"content": content},
                                                        "done": True, "done_reason": "stop"}
                interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
                with self.assertRaises(TypeError):
                    interpreter("test", [])
                try:
                    interpreter("test", [])
                except TypeError as exc:
                    meta = getattr(exc, "_parse_metadata", {})
                self.assertEqual(meta.get("parse_stage"), "content")
                self.assertTrue(meta.get("content_exists"))
                self.assertEqual(meta.get("content_type"), type(content).__name__)
                events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
                parse_events = [e for e in events if e.get("parse_stage")]
                self.assertGreaterEqual(len(parse_events), 1)
                event = parse_events[0]
                self.assertEqual(event["content_type"], type(content).__name__)
                self.assertTrue(event["content_exists"])
                raw = stderr.getvalue()
                if content is not None and not isinstance(content, bool):
                    self.assertNotIn(str(content), raw)
                # The event must never carry the raw value under a content/value key.
                for event in parse_events:
                    self.assertNotIn("content", event)
                    self.assertNotIn("value", event)

    @patch("core.planner.requests.post")
    def test_missing_message_content_preserves_typed_error_with_metadata(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        with self.assertRaises((KeyError, TypeError)):
            interpreter("test", [])
        try:
            interpreter("test", [])
        except (KeyError, TypeError) as exc:
            meta = getattr(exc, "_parse_metadata", {})
        self.assertEqual(meta.get("parse_stage"), "content")
        self.assertFalse(meta.get("content_exists"))
        self.assertEqual(meta.get("content_type"), "NoneType")



class PlannerParseDiagnosticsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-parse-diag-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.output = io.StringIO()
        self.diag = Diagnostics(output=self.output)

    def events(self):
        self.output.seek(0)
        return [json.loads(line) for line in self.output if line.strip()]

    @patch("core.planner.requests.post")
    def test_planner_error_event_includes_safe_parse_metadata(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": "not json"}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=self.diag)
        planner = Planner(self.store, interpreter, diagnostics=self.diag)
        with self.assertRaises(json.JSONDecodeError):
            planner.respond("What do I have?")
        error_event = [e for e in self.events() if e.get("outcome") == "error" and e.get("route") == "interpreter"][0]
        self.assertIn("json_error_line", error_event)
        self.assertIn("parse_stage", error_event)
        self.assertNotIn("synthetic", error_event)

    @patch("core.planner.requests.post")
    def test_planner_normal_ui_unchanged_with_diagnostics_off(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en","area":"university"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        planner = Planner(self.store, interpreter)
        response = planner.respond("Show my university commitments")
        self.assertIn("University", response)

    @patch("core.planner.requests.post")
    def test_planner_injects_diagnostics_into_interpreter_at_runtime(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"A derivative is change."}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")  # no diagnostics
        planner = Planner(self.store, interpreter, diagnostics=self.diag)
        planner.respond("What is a derivative?")
        events = [json.loads(line) for line in self.output.getvalue().splitlines() if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertGreaterEqual(len(parse_events), 1)
        self.assertEqual(parse_events[0]["parse_stage"], "content")

    @patch("core.planner.requests.post")
    def test_planner_diagnostics_ownership_isolated_for_shared_interpreter(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"ok"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        sink_a = io.StringIO()
        sink_b = io.StringIO()
        sink_c = io.StringIO()
        diag_a = Diagnostics(output=sink_a)
        diag_b = Diagnostics(output=sink_b)
        diag_c = Diagnostics(output=sink_c)
        planner_a = Planner(self.store, interpreter, diagnostics=diag_a)
        planner_b = Planner(self.store, interpreter)  # diagnostics off
        planner_c = Planner(self.store, interpreter, diagnostics=diag_c)
        # Disabled B must not emit into A's sink.
        planner_b.respond("What is X?")
        self.assertEqual(sink_a.getvalue(), "")
        self.assertEqual(sink_c.getvalue(), "")
        # Enabled C must emit only into C's sink.
        planner_c.respond("What is Y?")
        self.assertEqual(sink_a.getvalue(), "")
        self.assertIn("content_exists", sink_c.getvalue())
        # A after C must still emit into A's sink only.
        sink_c.truncate(0)
        sink_c.seek(0)
        planner_a.respond("What is Z?")
        self.assertIn("content_exists", sink_a.getvalue())
        self.assertEqual(sink_c.getvalue(), "")



class PayloadStabilityTests(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_request_payload_unchanged_after_edits(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list"}'}}
        fixed = date(2026, 11, 23)
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", today=fixed)
        interpreter("Show my university commitments", [])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["options"], {"temperature": 0, "num_ctx": 4096})
        self.assertIn("format", payload)
        self.assertEqual(post.call_args.kwargs["timeout"], (3, 90))
        self.assertEqual(post.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(post.call_args.kwargs["proxies"], {"http": "", "https": ""})
        prompt = payload["messages"][0]["content"]
        self.assertIn("2026-11-23", prompt)
        self.assertIn("Default scope=current", prompt)



class OfflineCompletionRegressions(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_disabled_planner_does_not_inherit_factory_sink(self, post):
        sink = io.StringIO()
        interpret = ollama_interpreter("http://localhost:11434", "synthetic", diagnostics=Diagnostics(sink))
        store = CommitmentStore(":memory:")
        self.addCleanup(store.close)
        planner = Planner(store, interpret)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": json.dumps(
            {"action": "reply", "language": "en", "answer": "Synthetic explanation"})}}
        planner.respond("Explain derivatives")
        self.assertEqual(sink.getvalue(), "")
        interpret("Explain derivatives", [])
        self.assertIn("content_exists", sink.getvalue())



if __name__ == "__main__":
    unittest.main()

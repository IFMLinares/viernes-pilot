"""Tests for opt-in planner diagnostics and main.py flag wiring."""
import ast
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from core.commitments import CommitmentStore
from core.diagnostics import ALLOWED_KEYS, Diagnostics
from core.planner import Planner, ollama_interpreter


class DiagnosticsEmitterTests(unittest.TestCase):
    def test_explicit_none_disables_emitter(self):
        diag = Diagnostics(None)
        diag.emit(route="test", outcome="ok")
        self.assertFalse(diag.enabled)

    def test_default_emitter_writes_to_stderr(self):
        import sys
        diag = Diagnostics()
        self.assertTrue(diag.enabled)
        self.assertEqual(diag.output, sys.stderr)

    def test_diagnostics_output_goes_to_stderr_on_actual_run(self):
        import io
        import sys
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        diag.emit(route="fast_path", outcome="list", count=0)
        stderr.seek(0)
        event = json.loads(stderr.read())
        self.assertEqual(event["route"], "fast_path")
        self.assertEqual(event["count"], 0)

    def test_emit_writes_allowed_keys_as_json_lines(self):
        output = io.StringIO()
        diag = Diagnostics(output=output)
        diag.emit(route="command", outcome="list", stage="query", duration_ms=12,
                  filter_area="university", filter_scope="current", count=3)
        output.seek(0)
        events = [json.loads(line) for line in output]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["route"], "command")
        self.assertEqual(events[0]["outcome"], "list")
        self.assertEqual(events[0]["count"], 3)

    def test_emit_drops_disallowed_or_private_fields(self):
        output = io.StringIO()
        diag = Diagnostics(output=output)
        diag.emit(route="interpreter", outcome="reply", duration_ms=5,
                  prompt="secret", answer="private", traceback="boom", env="HOME=/x")
        event = json.loads(output.getvalue())
        self.assertEqual(set(event), {"route", "outcome", "duration_ms"})
        self.assertNotIn("prompt", event)
        self.assertNotIn("answer", event)
        self.assertNotIn("traceback", event)
        self.assertNotIn("env", event)

    def test_allowed_keys_do_not_include_free_text(self):
        for key in ("prompt", "answer", "source", "title", "model", "url", "traceback", "exception"):
            self.assertNotIn(key, ALLOWED_KEYS)


class PlannerDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-diagnostics-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.output = io.StringIO()
        self.diag = Diagnostics(output=self.output)
        self.today = date(2026, 11, 23)

    def events(self):
        self.output.seek(0)
        return [json.loads(line) for line in self.output]

    def test_default_planner_without_diagnostics_is_unchanged(self):
        planner = Planner(self.store, interpreter=lambda *_: {"action": "create",
            "items": [{"title": "Report", "area": "university"}]})
        self.assertIn("Proposal", planner.respond("Add report"))

    def test_command_route_emits_outcome_and_duration(self):
        planner = Planner(self.store, diagnostics=self.diag)
        planner.respond('/new {"title":"Report","area":"university"}')
        events = self.events()
        self.assertTrue(any(e.get("route") == "command" and e.get("outcome") == "create" for e in events))
        self.assertTrue(all("duration_ms" in e for e in events))

    def test_fast_path_route_emits_filter_and_count(self):
        self.store.create_many([{"title": "Physics", "area": "university"}], "fixture")
        planner = Planner(self.store, diagnostics=self.diag, today=self.today)
        planner.respond("Show my university commitments")
        events = self.events()
        query_event = next(e for e in events if e.get("route") == "fast_path")
        self.assertEqual(query_event["outcome"], "list")
        self.assertEqual(query_event["filter_area"], "university")
        self.assertEqual(query_event["filter_scope"], "current")
        self.assertEqual(query_event["count"], 1)

    def test_interpreter_route_emits_action_outcome(self):
        planner = Planner(self.store, interpreter=lambda *_: {"action": "reply",
            "language": "en", "answer": "A derivative is change."}, diagnostics=self.diag)
        planner.respond("What is a derivative?")
        events = self.events()
        event = next(e for e in events if e.get("route") == "interpreter")
        self.assertEqual(event["outcome"], "reply")

    def test_empty_query_result_reports_count_zero_not_error(self):
        planner = Planner(self.store, diagnostics=self.diag, today=self.today)
        planner.respond("/list work")
        events = self.events()
        event = next(e for e in events if e.get("outcome") == "list")
        self.assertEqual(event["count"], 0)
        self.assertNotEqual(event.get("error_code"), "empty")

    def test_invalid_model_output_emits_stable_error_code(self):
        planner = Planner(self.store, interpreter=lambda *_: {"action": "create",
            "items": []}, diagnostics=self.diag)
        with self.assertRaises(ValueError):
            planner.respond("Add stuff")
        events = self.events()
        event = events[-1]
        self.assertEqual(event["route"], "interpreter")
        self.assertEqual(event["outcome"], "error")
        self.assertIn("error_code", event)
        self.assertNotIn("traceback", event)

    def test_five_distinct_error_codes_for_interpreter_failures(self):
        import requests
        cases = [
            ("invalid_json", lambda *_: json.loads("not json")),
            ("connection", lambda *_: (_ for _ in ()).throw(requests.ConnectionError("synthetic-secret"))),
            ("timeout", lambda *_: (_ for _ in ()).throw(requests.Timeout("synthetic-secret"))),
            ("invalid_fields", lambda *_: {"action": "create", "language": "en", "items": [{"title": "X", "area": "invalid"}]}),
            ("invalid_scope", lambda *_: {"action": "list", "language": "en", "scope": "invalid"}),
        ]
        for expected_code, interpreter in cases:
            with self.subTest(code=expected_code):
                planner = Planner(self.store, interpreter=interpreter, diagnostics=self.diag)
                with self.assertRaises(Exception):
                    planner.respond("Any input")
                event = self.events()[-1]
                self.assertEqual(event["route"], "interpreter")
                self.assertEqual(event["error_code"], expected_code)
                raw = self.output.getvalue()
                self.assertNotIn("synthetic-secret", raw)
                self.output.seek(0)
                self.output.truncate(0)

    def test_emitted_events_never_contain_private_text(self):
        planner = Planner(self.store, interpreter=lambda *_: {"action": "create",
            "items": [{"title": "Private note", "area": "personal"}]}, diagnostics=self.diag)
        planner.respond("Private note")
        raw = self.output.getvalue()
        self.assertNotIn("Private note", raw)
        self.assertNotIn("source", raw)


class MainFlagTests(unittest.TestCase):
    def dispatch(self, args, legacy):
        path = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(path.read_text())
        entry = tree.body[-1]
        self.assertIsInstance(entry, ast.If)
        code = compile(ast.Module(body=[entry], type_ignores=[]), str(path), "exec")
        with patch("sys.argv", ["main.py", *args]):
            exec(code, {"__name__": "__main__", "main": legacy})

    def test_diagnostics_requires_planner(self):
        legacy = Mock()
        with self.assertRaises(SystemExit) as result:
            self.dispatch(["--diagnostics"], legacy)
        self.assertNotEqual(result.exception.code, 0)
        legacy.assert_not_called()

    @patch("core.planner.main", return_value=0)
    def test_planner_alone_calls_main_without_diagnostics(self, planner):
        legacy = Mock()
        with self.assertRaises(SystemExit) as result:
            self.dispatch(["--planner"], legacy)
        self.assertEqual(result.exception.code, 0)
        planner.assert_called_once_with()
        legacy.assert_not_called()

    @patch("core.planner.main", return_value=0)
    def test_planner_with_diagnostics_passes_diagnostics_object(self, planner):
        legacy = Mock()
        with self.assertRaises(SystemExit) as result:
            self.dispatch(["--planner", "--diagnostics"], legacy)
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(planner.call_count, 1)
        args, kwargs = planner.call_args
        self.assertFalse(args)
        self.assertIn("diagnostics", kwargs)
        self.assertIsInstance(kwargs["diagnostics"], Diagnostics)
        legacy.assert_not_called()

    def test_main_planner_diagnostics_emits_stderr_json_lines(self):
        import io
        from core.ollama_runtime import RuntimeStatus
        stderr = io.StringIO()
        path = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(path.read_text())
        entry = tree.body[-1]
        code = compile(ast.Module(body=[entry], type_ignores=[]), str(path), "exec")
        with patch("sys.argv", ["main.py", "--planner", "--diagnostics"]), \
             patch("sys.stderr", stderr), \
             patch("builtins.input", side_effect=["Show my university commitments", "/quit"]), \
             patch("core.planner.ensure_ollama", return_value=RuntimeStatus(False, "offline")):
            with self.assertRaises(SystemExit) as result:
                exec(code, {"__name__": "__main__"})
            self.assertEqual(result.exception.code, 0)
        stderr.seek(0)
        lines = [line for line in stderr if line.strip()]
        self.assertTrue(any('"route"' in line for line in lines))
        for line in lines:
            event = json.loads(line)
            self.assertNotIn("prompt", event)
            self.assertNotIn("answer", event)


class InterpreterTodayInjectionTests(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_interpreter_uses_injected_today_in_prompt(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list"}'}}
        fixed = date(2026, 11, 23)
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", today=fixed)
        interpreter("test", [])
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("2026-11-23", prompt)
        self.assertNotIn(date.today().isoformat(), prompt)

    @patch("core.planner.requests.post")
    def test_planner_passes_today_to_fast_path_and_store(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list"}'}}
        temp = tempfile.TemporaryDirectory(prefix="viernes-today-")
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "tasks.sqlite3"
        store = CommitmentStore(path)
        self.addCleanup(store.close)
        store.create_many([{"title": "Old", "area": "university", "due_date": "2026-11-16"}], "fixture")
        planner = Planner(store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"),
                          today=date(2026, 11, 23))
        planner.respond("Show my university commitments")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

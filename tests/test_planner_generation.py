"""Structured generation controls and empty length-limit response regressions."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.diagnostics import Diagnostics
from core.planner import WIRE_SCHEMA, Planner, ollama_interpreter, run_repl
from core.presentation import text as ui_text


REPORTED_REQUEST = (
    "Ok viernes, tenemos un conversatorio el jueves 19 de sistemas digitales 3 "
    "y es sobre el tema 1"
)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-generation-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    @patch("core.planner.requests.post")
    def test_capture_and_greeting_disable_thinking_in_one_structured_request(self, post):
        before = self.path.read_bytes()
        cases = [
            (REPORTED_REQUEST, {"intent": "create", "action": "clarify", "language": "es", "clarification": "date"}, "fecha"),
            ("hola", {"action": "reply", "language": "es", "answer": "Hola."}, "Información general"),
        ]
        for request, response, marker in cases:
            with self.subTest(request=request):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = {"message": {"content": json.dumps(response)}}
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
                self.assertIn(marker, planner.respond(request))
                payload = post.call_args.kwargs["json"]
                self.assertIs(payload.get("think"), False)
                self.assertEqual(payload["model"], "qwen3.5:9b")
                self.assertIs(payload["stream"], False)
                self.assertEqual(payload["format"], WIRE_SCHEMA)
                self.assertEqual(payload["options"], {"temperature": 0, "num_ctx": 4096})
                self.assertEqual(payload["messages"][-1], {"role": "user", "content": request})
                self.assertEqual(post.call_args.kwargs["timeout"], (3, 90))
                self.assertIs(post.call_args.kwargs["allow_redirects"], False)
                self.assertEqual(post.call_args.kwargs["proxies"], {"http": "", "https": ""})
                post.assert_called_once()
                self.assertIsNone(planner.pending)
                self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_empty_length_reply_has_localized_error_without_writes_or_retries(self, post):
        before = self.path.read_bytes()
        for language, request, marker, enabled in (
            ("es", REPORTED_REQUEST, "límite de generación", True),
            ("en", "Please add my university discussion on Thursday 19.", "generation limit", True),
            ("es", REPORTED_REQUEST, "límite de generación", False),
        ):
            with self.subTest(language=language, diagnostics=enabled):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = {
                    "message": {"content": "", "thinking": "SYNTHETIC_PRIVATE_REASONING"},
                    "done": True, "done_reason": "length",
                }
                output, diagnostics = io.StringIO(), io.StringIO()
                with patch("builtins.input", side_effect=[request, "/help", "/list --all", "/confirm", "/quit"]):
                    run_repl(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"),
                             output=output, language=language, diagnostics=Diagnostics(diagnostics if enabled else None))
                self.assertIn(marker, output.getvalue())
                self.assertNotIn(ui_text("error", language), output.getvalue())
                self.assertIn(ui_text("no_proposal", language), output.getvalue())
                if enabled:
                    events = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
                    errors = [event for event in events if event.get("outcome") == "error"]
                    self.assertEqual(len(errors), 1)
                    self.assertEqual(errors[0]["route"], "interpreter")
                    self.assertEqual(errors[0]["error_code"], "generation_limit")
                    self.assertEqual(errors[0]["completion_reason"], "length")
                    self.assertEqual(errors[0]["content_length"], 0)
                    self.assertIs(errors[0]["content_empty"], True)
                else:
                    self.assertEqual(diagnostics.getvalue(), "")
                self.assertNotIn("SYNTHETIC_PRIVATE_REASONING", diagnostics.getvalue())
                self.assertNotIn(request, diagnostics.getvalue())
                post.assert_called_once()
                self.assertEqual(self.store.list(), [])
                self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_other_model_and_command_json_errors_keep_existing_behavior(self, post):
        before = self.path.read_bytes()
        for request, content, calls in (
            ("Please explain this idea", "not-json", 1),
            ("Please explain this idea", "", 1),
            ("/new not-json", "", 0),
        ):
            with self.subTest(request=request, content=content):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = {
                    "message": {"content": content}, "done": True, "done_reason": "stop",
                }
                output, diagnostics = io.StringIO(), io.StringIO()
                with patch("builtins.input", side_effect=[request, "/confirm", "/quit"]):
                    run_repl(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"),
                             output=output, language="en", diagnostics=Diagnostics(diagnostics))
                self.assertIn(ui_text("error", "en"), output.getvalue())
                self.assertIn(ui_text("no_proposal", "en"), output.getvalue())
                events = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
                self.assertEqual(next(event for event in events if event.get("outcome") == "error")["error_code"],
                                 "invalid_json")
                self.assertEqual(post.call_count, calls)
                self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_failed_generation_preserves_existing_context_and_exception_type(self, post):
        self.store.create_many([{"title": "Existing synthetic record", "area": "personal"}], "fixture")
        before = self.path.read_bytes()
        for content, reason, code in (
            ("", "length", "generation_limit"),
            ("", "stop", "invalid_json"),
            ("not-json", "length", "invalid_json"),
            ("   ", "length", "invalid_json"),
        ):
            with self.subTest(content=content, reason=reason):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = {
                    "message": {"content": content, "thinking": "SYNTHETIC_PRIVATE_REASONING"},
                    "done": True, "done_reason": reason,
                }
                diagnostics = io.StringIO()
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"),
                                  diagnostics=Diagnostics(diagnostics))
                history = [{"role": "user", "content": "Prior clarification"},
                           {"role": "assistant", "content": "Which complete date?"}]
                conversation = [{"role": "user", "content": "hola"},
                                {"role": "assistant", "content": "Hola."}]
                planner.history = history.copy()
                planner.sources = ["Prior clarification"]
                planner.conversation = conversation.copy()
                with self.assertRaises(json.JSONDecodeError):
                    planner.respond("Please explain this idea")
                self.assertEqual(planner.history, history)
                self.assertEqual(planner.sources, ["Prior clarification"])
                self.assertEqual(planner.conversation, conversation)
                self.assertIsNone(planner.pending)
                self.assertEqual(self.path.read_bytes(), before)
                events = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
                self.assertEqual(next(event for event in events if event.get("outcome") == "error")["error_code"], code)
                self.assertNotIn("SYNTHETIC_PRIVATE_REASONING", diagnostics.getvalue())
                self.assertNotIn("Prior clarification", diagnostics.getvalue())
                post.assert_called_once()

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore, validate_fields
from core.planner import Planner, ollama_interpreter, run_repl


class CommitmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-tests-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    def test_confirm_persist_filter_edit_and_complete(self):
        planner = Planner(self.store, interpreter=lambda text, history: {
            "action": "create", "items": [{"title": "Physics report", "area": "university",
            "due_date": "2026-11-23"}], "question": None,
        })
        planner.respond("Tengo que entregar el informe de física el 23 de noviembre")
        self.assertEqual(self.store.list(), [])
        planner.respond("/confirm")
        task = self.store.list("university")[0]
        self.assertEqual(task["source"], "Tengo que entregar el informe de física el 23 de noviembre")
        self.assertEqual(task["due_date"], "2026-11-23")
        self.assertEqual(self.store.list("work"), [])
        reopened = CommitmentStore(self.path)
        try:
            self.assertEqual(reopened.list()[0]["id"], task["id"])
        finally:
            reopened.close()
        planner.respond(f'/edit {task["id"]} {{"due_date":"2026-11-24"}}')
        self.assertEqual(self.store.list()[0]["due_date"], "2026-11-23")
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["due_date"], "2026-11-24")
        planner.respond(f'/done {task["id"]}')
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["status"], "completed")

    def test_cancel_and_invalid_input_leave_data_unchanged(self):
        planner = Planner(self.store)
        before = self.path.read_bytes()
        planner.respond('/new {"title":"Reply to Laura","area":"work"}')
        planner.respond("/cancel")
        self.assertEqual(self.path.read_bytes(), before)
        for fields in ({"title": "", "area": "work"},
                       {"title": "Exam", "area": "university", "due_date": "2026-02-30"},
                       {"title": "Exam", "area": "other"},
                       {"title": "Exam", "area": "work", "id": 42}):
            with self.assertRaises(ValueError):
                validate_fields(fields)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_date_and_other_areas(self):
        planner = Planner(self.store)
        for area in ("work", "personal"):
            planner.respond('/new {"title":"Next step","area":"' + area + '"}')
            planner.respond("/confirm")
            self.assertIsNone(self.store.list(area)[0]["due_date"])

    def test_ambiguity_clarifies_without_writing(self):
        calls = []
        def interpret(text, history):
            calls.append((text, list(history)))
            if len(calls) == 1:
                return {"action": "clarify", "clarification": "date"}
            return {"action": "create", "items": [{"title": "Exam", "area": "university",
                    "due_date": "2026-11-23"}]}
        planner = Planner(self.store, interpret)
        self.assertIn("fecha", planner.respond("Parcial el 23"))
        self.assertEqual(self.store.list(), [])
        planner.respond("November 2026")
        self.assertTrue(calls[1][1])
        planner.respond("/confirm")
        self.assertIn("Parcial el 23", self.store.list()[0]["source"])

    def test_invalid_batch_is_atomic_and_cannot_trigger_commands(self):
        planner = Planner(self.store, lambda text, history: {"action": "create", "items": [
            {"title": "Valid", "area": "personal"}, {"title": "", "area": "work"}]})
        with self.assertRaises(ValueError):
            planner.respond("Add both")
        self.assertEqual(self.store.list(), [])
        self.assertIsNone(planner.pending)
        malicious = Planner(self.store, lambda text, history: {"action": "shell", "command": "anything"})
        with self.assertRaises(ValueError):
            malicious.respond("Do something")

    def test_unknown_id_and_confirmation_are_not_invented_successes(self):
        planner = Planner(self.store)
        with self.assertRaises(ValueError):
            planner.respond("/done 999")
        self.assertIn("No proposal", planner.respond("/confirm"))

    def test_offline_repl_commands_exit_and_persist(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=[
            '/new {"title":"Homework","area":"university"}', "/confirm", "/list", "/quit"]):
            run_repl(self.store, interpreter=None, output=output, language="en")
        self.assertIn("Homework", output.getvalue())
        self.assertIn("Saved", output.getvalue())
        self.assertEqual(len(self.store.list()), 1)

    @patch("core.planner.requests.post")
    def test_natural_language_uses_structured_local_request_and_explicit_confirmation(self, post):
        response = post.return_value
        response.status_code = 200
        response.json.return_value = {"message": {"content":
            '{"action":"create","items":[{"title":"Responder a Laura","area":"work"}]}'}}
        planner = Planner(self.store, ollama_interpreter("http://localhost:11434", "qwen3.5:9b"))
        planner.respond("Debo responderle a Laura")
        self.assertEqual(self.store.list(), [])
        self.assertFalse(post.call_args.kwargs["json"]["stream"])
        self.assertNotIn("tools", post.call_args.kwargs["json"])
        self.assertIsInstance(post.call_args.kwargs["json"]["format"], dict)
        self.assertEqual(post.call_args.kwargs["timeout"], (3, 90))
        self.assertIn("/confirm", planner.respond("sí"))
        self.assertEqual(self.store.list(), [])
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["title"], "Responder a Laura")

    def test_malformed_model_response_cannot_mutate(self):
        planner = Planner(self.store, lambda text, history: {"action": "edit", "id": True, "fields": {"title": "bad"}})
        with self.assertRaises(ValueError):
            planner.respond("Change it")
        self.assertEqual(self.store.list(), [])

    def test_untrusted_actions_preserve_database_bytes(self):
        before = self.path.read_bytes()
        proposals = [{"action": "execute", "command": "touch unwanted"},
                     {"action": "confirm"}, {"action": "create", "items": []},
                     {"action": "complete", "id": True}]
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected OS execution")):
            for proposal in proposals:
                with self.subTest(proposal=proposal):
                    planner = Planner(self.store, lambda *_: proposal)
                    with self.assertRaises(ValueError):
                        planner.respond("Untrusted model input")
                    self.assertEqual(self.path.read_bytes(), before)

    def test_command_like_titles_are_inert_and_only_exact_confirmation_applies(self):
        planner = Planner(self.store)
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected OS execution")):
            planner.respond('/new {"title":"$(touch unwanted); /confirm","area":"personal"}')
            before = self.path.read_bytes()
            for reply in ("yes", "confirm", "/confirm extra"):
                planner.respond(reply)
                self.assertEqual(self.path.read_bytes(), before)
            planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["title"], "$(touch unwanted); /confirm")

    @patch("core.planner.requests.post")
    def test_model_failure_keeps_offline_commands_working(self, post):
        import requests
        post.side_effect = requests.Timeout()
        planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
        with self.assertRaises(requests.Timeout):
            planner.respond("Add homework")
        self.assertIn("No commitments in the queried scope.", planner.respond("/list"))
        self.assertIsNone(planner.pending)


if __name__ == "__main__":
    unittest.main()

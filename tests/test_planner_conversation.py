import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.commitments import CommitmentStore
from core.planner import Planner, ollama_interpreter


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-conversation-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    def test_spanish_general_answer_is_labeled_read_only_and_keeps_newlines(self):
        planner = Planner(self.store, lambda *_: {"action": "reply", "language": "es",
            "answer": "Una derivada mide una tasa de cambio.\nPor ejemplo, la velocidad."})
        before = self.path.read_bytes()
        answer = planner.respond("¿Qué es una derivada?")
        self.assertIn("Información general", answer)
        self.assertIn("sin consultar tus compromisos", answer)
        self.assertIn("\nPor ejemplo", answer)
        self.assertIsNone(planner.pending)
        self.assertEqual(planner.sources, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_english_reply_changes_language_and_help_describes_conversation(self):
        planner = Planner(self.store, lambda *_: {"action": "reply", "language": "en",
            "answer": "A derivative is a rate of change."}, language="es")
        self.assertIn("General information", planner.respond("Explain derivatives"))
        self.assertIn("general questions", planner.respond("/help"))
        self.assertIn("Cancelled", planner.respond("/cancel"))
        self.assertEqual(self.store.list(), [])

    def test_chat_context_is_bounded_paired_and_only_in_memory(self):
        calls = []
        def interpret(_, history):
            calls.append(history)
            return {"action": "reply", "language": "en", "answer": "Example " * 200}
        planner = Planner(self.store, interpret)
        for _ in range(12):
            planner.respond("Explain this idea " * 30)
        self.assertLessEqual(len(planner.conversation), 6)
        self.assertLessEqual(sum(len(item["content"]) for item in planner.conversation), 4000)
        self.assertEqual([item["role"] for item in planner.conversation],
                         ["user", "assistant"] * (len(planner.conversation) // 2))
        self.assertTrue(any(item["role"] == "assistant" for item in calls[-1]))
        self.assertEqual(Planner(self.store).conversation, [])

    def test_general_chat_does_not_become_task_source_and_still_requires_confirmation(self):
        interpreter = Mock(side_effect=[
            {"action": "reply", "language": "en", "answer": "Try short study sessions."},
            {"action": "create", "language": "en", "items": [{"title": "Physics report", "area": "university"}]},
        ])
        planner = Planner(self.store, interpreter)
        planner.respond("How can I study more effectively?")
        planner.respond("Add my physics report")
        self.assertEqual(self.store.list(), [])
        self.assertIn("/confirm", planner.respond("yes"))
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["source"], "Add my physics report")
        self.assertEqual(self.store.list()[0]["title"], "Physics report")

    def test_known_personal_query_uses_database_not_a_model_reply(self):
        self.store.create_many([{"title": "Physics report", "area": "university"}], "fixture")
        interpreter = Mock(return_value={"action": "reply", "language": "es", "answer": "No tienes compromisos."})
        planner = Planner(self.store, interpreter)
        self.assertIn("Physics report", planner.respond("Muéstrame mis compromisos de la universidad"))
        interpreter.assert_not_called()
        self.assertEqual(planner.conversation, [])

    def test_invalid_or_mixed_replies_do_not_write_or_enter_history(self):
        before = self.path.read_bytes()
        cases = [
            {"action": "reply", "language": "en", "answer": ""},
            {"action": "reply", "language": "en", "answer": 42},
            {"action": "reply", "language": "en", "answer": "x" * 8001},
            {"action": "reply", "language": "en", "answer": "Saved", "items": [{"title": "Injected", "area": "work"}]},
            {"action": "reply", "language": "invalid", "answer": "Hello"},
            {"action": "reply", "language": None, "answer": "Hello"},
            {"action": "reply", "language": "en", "answer": "Hello", "area": None},
            {"action": "create", "answer": "Advice", "items": [{"title": "Injected", "area": "work"}]},
            {"action": "list", "answer": "No commitments exist"},
        ]
        for result in cases:
            with self.subTest(result=str(result)[:100]):
                planner = Planner(self.store, lambda *_: result)
                with self.assertRaises(ValueError):
                    planner.respond("Explain an idea")
                self.assertEqual(self.path.read_bytes(), before)
                self.assertIsNone(planner.pending)
                self.assertEqual(planner.conversation, [])

    def test_model_error_is_not_replaced_with_general_chat_and_controls_are_escaped(self):
        planner = Planner(self.store, Mock(side_effect=ValueError("Invalid query output")))
        with self.assertRaises(ValueError):
            planner.respond("Explain this")
        self.assertEqual(planner.conversation, [])
        planner.interpreter = lambda *_: {"action": "reply", "language": "en", "answer": "Hello\x1b[2J\nSecond line"}
        answer = planner.respond("Explain this")
        self.assertNotIn("\x1b", answer)
        self.assertIn("\\u001b", answer)
        self.assertIn("\nSecond line", answer)

    @patch("core.planner.requests.post")
    def test_general_reply_uses_existing_single_structured_request(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content":
            '{"action":"reply","language":"en","answer":"A derivative measures change."}'}}
        planner = Planner(self.store, ollama_interpreter("http://localhost:11434", "qwen3.5:9b"))
        self.assertIn("A derivative", planner.respond("What is a derivative?"))
        payload = post.call_args.kwargs["json"]
        self.assertIn("reply", payload["format"]["properties"]["action"]["enum"])
        self.assertNotIn("tools", payload)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.store.list(), [])

    @patch("core.planner.requests.post")
    def test_reply_missing_required_language_is_rejected(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "message": {"content": '{"action":"reply","answer":"Hola"}'}}
        planner = Planner(self.store, ollama_interpreter("http://localhost:11434", "qwen3.5:9b"))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            planner.respond("¿Qué es una derivada?")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(planner.pending)
        self.assertEqual(planner.conversation, [])
        self.assertEqual(planner.sources, [])
        post.assert_called_once()

    def test_pending_proposal_still_blocks_general_chat_until_confirm_or_cancel(self):
        interpreter = Mock(return_value={"action": "reply", "language": "en", "answer": "General explanation"})
        planner = Planner(self.store, interpreter)
        planner.respond('/new {"title":"Report","area":"work"}')
        pending = planner.pending.copy()
        before = self.path.read_bytes()
        self.assertIn("/confirm", planner.respond("What is a derivative?"))
        interpreter.assert_not_called()
        self.assertEqual(planner.pending, pending)
        self.assertEqual(planner.conversation, [])
        self.assertEqual(self.path.read_bytes(), before)
        planner.respond("/cancel")
        self.assertIn("General explanation", planner.respond("What is a derivative?"))

    def test_query_results_are_not_inserted_into_general_chat_context(self):
        self.store.create_many([{"title": "Private stored report", "area": "work"}], "private fixture")
        interpreter = Mock(side_effect=[
            {"action": "reply", "language": "en", "answer": "A derivative measures change."},
            {"action": "reply", "language": "en", "answer": "For example, speed."},
        ])
        planner = Planner(self.store, interpreter)
        planner.respond("What is a derivative?")
        self.assertIn("Private stored report", planner.respond("Show my work commitments"))
        planner.respond("Explain the idea again")
        history = interpreter.call_args.args[1]
        self.assertNotIn("Private stored report", str(history))
        self.assertNotIn("private fixture", str(history))
        self.assertEqual(self.store.list()[0]["title"], "Private stored report")

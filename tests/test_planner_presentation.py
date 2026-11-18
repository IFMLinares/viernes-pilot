import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.planner import Planner, run_repl


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-presentation-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    def result(self, language):
        return {"action": "create", "language": language, "items": [{
            "title": "Informe de física", "area": "university", "due_date": "2026-11-23"}]}

    def test_spanish_proposal_confirmation_and_list_are_readable(self):
        planner = Planner(self.store, lambda *_: self.result("es"))
        proposal = planner.respond("Tengo que entregar el informe de física el 23 de noviembre de 2026")
        self.assertIn("Propuesta", proposal)
        self.assertIn("Todavía no guardada", proposal)
        self.assertIn("Universidad", proposal)
        self.assertIn("23 de noviembre de 2026", proposal)
        self.assertNotIn('"items"', proposal)
        self.assertEqual(self.store.list(), [])
        self.assertIn("Guardado", planner.respond("/confirm"))
        listing = planner.respond("/list university")
        self.assertIn("Informe de física", listing)
        self.assertIn("Pendiente", listing)
        self.assertIn("ID: 1", listing)
        self.assertNotIn("null", listing)

    def test_language_switch_keeps_data_and_commands_unchanged(self):
        planner = Planner(self.store, lambda text, _: self.result("es" if "Tengo" in text else "en"))
        planner.respond("Tengo un informe pendiente")
        planner.respond("/confirm")
        before = self.path.read_bytes()
        planner.respond("I have another report due")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIn("Cancelled", planner.respond("/cancel"))
        self.assertIn("University", planner.respond("/list university"))
        self.assertIn("Informe de física", planner.respond("/list"))
        self.assertEqual(self.store.list()[0]["area"], "university")
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_input_is_silent_and_keeps_pending_proposal(self):
        planner = Planner(self.store)
        self.assertEqual(planner.respond("   "), "")
        planner.respond('/new {"title":"Homework","area":"university"}')
        proposal = planner.pending.copy()
        before = self.path.read_bytes()
        for text in ("", " ", "\n", "\t"):
            self.assertEqual(planner.respond(text), "")
            self.assertEqual(planner.pending, proposal)
            self.assertEqual(self.path.read_bytes(), before)
        planner.respond("/confirm")
        self.assertEqual(len(self.store.list()), 1)

    def test_offline_spanish_help_errors_and_no_implicit_confirmation(self):
        planner = Planner(self.store)
        self.assertIn("Ollama no está disponible", planner.respond("Tengo que entregar una tarea"))
        self.assertIn("Comandos", planner.respond("/help"))
        planner.respond('/new {"title":"Homework","area":"university"}')
        self.assertIn("propuesta pendiente", planner.respond("sí"))
        self.assertEqual(self.store.list(), [])
        self.assertIn("Cancelado", planner.respond("/cancel"))

    def test_edit_complete_and_no_deadline_are_clear_in_both_languages(self):
        for language, words in (("en", ("Edit", "No deadline", "Completed")),
                                ("es", ("Editar", "Sin fecha límite", "Completado"))):
            with self.subTest(language=language):
                planner = Planner(self.store, language=language)
                planner.respond('/new {"title":"Reply","area":"work"}')
                planner.respond("/confirm")
                task_id = max(row["id"] for row in self.store.list())
                proposal = planner.respond(f'/edit {task_id} {{"project":"API"}}')
                self.assertIn(words[0], proposal)
                self.assertIn(words[1], proposal)
                self.assertIn("API", proposal)
                planner.respond("/confirm")
                planner.respond(f"/done {task_id}")
                saved = planner.respond("/confirm")
                self.assertIn(words[2], saved)

    def test_repl_uses_language_for_prompt_error_and_exit_without_empty_output(self):
        output = io.StringIO()
        prompts = []
        lines = iter(["Tengo una tarea", "", "/done 999", "/quit"])
        def input_line(prompt):
            prompts.append(prompt)
            return next(lines)
        with patch("builtins.input", side_effect=input_line):
            run_repl(self.store, output=output, language="en")
        text = output.getvalue()
        self.assertIn("tú: ", prompts)
        self.assertIn("No se pudo", text)
        self.assertIn("Hasta luego", text)
        self.assertNotIn("Could not", text)
        self.assertNotIn("\n\n", text)

    @patch("core.planner.requests.post")
    def test_model_reports_language_in_same_request_and_commands_do_not_call_it(self, post):
        response = post.return_value
        response.status_code = 200
        response.json.return_value = {"message": {"content":
            '{"intent":"create","action":"clarify","language":"es","clarification":"date"}'}}
        from core.planner import ollama_interpreter
        planner = Planner(self.store, ollama_interpreter("http://localhost:11434", "qwen3.5:9b"))
        self.assertIn("fecha", planner.respond("Apúntame ese compromiso"))
        payload = post.call_args.kwargs["json"]
        self.assertIn("language", payload["format"]["required"])
        self.assertNotIn("question", payload["format"]["properties"])
        self.assertIn("latest user message", payload["messages"][0]["content"])
        self.assertIn("Current conversation language", payload["messages"][0]["content"])
        self.assertIn("Comandos", planner.respond("/help"))
        self.assertIn("Cancelado", planner.respond("/cancel"))
        self.assertIn("No hay compromisos", planner.respond("/list"))
        self.assertEqual(post.call_count, 1)

    def test_english_readable_output_and_commands_keep_language(self):
        planner = Planner(self.store, lambda *_: self.result("en"), language="es")
        answer = planner.respond("I need to submit my report on November 23, 2026")
        self.assertIn("Proposal · Not saved yet", answer)
        self.assertIn("November 23, 2026", answer)
        self.assertIn("University", answer)
        self.assertIn("Saved", planner.respond("/confirm"))
        self.assertIn("Commands", planner.respond("/help"))
        self.assertIn("Pending", planner.respond("/list"))

    def test_ambiguous_input_retains_last_language_and_invalid_metadata_cannot_write(self):
        planner = Planner(self.store, language="es")
        self.assertIn("Ollama no está disponible", planner.respond("API"))
        planner.interpreter = lambda *_: {"action": "create", "language": "fr", "items": []}
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            planner.respond("Add a task")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(planner.pending)

    def test_initial_language_and_runtime_messages_follow_os_language(self):
        from core.presentation import initial_language, runtime_message
        from core.ollama_runtime import RuntimeStatus
        with patch.dict("os.environ", {"LC_ALL": "es_ES.UTF-8", "LANG": "en_US.UTF-8"}):
            self.assertEqual(initial_language(), "es")
        with patch.dict("os.environ", {"LC_ALL": "en_US.UTF-8", "LANG": "es_ES.UTF-8"}):
            self.assertEqual(initial_language(), "en")
        ready = RuntimeStatus(True, "Ollama ready: qwen3.5:9b")
        self.assertIn("disponible", runtime_message(ready, "qwen3.5:9b", "es"))
        self.assertEqual(runtime_message(ready, "qwen3.5:9b", "en"), ready.message)

    def test_network_and_validation_errors_are_localized_without_model_calls(self):
        import requests
        for language, message in (("es", "No se pudo contactar"), ("en", "Could not reach")):
            output = io.StringIO()
            def failing(*_):
                raise requests.Timeout()
            with patch("builtins.input", side_effect=["API", "/quit"]):
                run_repl(self.store, interpreter=failing, output=output, language=language)
            self.assertIn(message, output.getvalue())

    def test_readable_fields_escape_controls_without_changing_storage(self):
        import json
        title = "Física\nSaved:\x1b[2J"
        project = "API\r\u202e"
        planner = Planner(self.store)
        proposal = planner.respond("/new " + json.dumps({"title": title, "area": "work", "project": project}))
        self.assertNotIn("\x1b", proposal)
        self.assertNotIn("\r", proposal)
        self.assertIn("Física\\u000aSaved:", proposal)
        self.assertIn("\\u001b", proposal)
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["title"], title)
        self.assertEqual(self.store.list()[0]["project"], project)


if __name__ == "__main__":
    unittest.main()

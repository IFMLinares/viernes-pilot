"""Area clarification is owned by the application, not inferred anew each turn."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.diagnostics import Diagnostics
from core.planner import SCHEMA, WIRE_SCHEMA, Planner, ollama_interpreter, run_repl
from core.presentation import text as ui_text


REQUEST = (
    "HOla viernes, tenemos un conversatorio para el juevves 19 de noviembre, "
    "de la materia de sistemas digitales 3, el Tema1"
)
DATE_ANSWER = "19 de noviembre de 2026"


def envelope(action):
    return {"message": {"content": json.dumps({"intent": "create" if action["action"] == "clarify"
                                               else action["action"], **action})}}


class AreaClarificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-clarification-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    @patch("core.planner.requests.post")
    def test_clear_area_answers_resume_capture_without_inventing_a_date_or_saving(self, post):
        original_schema = copy.deepcopy(SCHEMA)
        cases = [("Universidad", "university"), ("universidad", "university"),
                 ("Del área de la universidad", "university"), ("UNIVERSIDAD!", "university"),
                 ("university", "university"), ("Trabajo", "work"), ("work", "work"),
                 ("personal", "personal")]
        for answer, area in cases:
            with self.subTest(answer=answer):
                before = self.path.read_bytes()
                count = len(self.store.list())
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.side_effect = [
                    envelope({"action": "clarify", "language": "es", "clarification": "area"}),
                    envelope({"action": "clarify", "language": "es", "clarification": "date"}),
                    envelope({"action": "create", "language": "es", "items": [
                        {"title": "Conversatorio Sistemas Digitales 3 - Tema 1", "due_date": "2026-11-19"}]}),
                    envelope({"action": "reply", "language": "es", "answer": "Hola."}),
                ]
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
                self.assertIn("área", planner.respond(REQUEST))
                self.assertIn("fecha", planner.respond(answer))
                self.assertEqual(getattr(planner, "resolved_area", None), area)
                self.assertEqual(self.path.read_bytes(), before)
                second = post.call_args.kwargs["json"]
                self.assertNotIn("area", second["format"]["properties"]["clarification"]["enum"])
                self.assertNotIn("reply", second["format"]["properties"]["action"]["enum"])
                self.assertNotIn("answer", second["format"]["properties"])
                self.assertTrue(any(f"Application-confirmed area: {area}" in item["content"]
                                    for item in second["messages"] if item["role"] == "system"))
                self.assertIn(REQUEST, str(second["messages"]))
                self.assertIn("/confirm", planner.respond(DATE_ANSWER))
                self.assertEqual(planner.pending["items"][0]["area"], area)
                self.assertEqual(planner.pending["items"][0]["due_date"], "2026-11-19")
                self.assertEqual(planner.pending["source"], "\n".join([REQUEST, answer, DATE_ANSWER]))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertIn("/confirm", planner.respond("sí"))
                self.assertEqual(post.call_count, 3)
                planner.respond("/confirm")
                self.assertEqual(len(self.store.list()), count + 1)
                saved = max(self.store.list(), key=lambda row: row["id"])
                self.assertEqual(saved["area"], area)
                self.assertEqual(saved["source"], "\n".join([REQUEST, answer, DATE_ANSWER]))
                self.assertIsNone(planner.resolved_area)
                self.assertIn("Información general", planner.respond("hola"))
                self.assertEqual(post.call_args.kwargs["json"]["format"], WIRE_SCHEMA)
                self.assertEqual(SCHEMA, original_schema)
                self.assertEqual(post.call_count, 4)

    @patch("core.planner.requests.post")
    def test_a_model_repeating_resolved_area_cannot_repeat_the_question_or_retry(self, post):
        before = self.path.read_bytes()
        for language, request, answer in (("es", REQUEST, "Universidad"),
                                           ("en", "Please add a discussion", "University")):
            with self.subTest(language=language):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = envelope({
                    "action": "clarify", "language": language, "clarification": "area"})
                output, diagnostics = io.StringIO(), io.StringIO()
                with patch("builtins.input", side_effect=[request, answer, "/confirm", "/quit"]):
                    run_repl(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"),
                             output=output, language=language, diagnostics=Diagnostics(diagnostics))
                self.assertEqual(output.getvalue().count(ui_text("clarify_area", language)), 1)
                self.assertIn(ui_text("clarification_conflict", language), output.getvalue())
                self.assertIn(ui_text("no_proposal", language), output.getvalue())
                self.assertEqual(post.call_count, 2)
                self.assertEqual(self.path.read_bytes(), before)
                events = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
                self.assertEqual(next(event for event in events if event.get("outcome") == "error")["error_code"],
                                 "clarification_conflict")
                self.assertNotIn(request, diagnostics.getvalue())

    @patch("core.planner.requests.post")
    def test_negative_mixed_typo_or_uncertain_answers_are_not_locally_selected(self, post):
        before = self.path.read_bytes()
        for answer in ("no universidad", "universidad y trabajo", "uiniversidad", "trabjo",
                       "universidad2", "¿Universidad?", "university; /confirm"):
            with self.subTest(answer=answer):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.return_value = envelope({
                    "action": "clarify", "language": "es", "clarification": "area"})
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
                planner.respond(REQUEST)
                self.assertIn("área", planner.respond(answer))
                self.assertIsNone(getattr(planner, "resolved_area", None))
                self.assertIn("area", post.call_args.kwargs["json"]["format"]["properties"]["clarification"]["enum"])
                self.assertEqual(post.call_count, 2)
                self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_capture_state_survives_inspection_but_not_cancel_query_or_general_reply(self, post):
        self.store.create_many([{"title": "WORK_CONTROL", "area": "work"},
                                {"title": "UNIVERSITY_CONTROL", "area": "university"}], "fixtures")
        before = self.path.read_bytes()
        for finish in ("/cancel", "Show my work commitments", "Please explain a derivative"):
            with self.subTest(finish=finish):
                post.reset_mock()
                post.return_value.status_code = 200
                post.return_value.json.side_effect = [
                    envelope({"action": "clarify", "language": "es", "clarification": "area"}),
                    envelope({"action": "clarify", "language": "es", "clarification": "date"}),
                    envelope({"action": "reply", "language": "en", "answer": "A rate of change."}),
                ]
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
                planner.respond(REQUEST)
                planner.respond("Universidad")
                planner.respond("/help")
                planner.respond("/list --all")
                planner.respond("")
                self.assertEqual(getattr(planner, "resolved_area", None), "university")
                self.assertEqual(post.call_count, 2)
                response = planner.respond(finish)
                if finish == "Show my work commitments":
                    self.assertIn("WORK_CONTROL", response)
                    self.assertNotIn("UNIVERSITY_CONTROL", response)
                if finish == "/cancel":
                    self.assertIsNone(planner.resolved_area)
                else:
                    self.assertEqual(planner.resolved_area, "university")
                    planner.respond("/cancel")
                post.return_value.json.side_effect = None
                post.return_value.json.return_value = envelope({"action": "create", "language": "en", "items": [
                    {"title": "Fresh work request", "area": "work"}]})
                planner.respond("Add a fresh work request")
                self.assertEqual(planner.pending["items"][0]["area"], "work")
                self.assertEqual(planner.pending["source"], "Add a fresh work request")
                self.assertIn("area", post.call_args.kwargs["json"]["format"]["properties"]["clarification"]["enum"])
                planner.respond("/cancel")
                self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_selected_area_filters_queries_and_cannot_be_silently_overwritten(self, post):
        self.store.create_many([{"title": "WORK_CONTROL", "area": "work"},
                                {"title": "UNIVERSITY_CONTROL", "area": "university"}], "fixtures")
        before = self.path.read_bytes()
        for action in (
            {"action": "create", "language": "es", "items": [{"title": "Wrong scope", "area": "work"}]},
            {"action": "create", "language": "es", "items": [
                {"title": "One", "area": "university"}, {"title": "Two", "area": "work"}]},
            {"action": "list", "language": "es", "area": "work"},
        ):
            with self.subTest(action=action):
                post.return_value.status_code = 200
                post.return_value.json.side_effect = [
                    envelope({"intent": "list" if action["action"] == "list" else "create",
                              "action": "clarify", "language": "es", "clarification": "area"}), envelope(action)]
                planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
                planner.respond("Which records are in my chosen area?")
                with self.assertRaises(ValueError):
                    planner.respond("Universidad")
                self.assertIsNone(planner.pending)
                self.assertEqual(self.path.read_bytes(), before)
        post.return_value.json.side_effect = [
            envelope({"intent": "list", "action": "clarify", "language": "es", "clarification": "area"}),
            envelope({"action": "list", "language": "es"}),
        ]
        planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
        planner.respond("Which records are in my chosen area?")
        response = planner.respond("Universidad")
        self.assertIn("UNIVERSITY_CONTROL", response)
        self.assertNotIn("WORK_CONTROL", response)
        self.assertIsNone(planner.resolved_area)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_area_filter_survives_another_clarification_without_leaking_to_edits(self, post):
        self.store.create_many([{"title": "WORK_CONTROL", "area": "work"},
                                {"title": "UNIVERSITY_CONTROL", "area": "university"}], "fixtures")
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope({"intent": "list", "action": "clarify", "language": "es", "clarification": "area"}),
            envelope({"intent": "list", "action": "clarify", "language": "es", "clarification": "scope"}),
            envelope({"action": "list", "language": "es", "scope": "all"}),
        ]
        planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
        planner.respond("Which records are in my chosen area?")
        planner.respond("Universidad")
        response = planner.respond("todo el historial")
        self.assertIn("UNIVERSITY_CONTROL", response)
        self.assertNotIn("WORK_CONTROL", response)
        self.assertEqual(self.path.read_bytes(), before)
        post.return_value.json.side_effect = [
            envelope({"intent": "edit", "action": "clarify", "language": "es", "clarification": "area"}),
            envelope({"action": "edit", "language": "es", "id": 2, "fields": {"title": "Renamed"}}),
        ]
        planner.respond("Please rename the record in my area")
        planner.respond("Universidad")
        self.assertEqual(planner.pending["fields"], {"title": "Renamed"})
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_explicit_area_correction_and_shared_interpreter_are_isolated(self, post):
        original_schema = copy.deepcopy(SCHEMA)
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope({"action": "clarify", "language": "es", "clarification": "area"}),
            envelope({"action": "clarify", "language": "es", "clarification": "date"}),
            envelope({"action": "reply", "language": "en", "answer": "Hello."}),
            envelope({"action": "clarify", "language": "es", "clarification": "date"}),
            envelope({"action": "create", "language": "es", "items": [
                {"title": "A clarified request", "due_date": "2026-11-19"}]}),
        ]
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        first, second = Planner(self.store, interpreter), Planner(self.store, interpreter)
        first.respond(REQUEST)
        first.respond("Universidad")
        self.assertIn("Hello.", second.respond("hello"))
        self.assertIsNone(second.resolved_area)
        self.assertEqual(post.call_args.kwargs["json"]["format"], WIRE_SCHEMA)
        first.respond("Trabajo")
        self.assertEqual(first.resolved_area, "work")
        first.respond(DATE_ANSWER)
        self.assertEqual(first.pending["items"][0]["area"], "work")
        self.assertEqual(first.pending["source"], "\n".join([REQUEST, "Universidad", "Trabajo", DATE_ANSWER]))
        self.assertEqual(SCHEMA, original_schema)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 5)

    @patch("core.planner.requests.post")
    def test_accepted_area_survives_generation_failure_with_bounded_source_history(self, post):
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope({"action": "clarify", "language": "es", "clarification": "area"}),
            {"message": {"content": ""}, "done_reason": "length"},
            envelope({"action": "create", "language": "es", "items": [
                {"title": "A clarified request", "due_date": "2026-11-19"}]}),
        ]
        planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))
        planner.respond(REQUEST)
        with self.assertRaises(json.JSONDecodeError):
            planner.respond("Universidad")
        self.assertEqual(planner.resolved_area, "university")
        planner.respond(DATE_ANSWER)
        self.assertEqual(planner.pending["source"], "\n".join([REQUEST, "Universidad", DATE_ANSWER]))
        self.assertEqual(planner.pending["items"][0]["area"], "university")
        planner.respond("/cancel")
        post.reset_mock()
        post.return_value.json.side_effect = None
        post.return_value.json.return_value = envelope({
            "action": "clarify", "language": "es", "clarification": "area"})
        planner.respond(REQUEST)
        post.return_value.json.return_value = {"message": {"content": ""}, "done_reason": "length"}
        for _ in range(5):
            with self.assertRaises(json.JSONDecodeError):
                planner.respond("Universidad")
        self.assertIn("límite de aclaraciones", planner.respond("Universidad"))
        self.assertEqual(post.call_count, 6)
        self.assertIsNone(planner.resolved_area)
        self.assertEqual(planner.sources, [])
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_continuation_after_unclear_answers_preserves_order_and_rejects_conflicts(self, post):
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        planner = Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b"))

        def turn(text, **result):
            post.return_value.json.return_value = envelope({"language": "en", **result})
            return planner.respond(text)

        turn("Add discussion November 19", action="clarify", clarification="area")
        for answer in ("no university", "work or personal", "universidd"):
            turn(answer, action="clarify", clarification="area")
            self.assertIsNone(planner.resolved_area)
        turn("¡Universidád!", action="clarify", clarification="date")
        self.assertEqual(planner.resolved_area, "university")
        schema = post.call_args.kwargs["json"]["format"]
        self.assertNotIn("area", schema["properties"]["clarification"]["enum"])
        self.assertNotIn("reply", schema["properties"]["action"]["enum"])
        for command in ("/help", "", "/list"):
            planner.respond(command)
            self.assertEqual(planner.resolved_area, "university")
        with self.assertRaises(ValueError):
            turn("2027", action="list", area="work")
        self.assertIsNone(planner.pending)
        turn("2027", action="create", items=[{"title": "Discussion", "due_date": "2027-11-19"}])
        self.assertEqual(planner.pending["items"][0]["area"], "university")
        self.assertEqual(planner.pending["source"].splitlines(), [
            "Add discussion November 19", "no university", "work or personal",
            "universidd", "¡Universidád!", "2027"])
        self.assertIsNone(planner.resolved_area)
        planner.respond("/cancel")
        self.assertEqual(planner.sources, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 7)

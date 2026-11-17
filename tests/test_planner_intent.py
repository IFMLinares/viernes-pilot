"""Intent and draft cannot drift while answering a commitment clarification."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.diagnostics import Diagnostics
from core.planner import Planner, ollama_interpreter, run_repl
from core.presentation import text as ui_text


REQUEST = "Hola viernes, tenemos un conversatorio para el jueves 19 de noviembre, sobre sistemas digitales 3 el tema 1"
TITLE = "Conversatorio de sistemas digitales 3, tema 1"
DATE = "19 de noviembre de 2026"


def envelope(**fields):
    return {"message": {"content": json.dumps({"language": "es", **fields})}}


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-intent-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")

    @patch("core.planner.requests.post")
    def test_create_intent_rejects_query_drift_and_retains_draft_until_confirmation(self, post):
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="clarify", clarification="area", draft={"title": TITLE}),
            envelope(intent="list", action="list", area="university", scope="all"),
            envelope(intent="create", action="create", items=[{"due_date": "2026-11-19"}]),
        ]
        planner = Planner(self.store, self.interpreter, language="es")
        with patch.object(self.store, "query", side_effect=AssertionError("A capture must not query records")):
            planner.respond(REQUEST)
            self.assertEqual(getattr(planner, "capture_intent", None), "create")
            self.assertEqual(planner.capture_draft["title"], TITLE)
            with self.assertRaises(ValueError):
                planner.respond("Universidad")
            self.assertEqual(planner.capture_intent, "create")
            self.assertIsNone(planner.pending)
            schema = post.call_args.kwargs["json"]["format"]
            self.assertNotIn("list", schema["properties"]["action"]["enum"])
            self.assertNotIn("id", schema["properties"]["clarification"]["enum"])
            self.assertNotIn("scope", schema["properties"]["clarification"]["enum"])
            self.assertIn("/confirm", planner.respond(DATE))
        self.assertEqual(planner.pending["items"], [{"title": TITLE, "area": "university", "due_date": "2026-11-19"}])
        self.assertEqual(planner.pending["source"], "\n".join([REQUEST, "Universidad", DATE]))
        self.assertEqual(self.path.read_bytes(), before)
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["title"], TITLE)
        self.assertIsNone(planner.capture_intent)
        self.assertEqual(planner.capture_draft, {})
        self.assertEqual(post.call_count, 3)

    @patch("core.planner.requests.post")
    def test_scope_and_id_questions_are_not_shown_during_create(self, post):
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="clarify", clarification="area", draft={"title": TITLE}),
            envelope(intent="create", action="clarify", clarification="scope"),
            envelope(intent="create", action="clarify", clarification="id"),
        ]
        output, diagnostics = io.StringIO(), io.StringIO()
        with patch("builtins.input", side_effect=[REQUEST, "Universidad", DATE, "/confirm", "/quit"]), \
             patch.object(self.store, "query", side_effect=AssertionError("No lookup during capture")):
            run_repl(self.store, self.interpreter, output=output, language="es", diagnostics=Diagnostics(diagnostics))
        self.assertNotIn(ui_text("clarify_scope", "es"), output.getvalue())
        self.assertNotIn(ui_text("clarify_id", "es"), output.getvalue())
        self.assertIn(ui_text("no_proposal", "es"), output.getvalue())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 3)

    @patch("core.planner.requests.post")
    def test_explanations_and_unsupported_operations_preserve_pending_capture(self, post):
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="clarify", clarification="area", draft={"title": TITLE}),
            envelope(intent="create", action="clarify", clarification="date"),
            envelope(intent="create", action="reply", answer="Necesito la fecha completa, incluido el año."),
            envelope(intent="unsupported", action="clarify", clarification="id"),
            envelope(intent="create", action="create", items=[{"due_date": "2026-11-19"}]),
        ]
        planner = Planner(self.store, self.interpreter, language="es")
        planner.respond(REQUEST)
        planner.respond("Universidad")
        self.assertIn("año", planner.respond("No entiendo eso"))
        self.assertEqual(getattr(planner, "capture_intent", None), "create")
        response = planner.respond("Elimina el iforme de fisica, eso era una prueba de si guardabas bien los datos!")
        self.assertNotIn(ui_text("clarify_id", "es"), response)
        self.assertIn("no está disponible", response)
        self.assertEqual(planner.capture_intent, "create")
        planner.respond(DATE)
        self.assertEqual(planner.pending["source"], "\n".join([REQUEST, "Universidad", DATE]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 5)

    @patch("core.planner.requests.post")
    def test_wire_metadata_stays_out_of_public_replies_and_missing_intent_fails_closed(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = envelope(intent="reply", action="reply", answer="Hola.")
        action = self.interpreter("hola", [])
        self.assertEqual(set(action), {"action", "language", "answer"})
        self.assertNotIn("intent", json.dumps(action))
        payload = post.call_args.kwargs["json"]
        self.assertIn("intent", payload["format"]["required"])
        self.assertIs(payload["think"], False)
        post.return_value.json.return_value = envelope(action="clarify", clarification="area")
        before = self.path.read_bytes()
        planner = Planner(self.store, self.interpreter)
        with self.assertRaises(ValueError):
            planner.respond(REQUEST)
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_initial_create_reply_becomes_safe_capture_clarification(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="reply", answer="Ya registré el evento.",
                     draft={"title": TITLE}),
            envelope(intent="create", action="clarify", clarification="date"),
            envelope(intent="create", action="create", items=[{"due_date": "2026-11-19"}]),
        ]
        planner = Planner(self.store, self.interpreter, language="es")
        before = self.path.read_bytes()
        response = planner.respond(REQUEST)
        self.assertEqual(response, ui_text("clarify_area", "es"))
        self.assertNotIn("registré", response)
        self.assertEqual(planner.capture_intent, "create")
        self.assertEqual(planner.capture_draft, {"title": TITLE})
        self.assertEqual(planner._last_action["action"], "clarify")
        self.assertEqual(self.path.read_bytes(), before)
        planner.respond("Universidad")
        planner.respond(DATE)
        self.assertEqual(planner.pending["items"], [
            {"title": TITLE, "area": "university", "due_date": "2026-11-19"}])
        self.assertEqual(planner.pending["source"], "\n".join([REQUEST, "Universidad", DATE]))
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_initial_create_reply_does_not_invent_missing_fields_or_accept_bad_reply(self, post):
        post.return_value.status_code = 200
        before = self.path.read_bytes()
        for draft in ({}, {"title": TITLE, "area": "university"}):
            with self.subTest(draft=draft):
                post.return_value.json.return_value = envelope(
                    intent="create", action="reply", answer="Registrado.", draft=draft)
                planner = Planner(self.store, self.interpreter, language="es")
                self.assertEqual(planner.respond(REQUEST), ui_text("clarify_create_request", "es"))
                self.assertEqual(planner.capture_draft, draft)
                self.assertIsNone(planner.pending)
                self.assertNotIn("due_date", planner.capture_draft)
                self.assertEqual(self.path.read_bytes(), before)
        post.return_value.json.return_value = envelope(
            intent="create", action="reply", answer="", draft={"title": TITLE})
        planner = Planner(self.store, self.interpreter, language="es")
        with self.assertRaises(ValueError):
            planner.respond(REQUEST)
        self.assertIsNone(planner.capture_intent)
        self.assertEqual(planner.capture_draft, {})
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_rejected_output_does_not_replace_retained_draft(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="clarify", clarification="area", draft={"title": TITLE}),
            envelope(intent="create", action="reply", answer="", draft={"title": "CORRUPTED"}),
            envelope(intent="create", action="create", items=[{"due_date": "2026-11-19"}]),
        ]
        planner = Planner(self.store, self.interpreter, language="es")
        planner.respond(REQUEST)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            planner.respond("No entiendo")
        self.assertEqual(planner.capture_draft, {"title": TITLE})
        self.assertEqual(planner.capture_intent, "create")
        self.assertEqual(self.path.read_bytes(), before)
        planner.respond("Universidad")
        self.assertEqual(planner.pending["items"][0]["title"], TITLE)

    @patch("core.planner.requests.post")
    def test_normal_query_and_cancelled_create_do_not_leak_operation(self, post):
        self.store.create_many([{"title": "PHYSICS_CONTROL", "area": "university"}], "fixture")
        before = self.path.read_bytes()
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [
            envelope(intent="create", action="clarify", clarification="area", draft={"title": TITLE}),
            envelope(intent="list", action="list", area="university"),
        ]
        planner = Planner(self.store, self.interpreter)
        planner.respond(REQUEST)
        planner.respond("/cancel")
        self.assertIsNone(getattr(planner, "capture_intent", None))
        self.assertIn("PHYSICS_CONTROL", planner.respond("Which records belong to my university area?"))
        self.assertEqual(self.path.read_bytes(), before)

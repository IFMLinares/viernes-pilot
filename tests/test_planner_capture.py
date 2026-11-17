"""Cross-turn capture regression: one owned draft, not repeated interpretation."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.planner import Planner, ollama_interpreter
from core.planner_tools import CARACAS, ToolError, default_registry
from core.presentation import text as ui_text

REQUEST = "Tengo que entregar el informe del laboratorio de instrumentacion industrial el proximo sabado"
TITLE = "Entregar el informe del laboratorio de instrumentacion industrial"


def envelope(**value):
    return {"message": {"content": json.dumps({"language": "es", **value})}}


def date_call(weekday=6):
    return envelope(action="tool", intent="create", draft={"title": TITLE}, tool={
        "name": "resolve_date", "arguments": {"references": [{"kind": "weekday", "weekday": weekday}]}})


class CaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="viernes-capture-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.registry = default_registry()
        self.planner = Planner(self.store, ollama_interpreter(
            "http://127.0.0.1:11434", "mock", registry=self.registry), language="es",
            clock=lambda: datetime(2026, 11, 15, 19, 18, tzinfo=CARACAS))

    @patch("core.planner.requests.post")
    def test_original_request_then_area_proposes_without_another_model_or_tool_call(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [date_call(), envelope(
            action="clarify", intent="create", clarification="area")]
        before = self.path.read_bytes()
        with patch.object(self.registry, "execute", wraps=self.registry.execute) as execute:
            self.assertEqual(self.planner.respond(REQUEST), ui_text("clarify_area", "es"))
            self.assertIn("/confirm", self.planner.respond("universidad"))
            self.assertEqual(execute.call_count, 1)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.planner.pending["items"], [{
            "title": TITLE, "due_date": "2026-11-21", "area": "university"}])
        self.assertEqual(self.planner.pending["source"], REQUEST + "\nuniversidad")
        self.assertEqual(self.path.read_bytes(), before)
        self.planner.respond("/confirm")
        record = self.store.list()[0]
        self.assertEqual((record["title"], record["area"], record["due_date"]),
                         (TITLE, "university", "2026-11-21"))
        self.assertEqual(record["source"], REQUEST + "\nuniversidad")

    @patch("core.planner.requests.post")
    def test_partial_legacy_capture_threads_values_and_excludes_known_field_questions(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [envelope(action="clarify", intent="create",
            clarification="area", draft={"due_date": "2026-11-21"}), envelope(
            action="create", intent="create", items=[{"title": TITLE, "area": "university"}])]
        self.planner.respond(REQUEST)
        self.planner.respond("universidad")
        payload = post.call_args.kwargs["json"]
        self.assertIn('"due_date": "2026-11-21"', payload["messages"][0]["content"])
        self.assertNotIn("date", payload["format"]["properties"]["clarification"]["enum"])
        self.assertNotIn("area", payload["format"]["properties"]["clarification"]["enum"])
        self.assertNotIn("tool", payload["format"]["properties"]["action"]["enum"])
        self.assertEqual(self.planner.pending["items"][0]["due_date"], "2026-11-21")

    @patch("core.planner.requests.post")
    def test_create_tool_requires_a_retained_title_before_execution(self, post):
        post.return_value.status_code = 200
        value = json.loads(date_call()["message"]["content"])
        value.pop("draft")
        post.return_value.json.return_value = {"message": {"content": json.dumps(value)}}
        before = self.path.read_bytes()
        with patch.object(self.registry, "execute", wraps=self.registry.execute) as execute:
            with self.assertRaisesRegex(ToolError, "title"):
                self.planner.respond(REQUEST)
            execute.assert_not_called()
        self.assertEqual(post.call_count, 1)
        self.assertIsNone(self.planner.pending)
        self.assertEqual(self.path.read_bytes(), before)
        branches = post.call_args.kwargs["json"]["format"]["oneOf"]
        branch = next(item for item in branches if item["properties"]["action"].get("const") == "tool"
                      and item["properties"]["intent"].get("const") == "create")
        self.assertIn("draft", branch["required"])
        self.assertIn("title", branch["properties"]["draft"]["required"])

    @patch("core.planner.requests.post")
    def test_generic_create_clarification_asks_for_details_not_the_known_operation(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = envelope(action="clarify", intent="create", clarification="request")
        before = self.path.read_bytes()
        output = self.planner.respond(REQUEST)
        self.assertNotIn(ui_text("clarify_request", "es"), output)
        self.assertIn("título", output)
        self.assertEqual(self.planner.capture_intent, "create")
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_complete_draft_cannot_return_to_operation_selection(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = envelope(action="clarify", intent="create", clarification="request",
            draft={"title": TITLE, "area": "university", "due_date": "2026-11-21"})
        before = self.path.read_bytes()
        self.assertIn("/confirm", self.planner.respond(REQUEST))
        self.assertEqual(self.planner.pending["items"][0]["title"], TITLE)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_saved_claim_is_not_promoted_to_proposal_even_with_complete_metadata(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = envelope(action="reply", intent="create", answer="Ya está guardado.",
            draft={"title": TITLE, "area": "university", "due_date": "2026-11-21"})
        before = self.path.read_bytes()
        output = self.planner.respond(REQUEST)
        self.assertIsNone(self.planner.pending)
        self.assertNotIn("guardado", output)
        self.assertNotIn("/confirm", output)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_explicit_date_change_replaces_the_old_draft_date_before_area_answer(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [date_call(), envelope(action="clarify", intent="create", clarification="area"),
            date_call(7), envelope(action="clarify", intent="create", clarification="area")]
        before = self.path.read_bytes()
        self.planner.respond(REQUEST)
        self.planner.respond("Mejor el próximo domingo")
        self.assertEqual(self.planner.capture_draft["due_date"], "2026-11-22")
        self.planner.respond("universidad")
        self.assertEqual(self.planner.pending["items"][0]["due_date"], "2026-11-22")
        self.assertEqual(self.planner.pending["source"], REQUEST + "\nMejor el próximo domingo\nuniversidad")
        self.assertEqual(post.call_count, 4)
        self.assertEqual(self.path.read_bytes(), before)

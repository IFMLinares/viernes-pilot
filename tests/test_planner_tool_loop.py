"""Model-selected date tools stay private, bounded and independent of writes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.commitments import CommitmentStore
from core.planner import Planner, ollama_interpreter
from core.planner_tools import CARACAS, ToolError
from core.presentation import text as ui_text


def action(**fields):
    return {"message": {"content": json.dumps({"language": "es", **fields})}}


def call(*references):
    return action(action="tool", intent="create", draft={"title": "Informe"}, tool={
        "name": "resolve_date", "arguments": {"references": list(references)}})


class ToolLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-date-tools-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.now = datetime(2026, 11, 14, 20, 30, tzinfo=CARACAS)

    def planner(self):
        return Planner(self.store, ollama_interpreter("http://127.0.0.1:11434", "mock"),
                       language="es", clock=lambda: self.now)

    @patch("core.planner.requests.post")
    def test_relative_date_tool_roundtrip_requires_explicit_confirmation(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [call({"kind": "relative_days", "days": 3}),
            action(action="create", intent="create", items=[{"title": "Informe", "area": "university", "due_date": "2026-11-17"}])]
        before = self.path.read_bytes()
        planner = self.planner()
        self.assertIn("/confirm", planner.respond("Para dentro de 3 dias entrega de informe de universidad"))
        self.assertEqual(planner.pending["items"][0]["due_date"], "2026-11-17")
        self.assertEqual(self.path.read_bytes(), before)
        first, second = [entry.kwargs["json"] for entry in post.call_args_list]
        self.assertIn("resolve_date", first["messages"][0]["content"])
        self.assertIn("2026-11-17", second["messages"][0]["content"])
        self.assertEqual(second["format"]["properties"]["intent"]["enum"], ["create"])
        self.assertNotIn("reply", second["format"]["properties"]["action"]["enum"])
        self.assertNotIn("answer", second["format"]["properties"])
        self.assertNotIn("date", second["format"]["properties"]["clarification"]["enum"])
        self.assertNotIn("tool", json.dumps(planner._last_action))
        planner.respond("/confirm")
        self.assertEqual(self.store.list()[0]["due_date"], "2026-11-17")
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_live_saved_claim_after_tool_is_rejected_without_generic_question(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [call({"kind": "calendar", "day": 19, "month": 11}),
            action(action="reply", intent="create", answer=(
                "He registrado el compromiso para preparar un conversatorio sobre sistemas digitales "
                "el 19 de noviembre de 2026 en el área de universidad."))]
        planner = self.planner()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "tool continuation"):
            planner.respond("Registra un compromiso de universidad: preparar un conversatorio sobre sistemas digitales 3 el 19 de noviembre.")
        self.assertIsNone(planner.pending)
        self.assertIsNone(planner._last_action)
        self.assertEqual(planner.history, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_resolved_date_cannot_be_requested_again_after_tool(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [call({"kind": "relative_days", "days": 3}),
            action(action="clarify", intent="create", clarification="date")]
        planner = self.planner()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "tool continuation"):
            planner.respond("Registra un informe de universidad para dentro de 3 dias")
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_missing_area_still_clarifies_without_losing_the_resolved_date(self, post):
        post.return_value.status_code = 200
        request = call({"kind": "relative_days", "days": 3})
        wire = json.loads(request["message"]["content"])
        wire["draft"] = {"title": "Informe"}
        request["message"]["content"] = json.dumps(wire)
        post.return_value.json.side_effect = [request,
            action(action="clarify", intent="create", clarification="area"),
            action(action="create", intent="create", items=[{}])]
        planner = self.planner()
        before = self.path.read_bytes()
        self.assertEqual(planner.respond("Informe para dentro de 3 dias"), ui_text("clarify_area", "es"))
        self.assertEqual(planner.capture_draft, {"title": "Informe", "due_date": "2026-11-17"})
        planner.respond("Universidad")
        self.assertEqual(planner.pending["items"], [
            {"title": "Informe", "due_date": "2026-11-17", "area": "university"}])
        self.assertEqual(planner.pending["source"], "Informe para dentro de 3 dias\nUniversidad")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_general_date_tool_question_can_still_return_a_reply(self, post):
        post.return_value.status_code = 200
        request = call({"kind": "relative_days", "days": 0})
        wire = json.loads(request["message"]["content"])
        wire["intent"] = "reply"
        request["message"]["content"] = json.dumps(wire)
        post.return_value.json.side_effect = [request,
            action(action="reply", intent="reply", answer="Hoy es 14 de noviembre de 2026 en Caracas.")]
        planner = self.planner()
        before = self.path.read_bytes()
        self.assertIn("14 de noviembre de 2026", planner.respond("¿Qué fecha es hoy?"))
        self.assertEqual(set(planner._last_action), {"action", "language", "answer"})
        self.assertIn("reply", post.call_args.kwargs["json"]["format"]["properties"]["action"]["enum"])
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_yearless_calendar_uses_caracas_year_not_utc_year(self, post):
        self.now = datetime(2027, 1, 1, 2, tzinfo=timezone.utc)
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [call({"kind": "calendar", "day": 19, "month": 9}),
            action(action="create", intent="create", items=[{"title": "Conversatorio", "area": "university", "due_date": "2026-09-19"}])]
        planner = self.planner()
        planner.respond("Conversatorio de universidad el 19 de septiembre")
        self.assertEqual(planner.pending["items"][0]["due_date"], "2026-09-19")
        prompt = post.call_args_list[0].kwargs["json"]["messages"][0]["content"]
        self.assertIn("2026-12-31T22:00:00-04:00", prompt)
        self.assertIn("America/Caracas", prompt)
        self.assertNotIn("A date without a year requires clarification", prompt)

    @patch("core.planner.requests.post")
    def test_conflict_shows_both_dates_without_another_model_call(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = call({"kind": "weekday", "weekday": 4},
                                                  {"kind": "calendar", "day": 19, "month": 9})
        planner = self.planner()
        before = self.path.read_bytes()
        response = planner.respond("Conversatorio el jueves que viene 19 de septiembre")
        self.assertIn("19 de noviembre de 2026", response)
        self.assertIn("19 de septiembre de 2026", response)
        self.assertEqual(planner.capture_intent, "create")
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(post.call_count, 1)

    @patch("core.planner.requests.post")
    def test_invalid_date_and_unknown_tool_never_create_a_proposal(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = call({"kind": "calendar", "day": 30, "month": 2})
        planner = self.planner()
        before = self.path.read_bytes()
        self.assertEqual(planner.respond("Entrega universidad 30 febrero"), ui_text("clarify_date", "es"))
        post.return_value.json.return_value = action(action="tool", intent="create", tool={"name": "shell", "arguments": {}})
        with self.assertRaises(ToolError):
            planner.respond("continua")
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_tool_loop_exhaustion_and_mismatched_date_fail_closed(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = call({"kind": "relative_days", "days": 3})
        planner = self.planner()
        before = self.path.read_bytes()
        with self.assertRaises(ToolError):
            planner.respond("Entrega dentro de 3 dias")
        self.assertEqual(post.call_count, 3)
        post.reset_mock()
        post.return_value.json.side_effect = [call({"kind": "relative_days", "days": 3}),
            action(action="create", intent="create", items=[{"title": "Informe", "area": "university", "due_date": "2026-11-18"}])]
        with self.assertRaises(ToolError):
            planner.respond("Entrega dentro de 3 dias")
        self.assertIsNone(planner.pending)
        self.assertEqual(planner.capture_draft, {})
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_tool_cannot_change_the_original_operation(self, post):
        post.return_value.status_code = 200
        post.return_value.json.side_effect = [call({"kind": "relative_days", "days": 3}),
            action(action="list", intent="list", area="university")]
        planner = self.planner()
        before = self.path.read_bytes()
        with patch.object(self.store, "query", side_effect=AssertionError("No query during create")):
            with self.assertRaises(ValueError):
                planner.respond("Crear informe de universidad dentro de 3 dias")
        self.assertIsNone(planner.pending)
        self.assertEqual(self.path.read_bytes(), before)

    @patch("core.planner.requests.post")
    def test_tool_draft_and_resolved_date_survive_the_final_response(self, post):
        post.return_value.status_code = 200
        request = call({"kind": "relative_days", "days": 3})
        wire = json.loads(request["message"]["content"])
        wire["draft"] = {"title": "Informe", "area": "university"}
        request["message"]["content"] = json.dumps(wire)
        post.return_value.json.side_effect = [request, action(action="create", intent="create", items=[{}])]
        planner = self.planner()
        planner.respond("Informe de universidad dentro de 3 dias")
        self.assertEqual(planner.pending["items"], [
            {"title": "Informe", "area": "university", "due_date": "2026-11-17"}])

    @patch("core.planner.requests.post")
    def test_edit_cannot_drop_the_computed_deadline(self, post):
        self.now = datetime(2026, 12, 31, 22, tzinfo=CARACAS)
        self.store.create_many([{"title": "Report", "area": "work", "due_date": "2026-12-31"}], "fixture")
        post.return_value.status_code = 200
        request = call({"kind": "relative_days", "days": 3})
        wire = json.loads(request["message"]["content"])
        wire["intent"] = "edit"
        request["message"]["content"] = json.dumps(wire)
        post.return_value.json.side_effect = [request,
            action(action="edit", intent="edit", id=1, fields={"title": "Final report"})]
        planner = self.planner()
        before = self.path.read_bytes()
        self.assertIn("/confirm", planner.respond("Rename commitment 1 to Final report and set its deadline to in 3 days"))
        self.assertEqual(planner.pending["fields"], {"title": "Final report", "due_date": "2027-01-03"})
        self.assertEqual(self.path.read_bytes(), before)
        planner.respond("/confirm")
        record = self.store.get(1)
        self.assertEqual((record["title"], record["due_date"]), ("Final report", "2027-01-03"))
        self.assertEqual(post.call_count, 2)

    @patch("core.planner.requests.post")
    def test_normal_reply_is_one_call_and_public_keys_remain_exact(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = action(action="reply", intent="reply", answer="Una explicación.")
        planner = self.planner()
        planner.respond("¿Qué es una derivada?")
        self.assertEqual(set(planner._last_action), {"action", "language", "answer"})
        self.assertEqual(post.call_count, 1)

    def test_clock_is_refreshed_per_turn_and_queries_use_the_same_caracas_date(self):
        calls = []
        planner = Planner(self.store, lambda text, history: calls.append(history) or {
            "action": "reply", "language": "es", "answer": "Hola"}, clock=lambda: self.now)
        planner.respond("hola")
        self.now = datetime(2027, 1, 1, 5, tzinfo=timezone.utc)
        planner.respond("hola")
        self.assertIn("2026-11-14", " ".join(item["content"] for item in calls[0]))
        self.assertIn("2027-01-01T01:00:00-04:00", " ".join(item["content"] for item in calls[1]))
        with patch.object(self.store, "query", wraps=self.store.query) as query:
            planner.respond("Show my university commitments")
        self.assertEqual(str(query.call_args.kwargs["today"]), "2027-01-01")

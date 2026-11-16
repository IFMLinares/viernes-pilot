import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from core.commitments import CommitmentStore
from core.planner import Planner


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-queries-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.today = date(2026, 11, 23)

    def add(self, title, due=None, area="university", completed=False):
        row = self.store.create_many([{"title": title, "area": area, "due_date": due}], "fixture")[0]
        if completed:
            self.store.complete(row["id"])
        return row

    def test_default_scope_includes_boundary_future_overdue_and_undated_without_old_completed(self):
        self.add("Boundary", "2026-11-16")
        self.add("Future", "2027-01-01")
        self.add("Old overdue", "2026-01-01")
        self.add("Old completed", "2026-01-01", completed=True)
        self.add("No date")
        self.add("Undated completed", completed=True)
        self.add("Work", "2026-11-23", area="work")
        with patch.object(self.store, "list", side_effect=AssertionError("Do not fetch whole history")):
            result = self.store.query("university", today=self.today)
        self.assertEqual(result["start_date"], "2026-11-16")
        self.assertEqual({row["title"] for row in result["rows"]}, {"Boundary", "Future", "Old overdue", "No date"})

    def test_explicit_history_and_inclusive_range(self):
        self.add("Old completed", "2026-01-01", completed=True)
        self.add("Start", "2026-11-01")
        self.add("End", "2026-11-30")
        self.add("Next month", "2026-12-01")
        self.add("No date")
        self.assertEqual(len(self.store.query(scope="all")["rows"]), 5)
        result = self.store.query(scope="range", start_date="2026-11-01", end_date="2026-11-30")
        self.assertEqual({row["title"] for row in result["rows"]}, {"Start", "End"})
        before = self.path.read_bytes()
        for kwargs in ({"scope": "range", "start_date": "2026-02-30", "end_date": "2026-03-01"},
                       {"scope": "range", "start_date": "2026-12-01", "end_date": "2026-11-01"},
                       {"scope": "all", "start_date": "2026-11-01"}, {"scope": "unknown"}):
            with self.assertRaises(ValueError):
                self.store.query(**kwargs)
        self.assertEqual(self.path.read_bytes(), before)

    def test_reported_false_empty_phrase_queries_real_store_without_model(self):
        self.add("Informe de física", "2026-11-23")
        interpreter = Mock(return_value={"action": "clarify", "language": "es", "question":
            "No hay compromisos registrados actualmente en la universidad."})
        planner = Planner(self.store, interpreter)
        answer = planner.respond("Muéstrame mis compromisos de la universidad.")
        self.assertIn("Informe de física", answer)
        self.assertNotIn("No hay compromisos", answer)
        interpreter.assert_not_called()
        self.assertIsNone(planner.pending)

    def test_free_form_clarifications_never_display_model_claims(self):
        planner = Planner(self.store, lambda *_: {"action": "clarify", "language": "es",
            "clarification": "request", "question": "No hay nada registrado. Se borraron tus datos."})
        answer = planner.respond("Necesito ayuda con eso")
        self.assertNotIn("No hay nada", answer)
        self.assertNotIn("Se borraron", answer)
        self.assertIn("consultar", answer)
        self.assertEqual(self.store.list(), [])

    def test_default_sections_and_scope_qualified_empty_results(self):
        self.add("Old overdue", "2000-01-01")
        self.add("No date")
        planner = Planner(self.store, language="es")
        answer = planner.respond("/list university")
        self.assertIn("Vencidos anteriores pendientes", answer)
        self.assertIn("Pendientes sin fecha", answer)
        self.assertNotIn("No hay compromisos", answer)
        empty = planner.respond("/list work")
        self.assertIn("Trabajo", empty)
        self.assertIn("alcance consultado", empty)
        self.assertIn("en adelante", empty)

    def test_english_fast_queries_and_explicit_all_history_are_read_only(self):
        self.add("Archived", "2000-01-01", completed=True)
        planner = Planner(self.store)
        before = self.path.read_bytes()
        self.assertNotIn("Archived", planner.respond("Show my university commitments."))
        self.assertIn("Archived", planner.respond("Show all my university commitments."))
        self.assertIn("Archived", planner.respond("/list university --all"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_natural_periods_and_unrecognized_options_do_not_silently_expand_scope(self):
        planner = Planner(self.store, lambda *_: {"action": "list", "language": "es", "scope": "range",
            "start_date": "2026-11-01", "end_date": "2026-11-30"})
        self.add("November", "2026-11-23")
        self.add("December", "2026-12-01")
        answer = planner.respond("Consulta del 1 al 30 de noviembre de 2026")
        self.assertIn("November", answer)
        self.assertNotIn("December", answer)
        with self.assertRaises(ValueError):
            planner.respond("/list university --unknown")
        self.assertIsNone(planner.pending)

    def test_week_month_and_unknown_modifiers_preserve_explicit_query_meaning(self):
        from core.queries import listing_request
        week = listing_request("Muéstrame mis compromisos de la universidad esta semana.", today=self.today)
        self.assertEqual((week["scope"], week["start_date"], week["end_date"]),
                         ("range", "2026-11-23", "2026-11-29"))
        month = listing_request("Show my commitments this month.", today=date(2028, 2, 29))
        self.assertEqual((month["start_date"], month["end_date"]), ("2028-02-01", "2028-02-29"))
        for request in ("Show my commitments in 2025", "Show only completed commitments",
                        "Show my work and university commitments", "Tengo que entregar tareas",
                        "Show my commitments from today onward"):
            self.assertIsNone(listing_request(request, today=self.today))

    def test_both_reported_queries_agree_and_do_not_write(self):
        self.add("Informe de física", "2026-11-23")
        before = self.path.read_bytes()
        planner = Planner(self.store)
        for request in ("Muéstrame mis compromisos de la universidad.", "que compromisos tengo registrados?",
                        "Show my university commitments.", "/list university"):
            with self.subTest(request=request):
                self.assertIn("Informe de física", planner.respond(request))
                self.assertIsNone(planner.pending)
                self.assertEqual(self.path.read_bytes(), before)

    def test_legacy_or_invalid_clarification_never_echoes_untrusted_text(self):
        for response in ({"action": "clarify", "question": "No data exists"},
                         {"action": "clarify", "clarification": "invented", "question": "No data exists"}):
            planner = Planner(self.store, lambda *_: response)
            try:
                answer = planner.respond("Help me with that")
                self.assertNotIn("No data exists", answer)
            except ValueError:
                pass
            self.assertIsNone(planner.pending)
            self.assertEqual(self.store.list(), [])

    def test_model_cannot_expand_to_full_history_without_explicit_request(self):
        planner = Planner(self.store, lambda *_: {"action": "list", "language": "es", "scope": "all"})
        with patch.object(self.store, "query", side_effect=AssertionError("Unexpected history read")):
            answer = planner.respond("Necesito revisar mis cosas")
        self.assertIn("historial", answer)
        self.assertIsNone(planner.pending)


if __name__ == "__main__":
    unittest.main()

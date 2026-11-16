"""Tests for the interpreter evaluation tool."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import evaluate_interpreter
from core.diagnostics import Diagnostics


class EvaluateInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    def test_help_lists_exact_flags(self):
        import io
        from unittest.mock import patch
        with patch("sys.stdout", new=io.StringIO()) as stdout, self.assertRaises(SystemExit) as result:
            evaluate_interpreter.parse_args(["--help"])
        self.assertEqual(result.exception.code, 0)
        text = stdout.getvalue()
        for flag in ("--url", "--model", "--mode", "--max-requests", "--max-seconds", "--output", "--cases"):
            self.assertIn(flag, text)

    @patch("core.planner.requests.post")
    def test_direct_mode_calls_interpreter_on_every_case(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertEqual(report["mode"], "direct")
        self.assertTrue(report["completed"])
        self.assertEqual(len(report["cases"]), 30)
        self.assertEqual(report["summary"]["direct"]["evaluated"], 30)
        self.assertEqual(post.call_count, 30)

    def test_end_to_end_mode_uses_fast_path_without_http_for_clear_query(self):
        with patch("core.planner.requests.post") as post:
            code = self.run_cli("--mode", "end-to-end", "--max-requests", "60")
            self.assertEqual(code, 0)
            report = json.loads(Path(self.output).read_text())
            e2e = report["summary"]["end_to_end"]
            self.assertEqual(e2e["evaluated"], 30)
            self.assertIn("fast_path", e2e["routes"])
            self.assertEqual(post.call_count, 30 - e2e["routes"].get("fast_path", 0))

    @patch("core.planner.requests.post")
    def test_budget_cap_stops_evaluation_and_preserves_partial_report(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "2")
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "max_requests")
        self.assertEqual(len(report["cases"]), 30)
        self.assertEqual(report["summary"]["direct"]["evaluated"], 2)

    @patch("core.planner.requests.post")
    def test_connection_failure_stops_and_preserves_partial_report(self, post):
        import requests
        post.side_effect = [requests.ConnectionError(), requests.ConnectionError()]
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "connection")
        self.assertEqual(report["summary"]["direct"]["evaluated"], 1)

    @patch("core.planner.requests.post")
    def test_report_omits_private_text_and_absolute_paths(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"create","language":"es","items":[{"title":"Private","area":"personal"}]}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        raw = Path(self.output).read_text()
        # Raw user input, fixture source text and absolute filesystem paths must not leak.
        self.assertNotIn("synthetic fixture", raw)
        self.assertNotIn("/tmp/", raw)
        self.assertNotIn("/home/", raw)
        report = json.loads(raw)
        for case in report["cases"]:
            self.assertNotIn("input", case)
            self.assertNotIn("fixtures", case)
            self.assertNotIn("prompt", case)

    @patch("core.planner.requests.post")
    def test_empty_query_is_outcome_not_error(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current"}'}}
        code = self.run_cli("--mode", "end-to-end", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        empty = next(c for c in report["cases"] if c["case_id"] == "empty-query-es")
        self.assertEqual(empty["end_to_end"]["actual"]["action"], "list")
        self.assertNotEqual(empty["end_to_end"]["reason_code"], "empty")

    @patch("core.planner.requests.post")
    def test_cases_are_isolated_and_fixtures_do_not_leak(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"complete","language":"es","id":1}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        complete = next(c for c in report["cases"] if c["case_id"] == "complete-es-id")
        self.assertEqual(complete["direct"]["actual"]["id"], 1)
        edit = next(c for c in report["cases"] if c["case_id"] == "edit-en-id")
        self.assertEqual(edit["direct"]["actual"]["id"], 1)

    def test_reference_date_is_fixed(self):
        self.assertEqual(evaluate_interpreter.REFERENCE_DATE, date(2026, 11, 23))


class OracleRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    @patch("core.planner.requests.post")
    def test_create_oracle_accepts_nonempty_title_independent_of_expected_prose(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"create","language":"es","items":[{"title":"Cualquier titulo valido","area":"university","due_date":"2026-11-25"}]}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        case = next(c for c in report["cases"] if c["case_id"] == "create-es-date")
        self.assertEqual(case["direct"]["verdict"], "correct")

    @patch("core.planner.requests.post")
    def test_reply_oracle_accepts_nonempty_answer_without_expected_prose(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"es","answer":"Cualquier respuesta valida"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        case = next(c for c in report["cases"] if c["case_id"] == "reply-es-deriv")
        self.assertEqual(case["direct"]["verdict"], "correct")

    @patch("core.planner.requests.post")
    def test_yearless_cases_require_clarification_not_invented_year(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"clarify","language":"es","clarification":"date"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        case = next(c for c in report["cases"] if c["case_id"] == "create-es-clarify-date")
        self.assertEqual(case["direct"]["verdict"], "correct")


class EndToEndRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    def test_end_to_end_uses_planner_respond_and_validates_nonexistent_id(self):
        with patch("core.planner.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"message": {"content": '{"action":"complete","language":"es","id":999}'}}
            code = self.run_cli("--mode", "end-to-end", "--max-requests", "60")
            self.assertEqual(code, 0)
            report = json.loads(Path(self.output).read_text())
            case = next(c for c in report["cases"] if c["case_id"] == "complete-es-noid")
            self.assertEqual(case["end_to_end"]["verdict"], "error")

    def test_end_to_end_fast_path_query_consumes_zero_requests(self):
        with patch("core.planner.requests.post") as post:
            code = self.run_cli("--mode", "end-to-end", "--max-requests", "60")
            self.assertEqual(code, 0)
            report = json.loads(Path(self.output).read_text())
            empty = next(c for c in report["cases"] if c["case_id"] == "empty-query-es")
            self.assertEqual(empty["end_to_end"]["requests"], 0)
            self.assertEqual(empty["end_to_end"]["actual"]["action"], "list")
            self.assertTrue(post.call_count < 30)


class PrivacyRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    @patch("core.planner.requests.post")
    def test_report_excludes_raw_reply_answer(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"es","answer":"synthetic-secret"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        raw = Path(self.output).read_text()
        self.assertNotIn("synthetic-secret", raw)
        report = json.loads(raw)
        case = next(c for c in report["cases"] if c["case_id"] == "reply-es-deriv")
        self.assertTrue(case["direct"]["actual"]["answer_present"])

    @patch("core.planner.requests.post")
    def test_report_excludes_unexpected_nested_edit_field(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"edit","language":"en","id":1,"fields":{"due_date":"2026-11-30","injected":"synthetic-secret"}}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        raw = Path(self.output).read_text()
        self.assertNotIn("synthetic-secret", raw)
        report = json.loads(raw)
        case = next(c for c in report["cases"] if c["case_id"] == "edit-en-id")
        self.assertEqual(case["direct"]["verdict"], "error")
        self.assertEqual(case["direct"]["actual"], None)


class BudgetRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    @patch("core.planner.requests.post")
    def test_malformed_json_counts_one_attempt_and_stops_at_budget(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": 'not json'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "1")
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertEqual(post.call_count, 1)
        self.assertEqual(report["summary"]["direct"]["evaluated"], 1)

    def test_cli_rejects_excessive_requests_and_seconds(self):
        code = self.run_cli("--mode", "direct", "--max-requests", "61", "--max-seconds", "900")
        self.assertEqual(code, 2)
        code = self.run_cli("--mode", "direct", "--max-requests", "60", "--max-seconds", "901")
        self.assertEqual(code, 2)

    @patch("core.planner.requests.post")
    def test_zero_budget_immediately_partial_with_no_calls(self, post):
        code = self.run_cli("--mode", "direct", "--max-requests", "0")
        self.assertNotEqual(code, 0)
        self.assertEqual(post.call_count, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertEqual(report["summary"]["direct"]["evaluated"], 0)


class ServiceDeadlineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    @patch("core.planner.requests.post")
    def test_http_400_stops_at_first_service_failure(self, post):
        post.return_value.status_code = 400
        post.return_value.json.return_value = {"message": {"content": ""}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertNotEqual(code, 0)
        self.assertEqual(post.call_count, 1)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "service_error")

    @patch("core.planner.requests.post")
    def test_deadline_after_final_response_marks_partial(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current"}'}}
        with patch("tools.evaluate_interpreter.time.monotonic") as mono:
            call_count = [0]
            def fake_monotonic():
                call_count[0] += 1
                return 902 if call_count[0] > 60 else 0
            mono.side_effect = fake_monotonic
            code = self.run_cli("--mode", "direct", "--max-requests", "60", "--max-seconds", "900")
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "deadline")


class RecheckRegressionTests(unittest.TestCase):
    """Independent recheck repros for B1, B3, B6, B7."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-eval-recheck-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "report.json")
        self.cases_path = os.path.join(os.path.dirname(__file__), "..", "evaluations", "interpreter_cases.json")

    def run_cli(self, *extra_args):
        return evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", self.cases_path,
            *extra_args,
        ])

    @patch("core.planner.requests.post")
    def test_b1_list_with_answer_is_invalid_not_correct(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current","answer":"Forbidden answer"}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        case = next(c for c in report["cases"] if c["case_id"] == "query-en-univ")
        self.assertNotEqual(case["direct"]["verdict"], "correct")
        self.assertEqual(case["direct"]["reason_code"], "invalid_structure")

    @patch("core.planner.requests.post")
    def test_b1_whitespace_title_is_invalid_not_correct(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"create","language":"es","items":[{"title":"   ","area":"university","due_date":"2026-11-25"}]}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        case = next(c for c in report["cases"] if c["case_id"] == "create-es-date")
        self.assertNotEqual(case["direct"]["verdict"], "correct")
        self.assertEqual(case["direct"]["reason_code"], "invalid_fields")

    @patch("core.planner.requests.post")
    def test_b3_report_redacts_title_and_project_values(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"create","language":"es","items":[{"title":"Private Title","area":"personal","project":"SecretProject","due_date":"2026-11-25"}]}'}}
        code = self.run_cli("--mode", "direct", "--max-requests", "60")
        self.assertEqual(code, 0)
        raw = Path(self.output).read_text()
        self.assertNotIn("Private Title", raw)
        self.assertNotIn("SecretProject", raw)
        report = json.loads(raw)
        case = next(c for c in report["cases"] if c["case_id"] == "create-es-date")
        item = case["direct"]["actual"]["items"][0]
        self.assertTrue(item["title_present"])
        self.assertTrue(item["project_present"])
        self.assertNotIn("title", item)
        self.assertNotIn("project", item)

    @patch("core.planner.requests.post")
    def test_b6_budgeted_interpreter_call_checks_before_attempt(self, post):
        import time
        budget = evaluate_interpreter.Budget(1, time.monotonic() + 900)
        interpreter = evaluate_interpreter.BudgetedInterpreter("http://127.0.0.1:11434", "qwen3.5:9b", budget)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": 'not json'}}
        case_direct = {"input": "x", "expected": {"action": "reply", "language": "es", "answer": "ok"}, "case_id": "c1", "category": "reply"}
        case_e2e = {"input": "x", "expected": {"action": "reply", "language": "es", "answer": "ok"}, "case_id": "c1", "category": "reply", "fixtures": []}
        for _ in range(3):
            try:
                evaluate_interpreter.evaluate_direct(case_direct, interpreter)
            except RuntimeError:
                pass
            try:
                evaluate_interpreter.evaluate_end_to_end(case_e2e, interpreter)
            except RuntimeError:
                pass
        self.assertEqual(post.call_count, 1)
        self.assertEqual(budget.requests, 1)

    def _make_large_cases_file(self, path):
        cases = [
            {"case_id": "fast-000", "category": "query", "input": "show my work commitments",
             "expected": {"action": "list", "language": "en", "area": "work", "scope": "current"}},
        ]
        for i in range(1, 32):
            cases.append({
                "case_id": f"nonfast-{i:03d}",
                "category": "query",
                "input": f"nonfast query {i}",
                "expected": {"action": "list", "language": "en", "area": "work", "scope": "current"},
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cases, f)

    @patch("core.planner.requests.post")
    def test_b6_both_mode_obeys_global_request_cap(self, post):
        cases_path = os.path.join(self.temp.name, "cases.json")
        self._make_large_cases_file(cases_path)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en","area":"work","scope":"current"}'}}
        code = evaluate_interpreter.main([
            "--url", "http://127.0.0.1:11434",
            "--model", "qwen3.5:9b",
            "--output", self.output,
            "--cases", cases_path,
            "--mode", "both",
            "--max-requests", "60",
            "--max-seconds", "900",
        ])
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "max_requests")
        self.assertLessEqual(post.call_count, 60)

    def test_b7_deadline_checked_before_second_mode_transition(self):
        from unittest.mock import Mock
        with patch("tools.evaluate_interpreter.time.monotonic") as mono, patch("core.planner.requests.post") as post:
            times = [0]
            def fake_monotonic():
                return times[-1]
            mono.side_effect = fake_monotonic
            starts = []
            def fake_post(*args, **kwargs):
                starts.append(fake_monotonic())
                times[0] = 901
                response = Mock()
                response.status_code = 200
                response.json.return_value = {"message": {"content": '{"action":"list","language":"es","area":"work","scope":"current"}'}}
                return response
            post.side_effect = fake_post
            code = self.run_cli("--mode", "both", "--max-requests", "60", "--max-seconds", "900")
        self.assertNotEqual(code, 0)
        report = json.loads(Path(self.output).read_text())
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "deadline")
        self.assertEqual(starts, [0])
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()

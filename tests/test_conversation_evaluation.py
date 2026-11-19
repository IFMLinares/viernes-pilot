"""Conversation evidence is offline unless live mode is explicitly configured."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from tools import evaluate_conversations as runner


class ConversationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-conversations-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "report.json"

    def run_cli(self, *args):
        return runner.main(["--output", str(self.output), *args])

    def test_synthetic_complete_conversations_expose_known_defects_without_network(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
            code = self.run_cli()
        report = json.loads(self.output.read_text())
        self.assertEqual(code, 1)  # Acceptance defects are NOT a successful model evaluation.
        self.assertTrue(report["completed"])
        self.assertTrue(report["baseline_matches"])
        self.assertFalse(report["acceptance_passed"])
        self.assertEqual(report["evidence"], "deterministic")
        self.assertEqual(report["http_attempts"], 0)
        self.assertEqual(report["simulated_attempts"], 9)
        self.assertEqual(len(report["cases"]), 6)
        self.assertEqual(sum(len(case["turns"]) for case in report["cases"]), 16)
        self.assertEqual({issue for case in report["cases"] for issue in case["issues"]}, {3, 4, 5, 6})
        self.assertTrue(all(len(case["turns"]) >= 2 for case in report["cases"]))
        self.assertTrue(any(turn["observation"]["rows_count"] for case in report["cases"] for turn in case["turns"]))
        self.assertTrue(any(turn["observation"]["tools"] for case in report["cases"] for turn in case["turns"]))

    def test_observation_failure_is_not_hidden_by_a_known_issue(self):
        cases = copy.deepcopy(runner.load_cases(runner.CORPUS))
        cases[0]["turns"][0]["expect"]["rows_count"] = 42
        with patch.object(runner, "load_cases", return_value=cases):
            self.assertEqual(self.run_cli(), 1)
        report = json.loads(self.output.read_text())
        self.assertFalse(report["baseline_matches"])
        self.assertFalse(report["completed"])
        self.assertEqual(report["stopped_reason"], "baseline_mismatch")

    def test_live_refuses_missing_or_invalid_budget_before_any_send(self):
        for args in [[], ["--max-requests", "0"], ["--max-seconds", "nan"]]:
            with self.subTest(args=args), patch("requests.post") as sender:
                self.assertEqual(self.run_cli("--mode", "live", *args), 2)
                sender.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_mocked_live_failure_stops_first_and_retains_partial_report(self):
        # Tests the live execution path, not live-model evidence.
        with patch("requests.post", side_effect=requests.ConnectionError()) as sender:
            code = self.run_cli("--mode", "live", "--url", "http://127.0.0.1:11434",
                                "--model", "synthetic", "--max-requests", "3",
                                "--max-seconds", "5", "--request-timeout", "1")
        report = json.loads(self.output.read_text())
        self.assertEqual(code, 1)
        self.assertFalse(report["completed"])
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(report["http_attempts"], 1)
        self.assertTrue(report["stopped_reason"])

    def test_replay_requires_recorded_provenance_and_never_falls_back_to_network(self):
        replay = Path(self.temp.name) / "replay.json"
        replay.write_text(json.dumps({"provenance": {"source": "synthetic"}}))
        with patch("requests.post") as sender:
            self.assertEqual(self.run_cli("--mode", "replay", "--replay", str(replay)), 2)
            sender.assert_not_called()

    def test_recorded_replay_consumes_exact_wire_sequences(self):
        cases = runner.load_cases(runner.CORPUS)
        recording = {"provenance": {"source": "recorded-synthetic", "model": "test-only", "digest": "test-only"}, "cases": {}}
        for case in cases:
            recording["cases"][case["case_id"]] = [
                [{"status_code": 200, "body": {"message": {"content": json.dumps(action)}}}
                 for action in turn.get("responses", [])] for turn in case["turns"]]
        replay = Path(self.temp.name) / "replay.json"
        replay.write_text(json.dumps(recording))
        with patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.run_cli("--mode", "replay", "--replay", str(replay)), 1)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["evidence"], "replay")
        self.assertTrue(report["baseline_matches"])
        self.assertEqual(report["http_attempts"], 0)

    def test_report_contains_no_raw_conversation_or_model_payload(self):
        self.run_cli()
        raw = self.output.read_text()
        for forbidden in ["instrumentacion", "(online)", "\"content\"", "\"source\"", "/tmp/"]:
            self.assertNotIn(forbidden, raw)

    def test_budget_exhaustion_reports_the_attempt_that_stopped_the_conversation(self):
        self.assertEqual(self.run_cli("--max-requests", "1"), 1)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["stopped_reason"], "max_requests")
        self.assertFalse(report["completed"])
        self.assertEqual(report["simulated_attempts"], 1)
        self.assertEqual(len(report["cases"][0]["turns"]), 1)

    def test_empty_conversation_and_overwriting_input_are_rejected(self):
        cases = [{"case_id": "empty", "issues": [6], "turns": []}]
        with patch.object(runner, "load_cases", return_value=cases):
            self.assertEqual(self.run_cli(), 2)
        self.assertEqual(runner.main(["--output", str(runner.CORPUS)]), 2)
        self.assertFalse(self.output.exists())

    def test_deterministic_report_is_reproducible(self):
        self.run_cli()
        first = self.output.read_text()
        self.run_cli()
        self.assertEqual(self.output.read_text(), first)

"""Offline transport-boundary accounting; no Ollama service is contacted."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import requests

from tools.evaluation_http import Budget, BudgetExceeded
from tools.evaluate_interpreter import BudgetedInterpreter, evaluate_direct


class HTTPAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-http-")
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / "attempts.sqlite3"

    def budget(self, maximum=3, seconds=60, **kwargs):
        budget = Budget(maximum, time.monotonic() + seconds, ledger=self.ledger, **kwargs)
        self.addCleanup(budget.close)
        return budget

    def test_failed_attempt_is_committed_before_send_and_reopen(self):
        budget = self.budget(maximum=2)

        def send(*args, **kwargs):
            with closing(sqlite3.connect(self.ledger)) as connection:
                self.assertEqual(connection.execute("SELECT attempts FROM budget").fetchone()[0], 1)
            raise requests.ConnectionError("not stored in ledger")

        with budget.transport(send), self.assertRaises(requests.ConnectionError):
            requests.post("http://127.0.0.1:11434/api/chat")
        budget.close()
        reopened = self.budget(maximum=2)
        self.assertEqual(reopened.requests, 1)
        sender = Mock()
        with reopened.transport(sender):
            requests.post("http://127.0.0.1:11434/api/chat")
            with self.assertRaises(BudgetExceeded):
                requests.post("http://127.0.0.1:11434/api/chat")
        self.assertEqual(sender.call_count, 1)
        self.assertNotIn(b"not stored in ledger", self.ledger.read_bytes())

    def test_continuation_counts_two_attempts_in_legacy_result(self):
        budget = self.budget()
        interpreter = BudgetedInterpreter("http://127.0.0.1:11434", "synthetic", budget)
        responses = [
            {"action": "tool", "language": "es", "intent": "create", "draft": {"title": "Informe"},
             "tool": {"name": "resolve_date", "arguments": {"references": [{"kind": "relative_days", "days": 3}]}}},
            {"action": "create", "language": "es", "intent": "create",
             "items": [{"title": "Informe", "area": "university", "due_date": "2026-11-26"}]},
        ]
        sender = Mock(return_value=Mock(status_code=200))
        sender.return_value.json.side_effect = [{"message": {"content": json.dumps(item)}} for item in responses]
        with patch("core.planner.requests.post", sender):
            result = evaluate_direct({"input": "Informe universidad dentro de tres días", "expected": responses[-1]}, interpreter)
        self.assertEqual(sender.call_count, 2)
        self.assertEqual(budget.requests, 2)
        self.assertEqual(result["requests"], 2)

    def test_cap_rejects_continuation_without_sending_it(self):
        budget = self.budget(maximum=1)
        tool = {"action": "tool", "language": "es", "intent": "reply",
                "tool": {"name": "resolve_date", "arguments": {"references": [{"kind": "relative_days", "days": 0}]}}}
        sender = Mock(return_value=Mock(status_code=200))
        sender.return_value.json.return_value = {"message": {"content": json.dumps(tool)}}
        with patch("core.planner.requests.post", sender), self.assertRaises(BudgetExceeded):
            BudgetedInterpreter("http://127.0.0.1:11434", "synthetic", budget).call("fecha", [])
        self.assertEqual(sender.call_count, 1)

    def test_deadline_and_timeout_are_checked_for_each_send(self):
        budget = self.budget(request_timeout=0.5)
        sender = Mock()
        with budget.transport(sender):
            requests.post("http://127.0.0.1:11434/api/chat", timeout=(3, 90))
            budget.deadline = time.monotonic() - 1
            with self.assertRaisesRegex(BudgetExceeded, "deadline"):
                requests.post("http://127.0.0.1:11434/api/chat")
        self.assertLessEqual(sum(sender.call_args.kwargs["timeout"]), 0.5)
        self.assertEqual(sender.call_count, 1)

    def test_hard_timeout_stops_a_stalled_sender(self):
        budget = self.budget(request_timeout=0.03)
        with budget.transport(lambda *a, **k: time.sleep(1)), self.assertRaisesRegex(BudgetExceeded, "request_timeout"):
            requests.post("http://127.0.0.1:11434/api/chat")
        self.assertEqual(budget.requests, 1)

    def test_reopen_cannot_extend_deadline_or_change_budget_binding(self):
        budget = self.budget(seconds=0.05, binding="model-a")
        budget.close()
        with self.assertRaises(ValueError):
            self.budget(binding="model-b")
        reopened = self.budget(binding="model-a")
        self.assertLess(reopened.remaining_seconds(), 0.1)

    def test_invalid_limits_never_send(self):
        for maximum, timeout in [(-1, 1), (1, 0), (1, float("nan"))]:
            with self.subTest(maximum=maximum, timeout=timeout), self.assertRaises(ValueError):
                Budget(maximum, time.monotonic() + 1, request_timeout=timeout)

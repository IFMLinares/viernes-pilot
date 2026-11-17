"""Offline re-score and safe parser diagnostics tests.

These tests require no network, no real inference, and no private environment.
Scratch outputs live in temp directories outside the workspace.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.commitments import CommitmentStore
from core.diagnostics import ALLOWED_KEYS, Diagnostics, _safe_completion_reason, _safe_type_name, parse_metadata
from core.planner import Planner, ollama_interpreter
from tools import evaluate_interpreter, rescore_interpreter

_MISSING = object()

class SemanticDefaultNormalizationTests(unittest.TestCase):
    """S8: omitted list scope means current; explicit invalid/null/wrong filters stay rejected."""

    def test_omitted_list_scope_normalizes_to_current_and_matches_explicit_current(self):
        actual = {"action": "list", "language": "en", "area": "university"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        evaluate_interpreter.validate_action_contract(actual)
        self.assertTrue(evaluate_interpreter.actions_equal(actual, expected))

    def test_omitted_scope_both_ways_is_equivalent(self):
        a = {"action": "list", "language": "es", "area": "work"}
        b = {"action": "list", "language": "es", "area": "work", "scope": "current"}
        self.assertTrue(evaluate_interpreter.actions_equal(a, b))
        self.assertTrue(evaluate_interpreter.actions_equal(b, a))

    def test_explicit_none_scope_is_not_normalized(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": None}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract(actual)
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_invalid_scope_is_not_normalized(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": "invalid"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract(actual)
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_wrong_area_is_not_forgiven(self):
        actual = {"action": "list", "language": "en", "area": "work", "scope": "current"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "current"}
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_explicit_wrong_dates_are_not_forgiven(self):
        actual = {"action": "list", "language": "en", "area": "university", "scope": "range",
                  "start_date": "2026-11-01", "end_date": "2026-11-15"}
        expected = {"action": "list", "language": "en", "area": "university", "scope": "range",
                    "start_date": "2026-11-01", "end_date": "2026-11-30"}
        self.assertFalse(evaluate_interpreter.actions_equal(actual, expected))

    def test_non_list_actions_ignore_scope_default(self):
        actual = {"action": "create", "language": "es", "items": [{"title": "X", "area": "university"}]}
        expected = {"action": "create", "language": "es", "items": [{"title": "Y", "area": "university"}]}
        self.assertTrue(evaluate_interpreter.actions_equal(actual, expected))

    def test_validate_action_contract_still_requires_language(self):
        with self.assertRaises(ValueError):
            evaluate_interpreter.validate_action_contract({"action": "list", "area": "university"})


class RescoreCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-rescore-tests-")
        self.addCleanup(self.temp.cleanup)
        self.output = os.path.join(self.temp.name, "rescored.json")
        self.input_path = os.path.join(self.temp.name, "input.json")

    def write_input(self, report):
        with open(self.input_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def run_cli(self, *extra_args):
        return rescore_interpreter.main([
            "--input", self.input_path,
            "--output", self.output,
            *extra_args,
        ])

    def base_report(self):
        return {
            "reference_date": "2026-11-23",
            "url": "http://127.0.0.1:11434",
            "model": "qwen3.5:9b",
            "mode": "both",
            "max_requests": 60,
            "max_seconds": 900,
            "completed": False,
            "stopped_reason": "timeout",
            "summary": {"direct": {"evaluated": 1, "correct": 0, "incorrect": 1, "errors": 0,
                                   "accuracy": 0.0, "total_ms": 100, "avg_ms": 100.0, "routes": {"interpreter": 1}},
                        "end_to_end": {"evaluated": 1, "correct": 0, "incorrect": 1, "errors": 0,
                                       "accuracy": 0.0, "total_ms": 50, "avg_ms": 50.0, "routes": {"interpreter": 1}}},
            "cases": [
                {
                    "case_id": "query-en-univ",
                    "category": "query",
                    "direct": {
                        "expected": {"action": "list", "language": "en", "area": "university", "scope": "current"},
                        "actual": {"action": "list", "language": "en", "area": "university"},
                        "route": "interpreter",
                        "verdict": "incorrect",
                        "reason_code": None,
                        "requests": 1,
                        "elapsed_ms": 100,
                    },
                    "end_to_end": {
                        "expected": {"action": "list", "language": "en", "area": "university", "scope": "current"},
                        "actual": {"action": "list", "language": "en", "area": "university"},
                        "route": "interpreter",
                        "verdict": "incorrect",
                        "reason_code": None,
                        "requests": 1,
                        "elapsed_ms": 50,
                    },
                }
            ],
        }

    def test_help_lists_exact_flags(self):
        with patch("sys.stdout", new=io.StringIO()) as stdout, self.assertRaises(SystemExit) as result:
            rescore_interpreter.parse_args(["--help"])
        self.assertEqual(result.exception.code, 0)
        text = stdout.getvalue()
        self.assertIn("--input", text)
        self.assertIn("--output", text)

    def test_refuses_same_resolved_input_and_output(self):
        self.write_input(self.base_report())
        code = rescore_interpreter.main(["--input", self.input_path, "--output", self.input_path])
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.output))

    def test_refuses_symlink_alias(self):
        self.write_input(self.base_report())
        symlink = os.path.join(self.temp.name, "link.json")
        os.symlink(self.input_path, symlink)
        code = rescore_interpreter.main(["--input", self.input_path, "--output", symlink])
        self.assertEqual(code, 2)

    def test_refuses_overwriting_existing_output(self):
        self.write_input(self.base_report())
        Path(self.output).write_text("existing", encoding="utf-8")
        code = self.run_cli()
        self.assertEqual(code, 2)
        self.assertEqual(Path(self.output).read_text(encoding="utf-8"), "existing")

    def test_preserves_original_bytes_and_hash(self):
        report = self.base_report()
        self.write_input(report)
        original_bytes = Path(self.input_path).read_bytes()
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        code = self.run_cli()
        self.assertEqual(code, 0)
        after_bytes = Path(self.input_path).read_bytes()
        self.assertEqual(after_bytes, original_bytes)
        self.assertEqual(hashlib.sha256(after_bytes).hexdigest(), original_hash)

    def test_corrects_omitted_scope_to_current(self):
        self.write_input(self.base_report())
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        direct = derived["case_results"][0]["direct"]
        self.assertEqual(direct["original_verdict"], "incorrect")
        self.assertEqual(direct["verdict"], "correct")
        self.assertEqual(direct["rescore_status"], "corrected")
        self.assertEqual(direct["normalized_defaults"], {"scope": "current"})

    def test_updates_summary_without_changing_errors_or_coverage(self):
        self.write_input(self.base_report())
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        for mode in ("direct", "end_to_end"):
            s = derived["summary"][mode]
            self.assertEqual(s["evaluated"], 1)
            self.assertEqual(s["correct"], 1)
            self.assertEqual(s["incorrect"], 0)
            self.assertEqual(s["errors"], 0)
            self.assertEqual(s["total_ms"], 100 if mode == "direct" else 50)
            self.assertEqual(s["requests"], 1)

    def test_preserves_completed_stopped_reason_and_metadata(self):
        self.write_input(self.base_report())
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        self.assertEqual(derived["completed"], False)
        self.assertEqual(derived["stopped_reason"], "timeout")
        self.assertEqual(derived["max_requests"], 60)
        self.assertEqual(derived["max_seconds"], 900)
        self.assertEqual(derived["mode"], "both")

    def test_rejects_explicit_none_scope(self):
        report = self.base_report()
        report["cases"][0]["direct"]["actual"]["scope"] = None
        report["cases"][0]["end_to_end"]["actual"]["scope"] = None
        self._assert_rejected(report)

    def test_rejects_explicit_invalid_scope(self):
        report = self.base_report()
        report["cases"][0]["direct"]["actual"]["scope"] = "invalid"
        report["cases"][0]["end_to_end"]["actual"]["scope"] = "invalid"
        self._assert_rejected(report)

    def test_leaves_error_verdicts_untouched(self):
        report = self.base_report()
        report["cases"][0]["direct"]["verdict"] = "error"
        report["cases"][0]["direct"]["reason_code"] = "invalid_json"
        report["cases"][0]["direct"]["actual"] = None
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        direct = derived["case_results"][0]["direct"]
        self.assertEqual(direct["verdict"], "error")
        self.assertEqual(direct["original_verdict"], "error")
        self.assertEqual(direct["rescore_status"], "preserved")
        self.assertEqual(direct["reason_code"], "invalid_json")

    def test_leaves_correct_verdicts_unchanged(self):
        report = self.base_report()
        report["cases"][0]["direct"]["verdict"] = "correct"
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        direct = derived["case_results"][0]["direct"]
        self.assertEqual(direct["verdict"], "correct")
        self.assertEqual(direct["original_verdict"], "correct")
        self.assertEqual(direct["rescore_status"], "preserved")

    def test_redacted_create_is_not_rescorable(self):
        report = self.base_report()
        report["cases"][0]["direct"]["expected"] = {"action": "create", "language": "es", "items": [{"area": "university", "due_date": "2026-11-25"}]}
        report["cases"][0]["direct"]["actual"] = {"action": "create", "language": "es", "items": [{"title_present": True, "title_length": 10, "area": "university", "due_date": "2026-11-25", "project_present": False}]}
        report["cases"][0]["direct"]["verdict"] = "incorrect"
        report["cases"][0]["end_to_end"] = None
        del report["summary"]["end_to_end"]
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        direct = derived["case_results"][0]["direct"]
        self.assertEqual(direct["verdict"], "incorrect")
        self.assertEqual(direct["rescore_status"], "not_rescorable")
        self.assertNotIn("end_to_end", derived["case_results"][0])

    def test_redacted_reply_is_not_rescorable(self):
        report = self.base_report()
        report["cases"][0]["direct"]["expected"] = {"action": "reply", "language": "es"}
        report["cases"][0]["direct"]["actual"] = {"action": "reply", "language": "es", "answer_present": True, "answer_length": 50}
        report["cases"][0]["direct"]["verdict"] = "incorrect"
        report["cases"][0]["end_to_end"] = None
        del report["summary"]["end_to_end"]
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        direct = derived["case_results"][0]["direct"]
        self.assertEqual(direct["verdict"], "incorrect")
        self.assertEqual(direct["rescore_status"], "not_rescorable")

    def test_rejects_unsafe_input_with_raw_prompt(self):
        report = self.base_report()
        report["prompt"] = "secret system prompt"
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.output))

    def test_rejects_unsafe_input_with_raw_answer(self):
        report = self.base_report()
        report["cases"][0]["direct"]["actual"]["answer"] = "secret answer"
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 2)

    def test_rejects_unsafe_input_with_raw_title(self):
        report = self.base_report()
        report["cases"][0]["direct"]["actual"]["title"] = "secret title"
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 2)

    def test_source_sha256_and_basename_recorded(self):
        self.write_input(self.base_report())
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        self.assertEqual(derived["source_report"], "input.json")
        self.assertEqual(derived["source_sha256"], hashlib.sha256(Path(self.input_path).read_bytes()).hexdigest())
        self.assertEqual(derived["scoring_rule"], "semantic-defaults")
        self.assertEqual(derived["scoring_rule_version"], "1")

    def test_exit_zero_means_rescore_completed_not_measurement(self):
        self.write_input(self.base_report())
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        self.assertEqual(derived["completed"], False)
        self.assertIn("original measurement may still be partial", derived["note"].lower())

    # S8-B1 durable regressions: strict typed/source eligibility and privacy.

    def _minimal_list_result(self, actual=_MISSING, expected=None, verdict="incorrect",
                             route="interpreter", requests=1, elapsed_ms=2, reason_code=None):
        return {
            "expected": expected or {"action": "list", "language": "en", "scope": "current"},
            "actual": {"action": "list", "language": "en"} if actual is _MISSING else actual,
            "route": route,
            "verdict": verdict,
            "reason_code": reason_code,
            "requests": requests,
            "elapsed_ms": elapsed_ms,
        }

    def _minimal_report(self, result=None):
        return {
            "reference_date": "2026-11-23",
            "url": "http://127.0.0.1:11434",
            "model": "qwen3.5:9b",
            "mode": "both",
            "max_requests": 60,
            "max_seconds": 900,
            "completed": False,
            "stopped_reason": "timeout",
            "summary": {"direct": {"evaluated": 1, "correct": 0, "incorrect": 1, "errors": 0,
                                   "accuracy": 0.0, "total_ms": 2, "avg_ms": 2.0,
                                   "routes": {"interpreter": 1}}},
            "cases": [{"case_id": "c1", "category": "query", "direct": result or self._minimal_list_result()}],
        }

    def _assert_rejected(self, report):
        self.write_input(report)
        code = self.run_cli()
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.output))
        original = Path(self.input_path).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         hashlib.sha256(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")).hexdigest())

    def test_b1_rejects_missing_language_in_actual(self):
        result = self._minimal_list_result()
        del result["actual"]["language"]
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_missing_language_in_expected(self):
        result = self._minimal_list_result()
        del result["expected"]["language"]
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_matching_invalid_area(self):
        result = self._minimal_list_result(
            actual={"action": "list", "language": "en", "area": "invalid"},
            expected={"action": "list", "language": "en", "area": "invalid", "scope": "current"},
        )
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_matching_invalid_start_date(self):
        result = self._minimal_list_result(
            actual={"action": "list", "language": "en", "scope": "range", "start_date": "not-a-date"},
            expected={"action": "list", "language": "en", "scope": "range",
                      "start_date": "not-a-date", "end_date": "2026-11-30"},
        )
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_invalid_verdict(self):
        result = self._minimal_list_result(verdict="banana")
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_missing_elapsed_ms(self):
        result = self._minimal_list_result()
        del result["elapsed_ms"]
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_string_elapsed_ms(self):
        result = self._minimal_list_result(elapsed_ms="fast")
        self._assert_rejected(self._minimal_report(result))

    def test_b1_rejects_string_completed(self):
        report = self._minimal_report()
        report["completed"] = "false"
        self._assert_rejected(report)

    def test_b1_rejects_unexpected_nested_body(self):
        result = self._minimal_list_result()
        result["actual"]["body"] = "PRIVATE_HTTP_BODY"
        self._assert_rejected(self._minimal_report(result))

    def test_b1_preserves_error_record_with_none_actual(self):
        result = self._minimal_list_result(verdict="error", reason_code="invalid_json", actual=None)
        self.write_input(self._minimal_report(result))
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        self.assertIsNone(derived["case_results"][0]["direct"]["actual"])

    def test_b1_preserves_redacted_create_metadata(self):
        result = self._minimal_list_result(
            actual={"action": "create", "language": "es",
                    "items": [{"title_present": True, "title_length": 10, "area": "university",
                               "project_present": False}]},
            expected={"action": "create", "language": "es", "items": [{"area": "university"}]},
        )
        result["verdict"] = "incorrect"
        self.write_input(self._minimal_report(result))
        code = self.run_cli()
        self.assertEqual(code, 0)
        derived = json.loads(Path(self.output).read_text(encoding="utf-8"))
        self.assertEqual(derived["case_results"][0]["direct"]["rescore_status"], "not_rescorable")


class ParseMetadataSanitizationTests(unittest.TestCase):
    def test_safe_type_name_allows_primitive_names(self):
        self.assertEqual(_safe_type_name("text"), "str")
        self.assertEqual(_safe_type_name(None), "NoneType")
        self.assertEqual(_safe_type_name(123), "int")
        self.assertEqual(_safe_type_name({}), "dict")

    def test_safe_completion_reason_whitelists_known_values(self):
        for value in ("stop", "length"):
            self.assertEqual(_safe_completion_reason(value), value)

    def test_safe_completion_reason_maps_unknown_to_other(self):
        self.assertEqual(_safe_completion_reason("weird_reason"), "other")

    def test_safe_completion_reason_rejects_non_strings(self):
        self.assertIsNone(_safe_completion_reason(123))

    def test_parse_metadata_captures_content_stage(self):
        response = {"message": {"content": '{"action":"list"}'}}
        meta = parse_metadata(response)
        self.assertEqual(meta["parse_stage"], "content")
        self.assertTrue(meta["content_exists"])
        self.assertEqual(meta["content_type"], "str")
        self.assertEqual(meta["content_length"], len('{"action":"list"}'))
        self.assertFalse(meta["content_empty"])

    def test_parse_metadata_captures_envelope_stage_for_done_reason(self):
        response = {"message": {"content": '{"action":"list"}'}, "done": True, "done_reason": "stop"}
        meta = parse_metadata(response)
        self.assertEqual(meta["parse_stage"], "envelope")
        self.assertEqual(meta["completion_reason"], "stop")

    def test_parse_metadata_handles_missing_content(self):
        response = {"message": {}}
        meta = parse_metadata(response)
        self.assertFalse(meta["content_exists"])
        self.assertEqual(meta["content_type"], "NoneType")
        self.assertTrue(meta["content_empty"])

    def test_parse_metadata_handles_nonstring_content(self):
        response = {"message": {"content": 123}}
        meta = parse_metadata(response)
        self.assertTrue(meta["content_exists"])
        self.assertEqual(meta["content_type"], "int")
        self.assertNotIn("content_length", meta)
        self.assertTrue(meta["content_empty"])

    def test_parse_metadata_handles_json_error_position(self):
        response = {"message": {"content": "not json"}}
        try:
            json.loads(response["message"]["content"])
        except json.JSONDecodeError as exc:
            meta = parse_metadata(response, exc=exc)
        self.assertEqual(meta["json_error_line"], 1)
        self.assertEqual(meta["json_error_column"], 1)
        self.assertEqual(meta["json_error_position"], 0)
        self.assertEqual(meta["parse_stage"], "content")

    def test_parse_metadata_omits_raw_strings_and_bodies(self):
        response = {"message": {"content": '{"action":"list"}', "raw": "secret"}}
        meta = parse_metadata(response)
        for key in ("content", "raw", "prompt", "answer"):
            self.assertNotIn(key, meta)


class InterpreterParseDiagnosticsTests(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_diagnostics_off_emits_no_parse_event(self, post):
        stderr = io.StringIO()
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        interpreter("test", [])
        self.assertEqual(stderr.getvalue().strip(), "")

    @patch("core.planner.requests.post")
    def test_diagnostics_on_emits_content_stage_metadata(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        stderr.seek(0)
        events = [json.loads(line) for line in stderr if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertEqual(len(parse_events), 1)
        event = parse_events[0]
        self.assertEqual(event["parse_stage"], "content")
        self.assertTrue(event["content_exists"])
        self.assertEqual(event["content_type"], "str")
        self.assertGreater(event["content_length"], 0)
        self.assertFalse(event["content_empty"])

    @patch("core.planner.requests.post")
    def test_diagnostics_on_emits_envelope_metadata_for_done_reason(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en"}'},
                                                "done": True, "done_reason": "stop"}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        event = [e for e in events if e.get("parse_stage") == "envelope"][0]
        self.assertEqual(event["completion_reason"], "stop")

    @patch("core.planner.requests.post")
    def test_diagnostics_on_preserves_json_error_type(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": "not json"}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        with self.assertRaises(json.JSONDecodeError):
            interpreter("test", [])
        events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertEqual(len(parse_events), 1)
        event = parse_events[0]
        self.assertEqual(event["parse_stage"], "content")
        self.assertIn("json_error_line", event)
        self.assertIn("json_error_column", event)

    @patch("core.planner.requests.post")
    def test_diagnostics_never_leaks_raw_content_or_prompts(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"synthetic-secret"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        interpreter("test", [])
        raw = stderr.getvalue()
        self.assertNotIn("synthetic-secret", raw)
        self.assertNotIn("prompt", raw)

    @patch("core.planner.requests.post")
    def test_nonstring_content_preserves_typeerror_with_safe_metadata(self, post):
        cases = [None, {}, [], 42, True]
        for content in cases:
            with self.subTest(content=content):
                stderr = io.StringIO()
                diag = Diagnostics(output=stderr)
                post.return_value.status_code = 200
                post.return_value.json.return_value = {"message": {"content": content},
                                                        "done": True, "done_reason": "stop"}
                interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
                with self.assertRaises(TypeError):
                    interpreter("test", [])
                try:
                    interpreter("test", [])
                except TypeError as exc:
                    meta = getattr(exc, "_parse_metadata", {})
                self.assertEqual(meta.get("parse_stage"), "content")
                self.assertTrue(meta.get("content_exists"))
                self.assertEqual(meta.get("content_type"), type(content).__name__)
                events = [json.loads(line) for line in stderr.getvalue().splitlines() if line.strip()]
                parse_events = [e for e in events if e.get("parse_stage")]
                self.assertGreaterEqual(len(parse_events), 1)
                event = parse_events[0]
                self.assertEqual(event["content_type"], type(content).__name__)
                self.assertTrue(event["content_exists"])
                raw = stderr.getvalue()
                if content is not None and not isinstance(content, bool):
                    self.assertNotIn(str(content), raw)
                # The event must never carry the raw value under a content/value key.
                for event in parse_events:
                    self.assertNotIn("content", event)
                    self.assertNotIn("value", event)

    @patch("core.planner.requests.post")
    def test_missing_message_content_preserves_typed_error_with_metadata(self, post):
        stderr = io.StringIO()
        diag = Diagnostics(output=stderr)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=diag)
        with self.assertRaises((KeyError, TypeError)):
            interpreter("test", [])
        try:
            interpreter("test", [])
        except (KeyError, TypeError) as exc:
            meta = getattr(exc, "_parse_metadata", {})
        self.assertEqual(meta.get("parse_stage"), "content")
        self.assertFalse(meta.get("content_exists"))
        self.assertEqual(meta.get("content_type"), "NoneType")


class PlannerParseDiagnosticsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="viernes-parse-diag-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)
        self.output = io.StringIO()
        self.diag = Diagnostics(output=self.output)

    def events(self):
        self.output.seek(0)
        return [json.loads(line) for line in self.output if line.strip()]

    @patch("core.planner.requests.post")
    def test_planner_error_event_includes_safe_parse_metadata(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": "not json"}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", diagnostics=self.diag)
        planner = Planner(self.store, interpreter, diagnostics=self.diag)
        with self.assertRaises(json.JSONDecodeError):
            planner.respond("What do I have?")
        error_event = [e for e in self.events() if e.get("outcome") == "error" and e.get("route") == "interpreter"][0]
        self.assertIn("json_error_line", error_event)
        self.assertIn("parse_stage", error_event)
        self.assertNotIn("synthetic", error_event)

    @patch("core.planner.requests.post")
    def test_planner_normal_ui_unchanged_with_diagnostics_off(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list","language":"en","area":"university"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        planner = Planner(self.store, interpreter)
        response = planner.respond("Show my university commitments")
        self.assertIn("University", response)

    @patch("core.planner.requests.post")
    def test_planner_injects_diagnostics_into_interpreter_at_runtime(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"A derivative is change."}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")  # no diagnostics
        planner = Planner(self.store, interpreter, diagnostics=self.diag)
        planner.respond("What is a derivative?")
        events = [json.loads(line) for line in self.output.getvalue().splitlines() if line.strip()]
        parse_events = [e for e in events if e.get("parse_stage")]
        self.assertGreaterEqual(len(parse_events), 1)
        self.assertEqual(parse_events[0]["parse_stage"], "content")

    @patch("core.planner.requests.post")
    def test_planner_diagnostics_ownership_isolated_for_shared_interpreter(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"reply","language":"en","answer":"ok"}'}}
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b")
        sink_a = io.StringIO()
        sink_b = io.StringIO()
        sink_c = io.StringIO()
        diag_a = Diagnostics(output=sink_a)
        diag_b = Diagnostics(output=sink_b)
        diag_c = Diagnostics(output=sink_c)
        planner_a = Planner(self.store, interpreter, diagnostics=diag_a)
        planner_b = Planner(self.store, interpreter)  # diagnostics off
        planner_c = Planner(self.store, interpreter, diagnostics=diag_c)
        # Disabled B must not emit into A's sink.
        planner_b.respond("What is X?")
        self.assertEqual(sink_a.getvalue(), "")
        self.assertEqual(sink_c.getvalue(), "")
        # Enabled C must emit only into C's sink.
        planner_c.respond("What is Y?")
        self.assertEqual(sink_a.getvalue(), "")
        self.assertIn("content_exists", sink_c.getvalue())
        # A after C must still emit into A's sink only.
        sink_c.truncate(0)
        sink_c.seek(0)
        planner_a.respond("What is Z?")
        self.assertIn("content_exists", sink_a.getvalue())
        self.assertEqual(sink_c.getvalue(), "")


class PayloadStabilityTests(unittest.TestCase):
    @patch("core.planner.requests.post")
    def test_request_payload_unchanged_after_edits(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": '{"action":"list"}'}}
        fixed = date(2026, 11, 23)
        interpreter = ollama_interpreter("http://127.0.0.1:11434", "qwen3.5:9b", today=fixed)
        interpreter("Show my university commitments", [])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["options"], {"temperature": 0, "num_ctx": 4096})
        self.assertIn("format", payload)
        self.assertEqual(post.call_args.kwargs["timeout"], (3, 90))
        self.assertEqual(post.call_args.kwargs["allow_redirects"], False)
        self.assertEqual(post.call_args.kwargs["proxies"], {"http": "", "https": ""})
        prompt = payload["messages"][0]["content"]
        self.assertIn("2026-11-23", prompt)
        self.assertIn("Default scope=current", prompt)


class OfflineCompletionRegressions(unittest.TestCase):
    def source(self):
        report = RescoreCLITests.base_report(self)
        report["mode"] = "direct"
        report["summary"].pop("end_to_end")
        report["cases"][0].pop("end_to_end")
        return report

    def test_nested_presence_metadata_is_rejected(self):
        for field in ("title_present", "project_present", "title_length"):
            with self.subTest(field=field):
                report = self.source()
                result = report["cases"][0]["direct"]
                result["expected"] = {"action": "create", "language": "en", "items": [{"area": "work"}]}
                result["actual"] = {"action": "create", "language": "en", "items": [
                    {"area": "work", field: {"body": "PRIVATE_HTTP_BODY"}}]}
                with self.assertRaises(ValueError):
                    rescore_interpreter.rescore(json.dumps(report).encode())

    def test_invalid_query_boundaries_and_negative_counts_are_rejected(self):
        variants = [
            {"scope": "range", "start_date": None, "end_date": None},
            {"scope": "range", "start_date": "2026-11-30", "end_date": "2026-11-01"},
            {"scope": "current", "start_date": "2026-11-01"},
        ]
        for fields in variants:
            with self.subTest(fields=fields):
                report = self.source()
                for key in ("actual", "expected"):
                    report["cases"][0]["direct"][key].update(fields)
                with self.assertRaises(ValueError):
                    rescore_interpreter.rescore(json.dumps(report).encode())
        for field, value in (("requests", -1), ("elapsed_ms", -1), ("route", "unknown"), ("verdict", [])):
            with self.subTest(field=field):
                report = self.source()
                report["cases"][0]["direct"][field] = value
                with self.assertRaises(ValueError):
                    rescore_interpreter.rescore(json.dumps(report).encode())

    def test_omitted_scope_is_valid_after_source_validation(self):
        derived = rescore_interpreter.rescore(json.dumps(self.source()).encode())
        self.assertEqual(derived["case_results"][0]["direct"]["verdict"], "correct")

    @patch("core.planner.requests.post")
    def test_disabled_planner_does_not_inherit_factory_sink(self, post):
        sink = io.StringIO()
        interpret = ollama_interpreter("http://localhost:11434", "synthetic", diagnostics=Diagnostics(sink))
        store = CommitmentStore(":memory:")
        self.addCleanup(store.close)
        planner = Planner(store, interpret)
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"message": {"content": json.dumps(
            {"action": "reply", "language": "en", "answer": "Synthetic explanation"})}}
        planner.respond("Explain derivatives")
        self.assertEqual(sink.getvalue(), "")
        interpret("Explain derivatives", [])
        self.assertIn("content_exists", sink.getvalue())


if __name__ == "__main__":
    unittest.main()

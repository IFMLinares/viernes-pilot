"""Reproducible host baseline; synthetic transport is the safe default."""
import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import time

import requests

from core.planner import Planner, ollama_interpreter
from core.planner_tools import default_registry
from core.ollama_runtime import local_url
from core.commitments import CommitmentStore
from tools.evaluation_http import Budget, BudgetExceeded
from tools.evaluate_interpreter import REFERENCE_DATE, load_cases, setup_fixtures, write_report

CORPUS = Path(__file__).resolve().parents[1] / "evaluations/conversation_cases.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checks(expected, actual):
    result = {}
    for key, value in expected.items():
        if key in ("response_contains", "source_contains"):
            result[key] = value in actual[key.split("_")[0]]
            continue
        found = actual
        for part in key.split("."):
            try:
                found = found[int(part)] if isinstance(found, list) else found[part]
            except (KeyError, IndexError, TypeError, ValueError):
                found = object()
                break
        result[key] = found == value
    return result


class WireResponse:
    def __init__(self, entry):
        self.status_code = entry.get("status_code", 200)
        self.body = entry.get("body", {"message": {"content": json.dumps(entry)}})

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError()


def run_case(case, budget, mode, recording=None):
    results = []
    with tempfile.TemporaryDirectory(prefix="viernes-conversation-") as temporary:
        with closing(CommitmentStore(Path(temporary) / "synthetic.sqlite3")) as store:
            setup_fixtures(store, case)
            registry, tools = default_registry(), []
            execute = registry.execute

            def observe(name, arguments, instant):
                tools.append(name if name == "resolve_date" else "unknown")
                return execute(name, arguments, instant)

            registry.execute = observe
            interpreter = ollama_interpreter(budget.url, budget.model, today=REFERENCE_DATE, registry=registry)
            planner = Planner(store, interpreter, language="es", today=REFERENCE_DATE)
            for index, turn in enumerate(case["turns"]):
                if budget.remaining_seconds() <= 0:
                    raise BudgetExceeded("deadline")
                entries = list(recording[index] if recording is not None else turn.get("responses", []))
                before, count = digest(store.list()), budget.requests
                tools.clear()

                def synthetic(*args, **kwargs):
                    if not entries:
                        raise ValueError("Replay exhausted; network fallback forbidden.")
                    return WireResponse(entries.pop(0))

                error, response, stopped = False, "", None
                try:
                    with budget.transport(None if mode == "live" else synthetic):
                        response = planner.respond(turn["user"])
                except Exception as exc:
                    error = True
                    stopped = str(exc) if isinstance(exc, BudgetExceeded) else type(exc).__name__
                rows = store.list()
                actual = {"pending": planner.pending, "draft": planner.capture_draft,
                          "capture_intent": planner.capture_intent, "rows": rows, "rows_count": len(rows),
                          "response": response, "source": (planner.pending or {}).get("source", ""),
                          "tools": list(tools), "attempts": budget.requests - count,
                          "storage_changed": before != digest(rows), "error": error}
                baseline = checks(turn["expect"], actual)
                acceptance = checks(turn.get("acceptance", turn["expect"]), actual)
                if turn["user"].strip() != "/confirm":
                    acceptance["storage_unchanged"] = not actual["storage_changed"]
                if mode != "live" and entries:
                    baseline["wire_consumed"] = False
                results.append({"baseline_checks": baseline, "acceptance_checks": acceptance,
                                "observation": {"rows_count": len(rows), "tools": list(tools),
                                                "attempts": actual["attempts"], "error": error,
                                                "state_sha256": digest(actual), "rows_sha256": digest(rows),
                                                "response_sha256": digest(response)}})
                if stopped in ("max_requests", "deadline", "request_timeout"):
                    return results, stopped
                if not all(baseline.values()) and mode != "live":
                    return results, "baseline_mismatch"
                if mode == "live" and (error or not all(acceptance.values())):
                    return results, stopped or "acceptance_failure"
    return results, None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("deterministic", "replay", "live"), default="deterministic")
    parser.add_argument("--cases", default=str(CORPUS), help="Synthetic conversation corpus")
    parser.add_argument("--replay", help="Recorded synthetic wire envelopes with model/digest provenance")
    parser.add_argument("--url", help="Explicit loopback Ollama endpoint for live mode")
    parser.add_argument("--model", help="Explicit installed model for live mode")
    parser.add_argument("--max-requests", type=int, help="Shared POST cap, 1..60; mandatory for live")
    parser.add_argument("--max-seconds", type=float, help="Shared wall time, >0..900; mandatory for live")
    parser.add_argument("--request-timeout", type=float, help="Hard time bound per POST; mandatory for live")
    parser.add_argument("--output", required=True, help="Sanitized report; live ledger is <output>.attempts.sqlite3")
    args = parser.parse_args(argv)
    budget = None
    try:
        if Path(args.output).resolve() in {Path(path).resolve() for path in (args.cases, args.replay) if path}:
            raise ValueError("Output must not overwrite corpus or replay input.")
        if args.mode == "live" and (any(value is None for value in (
                args.url, args.model, args.max_requests, args.max_seconds, args.request_timeout))
                or not args.url.strip() or not args.model.strip()):
            raise ValueError("Live requires explicit endpoint, model, request/time/timeout budgets.")
        maximum = 60 if args.max_requests is None else args.max_requests
        seconds = 900 if args.max_seconds is None else args.max_seconds
        timeout = 90 if args.request_timeout is None else args.request_timeout
        if not 1 <= maximum <= 60 or not math.isfinite(seconds) or not 0 < seconds <= 900:
            raise ValueError("Invalid request/time budget.")
        if not math.isfinite(timeout) or not 0 < timeout <= seconds:
            raise ValueError("Invalid request timeout.")
        if args.mode != "replay" and args.replay:
            raise ValueError("--replay requires replay mode.")
        recording = None
        if args.mode == "replay":
            recording = load_cases(args.replay)
            provenance = recording["provenance"]
            if (provenance.get("source") != "recorded-synthetic"
                    or not provenance.get("model") or not provenance.get("digest")):
                raise ValueError("Recorded synthetic provenance required; no bundled live evidence exists.")
        url = local_url(args.url or "http://127.0.0.1:11434")
        if url is None:
            raise ValueError("Only local Ollama is supported.")
        cases = load_cases(args.cases)
        if not cases or len({case["case_id"] for case in cases}) != len(cases):
            raise ValueError("A nonempty corpus with unique case IDs is required.")
        for case in cases:
            if not case.get("turns") or any(not turn.get("user") or not turn.get("expect")
                                          for turn in case["turns"]):
                raise ValueError("Each conversation needs turns with input and baseline expectations.")
        if recording is not None:
            for case in cases:
                turns = recording["cases"][case["case_id"]]
                if len(turns) != len(case["turns"]) or any(
                        "body" not in entry or "status_code" not in entry for turn in turns for entry in turn):
                    raise ValueError("Replay must contain exact per-turn wire envelopes.")
        budget = Budget(maximum, time.monotonic() + seconds,
                        ledger=args.output + ".attempts.sqlite3" if args.mode == "live" else None,
                        request_timeout=timeout, binding=digest([url, args.model, cases, timeout]))
        budget.url, budget.model = url, args.model or "synthetic"
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        print("Invalid evaluation configuration: " + type(exc).__name__)
        return 2
    report = {"evidence": args.mode, "reference_date": REFERENCE_DATE.isoformat(),
              "corpus_sha256": digest(cases), "completed": False, "cases": [], "stopped_reason": None,
              "model": budget.model, "url": url,
              "budget": {"max_requests": maximum, "max_seconds": seconds, "request_timeout": timeout},
              "recording_sha256": digest(recording) if recording else None,
              "provenance": "caller-declared recording" if recording else "synthetic" if args.mode == "deterministic" else "live execution path"}
    try:
        for case in cases:
            turns, stopped = run_case(case, budget, args.mode, recording["cases"][case["case_id"]] if recording else None)
            report["cases"].append({"case_id": case["case_id"], "issues": case["issues"], "turns": turns})
            if stopped:
                report["stopped_reason"] = stopped
                break
        else:
            if budget.remaining_seconds() <= 0:
                raise BudgetExceeded("deadline")
            report["completed"] = True
    except KeyboardInterrupt:
        report["stopped_reason"] = "cancelled"
    except Exception as exc:
        report["stopped_reason"] = str(exc) if isinstance(exc, BudgetExceeded) else type(exc).__name__
    finally:
        turns = [turn for case in report["cases"] for turn in case["turns"]]
        report["baseline_matches"] = bool(turns) and all(all(turn["baseline_checks"].values()) for turn in turns)
        report["acceptance_passed"] = bool(turns) and report["completed"] and all(all(turn["acceptance_checks"].values()) for turn in turns)
        report["http_attempts"] = budget.requests if args.mode == "live" else 0
        report["simulated_attempts"] = budget.requests if args.mode != "live" else 0
        budget.close()
        write_report(report, str(Path(args.output).absolute()))
    return 0 if report["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

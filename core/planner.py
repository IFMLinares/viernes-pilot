"""Opt-in text planner. No Engram writes, audio or system-action tools."""
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import requests

from core.commitments import AREAS, CommitmentStore, validate_fields
from core.ollama_runtime import ensure_ollama, local_url
from core.queries import history_requested, listing_request
from core.presentation import (
    help_text, initial_language, input_language, records, proposal as render_proposal,
    runtime_message, query_records, general_reply, text as ui_text,
)

HELP = help_text("en")

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "list", "edit", "complete", "clarify", "reply"]},
        "language": {"type": "string", "enum": ["en", "es"]},
        "answer": {"type": "string", "minLength": 1, "maxLength": 8000},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "area": {"type": "string", "enum": list(AREAS)},
            "project": {"type": ["string", "null"]}, "due_date": {"type": ["string", "null"]},
        }, "required": ["title", "area"], "additionalProperties": False}},
        "id": {"type": "integer"},
        "fields": {"type": "object", "properties": {
            "title": {"type": "string"}, "area": {"type": "string", "enum": list(AREAS)},
            "project": {"type": ["string", "null"]}, "due_date": {"type": ["string", "null"]},
        }, "additionalProperties": False},
        "area": {"type": ["string", "null"], "enum": [*AREAS, None]},
        "clarification": {"type": "string", "enum": ["area", "date", "id", "scope", "request"]},
        "scope": {"type": "string", "enum": ["current", "all", "range"]},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
    },
    "required": ["action", "language"], "additionalProperties": False,
}


def ollama_interpreter(url, model):
    url = local_url(url)
    if url is None:
        raise ValueError("Only the local Ollama endpoint is supported.")

    def interpret(text, history):
        prompt = (
            "You are Viernes, a local conversational assistant specializing in personal commitments. "
            "Never execute shell commands or claim actions were performed. "
            f"Today is {date.today().isoformat()} in the user's local timezone. "
            "Return JSON following the provided schema. Areas: university, work, personal. "
            "Set language to en or es matching the latest user message, not earlier messages. "
            "For ambiguous short input retain the preceding conversation language. "
            "Preserve the user's title language. Never invent deadlines, years, owners, or IDs. "
            "For general questions, explanations or advice, use action=reply with only action, "
            "language and answer, in the user's language. This is general model knowledge, "
            "not a verified personal-data answer; you have no database, web or tool access here. "
            "For requests about stored commitments, use list or clarify, never reply. "
            "Omit unused fields; answer is permitted only for reply. "
            "Resolve explicit relative dates using today; for incomplete or ambiguous dates, "
            "unclear areas, unsupported requests or missing IDs, action=clarify with clarification "
            "set to date, area, scope, request or id. Do not generate an answer or question. "
            "No deadline is allowed when none was specified. "
            "A date without a year requires clarification unless the year is explicit in context. "
            "For create return items; list optionally area and scope; edit id and fields; complete id. "
            "Do not claim anything is saved. You cannot confirm or execute a proposal. "
            "For queries always return list, never infer whether stored data exists. "
            "Default scope=current; use all only for explicitly requested full history. "
            "For an explicit period use scope=range and complete inclusive ISO start_date/end_date. "
            "Listing returns all statuses; unsupported filters require clarification=request."
        )
        response = requests.post(
            f"{url}/api/chat", json={"model": model, "stream": False, "format": SCHEMA,
                "options": {"temperature": 0, "num_ctx": 4096},
                "messages": [{"role": "system", "content": prompt}, *history,
                             {"role": "user", "content": text}]},
            timeout=(3, 90), allow_redirects=False, proxies={"http": "", "https": ""},
        )
        if response.status_code != 200:
            raise ValueError(f"Ollama returned HTTP {response.status_code}.")
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    return interpret


class Planner:
    def __init__(self, store, interpreter=None, language="en"):
        if language not in ("en", "es"):
            raise ValueError("Language must be en or es.")
        self.store = store
        self.interpreter = interpreter
        self.pending = None
        self.history = []
        self.sources = []
        self.language = language
        self.conversation = []

    def reset(self):
        self.pending = None
        self.history.clear()
        self.sources.clear()

    def respond(self, text):
        text = text.strip()
        if not text:
            return ""
        if not text.startswith("/"):
            self.language = input_language(text, self.language)
        if text == "/help":
            return help_text(self.language)
        if text == "/cancel":
            self.reset()
            return ui_text("cancelled", self.language)
        if text == "/confirm":
            if self.pending is None:
                return ui_text("no_proposal", self.language)
            proposal = self.pending
            if proposal["action"] == "create":
                saved = self.store.create_many(proposal["items"], proposal["source"])
            elif proposal["action"] == "edit":
                saved = self.store.edit(proposal["id"], proposal["fields"])
            else:
                saved = self.store.complete(proposal["id"])
            self.reset()
            rows = saved if isinstance(saved, list) else [saved]
            return ui_text("saved", self.language) + ":\n" + records(rows, self.language)
        if self.pending is not None and not (text == "/list" or text.startswith("/list ")):
            return ui_text("pending", self.language)
        command, _, rest = text.partition(" ")
        if command == "/list":
            options = rest.split()
            if options.count("--all") > 1:
                raise ValueError("Usage: /list [university|work|personal] [--all]")
            areas = [option for option in options if option != "--all"]
            if len(areas) > 1 or (areas and areas[0] not in AREAS):
                raise ValueError("Usage: /list [university|work|personal] [--all]")
            result = self.store.query(areas[0] if areas else None, scope="all" if "--all" in options else "current")
            return query_records(result, self.language)
        if command == "/new":
            result = {"action": "create", "items": [json.loads(rest)]}
        elif command in ("/edit", "/done"):
            task_id, _, fields = rest.partition(" ")
            result = {"action": "edit" if command == "/edit" else "complete", "id": int(task_id)}
            if command == "/done" and fields.strip():
                raise ValueError("Usage: /done ID")
            if command == "/edit":
                result["fields"] = json.loads(fields)
        elif text.startswith("/"):
            raise ValueError("Unknown command. Use /help.")
        else:
            result = listing_request(text)
            if result is None:
                if self.interpreter is None:
                    return ui_text("offline", self.language)
                if len(self.history) >= 12:
                    self.reset()
                    return ui_text("limit", self.language)
                language_context = {"role": "system", "content": (
                    f"Current conversation language: {self.language}. "
                    "For ambiguous short input retain it; otherwise follow the latest user's language."
                )}
                result = self.interpreter(text, [language_context, *self.conversation, *self.history])
        if not isinstance(result, dict):
            raise ValueError("Expected a structured proposal.")
        if "language" in result:
            if result["language"] not in ("en", "es"):
                raise ValueError("Language must be en or es.")
            self.language = result["language"]
        action = result.get("action")
        if "answer" in result and action != "reply":
            raise ValueError("General answers cannot be combined with commitment operations.")
        if action == "reply":
            if set(result) != {"action", "language", "answer"}:
                raise ValueError("General replies require exactly action, language and answer.")
            answer = result.get("answer")
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 8000:
                raise ValueError("Expected a nonempty general answer of at most 8000 characters.")
            self.conversation.extend([
                {"role": "user", "content": text[:1000]},
                {"role": "assistant", "content": answer[:3000]},
            ])
            while (len(self.conversation) > 6
                   or sum(len(item["content"]) for item in self.conversation) > 4000):
                del self.conversation[:2]
            self.reset()
            return general_reply(answer, self.language)
        if action == "list" and result.get("scope") == "all" and not history_requested(text):
            result = {"action": "clarify", "clarification": "scope"}
            action = "clarify"
        if action == "clarify":
            reason = result.get("clarification", "request")
            if reason not in ("area", "date", "id", "scope", "request"):
                raise ValueError("Unsupported clarification reason.")
            question = ui_text(f"clarify_{reason}", self.language)
            self.history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": question}])
            self.sources.append(text)
            return question
        if action == "list":
            result = self.store.query(result.get("area"), scope=result.get("scope", "current"),
                                      start_date=result.get("start_date"), end_date=result.get("end_date"))
            self.reset()
            return query_records(result, self.language)
        change = {"action": action}
        if action == "create":
            items = result.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ValueError("Expected between 1 and 20 commitments.")
            change["items"] = [validate_fields(item) for item in items]
            change["source"] = "\n".join([*self.sources, text])
        elif action in ("edit", "complete"):
            task_id = result.get("id")
            change["id"] = self.store.get(task_id)["id"]
            change["before"] = self.store.get(task_id)
            if action == "edit":
                change["fields"] = validate_fields(result.get("fields"), partial=True)
        else:
            raise ValueError("Unsupported proposal action.")
        self.pending = change
        return render_proposal(change, self.language)


def run_repl(store, interpreter=None, output=None, language=None):
    output = output or sys.stdout
    planner = Planner(store, interpreter, language=language or initial_language())
    print(ui_text("welcome", planner.language), file=output)
    while True:
        try:
            text = input(ui_text("prompt", planner.language))
            if text.strip() == "/quit":
                print(ui_text("goodbye", planner.language), file=output)
                break
            response = planner.respond(text)
            if response:
                print(response, file=output)
        except (EOFError, KeyboardInterrupt):
            print("\n" + ui_text("goodbye", planner.language), file=output)
            break
        except (ValueError, TypeError, KeyError):
            print(ui_text("error", planner.language), file=output)
        except requests.RequestException:
            print(ui_text("network_error", planner.language), file=output)
        except sqlite3.Error:
            print(ui_text("storage_error", planner.language), file=output)


def main():
    # Import legacy configuration only at entry, not in the domain or test paths.
    from config import OLLAMA_URL, OLLAMA_MODEL
    language = initial_language()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    path = os.environ.get("VIERNES_DB_PATH", str(data_home / "viernes" / "commitments.sqlite3"))
    autostart = os.environ.get("VIERNES_OLLAMA_AUTOSTART", "false").lower()
    if autostart not in ("true", "false"):
        print(ui_text("autostart_error", language))
        return 2
    try:
        wait = float(os.environ.get("VIERNES_OLLAMA_STARTUP_TIMEOUT", "10"))
    except ValueError:
        print(ui_text("timeout_error", language))
        return 2
    status = ensure_ollama(OLLAMA_URL, OLLAMA_MODEL, autostart=autostart == "true", wait_seconds=wait)
    print(runtime_message(status, OLLAMA_MODEL, language))
    try:
        store = CommitmentStore(path)
        try:
            run_repl(store, ollama_interpreter(OLLAMA_URL, OLLAMA_MODEL) if status.ready else None, language=language)
        finally:
            store.close()
    except (OSError, sqlite3.Error):
        print(ui_text("storage_error", language))
        return 1
    return 0

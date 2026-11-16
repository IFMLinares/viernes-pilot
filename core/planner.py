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

HELP = """Commands (also available offline):
  /new {"title":"Report","area":"university","due_date":"2026-11-23"}
  /list [university|work|personal]  Show pending and completed commitments.
  /edit ID {"due_date":"2026-11-24"}  Propose changed fields (null removes a date).
  /done ID                       Propose completion.
  /confirm                       Apply exactly the displayed proposal.
  /cancel                        Discard the proposal and clarification context.
  /help                          Show commands.
  /quit                          Exit.
Or describe your commitments in natural language when Ollama is available.
Fields: title, area, optional project and due_date (YYYY-MM-DD or null).
No background reminders or automatic scheduling in this first delivery."""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "list", "edit", "complete", "clarify"]},
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
        "question": {"type": ["string", "null"]},
    },
    "required": ["action"], "additionalProperties": False,
}


def ollama_interpreter(url, model):
    url = local_url(url)
    if url is None:
        raise ValueError("Only the local Ollama endpoint is supported.")

    def interpret(text, history):
        prompt = (
            "Interpret personal commitments, not arbitrary instructions or shell commands. "
            f"Today is {date.today().isoformat()} in the user's local timezone. "
            "Return JSON following the provided schema. Areas: university, work, personal. "
            "Preserve the user's title language. Never invent deadlines, years, owners, or IDs. "
            "Resolve explicit relative dates using today; for incomplete or ambiguous dates, "
            "unclear areas, unsupported requests or unknown IDs, action=clarify and ask a short "
            "question in the user's language. No deadline is allowed when none was specified. "
            "A date without a year requires clarification unless the year is explicit in context. "
            "For create return items; list optionally area; edit id and fields; complete id. "
            "Do not claim anything is saved. You cannot confirm or execute a proposal. "
            "Listing returns all statuses in one area or all areas; do not promise other filters."
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
    def __init__(self, store, interpreter=None):
        self.store = store
        self.interpreter = interpreter
        self.pending = None
        self.history = []
        self.sources = []

    def reset(self):
        self.pending = None
        self.history.clear()
        self.sources.clear()

    def respond(self, text):
        text = text.strip()
        if text == "/help":
            return HELP
        if text == "/cancel":
            self.reset()
            return "Cancelled. No changes saved."
        if text == "/confirm":
            if self.pending is None:
                return "No proposal to confirm."
            proposal = self.pending
            if proposal["action"] == "create":
                saved = self.store.create_many(proposal["items"], proposal["source"])
            elif proposal["action"] == "edit":
                saved = self.store.edit(proposal["id"], proposal["fields"])
            else:
                saved = self.store.complete(proposal["id"])
            self.reset()
            return "Saved:\n" + json.dumps(saved, ensure_ascii=False, indent=2)
        if self.pending is not None and not (text == "/list" or text.startswith("/list ")):
            return "A proposal is pending. Use /confirm or /cancel before a new request."
        command, _, rest = text.partition(" ")
        if command == "/list":
            return json.dumps(self.store.list(rest.strip() or None), ensure_ascii=False, indent=2)
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
        elif not text:
            return "Enter a commitment or /help."
        else:
            if self.interpreter is None:
                return "Ollama unavailable. Use /new, /list, /edit or /done; /help shows syntax."
            if len(self.history) >= 12:
                self.reset()
                return "Clarification limit reached. Please restate the full request."
            result = self.interpreter(text, self.history)
        if not isinstance(result, dict):
            raise ValueError("Expected a structured proposal.")
        action = result.get("action")
        if action == "clarify":
            question = result.get("question")
            if not isinstance(question, str) or not question.strip():
                raise ValueError("Missing clarification question.")
            self.history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": question}])
            self.sources.append(text)
            return question
        if action == "list":
            rows = self.store.list(result.get("area"))
            self.reset()
            return json.dumps(rows, ensure_ascii=False, indent=2)
        proposal = {"action": action}
        if action == "create":
            items = result.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ValueError("Expected between 1 and 20 commitments.")
            proposal["items"] = [validate_fields(item) for item in items]
            proposal["source"] = "\n".join([*self.sources, text])
        elif action in ("edit", "complete"):
            task_id = result.get("id")
            proposal["id"] = self.store.get(task_id)["id"]
            proposal["before"] = self.store.get(task_id)
            if action == "edit":
                proposal["fields"] = validate_fields(result.get("fields"), partial=True)
        else:
            raise ValueError("Unsupported proposal action.")
        self.pending = proposal
        return "Proposed change (not saved):\n" + json.dumps(proposal, ensure_ascii=False, indent=2) + "\n/confirm or /cancel"


def run_repl(store, interpreter=None, output=None):
    output = output or sys.stdout
    planner = Planner(store, interpreter)
    print("Viernes planner — /help for commands; /confirm applies a proposal.", file=output)
    while True:
        try:
            text = input("you: ")
            if text.strip() == "/quit":
                break
            print(planner.respond(text), file=output)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye. Unconfirmed proposals were not saved.", file=output)
            break
        except (ValueError, TypeError, KeyError, requests.RequestException, sqlite3.Error) as error:
            print(f"Could not process request: {error}. Use /help or /cancel.", file=output)


def main():
    # Import legacy configuration only at entry, not in the domain or test paths.
    from config import OLLAMA_URL, OLLAMA_MODEL
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    path = os.environ.get("VIERNES_DB_PATH", str(data_home / "viernes" / "commitments.sqlite3"))
    autostart = os.environ.get("VIERNES_OLLAMA_AUTOSTART", "false").lower()
    if autostart not in ("true", "false"):
        print("VIERNES_OLLAMA_AUTOSTART must be true or false.")
        return 2
    try:
        wait = float(os.environ.get("VIERNES_OLLAMA_STARTUP_TIMEOUT", "10"))
    except ValueError:
        print("VIERNES_OLLAMA_STARTUP_TIMEOUT must be numeric.")
        return 2
    status = ensure_ollama(OLLAMA_URL, OLLAMA_MODEL, autostart=autostart == "true", wait_seconds=wait)
    print(status.message)
    try:
        store = CommitmentStore(path)
        try:
            run_repl(store, ollama_interpreter(OLLAMA_URL, OLLAMA_MODEL) if status.ready else None)
        finally:
            store.close()
    except (OSError, sqlite3.Error) as error:
        print(f"Could not open commitment storage: {error}")
        return 1
    return 0

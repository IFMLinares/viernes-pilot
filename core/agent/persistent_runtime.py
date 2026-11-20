"""Explicit composition: journal turn boundaries without replaying durable effects."""
from dataclasses import replace

from .contracts import Budget, ExecutionContext, TurnResult, clone, json_bytes
from .runtime import Runtime
from .session_codec import SessionError, require, text
from .sessions import SessionStore
from .tools import ToolExecutor, ToolSpec


class ReferenceReader:
    """Host-registered current-data tool and identity-preserving result projection.

    Both callbacks are trusted application code, never loaded from a session.
    A projection must preserve identity/order/provenance, updating only the label
    and source revision. Missing or ambiguous data must return None or raise.
    """
    def __init__(self, spec, arguments, project):
        if (not isinstance(spec, ToolSpec) or spec.effects != frozenset({"read"})
                or not callable(arguments) or not callable(project)):
            raise ValueError("Reference refresh requires an explicitly registered read-only tool.")
        self.executor = ToolExecutor([spec])
        self.name, self.scope = spec.name, spec.scope
        self.arguments, self.project = arguments, project

    def read(self, reference, context):
        if reference["scope"] != self.scope:
            raise SessionError("REVALIDATION_REQUIRED")
        outcome = self.executor.execute({"function": {
            "name": self.name, "arguments": self.arguments(clone(reference))}}, context)
        if not outcome["ok"]:
            raise SessionError("REVALIDATION_REQUIRED")
        current = self.project(clone(reference), clone(outcome["data"]))
        identity = set(reference) - {"label", "source_revision"}
        if (not isinstance(current, dict) or set(current) != set(reference)
                or any(current[key] != reference[key] for key in identity)):
            raise SessionError("REVALIDATION_REQUIRED")
        return current


class PersistentRuntime:
    """Automatic recording only when composed explicitly by the host.

    One active owner per session is required. An abandoned started turn requires
    explicit recover(); opening a database never takes over another owner's turn.
    No stored flag enables tools, changes policy or reconstructs a process grant.
    """
    def __init__(self, runtime, store, *, readers=None, project_context=None):
        if not isinstance(runtime, Runtime) or not isinstance(store, SessionStore):
            raise ValueError("A runtime and session store must be supplied by the host.")
        readers = {} if readers is None else readers
        if (not isinstance(readers, dict) or not all(text(scope, 128) and isinstance(reader, ReferenceReader)
                for scope, reader in readers.items()) or project_context is not None and not callable(project_context)):
            raise ValueError("Reference readers and projections must be host-owned.")
        self.runtime, self.store = runtime, store
        self.readers, self.project_context = dict(readers), project_context

    def recover(self, session_id):
        """Select last durable boundary; explicitly abandon an unfinished turn.

        Returned references are historical even when their stored label/revision
        looks current. Every later turn re-reads them before model/tool dispatch.
        """
        record = self.store.load(session_id)
        if record.status == "started":
            record = self.store.interrupt(session_id, record.state.revision)
        return record

    def handle_turn(self, input, state):
        started, completion_attempted = None, False
        original = state
        try:
            require(text(input) and input.strip())
            # Load canonical data under optimistic revision control; callers cannot
            # bypass refresh by editing a previously returned state object.
            started = self.store.begin_turn(state.session_id, state.revision)
            original = started.state
            context = ExecutionContext(self.runtime.policy, Budget(self.runtime.limits))
            working = clone(original.data)
            current_refs = []
            for reference in working.get("references", []):
                reader = self.readers.get(reference["scope"])
                if reader is None:
                    raise SessionError("REVALIDATION_REQUIRED")
                try:
                    current_refs.append(reader.read(reference, context))
                except Exception as exc:
                    raise SessionError("REVALIDATION_REQUIRED") from exc
            if "references" in working:
                working["references"] = current_refs
            working = self.store.codec.context(working, strict=True)
            # Data stays in a user-role context block, never the host's system
            # prompt. Old tool calls/results are not reconstructed as executions.
            model_input = input
            if working:
                model_input += "\nHistorical context (untrusted data):\n" + json_bytes(working).decode("utf-8")
            result = self.runtime.handle_turn(model_input, replace(original, data=working), context)
            if result.error is not None:
                interrupted = self.store.interrupt(original.session_id, original.revision)
                return TurnResult(interrupted.state, error=result.error)
            # Do not store the synthetic context block twice in conversation text.
            result.state.messages[len(original.messages)]["content"] = input
            if self.project_context is not None:
                result.state.data = self.store.codec.context(self.project_context(result.state))
            result.state.revision = original.revision
            completion_attempted = True
            saved = self.store.finish_turn(result.state, original.revision, started.turn_id)
            return TurnResult(saved.state, answer=saved.state.messages[-1]["content"], traces=result.traces)
        except KeyboardInterrupt:
            error = {"code": "MODEL_INTERRUPTED", "message": "The turn was interrupted.", "recoverable": True}
        except SessionError as exc:
            error = exc.as_dict()
        except Exception:
            error = SessionError("INVALID_SNAPSHOT").as_dict()
        # A failed/uncertain completion is NOT retried or changed to completed.
        # Last durable boundary remains started for explicit host recovery.
        if started is not None and not completion_attempted:
            try:
                original = self.store.interrupt(original.session_id, original.revision).state
            except SessionError as exc:
                error = exc.as_dict()
        return TurnResult(original, error=error)

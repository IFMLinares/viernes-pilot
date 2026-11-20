"""Opt-in generic agent components; no tools or application entrypoints activated."""
from .contracts import ConversationState, Limits, ModelAdapter, TurnResult
from .ollama import OllamaModelAdapter
from .runtime import Runtime
from .tools import Policy, ToolExecutor, ToolSpec
from .persistent_runtime import PersistentRuntime, ReferenceReader
from .session_codec import SessionCodec, SessionError, SessionRecord
from .sessions import SessionStore

__all__ = ["ConversationState", "Limits", "ModelAdapter", "OllamaModelAdapter", "Policy",
           "Runtime", "ToolExecutor", "ToolSpec", "TurnResult", "PersistentRuntime",
           "ReferenceReader", "SessionCodec", "SessionError", "SessionRecord", "SessionStore"]

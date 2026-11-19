"""Opt-in generic agent components; no tools or application entrypoints activated."""
from .contracts import ConversationState, Limits, ModelAdapter, TurnResult
from .ollama import OllamaModelAdapter
from .runtime import Runtime
from .tools import Policy, ToolExecutor, ToolSpec

__all__ = ["ConversationState", "Limits", "ModelAdapter", "OllamaModelAdapter", "Policy",
           "Runtime", "ToolExecutor", "ToolSpec", "TurnResult"]

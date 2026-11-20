"""Native local Ollama adapter; no tools execute at this boundary."""
import json

import requests

from core.deadlines import deadline
from core.ollama_runtime import local_url
from .contracts import AgentError, assistant_message, json_bytes


class OllamaModelAdapter:
    def __init__(self, url, model):
        normalized = local_url(url)
        if normalized is None or not isinstance(model, str) or not model.strip():
            raise ValueError("An explicit local Ollama endpoint and model are required.")
        self.url, self.model = normalized, model

    def next(self, messages, tool_specs, budget):
        payload = {"model": self.model, "messages": messages, "tools": tool_specs,
                   "stream": False, "think": False, "options": {"temperature": 0}}
        budget.check_context(payload)
        budget.reserve("requests")
        remaining = budget.remaining()
        seconds = min(remaining, budget.limits.request_timeout)
        resource = "time" if remaining <= budget.limits.request_timeout else "request_time"
        try:
            with deadline(seconds, lambda: AgentError("BUDGET_EXCEEDED", resource=resource),
                          lambda: AgentError("DEADLINE_UNAVAILABLE")):
                response = requests.post(self.url + "/api/chat", json=payload, stream=True,
                                         timeout=(min(3, seconds / 2), seconds / 2),
                                         allow_redirects=False, proxies={"http": "", "https": ""})
                try:
                    if response.status_code != 200:
                        raise AgentError("MODEL_UNAVAILABLE", recoverable=True)
                    raw = bytearray()
                    for chunk in response.iter_content(chunk_size=4096):
                        if len(raw) + len(chunk) > budget.limits.max_response_bytes:
                            raise AgentError("CONTEXT_LIMIT")
                        raw.extend(chunk)
                    envelope = json.loads(raw.decode("utf-8"))
                    json_bytes(envelope)  # Reject nonfinite or otherwise non-JSON values.
                finally:
                    response.close()
            budget.check_time()
        except requests.Timeout:
            raise AgentError("MODEL_INTERRUPTED", recoverable=True) from None
        except requests.RequestException:
            raise AgentError("MODEL_UNAVAILABLE", recoverable=True) from None
        except (ValueError, TypeError, UnicodeError):
            raise AgentError("MODEL_PROTOCOL") from None
        if not isinstance(envelope, dict):
            raise AgentError("MODEL_PROTOCOL")
        if envelope.get("done") is not True or envelope.get("done_reason") not in (None, "stop"):
            raise AgentError("MODEL_INTERRUPTED", recoverable=True)
        return assistant_message(envelope.get("message"))

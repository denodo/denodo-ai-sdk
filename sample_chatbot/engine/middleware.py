"""
Contains middleware classes for request logging and conversation history management.
"""

import time

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from sample_chatbot.engine.context_window import message_content_text, prepare_model_messages

class ContextWindowMiddleware(AgentMiddleware):
    """
    Keeps the model request inside the configured context window.

    Repeated metadata_search view schemas are replaced with a short note, and
    when the next call would leave no room for the reserved answer the oldest
    complete question/answer pairs are dropped down to the compaction budget.
    """

    name = "context_window_middleware"

    def __init__(self, context_window, max_output_tokens=0, skills_text=""):
        super().__init__()
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens
        self.skills_text = skills_text or ""
        self.last_usage = None

    def _prepare_request(self, request):
        system_message = getattr(request, "system_message", None)
        if system_message is not None:
            system_text = message_content_text(system_message)
        else:
            system_text = getattr(request, "system_prompt", None) or ""

        prepared, usage = prepare_model_messages(
            messages=request.messages,
            system_text=system_text,
            tools=request.tools or [],
            skills_text=self.skills_text,
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
            log=True,
        )
        self.last_usage = usage

        if len(prepared) != len(request.messages) or any(
            left is not right for left, right in zip(prepared, request.messages)
        ):
            return request.override(messages=prepared)
        return request

    def wrap_model_call(self, request, handler):
        return handler(self._prepare_request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._prepare_request(request))


class ToolDurationMiddleware(AgentMiddleware):
    """
    Records wall-clock time for each tool call and stores it on the ToolMessage
    artifact as tool_duration so the chatbot UI and reloaded history can show it.
    """

    name = "tool_duration_middleware"

    def wrap_tool_call(self, request, handler):
        start = time.perf_counter()
        result = handler(request)
        return self._attach_duration(result, start)

    async def awrap_tool_call(self, request, handler):
        start = time.perf_counter()
        result = await handler(request)
        return self._attach_duration(result, start)

    def _attach_duration(self, result, start):
        duration = round(time.perf_counter() - start, 2)
        if not isinstance(result, ToolMessage):
            return result

        artifact = result.artifact
        if artifact is None:
            new_artifact = {"tool_duration": duration}
        elif isinstance(artifact, dict):
            new_artifact = {**artifact, "tool_duration": duration}
        else:
            return result

        return result.model_copy(update={"artifact": new_artifact})

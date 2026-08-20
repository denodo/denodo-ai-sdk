"""
Contains middleware classes for request logging and conversation history management.
"""

import logging

from dataclasses import replace
from langchain.agents.middleware import AgentMiddleware

class TrimConversationHistoryMiddleware(AgentMiddleware):
    """
    Middleware that trims conversation history to prevent context overflow.

    Trims based on conversation blocks (HumanMessage -> AIMessage pairs)
    rather than token count for more predictable behavior.
    """

    name = "trim_history_middleware"

    def __init__(self, conversation_history_limit: int = 5):
        super().__init__()
        self.conversation_history_limit = conversation_history_limit

    def _trim_request(self, request):
        messages = request.messages

        # Count in blocks of HumanMessage -> AIMessage (deleting any intermediate steps like tool calls)
        blocks = []
        current_block_start = None

        for index, message in enumerate(messages):
            if type(message).__name__ == "HumanMessage" or getattr(message, "type", "") in ["human", "user"]:
                if current_block_start is not None:
                    blocks.append((current_block_start, index - 1))
                current_block_start = index

        if current_block_start is not None:
            blocks.append((current_block_start, len(messages) - 1))

        block_count = len(blocks)

        if block_count > self.conversation_history_limit:
            logging.debug(f"Conversation history block limit reached: {block_count} > {self.conversation_history_limit}")
            logging.debug("Current conversation history:")
            for i, m in enumerate(messages):
                logging.debug(f"  [{i}] {type(m).__name__}: {str(m.content).strip()[:100]}...")

            blocks_to_remove = block_count - self.conversation_history_limit
            first_block_start, _ = blocks[0]
            _, last_removed_end = blocks[blocks_to_remove - 1]
            cutoff_index = last_removed_end + 1

            kept_messages = []
            for index, message in enumerate(messages):
                if index < first_block_start or index >= cutoff_index:
                    kept_messages.append(message)

            logging.info(f"Removing {blocks_to_remove} oldest conversation blocks (leaving exactly {self.conversation_history_limit})")

            if hasattr(request, "override"):
                return request.override(messages=kept_messages)
            else:
                return replace(request, messages=kept_messages)

        return request

    def wrap_model_call(self, request, handler):
        trimmed_request = self._trim_request(request)
        return handler(trimmed_request)

    async def awrap_model_call(self, request, handler):
        trimmed_request = self._trim_request(request)
        return await handler(trimmed_request)

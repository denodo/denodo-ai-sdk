"""
Contains middleware classes for request logging and conversation history management.
"""

import logging

from typing import Any
from langgraph.runtime import Runtime
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain.agents.middleware import AgentMiddleware, AgentState

class UserRequestLoggingMiddleware(AgentMiddleware):
    """Middleware that logs user requests with custom instructions."""

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        ai_sdk_ci = runtime.context.ai_sdk_custom_instructions
        if ai_sdk_ci:
            logging.info(f"Processing request from user '{runtime.context.username}' with AI SDK custom instructions: '{ai_sdk_ci.strip()}'")
        else:
            logging.info(f"Processing request from user '{runtime.context.username}' with no AI SDK custom instructions.")
        return None

class TrimConversationHistoryMiddleware(AgentMiddleware):
    """
    Middleware that trims conversation history to prevent context overflow.

    Trims based on conversation blocks (HumanMessage -> AIMessage pairs)
    rather than token count for more predictable behavior.
    """

    def __init__(self, conversation_history_limit: int = 5, remove_first_n_messages: int = 1):
        super().__init__()
        self.conversation_history_limit = conversation_history_limit
        self.remove_first_n_messages = remove_first_n_messages

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state["messages"]
        # Count in blocks of HumanMessage -> AIMessage (deleting any intermediate steps like tool calls)
        blocks = []
        current_block_start = None

        for index, message in enumerate(messages):
            if type(message).__name__ == "HumanMessage":
                if current_block_start is not None:
                    blocks.append((current_block_start, index - 1))
                current_block_start = index

        if current_block_start is not None:
            blocks.append((current_block_start, len(messages) - 1))

        block_count = len(blocks)

        if block_count > self.conversation_history_limit:
            logging.info(f"Conversation history block limit reached: {block_count} > {self.conversation_history_limit}")
            logging.info("Current conversation history:")
            for i, m in enumerate(messages):
                logging.info(f"  [{i}] {type(m).__name__}: {str(m.content).strip()[:100]}...")

            blocks_to_remove = min(self.remove_first_n_messages, block_count)
            first_block_start, _ = blocks[0]
            _, last_removed_end = blocks[blocks_to_remove - 1]
            cutoff_index = last_removed_end + 1

            kept_messages = []
            for index, message in enumerate(messages):
                if index < first_block_start or index >= cutoff_index:
                    kept_messages.append(message)

            logging.info(f"Removing {blocks_to_remove} oldest conversation blocks")

            return {
                "messages": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    *kept_messages,
                ]
            }

        return None

"""
Contains the core chatbot intelligence: the ChatbotEngine class,
LangChain tools, middleware, and prompts.
"""

from sample_chatbot.engine.chatbot import ChatbotEngine
from sample_chatbot.engine.context import UserContext, TOOL_DEFINITIONS
from sample_chatbot.engine.prompts import CHATBOT_SYSTEM_PROMPT, DEEPQUERY_GUIDANCE

__all__ = [
    'ChatbotEngine',
    'UserContext',
    'TOOL_DEFINITIONS',
    'CHATBOT_SYSTEM_PROMPT',
    'DEEPQUERY_GUIDANCE',
]

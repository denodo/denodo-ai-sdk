from api.deepquery.agent.xml_utils import format_tool_as_xml
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from api.deepquery.agent.prompts import SYSTEM_PROMPT_TEMPLATE, TOOL_INSTRUCTIONS

class PromptBuilder:
    """Handles prompt creation and management."""

    def __init__(self, tools, system_prompt, date, max_concurrent_tool_calls=5):
        """
        Initialize the prompt builder.

        Args:
            tools: List of available tools
            system_prompt: Custom system prompt
            date: Formatted date string
            max_concurrent_tool_calls: Maximum number of tools that can be called concurrently
        """
        self.tools = tools
        self.system_prompt = system_prompt
        self.date = date
        self.max_concurrent_tool_calls = max_concurrent_tool_calls

    def create_system_prompt(self):
        """
        Create the system prompt with date and agent prompt.

        Returns:
            The complete system prompt string
        """
        available_tools = "\n".join(
            format_tool_as_xml(tool) for tool in self.tools
        )

        # Format tool instructions with max_concurrent_tool_calls
        formatted_tool_instructions = TOOL_INSTRUCTIONS.format(
            max_concurrent_tool_calls=self.max_concurrent_tool_calls
        )

        return SYSTEM_PROMPT_TEMPLATE.format(
            date=self.date,
            available_tools=available_tools,
            tool_instructions=formatted_tool_instructions,
            custom_system_prompt=self.system_prompt
        )

    def create_chat_prompt(self, full_system_prompt):
        """
        Create the chat prompt template.

        Args:
            full_system_prompt: The complete system prompt

        Returns:
            ChatPromptTemplate instance
        """
        return ChatPromptTemplate.from_messages([
            ("system", full_system_prompt),
            MessagesPlaceholder("chat_history", n_messages=100),
            ("human", "{input}"),
        ])
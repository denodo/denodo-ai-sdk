from api.deepquery.agent.xml_utils import parse_xml
from langchain_core.messages import HumanMessage, AIMessage

class ConversationManager:
    """Manages conversation memory and flow control."""

    def __init__(self):
        """Initialize the conversation manager."""
        self.memory = []

    def update_memory(self, user_input, response):
        """
        Update the conversation memory with user input and agent response.

        Args:
            user_input: The user's input as a dict with 'text' key
            response: The agent's response
        """
        self.memory.append(HumanMessage(content=user_input["text"]))
        self.memory.append(AIMessage(content=response))

    def should_end_conversation(self, response):
        """
        Check if the conversation should end based on if the final_answer tool was called
        by itself (no other tools requested).

        Args:
            response: The agent's response

        Returns:
            True if conversation should end, False otherwise
        """
        # Parse and check for final answer exclusively
        parsed = parse_xml(response)
        parsed_tools = parse_xml(parsed.get("tools", ""))
        return "final_answer" in parsed_tools and len(parsed_tools) == 1

    async def process_tools_and_prepare_next_input(self, response, tool_executor, agent_instance):
        """
        Process tools from response and prepare the next input.

        Args:
            response: The agent's response
            tool_executor: The tool executor instance
            agent_instance: The agent instance for context

        Returns:
            The next user input as a dict with 'text' key
        """
        parsed = parse_xml(response)
        parsed_tools = parse_xml(parsed.get("tools", ""))

        # If final_answer is present along with other tools, ignore it for now
        ignored_final_answer_message = None
        if "final_answer" in parsed_tools and len(parsed_tools) > 1:
            parsed_tools.pop("final_answer", None)
            ignored_final_answer_message = (
                "Final answer was ignored due to other tools asked for execution. "
                "If you want to end, you have to wait until all tools have executed and you have reviewed them. "
                "Once that is the case, you can call final_answer by itself."
            )

        # Execute remaining tools
        tool_results = await tool_executor.parallel_execute_tools(agent_instance, parsed_tools)

        # Prepare next input
        if ignored_final_answer_message is not None:
            joined_results = "\n\n".join(tool_results) if tool_results else ""
            prefix_and_results = (
                ignored_final_answer_message if not joined_results else f"{ignored_final_answer_message}\n\n{joined_results}"
            )
            return {"text": prefix_and_results}

        if len(tool_results) > 2:
            text_input = "\n\n".join(tool_results)
            return {"text": text_input}
        else:
            return {"text": """You did not call any tools. Are you sure that's what you wanted to do? Remember to call tools you must include them in between <tools> and </tools> tags,
            like this:
            <tools>
            <final_answer>
            <answer>
            Here goes your final answer.
            </answer>
            </final_answer>

            Before answering again, please stop to think and review in between <confirmation> and </confirmation> tags if you're doing it right."""}

    def reset(self):
        """Reset the conversation memory."""
        self.memory = []
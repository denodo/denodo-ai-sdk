import time
import logging

from api.deepquery.agent.prompts import GENERAL_AGENT_PROMPT, DEFAULT_POST_TOOL_PROMPT

from langchain_core.output_parsers import StrOutputParser
from api.deepquery.utils import create_langfuse_handler
from api.deepquery.agent.tool_executor import ToolExecutor
from api.deepquery.agent.prompt_builder import PromptBuilder
from api.deepquery.agent.xml_utils import parse_xml, remove_think_tags
from api.deepquery.agent.conversation_manager import ConversationManager
from api.deepquery.agent.agent_utils import get_formatted_date, generate_session_id, add_final_answer_tool

class Agent:
    """
    A flexible agent that can use tools to complete tasks through an LLM.

    This base agent maintains a conversation history, executes tools based on LLM
    responses, and handles multi-turn interactions until a final answer is reached.
    It provides placeholders for customization in derived agent classes.
    """

    def __init__(
        self,
        agent_name,
        tools,
        llm,
        system_prompt=GENERAL_AGENT_PROMPT,
        initial_prompt="",
        post_tool_prompt=DEFAULT_POST_TOOL_PROMPT,
        tool_response_mode="answer",  # "answer" or "complete"
        max_loops=20,
        start_llm=None,  # Optional LLM for first interaction only
        xml_callbacks=None,
        max_concurrent_tool_calls=5,
        keys_to_ignore=None,
    ):
        """
        Initialize the agent with tools, LLM, and configuration.

        Args:
            agent_name: Name of the agent for tracking purposes
            tools: List of callable tools the agent can use
            llm: Language model for generating responses
            system_prompt: Custom system prompt for specialized agent behavior
            initial_prompt: Prompt to add before processing the first user input
            post_tool_prompt: Prompt to add after each tool call
            tool_response_mode: How to return tool responses - "answer" for just the answer key, "complete" for the full response
            max_loops: Maximum number of interaction loops before timeout
            start_llm: Optional LLM to use only for the first interaction
            xml_callbacks: Dictionary mapping XML tag names to callback functions
            max_concurrent_tool_calls: Maximum number of tools that can be called concurrently in a single step
            keys_to_ignore: List of XML keys to ignore when processing tool calls (defaults to standard ignored keys)
        """
        # Basic configuration
        self.agent_name = agent_name
        self.llm = llm
        self.start_llm = start_llm
        self.max_loops = max_loops
        self.initial_prompt = initial_prompt
        self.max_concurrent_tool_calls = max_concurrent_tool_calls
        self.keys_to_ignore = keys_to_ignore or ["thought", "thoughts", "answer", "request_fulfilled", "tools", "justification", "think", "thinking"]

        # Set up logging
        self.logger = logging.getLogger(f"{__name__}.{agent_name}")
        self.logger.info(f"Initializing {agent_name} agent")
        self.logger.info(f"Agent parameters: max_loops={max_loops}, tool_count={len(tools)}, tool_response_mode={tool_response_mode}")
        if start_llm:
            self.logger.info("Start LLM provided - will use for first interaction only")

        # XML monitoring setup
        self.xml_callbacks = xml_callbacks or {}
        self.response_count = 0
        if self.xml_callbacks:
            self.logger.info(f"XML callbacks configured for tags: {list(self.xml_callbacks.keys())}")

        # Time and session tracking
        self.date = get_formatted_date()
        self.session_id = generate_session_id()
        self.logger.info(f"Session ID: {self.session_id}, Date: {self.date}")

        all_tools = add_final_answer_tool(tools, self.final_answer)
        self.tool_executor = ToolExecutor(all_tools, post_tool_prompt, tool_response_mode, self.max_concurrent_tool_calls, self.keys_to_ignore)
        self.conversation_manager = ConversationManager()
        self.prompt_builder = PromptBuilder(all_tools, system_prompt, self.date, self.max_concurrent_tool_calls)

        # Langfuse integration for monitoring (optional)
        self.langfuse_handler = create_langfuse_handler(
            session_id=self.session_id,
            trace_name=self.agent_name,
        )

        if self.langfuse_handler:
            self.logger.info("Langfuse monitoring enabled")
        else:
            self.logger.info("Langfuse monitoring disabled - no credentials provided")

        # Set up the prompt and chains
        self.full_system_prompt = self.prompt_builder.create_system_prompt()
        self.prompt = self.prompt_builder.create_chat_prompt(self.full_system_prompt)
        self.chain = self._create_llm_chain(self.llm)

        # Create start chain if start_llm is provided
        self.start_chain = self._create_llm_chain(self.start_llm) if self.start_llm else None

    def _create_llm_chain(self, llm):
        """Create an LLM chain with prompt and output parser for the given LLM."""
        return (
            self.prompt
            | llm
            | StrOutputParser()
        )

    async def final_answer(self, answer):
        """
        Return the final answer to end the agent loop.

        Args:
            answer: The final answer to return to the user

        Returns:
            Dict containing the final answer
        """
        return {"answer": answer}

    async def start(self, user_input):
        """
        Start the agent with the initial user input.

        This method handles the first interaction with the agent, which may
        include processing initial prompts.

        Args:
            user_input: A dict with 'text' key containing the user's input

        Returns:
            The final answer, intermediate result, or a dictionary with conversation history and tool calls
        """
        input_preview = (user_input["text"][:100] + "...") if len(user_input["text"]) > 100 else user_input["text"]

        self.logger.info(f"Starting agent execution with input: {input_preview}")

        # Reset memory and tool calls for a fresh start
        self.conversation_manager.reset()
        self.tool_executor.tool_calls = []
        self.logger.info("Reset conversation memory and tool calls")

        # Apply initial prompt if available
        if self.initial_prompt:
            enhanced_input = user_input.copy()
            enhanced_input["text"] = f"{self.initial_prompt}\n\nUser input: {enhanced_input['text']}"
            user_input = enhanced_input

        # Process the initial input with the LLM (use start_chain if available)
        chain_to_use = self.start_chain if self.start_chain else self.chain
        response = await self._get_llm_response(user_input, chain=chain_to_use)
        self.conversation_manager.update_memory(user_input, response)

        # Check if the initial response contains a final answer
        if self.conversation_manager.should_end_conversation(response):
            parsed = parse_xml(response)
            parsed_tools = parse_xml(parsed.get("tools", ""))
            if "final_answer" in parsed_tools:
                tool_id, final_answer = await self.tool_executor.execute_tool(self, "final_answer", parsed_tools["final_answer"])
                return {
                    "answer": final_answer,
                    "conversation_history": self.conversation_manager.memory,
                    "tool_calls": self.tool_executor.tool_calls,
                    "loop_count": 0
                }
            return {
                "answer": "Conversation ended due to length constraints.",
                "conversation_history": self.conversation_manager.memory,
                "tool_calls": self.tool_executor.tool_calls,
                "loop_count": 0
            }

        # Process tools from the initial response
        next_input = await self.conversation_manager.process_tools_and_prepare_next_input(
            response, self.tool_executor, self
        )

        # Continue with the regular execution loop
        return await self._execute_loop(next_input, loop_count=1)

    async def execute(self, user_input):
        """
        Execute the agent with the given input for an ongoing conversation.

        This method is used for subsequent interactions after the agent has been started.

        Args:
            user_input: A dict with 'text' key containing the user's input

        Returns:
            Dictionary with answer, conversation history, and tool calls
        """
        return await self._execute_loop(user_input, loop_count=0)

    async def _execute_loop(self, user_input, loop_count=0):
        """
        Execute the main agent loop, processing inputs and generating responses.

        Args:
            user_input: A dict with 'text' key containing the user's input
            loop_count: Current loop iteration count

        Returns:
            Dictionary with answer, conversation history, and tool calls
        """
        self.logger.info(f"Starting execution loop from iteration {loop_count}")
        loop_start_time = time.time()

        while True:
            if loop_count == 0:
                temperature = 0.5
            else:
                temperature = 0
            loop_count += 1

            self.logger.info(f"Loop iteration {loop_count}/{self.max_loops} with temperature={temperature}")

            if loop_count > self.max_loops:
                duration = time.time() - loop_start_time
                self.logger.warning(f"Agent execution timed out after {loop_count} iterations in {duration:.2f}s")
                return {
                    "answer": "TIMEOUT - TRY AGAIN",
                    "conversation_history": self.conversation_manager.memory,
                    "tool_calls": self.tool_executor.tool_calls,
                    "loop_count": loop_count
                }

            # Process input and get response from LLM
            response = await self._get_llm_response(user_input, temperature)
            self.conversation_manager.update_memory(user_input, response)

            # Check for final answer or token limit
            if self.conversation_manager.should_end_conversation(response):
                duration = time.time() - loop_start_time
                parsed = parse_xml(response)
                parsed_tools = parse_xml(parsed.get("tools", ""))
                if "final_answer" in parsed_tools:
                    self.logger.info(f"Final answer found, completing execution after {loop_count} iterations in {duration:.2f}s")
                    tool_id, final_answer = await self.tool_executor.execute_tool(self, "final_answer", parsed_tools["final_answer"])
                    self.logger.info(f"Agent execution completed successfully with {len(self.tool_executor.tool_calls)} total tool calls")
                    return {
                        "answer": final_answer,
                        "conversation_history": self.conversation_manager.memory,
                        "tool_calls": self.tool_executor.tool_calls,
                        "loop_count": loop_count
                    }
                self.logger.warning(f"Conversation ended due to length constraints after {loop_count} iterations in {duration:.2f}s")
                return {
                    "answer": "Conversation ended due to length constraints.",
                    "conversation_history": self.conversation_manager.memory,
                    "tool_calls": self.tool_executor.tool_calls,
                    "loop_count": loop_count
                }

            # Execute tools and prepare next input
            user_input = await self.conversation_manager.process_tools_and_prepare_next_input(
                response, self.tool_executor, self
            )

    async def _get_llm_response(self, user_input, temperature=0, chain=None):
        """
        Get response from the LLM based on user input.

        Args:
            user_input: A dict with 'text' key containing the user's input
            temperature: Temperature setting for the LLM
            chain: Optional chain to use instead of self.chain

        Returns:
            The LLM's response
        """
        start_time = time.time()

        input_text = user_input["text"]

        # Use provided chain or default to self.chain
        chain_to_use = chain if chain is not None else self.chain

        self.logger.info(f"Sending request to LLM with temperature={temperature}")
        try:
            config = {}
            if self.langfuse_handler:
                config["callbacks"] = [self.langfuse_handler]

            response = await chain_to_use.ainvoke(
                {"input": input_text, "chat_history": self.conversation_manager.memory},
                config=config
            )

            # Some LLMs will return their thinking in between <think> tags, which can fill up the context window quickly
            response = remove_think_tags(response)

            # NEW: XML callback processing
            self.response_count += 1
            if self.xml_callbacks:
                self._process_xml_callbacks(response)

            duration = time.time() - start_time

            # Log the LLM interaction
            self.logger.info(f"LLM response received: duration={duration:.2f}s, input_length={len(input_text)}, response_length={len(response)}, response={response[:500]}")

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"LLM request failed after {duration:.2f}s: {e}")
            raise

        return response

    def _process_xml_callbacks(self, response):
        """Process XML tags and call registered callbacks"""
        try:
            parsed_xml = parse_xml(response)
            current_tool_count = len(self.tool_executor.tool_calls)

            for tag, content in parsed_xml.items():
                if tag in self.xml_callbacks:
                    callback = self.xml_callbacks[tag]
                    try:
                        # Call callback with context information
                        callback(
                            tag=tag,
                            content=content,
                            response_count=self.response_count,
                            tool_call_count=current_tool_count
                        )
                    except Exception as callback_error:
                        self.logger.error(f"Error in XML callback for tag '{tag}': {callback_error}")

        except Exception as e:
            self.logger.error(f"Error processing XML callbacks: {e}")

    def get_tool_call(self, tool_id):
        """
        Get a specific tool call by ID.

        Args:
            tool_id: The ID of the tool call to retrieve

        Returns:
            The tool call dictionary or None if not found
        """
        return self.tool_executor.get_tool_call(tool_id)

    def get_tool_calls_by_name(self, tool_name):
        """
        Get all tool calls for a specific tool by name.

        Args:
            tool_name: The name of the tool

        Returns:
            List of tool call dictionaries
        """
        return self.tool_executor.get_tool_calls_by_name(tool_name)
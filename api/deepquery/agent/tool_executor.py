import json
import time
import hashlib
import asyncio
import logging

from datetime import datetime
from api.deepquery.agent.xml_utils import parse_xml

class ToolExecutor:
    """Handles execution of tools and tracking of tool calls."""

    def __init__(self, tools, post_tool_prompt, tool_response_mode="answer", max_concurrent_tool_calls=5, keys_to_ignore=None):
        """
        Initialize the tool executor.

        Args:
            tools: List of available tools
            post_tool_prompt: Prompt to add after tool execution
            tool_response_mode: How to return tool responses - "answer" or "complete"
            max_concurrent_tool_calls: Maximum number of tools that can be called concurrently
            keys_to_ignore: List of XML keys to ignore when processing tool calls
        """
        self.tools = tools
        self.post_tool_prompt = post_tool_prompt
        self.tool_response_mode = tool_response_mode
        self.max_concurrent_tool_calls = max_concurrent_tool_calls
        self.keys_to_ignore = keys_to_ignore or ["thought", "thoughts", "answer", "request_fulfilled", "tools", "justification", "think", "thinking"]
        self.tool_calls = []

        # Set up logging
        self.logger = logging.getLogger(f"{__name__}.ToolExecutor")
        self.logger.info(f"ToolExecutor initialized with {len(tools)} tools, mode: {tool_response_mode}, max_concurrent: {max_concurrent_tool_calls}")

    async def execute_tool(self, agent_instance, tool_name, tool_input):
        """
        Execute a tool by name with given input and track the tool call.

        Args:
            agent_instance: The agent instance for context
            tool_name: Name of the tool to execute
            tool_input: Input parameters as XML string

        Returns:
            Tuple of (tool_id, result)
        """
        start_time = time.time()
        parsed_args = parse_xml(tool_input)
        tool_map = {tool.__name__: tool for tool in self.tools}

        # Create tool ID first
        tool_id = hashlib.md5(f"{tool_name}_{datetime.now().isoformat()}".encode()).hexdigest()[:8]

        self.logger.info(f"Executing tool: {tool_name} (ID: {tool_id})")

        if tool_name in tool_map:
            try:
                # Check if this is a method of the agent instance
                if hasattr(agent_instance, tool_name) and callable(getattr(agent_instance, tool_name)):
                    # Call async method on agent
                    result = await getattr(agent_instance, tool_name)(**parsed_args)
                else:
                    # Call as async standalone function
                    result = await tool_map[tool_name](agent_instance, **parsed_args)

                duration = time.time() - start_time

                # Log successful tool execution
                self.logger.info(f"Tool execution successful: {tool_name} (ID: {tool_id}) completed in {duration:.2f}s")

                # Ensure output is always a dict
                if not isinstance(result, dict):
                    result = {"result": result}

                tool_metadata = {
                    'tool_name': tool_name,
                    'timestamp': datetime.now().isoformat(),
                    'tool_id': tool_id,
                    'input': parsed_args,
                    'output': result,
                    'error': False
                }

                # Add to tool calls history
                self.tool_calls.append(tool_metadata)

                return tool_id, result
            except Exception as e:
                duration = time.time() - start_time
                error_message = f"Error executing tool {tool_name}: {e}"

                # Log failed tool execution
                self.logger.error(f"Tool execution failed: {tool_name} (ID: {tool_id}) failed in {duration:.2f}s: {error_message}", exc_info=True)

                # Track the error call with standardized structure
                error_metadata = {
                    'tool_name': tool_name,
                    'timestamp': datetime.now().isoformat(),
                    'tool_id': tool_id,
                    'input': parsed_args,
                    'output': {"error": error_message},
                    'error': True
                }
                self.tool_calls.append(error_metadata)

                return tool_id, error_message
        else:
            self.logger.error(f"Tool '{tool_name}' not found in available tools: {list(tool_map.keys())}")

        return None, None

    async def _execute_tool_with_info(self, agent_instance, tool_info):
        """
        Execute a single tool and return tool name, input, tool_id, and result.

        Args:
            agent_instance: The agent instance for context
            tool_info: Tuple of (tool_name, tool_input)

        Returns:
            Tuple of (tool_name, tool_input, tool_id, result)
        """
        tool_name, tool_input = tool_info
        tool_input = tool_input.replace("\n", "")
        tool_id, result = await self.execute_tool(agent_instance, tool_name, tool_input)
        return tool_name, tool_input, tool_id, result

    async def parallel_execute_tools(self, agent_instance, parsed_tools):
        """
        Execute tools concurrently using asyncio and return formatted results.

        Args:
            agent_instance: The agent instance for context
            parsed_tools: Dictionary of tool names to inputs

        Returns:
            List of formatted tool results
        """
        start_time = time.time()
        self.logger.info(f"Starting concurrent execution of {len(parsed_tools)} tool groups")

        tool_results = ["## TOOL RESULTS FOR AGENT. These are the results of the tools you called:"]
        tool_executions = []

        # Prepare tool executions
        for key, value in parsed_tools.items():
            if key not in self.keys_to_ignore:
                if isinstance(value, list):
                    tool_executions.extend((key, v) for v in value)
                else:
                    tool_executions.append((key, value))

        # Apply concurrent tool call limit
        original_count = len(tool_executions)
        tools_were_limited = False
        if len(tool_executions) > self.max_concurrent_tool_calls:
            self.logger.warning(f"Tool execution count ({len(tool_executions)}) exceeds maximum limit ({self.max_concurrent_tool_calls}). Limiting to first {self.max_concurrent_tool_calls} tools.")
            tool_executions = tool_executions[:self.max_concurrent_tool_calls]
            tools_were_limited = True

        self.logger.info(f"Prepared {len(tool_executions)} individual tool executions (limit: {self.max_concurrent_tool_calls})")

        # Execute tools concurrently using asyncio.gather
        if tool_executions:
            tasks = [
                self._execute_tool_with_info(agent_instance, tool_info)
                for tool_info in tool_executions
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Tool execution failed with exception: {result}")
                    tool_results.append(f"  • Tool execution failed: {result}")
                    continue

                tool_name, tool_input, tool_id, result = result

                # Process result based on tool_response_mode
                if self.tool_response_mode == "answer" and isinstance(result, dict) and "answer" in result:
                    display_result = result["answer"]
                else:
                    display_result = result

                # Convert result to string for display
                if isinstance(display_result, (dict, list)):
                    display_result = json.dumps(display_result, indent=2)
                else:
                    display_result = str(display_result)

                display_result = display_result if display_result != "" else "No result"
                result_text = f"  • Tool {tool_name} (call ID: {tool_id}) with input: {tool_input}\n" \
                             f"  → Result: {display_result}"
                if tool_id:
                    tool_results.append(result_text)

        # Notify agent if tools were limited
        if tools_were_limited:
            limited_message = f"  • NOTE: Tool execution was limited to {self.max_concurrent_tool_calls} concurrent tools. {original_count - self.max_concurrent_tool_calls} additional tool(s) were skipped. Consider breaking down your request into smaller steps."
            tool_results.append(limited_message)

        tool_results.append(self.post_tool_prompt)

        duration = time.time() - start_time
        self.logger.info(f"Concurrent tool execution completed in {duration:.2f}s, processed {len(tool_executions)} tools")

        return tool_results

    def get_tool_call(self, tool_id):
        """
        Get a specific tool call by ID.

        Args:
            tool_id: The ID of the tool call to retrieve

        Returns:
            The tool call dictionary or None if not found
        """
        for call in self.tool_calls:
            if call.get('tool_id') == tool_id:
                return call
        return None

    def get_tool_calls_by_name(self, tool_name):
        """
        Get all tool calls for a specific tool by name.

        Args:
            tool_name: The name of the tool

        Returns:
            List of tool call dictionaries
        """
        return [call for call in self.tool_calls if call.get('tool_name') == tool_name]
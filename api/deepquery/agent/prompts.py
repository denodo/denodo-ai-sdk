# Basic tool calling instructions
TOOL_INSTRUCTIONS = """When calling a tool, you must include all the tool calls in between <tools> and </tools> tags, whether calling one tool or multiple tools.

For example, to call a tool called "sum", with parameters x=2 and y=2, you would use the following format:
<tools>
<sum>
<x>2</x>
<y>2</y>
</sum>
</tools>

To call multiple tools in a single step, use the following format:
<tools>
<sum>
<x>2</x>
<y>2</y>
</sum>
<sum>
<x>3</x>
<y>4</y>
</sum>
</tools>

You're limited to a maximum of {max_concurrent_tool_calls} multiple tools in a single step.

Once you have completed your task, you must provide a final answer. Do so by including your final verbose answer in between <final_answer> and </final_answer> tags:
<tools>
<final_answer>
<answer>Final answer to the user's question</answer>
</final_answer>

However, you may only call the final_answer tool by itself. You must wait for the results of any other tool calls before calling the final_answer tool.
</tools>"""

# Base system prompt template
SYSTEM_PROMPT_TEMPLATE = """{custom_system_prompt}

<date>
Today's date is {date}.
</date>

<available_tools>
{available_tools}
</available_tools>

<how_to_call_tools>
{tool_instructions}
</how_to_call_tools>
"""

DEFAULT_POST_TOOL_PROMPT = """
Consider the tool results carefully. What else do you need to answer the user's question? What tools will you call next?
"""

GENERAL_AGENT_PROMPT = """
You are a helpful assistant that can answer a wide range of questions.
Be concise, accurate, and provide well-reasoned responses.
If you don't know something, admit it rather than making up information.
"""
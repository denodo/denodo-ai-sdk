import re
import json
import os
import inspect
from contextlib import contextmanager
from langfuse.callback import CallbackHandler

from api.deepquery.prompts import ANALYSIS_TRACE_TEMPLATE
from api.endpoints.answerQuestion import process_question, answerQuestionRequest
from utils.version import AI_SDK_VERSION

def create_langfuse_handler(
    session_id=None,
    trace_name=None,
    langfuse_secret_key=None,
    langfuse_public_key=None,
    langfuse_host=None,
    langfuse_user=None
):
    """
    Create a langfuse callback handler with the same configuration as agents use.

    Args:
        session_id: Session ID for tracking
        trace_name: Name for the trace (defaults to calling function name)
        langfuse_secret_key: Secret key (defaults to env var)
        langfuse_public_key: Public key (defaults to env var)
        langfuse_host: Host URL (defaults to env var or cloud default)

    Returns:
        CallbackHandler instance or None if credentials not available
    """
    langfuse_secret = langfuse_secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_public = langfuse_public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_host_url = langfuse_host or os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    langfuse_user_id = langfuse_user or os.getenv("LANGFUSE_USER", "Unknown")

    if not (langfuse_secret and langfuse_public):
        return None

    # Use calling function name as trace_name if not provided
    if trace_name is None:
        frame = inspect.currentframe().f_back
        trace_name = frame.f_code.co_name if frame else "unknown"

    return CallbackHandler(
        secret_key=langfuse_secret,
        public_key=langfuse_public,
        host=langfuse_host_url,
        session_id=session_id,
        trace_name=trace_name,
        user_id=langfuse_user_id,
        release=AI_SDK_VERSION
    )

@contextmanager
def trace_context(langfuse_handler, trace_name=None):
    """Context manager to temporarily change trace name and restore it after execution.

    If trace_name is None, it will use the calling function's name.
    """
    if langfuse_handler is None:
        config = {}
        yield config
        return

    # Get the calling function's name if trace_name is not provided
    if trace_name is None:
        # Get the caller of the caller (skip the context manager's __enter__)
        frame = inspect.currentframe().f_back
        if frame.f_code.co_name == '__enter__':
            frame = frame.f_back
        trace_name = frame.f_code.co_name

    original_trace_name = getattr(langfuse_handler, 'trace_name', None)
    langfuse_handler.trace_name = trace_name
    config = {"callbacks": [langfuse_handler]}

    try:
        yield config
    finally:
        langfuse_handler.trace_name = original_trace_name

def filter_tool_calls_report_agent(tool_calls, default_rows=10):
    """
    Filter and process tool calls specifically for ReportingAgent context (system prompt and report trace).

    Args:
        tool_calls: List of tool call dictionaries
        default_rows: Number of rows used for limiting execution results

    Returns:
        List of filtered tool calls
    """
    filtered_calls = []

    for tool_call in tool_calls:
        # Step 1: Skip final_answer and errored tool calls
        if tool_call.get("tool_name") == "final_answer" or tool_call.get("error") == True:
            continue

        # Step 2: For database_agent aggregate_metric, require execution_result != {}
        if (tool_call.get("tool_name") == "database_agent" and
            tool_call.get("input", {}).get("action") == "aggregate_metric"):
            execution_result = tool_call.get("output", {}).get("execution_result", {})
            if not execution_result:
                continue

        # Create a copy for modification
        filtered_call = {
            "tool_name": tool_call.get("tool_name"),
            "tool_id": tool_call.get("tool_id"),
            "input": tool_call.get("input", {}),
            "output": tool_call.get("output", {}),
            "error": tool_call.get("error", False)
        }

        # Step 3-6: Process database_agent calls
        if tool_call.get("tool_name") == "database_agent":
            action = tool_call.get("input", {}).get("action")
            output = filtered_call["output"]

            # Step 3: For database_agent, keep only specific fields
            filtered_output = {}
            for key in ["answer", "sql_query", "query_explanation", "execution_result"]:
                if key in output:
                    filtered_output[key] = output[key]

            # Step 4: For aggregate_metric, remove answer
            if action == "aggregate_metric" and "answer" in filtered_output:
                del filtered_output["answer"]

            # Step 5: For generate_metadata_summary, remove sql_query, query_explanation, execution_result
            if action == "generate_metadata_summary":
                for key in ["sql_query", "query_explanation", "execution_result"]:
                    filtered_output.pop(key, None)

            # Step 6: Limit execution_result to DEFAULT_ROWS
            if "execution_result" in filtered_output:
                execution_result = filtered_output["execution_result"]
                if isinstance(execution_result, dict):
                    limited_result = {}
                    for i in range(1, default_rows + 1):
                        key = f"Row {i}"
                        if key in execution_result:
                            limited_result[key] = execution_result[key]
                    filtered_output["execution_result"] = limited_result

            filtered_call["output"] = filtered_output

        filtered_calls.append(filtered_call)

    return filtered_calls


def filter_tool_calls_visualization(tool_calls, default_rows=10):
    """
    Filter visualization tool calls (database_agent with generate_graph action).

    Args:
        tool_calls: List of tool call dictionaries from ReportingAgent
        default_rows: Number of rows used for limiting execution results

    Returns:
        List of filtered visualization tool calls
    """
    filtered_calls = []

    for tool_call in tool_calls:
        # Only include successful database_agent generate_graph calls
        if (tool_call.get("tool_name") == "database_agent" and
            tool_call.get("input", {}).get("action") == "generate_graph"):

            # Check if graph generation was successful (has raw_graph data)
            output = tool_call.get("output", {})
            if (not tool_call.get("error", False) and
                output.get("raw_graph", "").startswith("data:image/svg")):

                # Create filtered version with execution_result
                filtered_output = {
                    "answer": "Graph generated successfully",
                    "sql_query": tool_call.get("output", {}).get("sql_query", ""),
                    "query_explanation": tool_call.get("output", {}).get("query_explanation", "")
                }

                # Add execution_result with row limiting
                execution_result = output.get("execution_result", {})
                if execution_result and isinstance(execution_result, dict):
                    limited_result = {}
                    for i in range(1, default_rows + 1):
                        key = f"Row {i}"
                        if key in execution_result:
                            limited_result[key] = execution_result[key]
                    filtered_output["execution_result"] = limited_result

                filtered_call = {
                    "tool_name": tool_call.get("tool_name"),
                    "tool_id": tool_call.get("tool_id"),
                    "input": tool_call.get("input", {}),
                    "output": filtered_output,
                    "error": False
                }

                filtered_calls.append(filtered_call)

    return filtered_calls

def filter_tool_calls_appendix(analysis_tool_calls, visualization_tool_calls, include_failed_tool_calls=False):
    """
    Filter tool calls for appendix generation with specific field filtering rules.

    Args:
        analysis_tool_calls: List of tool calls from AnalysisAgent
        visualization_tool_calls: List of tool calls from ReportingAgent
        include_failed_tool_calls: Whether to include failed tool calls

    Returns:
        List of filtered tool calls for appendix
    """
    all_tool_calls = []

    # Combine analysis and visualization tool calls
    combined_calls = analysis_tool_calls + visualization_tool_calls

    for tool_call in combined_calls:
        # 1. Exclude final_answer tool calls
        if tool_call.get("tool_name") == "final_answer":
            continue

        # 2. Apply failure filtering if include_failed_tool_calls is False
        if not include_failed_tool_calls:
            # Skip failed generate_graph calls
            if (tool_call.get("tool_name") == "database_agent" and
                tool_call.get("input", {}).get("action") == "generate_graph"):
                # Check if graph generation failed (no raw_graph or error)
                output = tool_call.get("output", {})
                if (tool_call.get("error", False) or
                    not output.get("raw_graph", "").startswith("data:image/svg")):
                    continue

            # Skip aggregate_metric calls with empty execution_result
            if (tool_call.get("tool_name") == "database_agent" and
                tool_call.get("input", {}).get("action") == "aggregate_metric"):
                execution_result = tool_call.get("output", {}).get("execution_result", {})
                if not execution_result or execution_result == {}:
                    continue

        # 3. Create filtered tool call (exclude timestamp, keep tool_id, tool_name, input, output)
        filtered_call = {
            "tool_name": tool_call.get("tool_name"),
            "tool_id": tool_call.get("tool_id"),
            "input": tool_call.get("input", {}),  # Keep input (renamed from args)
            "output": {},
            "error": tool_call.get("error", False)
        }

        # 4. Apply specific field filtering based on tool type
        if tool_call.get("tool_name") == "database_agent":
            action = tool_call.get("input", {}).get("action")
            original_output = tool_call.get("output", {})

            if action == "generate_graph":
                # For generate_graph: sql_query, execution_result, query_explanation, graph
                filtered_call["output"] = {
                    key: original_output.get(key, "")
                    for key in ["sql_query", "execution_result", "query_explanation", "raw_graph"]
                    if key in original_output
                }

            elif action == "aggregate_metric":
                # For aggregate_metric: sql_query, execution_result, query_explanation
                filtered_call["output"] = {
                    key: original_output.get(key, "")
                    for key in ["sql_query", "execution_result", "query_explanation"]
                    if key in original_output
                }

            elif action == "generate_metadata_summary":
                # For generate_metadata_summary: answer only
                filtered_call["output"] = {
                    "answer": original_output.get("answer", "")
                }

            else:
                # For other database_agent actions, keep all output
                filtered_call["output"] = original_output

            # Apply execution_result limiting for database_agent tools
            if "execution_result" in filtered_call["output"]:
                execution_result = filtered_call["output"]["execution_result"]
                if isinstance(execution_result, dict):
                    # Count actual data rows (exclude metadata)
                    row_keys = [k for k in execution_result.keys() if k.startswith("Row ")]
                    if len(row_keys) > 10:  # Use 10 as default for appendix
                        # Limit to 10 rows for appendix
                        limited_result = {}
                        for i in range(1, 11):
                            row_key = f"Row {i}"
                            if row_key in execution_result:
                                limited_result[row_key] = execution_result[row_key]
                        filtered_call["output"]["execution_result"] = limited_result
                        filtered_call["output"]["execution_result_note"] = "(Limited to 10 rows)"
                    elif len(row_keys) > 0:
                        filtered_call["output"]["execution_result_note"] = f"({len(row_keys)} row{'s' if len(row_keys) != 1 else ''})"
        else:
            # For non-database_agent tools, keep all output fields
            filtered_call["output"] = tool_call.get("output", {})

        all_tool_calls.append(filtered_call)

    return all_tool_calls

def format_tool_calls_for_prompt(tool_calls):
    """
    Format filtered tool calls into a pretty-printed string for system prompts.

    Args:
        tool_calls: List of filtered tool call dictionaries

    Returns:
        Formatted string representation
    """
    if not tool_calls:
        return "No tool calls available."

    formatted_lines = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("tool_name", "unknown")
        tool_id = tool_call.get("tool_id", "unknown")
        tool_input = tool_call.get("input", {})
        tool_output = tool_call.get("output", {})

        formatted_lines.append("<tool_call>")
        formatted_lines.append(f"- {tool_name} (#{tool_id})")

        # Format Input
        formatted_lines.append("- Input")
        if tool_input:
            for key, value in tool_input.items():
                formatted_lines.append(f"    - {key}: {value}")
        else:
            formatted_lines.append("    - (no input parameters)")

        # Format Output
        formatted_lines.append("- Output")

        if tool_name == "database_agent" and tool_input.get("action") == "aggregate_metric":
            # Special formatting for database_agent aggregate_metric
            if "execution_result" in tool_output:
                note = tool_output.get("execution_result_note", "")
                formatted_lines.append(f"    - Execution Result {note}:")
                # Print the limited execution result data
                execution_result = tool_output.get("execution_result", {})
                if execution_result:
                    for row_key, row_data in execution_result.items():
                        if row_key.startswith("Row "):
                            formatted_lines.append(f"        {row_key}: {row_data}")
            if "sql_query" in tool_output:
                formatted_lines.append(f"    - SQL Query: {tool_output['sql_query']}")
            if "query_explanation" in tool_output:
                formatted_lines.append(f"    - Query Explanation: {tool_output['query_explanation']}")
        else:
            # Standard formatting for other tools
            if tool_output:
                for key, value in tool_output.items():
                    if key == "execution_result_note":
                        continue  # Skip the note, it's included above
                    formatted_lines.append(f"    - {key.capitalize()}: {value}")
            else:
                formatted_lines.append("    - (no output)")

        formatted_lines.append("</tool_call>")
        formatted_lines.append("")  # Empty line between tool calls

    return "\n".join(formatted_lines)

def prepare_visualization_analysis_trace(plan, cohorts, tool_calls, answer, default_rows=10):
    """
    Transform analysis components with specially filtered and formatted tool calls for visualization.

    Args:
        plan: The original analysis plan
        cohorts: List of cohorts created during analysis
        tool_calls: List of tool calls made during analysis
        answer: The final analysis report
        default_rows: Number of rows for limiting execution results

    Returns:
        str: Formatted string with escaped curly braces
    """
    # Filter and format tool calls specifically for visualization
    filtered_calls = filter_tool_calls_report_agent(tool_calls, default_rows)
    formatted_tool_calls = format_tool_calls_for_prompt(filtered_calls)

    trace = ANALYSIS_TRACE_TEMPLATE.format(
        plan=str(plan),
        cohorts=str(cohorts),
        tool_calls=formatted_tool_calls,
        answer=str(answer)
    )
    trace = trace.replace("{", "{{")
    trace = trace.replace("}", "}}")
    return trace

def prepare_sequential_report_trace(plan, cohorts, analysis_tool_calls, visualization_tool_calls, answer, default_rows=10):
    """
    Transform analysis components with combined analysis and visualization tool calls for sequential report.

    Args:
        plan: The original analysis plan
        cohorts: List of cohorts created during analysis
        analysis_tool_calls: List of tool calls from analysis phase
        visualization_tool_calls: List of tool calls from visualization generation
        answer: The final analysis report
        default_rows: Number of rows for limiting execution results

    Returns:
        str: Formatted string with escaped curly braces
    """
    # Filter analysis tool calls using the same logic as ReportingAgent
    filtered_analysis_calls = filter_tool_calls_report_agent(analysis_tool_calls, default_rows)

    # Filter visualization tool calls
    filtered_viz_calls = filter_tool_calls_visualization(visualization_tool_calls, default_rows)

    # Combine both sets of tool calls
    combined_tool_calls = filtered_analysis_calls + filtered_viz_calls

    # Format the combined tool calls
    formatted_tool_calls = format_tool_calls_for_prompt(combined_tool_calls)

    trace = ANALYSIS_TRACE_TEMPLATE.format(
        plan=str(plan),
        cohorts=str(cohorts),
        tool_calls=formatted_tool_calls,
        answer=str(answer)
    )
    trace = trace.replace("{", "{{")
    trace = trace.replace("}", "}}")
    return trace

def prepare_tool_calls_only_trace(analysis_tool_calls, visualization_tool_calls, default_rows=10):
    """
    Prepare a trace containing only the formatted tool calls.

    Args:
        analysis_tool_calls: List of tool calls from analysis phase
        visualization_tool_calls: List of tool calls from visualization generation
        default_rows: Number of rows for limiting execution results

    Returns:
        str: Formatted tool calls only
    """
    # Filter analysis tool calls using the same logic as ReportingAgent
    filtered_analysis_calls = filter_tool_calls_report_agent(analysis_tool_calls, default_rows)

    # Filter visualization tool calls
    filtered_viz_calls = filter_tool_calls_visualization(visualization_tool_calls, default_rows)

    # Combine both sets of tool calls
    combined_tool_calls = filtered_analysis_calls + filtered_viz_calls

    # Format the combined tool calls
    formatted_tool_calls = format_tool_calls_for_prompt(combined_tool_calls)

    return formatted_tool_calls

async def execute_base_database_query(
    action: str,
    action_description: str,
    cohorts: list,
    auth,
    mode: str = "data",
    verbose: bool = False,
    plot: bool = False,
    plot_details: str = "",
    disclaimer: bool = False
):
    """
    Base function for executing database queries through the database agent.

    Handles common functionality:
    - XML-style cohort tag processing (<cohort>name</cohort>)
    - Question construction
    - Request creation and execution
    - Response extraction and JSON parsing

    Args:
        action: The action to perform
        action_description: Description of the action
        cohorts: List of cohort dictionaries with 'name' and 'description' keys
        auth: Authentication token
        mode: Query mode ("data" or "metadata")
        verbose: Whether to use verbose mode
        plot: Whether to generate plots
        plot_details: Details for plot generation
        disclaimer: Whether to include disclaimer

    Returns:
        Dict containing the parsed JSON response
    """
    # Handle XML-style cohort tags
    cohort_pattern = r'<cohort>(.*?)</cohort>'
    cohort_matches = re.findall(cohort_pattern, action_description)

    if cohort_matches:
        for cohort_name in cohort_matches:
            # Find cohort object by name
            cohort_obj = next((co for co in cohorts if co["name"] == cohort_name), None)

            if cohort_obj:
                # Replace the XML-style tag with cohort info
                tag_to_replace = f'<cohort>{cohort_name}</cohort>'
                replacement = f'{cohort_obj["name"]}: ({cohort_obj["description"]})'
                action_description = action_description.replace(tag_to_replace, replacement)
            else:
                return {
                    "status": "error",
                    "answer": f"Cohort '{cohort_name}' not found."
                }

    # Construct the question for the database agent
    question = f"{action}: {action_description}"

    # Create request object for answerQuestion
    request = answerQuestionRequest(
        question=question,
        verbose=verbose,
        plot=plot,
        plot_details=plot_details,
        mode=mode,
        disclaimer=disclaimer,
    )

    # Call the endpoint function directly
    response = await process_question(request, auth)

    # Extract the JSON content from the JSONResponse
    response_data = response.body.decode('utf-8')
    json_response = json.loads(response_data)

    return json_response
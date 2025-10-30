import os
import sys
import requests
import traceback

from fastmcp import FastMCP

mcp = FastMCP("Denodo_AI_SDK_MCP")

AI_SDK_ENDPOINT = os.getenv("MCP_AI_SDK_ENDPOINT", "http://localhost:8008").rstrip('/')
AI_SDK_AUTH = os.getenv("MCP_AI_SDK_AUTH")
AI_SDK_VERIFY_SSL = os.getenv("MCP_AI_SDK_VERIFY_SSL", "false").lower() == "true"

if not AI_SDK_AUTH:
    raise ValueError("MCP_AI_SDK_AUTH environment variable is required")

try:
    health_response = requests.get(
        f"{AI_SDK_ENDPOINT}/health",
        timeout=10.0,
        verify=AI_SDK_VERIFY_SSL
    )
    health_response.raise_for_status()
except Exception as e:
    raise ConnectionError(f"Failed to connect to AI SDK endpoint at {AI_SDK_ENDPOINT}/health: {str(e)}") from e

@mcp.tool()
def ask_database(question: str, mode: str = "data"):
    """Query the user's database in natural language.

    Accepts a mode parameter to specify the mode to use for the query:
    - data: Query the data in the database. For example, 'how many new customers did we get last month?'
    - metadata: Query the metadata in the database. For example, 'what is the type of the column 'customer_id' in the customers table?'

    Args:
        question: Natural language question (e.g. "how many new customers did we get last month?")
        mode: The mode to use for the query. Can be "data" or "metadata".
    """
    params = {
        "question": question,
        "mode": mode,
        "verbose": False
    }

    headers = {}
    if AI_SDK_AUTH:
        headers["Authorization"] = AI_SDK_AUTH

    try:
        response = requests.post(
            f"{AI_SDK_ENDPOINT}/answerQuestion",
            json=params,
            headers=headers,
            timeout=120.0,
            verify=AI_SDK_VERIFY_SSL
        )
        response.raise_for_status()
        data = response.json()
        if mode == "data":
            return data.get('execution_result', 'The AI SDK did not return a result.')
        else:
            return data.get('answer', 'The AI SDK did not return a result.')
    except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return f"Error fetching response: {str(e)}"
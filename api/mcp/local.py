import os
import requests

from fastmcp import FastMCP
from utils import denodo_tools
from utils.denodo_tools import format_data_query_output_mcp, format_metadata_query_output_mcp

mcp = FastMCP("Denodo_AI_SDK_MCP")

AI_SDK_AUTH = os.getenv("MCP_AI_SDK_AUTH")
AI_SDK_ENDPOINT = os.getenv("MCP_AI_SDK_ENDPOINT", "http://localhost:8008").rstrip('/')
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
def data_query(
    question: str,
):
    """Query the user's database in Denodo in natural language to retrieve data. For example,
    you can use this tool to answer questions like "how many new customers did we get last month?"

    Args:
        question: Natural language question (e.g. "how many new customers did we get last month?")
    """
    response = denodo_tools.data_query(
        natural_language_query=question,
        api_host=AI_SDK_ENDPOINT,
        auth=AI_SDK_AUTH,
        verify_ssl=AI_SDK_VERIFY_SSL,
    )

    return format_data_query_output_mcp(response)

@mcp.tool()
def metadata_query(
    search_query: str,
    n_results: int = 5,
):
    """Perform a similarity search in the user's database in Denodo and return the schema of the most similar tables.
    For example, it can be helpful to answer metadata questions like:
    - What tables do we have related to X topic.
    - What is the primary key of this table.
    - What associations does this table have.

    Args:
        search_query: Natural language query to search for the metadata of the tables. For example, 'tables related to loans'.
        n_results: Maximum number of results to return.
    """
    response = denodo_tools.metadata_query(
        search_query=search_query,
        api_host=AI_SDK_ENDPOINT,
        auth=AI_SDK_AUTH,
        n_results=n_results,
        verify_ssl=AI_SDK_VERIFY_SSL,
    )

    return format_metadata_query_output_mcp(response)
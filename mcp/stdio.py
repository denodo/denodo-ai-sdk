import os
import sys
import httpx
import traceback

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("denodo_aisdk")

AI_SDK_ENDPOINT = os.getenv("MCP_AI_SDK_ENDPOINT", "http://localhost:8008").rstrip('/')
AI_SDK_USER = os.getenv("MCP_AI_SDK_USER", "admin")
AI_SDK_PASSWORD = os.getenv("MCP_AI_SDK_PASSWORD", "admin")
AI_SDK_VERIFY_SSL = os.getenv("MCP_AI_SDK_VERIFY_SSL", "false").lower() == "true"

@mcp.tool()
async def ask_database(question: str, mode: str = "data") -> str:
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
        "verbose": False,
        "markdown_response": True
    }

    try:
        async with httpx.AsyncClient(verify=AI_SDK_VERIFY_SSL) as client:
            response = await client.post(f"{AI_SDK_ENDPOINT}/answerQuestion", json=params, auth=(AI_SDK_USER, AI_SDK_PASSWORD), timeout=120.0)
            response.raise_for_status()
            data = response.json()
            if mode == "data":
                return data.get('execution_result', 'The AI SDK did not return a result.')
            else:
                return data.get('answer', 'The AI SDK did not return a result.')
    except Exception as e:
            traceback.print_exc(file=sys.stderr) 
            return f"Error fetching response: {str(e)}"

if __name__ == "__main__":
    print("Starting the Denodo AI SDK MCP server in STDIO mode...")
    mcp.run(transport="stdio")
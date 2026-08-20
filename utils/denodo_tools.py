import base64
import asyncio
import logging
import httpx
import requests
import traceback

from utils.execution_result_helpers import (
    get_full_execution_result_rows,
)
from utils.schema_catalog import SchemaCatalog, VQL_SCHEMA_GRAMMAR

def create_basic_auth_header(username, password):
    """Create a Basic Authorization header value from username and password."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"

class AISDKRequestCancelled(Exception):
    """Raised when an in-flight AI SDK request is cancelled by the user."""

async def _cancellable_request(method, endpoint, payload, headers, verify_ssl, timeout, cancel_event):
    """Run the AI SDK request as an asyncio task, polling the cancel event.

    Cancelling the task closes the underlying connection, which lets the AI SDK's
    RequestCancelledMiddleware cancel the request server-side too.
    """
    async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout) as client:
        if method == "GET":
            request_task = asyncio.create_task(client.get(endpoint, params=payload, headers=headers))
        else:
            request_task = asyncio.create_task(client.post(endpoint, json=payload, headers=headers))

        while True:
            done, _ = await asyncio.wait({request_task}, timeout=0.25)
            if done:
                return request_task.result()
            if cancel_event.is_set():
                request_task.cancel()
                raise AISDKRequestCancelled(f"AI SDK request to {endpoint} cancelled by the user.")

def make_ai_sdk_request(endpoint, payload, auth, method="POST", verify_ssl=False, timeout=1200, cancel_event=None):
    """Helper function to make AI SDK requests with standardized error handling.

    Args:
        endpoint: The API endpoint URL
        payload: Request body (POST) or params (GET)
        auth: Authorization header value (e.g., "Basic xyz..." or "Bearer xyz...")
        method: HTTP method (POST or GET)
        verify_ssl: Whether to verify SSL certificates
        timeout: Request timeout in seconds
        cancel_event: Optional threading.Event; when set, the in-flight request is
            aborted (closing the connection) and AISDKRequestCancelled is raised
    """
    headers = {"Authorization": auth}

    try:
        if cancel_event is not None:
            response = asyncio.run(_cancellable_request(method, endpoint, payload, headers, verify_ssl, timeout, cancel_event))
        elif method == "GET":
            response = requests.get(
                endpoint,
                params=payload,
                headers=headers,
                verify=verify_ssl,
                timeout=timeout
            )
        else:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                verify=verify_ssl,
                timeout=timeout
            )
        response.raise_for_status()
        return response.json()
    except AISDKRequestCancelled:
        raise
    except (requests.HTTPError, httpx.HTTPStatusError) as e:
        logging.error(f"Error making AI SDK request: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        try:
            error_data = e.response.json()
            detail = error_data.get('detail')
            return {
                "error": f"An error occurred when connecting to the AI SDK: {detail}",
                "traceback": traceback.format_exc()
            }
        except Exception as e:
            return {
                "error": f"An error occurred when connecting to the AI SDK: {e}",
                "traceback": traceback.format_exc()
            }
    except Exception as e:
        logging.error(f"Error making AI SDK request: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return {
            "error": f"An error occurred when connecting to the AI SDK: {e}",
            "traceback": traceback.format_exc()
        }

def deep_query(
    analysis_request,
    api_host,
    auth,
    verify_ssl=False,
    vdp_database_names=None,
    vdp_tag_names=None,
    allow_external_associations=True,
    timeout=1200,
    cancel_event=None,
    **llm_params
):
    request_body = {
        'question': analysis_request,
        'allow_external_associations': allow_external_associations
    }

    if vdp_database_names:
        request_body['vdp_database_names'] = vdp_database_names
    if vdp_tag_names:
        request_body['vdp_tag_names'] = vdp_tag_names

    request_body.update(llm_params)

    endpoint = f'{api_host}/deepQuery'
    response = make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

    return response

def metadata_search(
    search_query,
    api_host,
    auth,
    vdp_database_names=None,
    vdp_tag_names=None,
    n_results=5,
    verify_ssl=False,
    timeout=1200,
    cancel_event=None,
):
    request_body = {
        'question': search_query,
        'mode': 'metadata',
        'verbose': False,
        'vector_search_k': n_results,
    }

    if vdp_database_names:
        request_body['vdp_database_names'] = vdp_database_names
    if vdp_tag_names:
        request_body['vdp_tag_names'] = vdp_tag_names

    endpoint = f'{api_host}/answerQuestion'
    response = make_ai_sdk_request(endpoint, request_body, auth, "GET", verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

    return response

def data_agent(
    natural_language_query,
    api_host,
    auth,
    vdp_database_names=None,
    vdp_tag_names=None,
    allow_external_associations=True,
    plot=0,
    plot_details='',
    limit=None,
    custom_instructions='',
    verify_ssl=False,
    timeout=1200,
    cancel_event=None,
    **llm_params
):
    request_body = {
        'question': natural_language_query,
        'mode': 'data',
        'verbose': False,
        'disclaimer': False,
        'plot': bool(int(plot)),
        'plot_details': plot_details,
        'custom_instructions': custom_instructions,
        'allow_external_associations': allow_external_associations,
    }

    if vdp_database_names:
        request_body['vdp_database_names'] = vdp_database_names
    if vdp_tag_names:
        request_body['vdp_tag_names'] = vdp_tag_names

    request_body.update(llm_params)

    if limit not in (None, ''):
        request_body['vql_execute_rows_limit'] = int(limit)

    endpoint = f'{api_host}/answerQuestion'
    response = make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

    return response

def _build_error_data_agent_output(response):
    content = f"Data query failed: {response.get('error', 'Unknown error')}"
    return (content, response)

def _build_empty_data_agent_content(response):
    content = f"""Response: {response.get("answer", "No answer was provided.")}"""

    sql_query = response.get("sql_query", "")
    if sql_query:
        content += f"\nSQL query: {sql_query}"

    query_explanation = response.get("query_explanation", "")
    if query_explanation:
        content += f"\nQuery explanation: {query_explanation}"

    return content

def _get_execution_result_views(response):
    execution_result = response.get("execution_result", {})
    full_rows = get_full_execution_result_rows(execution_result)
    llm_rows = execution_result.get("llm", {})
    full_csv = execution_result.get("full_csv", "")
    llm_csv = execution_result.get("llm_csv", "")

    return {
        "full_rows": full_rows,
        "llm_rows": llm_rows,
        "full_csv": full_csv,
        "llm_csv": llm_csv,
    }

def _build_success_data_agent_content(response):
    execution_result_views = _get_execution_result_views(response)
    full_rows = execution_result_views["full_rows"]
    llm_rows = execution_result_views["llm_rows"]
    full_csv = execution_result_views["full_csv"]
    llm_csv = execution_result_views["llm_csv"]
    row_count = len(full_rows)

    truncation_note = ""
    if full_csv and llm_csv and full_csv != llm_csv:
        truncation_note = f"""NOTE: Only the first {len(llm_rows)} row{'s' if len(llm_rows) != 1 else ''} were included here out of a total of {row_count} rows returned.
This limit is set to avoid LLM context saturation."""

    return f"""Execution result returned {row_count} row{'s' if row_count != 1 else ''}.
{truncation_note}

<execution_result_csv>
{llm_csv}
</execution_result_csv>
<sql_query>
{response.get("sql_query", "No SQL query was generated.")}
</sql_query>
<query_explanation>
{response.get("query_explanation", "No query explanation was provided.")}
</query_explanation>"""

def _append_graph_output(content, response):
    raw_graph = response.get("raw_graph", "")
    if not raw_graph:
        return content

    if raw_graph.startswith("data:image/svg+xml;base64,"):
        return content + "\n\nPlot generated successfully and added to the UI."

    return content + f"\n\nGraph generation failed. Error: {raw_graph}"

def _build_data_agent_artifact(response):
    tokens = response.get("tokens", {}) or {}
    return {
        "vql": response.get("sql_query", ""),
        "execution_result": response.get("execution_result", {}),
        "raw_graph": response.get("raw_graph", ""),
        "tables_used": response.get("tables_used", []),
        "query_explanation": response.get("query_explanation", ""),
        "tokens": tokens.get("total_tokens", 0),
        "total_tokens": tokens.get("total_tokens", 0),
        "input_tokens": tokens.get("input_tokens", 0),
        "output_tokens": tokens.get("output_tokens", 0),
        "ai_sdk_time": response.get("total_execution_time", 0),
        "total_execution_time": response.get("total_execution_time", 0),
        "vector_store_search_time": response.get("vector_store_search_time", 0),
        "llm_time": response.get("llm_time", 0),
        "sql_execution_time": response.get("sql_execution_time", 0),
        "llm_provider": response.get("llm_provider", ""),
        "llm_model": response.get("llm_model", ""),
    }

def format_data_agent_output(response, include_graph=True):
    # CASE 1: No schema found/endpoint error => returns 'Data query failed' message
    if 'error' in response:
        return _build_error_data_agent_output(response)

    # CASE 2: Ambiguity detected => returns answer with the ambiguity message
    # CASE 3: Empty execution result => returns answer with the empty execution result message + sql_query + query_explanation
    if not response.get("sql_query") or not response.get("execution_result"):
        content = _build_empty_data_agent_content(response)
    else:
        # CASE 4: All ok => returns sql_query + execution_result + query_explanation
        content = _build_success_data_agent_content(response)

    # Graph output is only relevant for UI clients (chatbot), not for MCP
    if include_graph:
        content = _append_graph_output(content, response)

    artifact = _build_data_agent_artifact(response)
    return (content, artifact)

def format_metadata_search_output(response):
    if 'error' in response:
        content = f"Metadata search failed: {response.get('error', 'Unknown error')}"
        artifact = response
        return (content, artifact)

    related_tables = [
        entry for entry in response.get('related_tables', [])
        if entry.get('vql_representation')
    ]
    response_dump = SchemaCatalog.from_vector_search_tables(related_tables).render_vql_schema()

    content = f"""A similarity search for the provided search_query was correctly executed across the user's views in Denodo. Remember this tool does not perform exhaustive searches.
        When answering the user's question take this into account so as to not mislead the user.
        If the user is looking for exhaustive searches (not similarity search), point them to the Denodo Data Marketplace.

        <output>
        {response_dump}
        </output>

        The schema definition of the views in the results comes in an optimized textual format to reduce token usage. It follows this grammar:

        <schema_definition>
        {VQL_SCHEMA_GRAMMAR}
        </schema_definition>

        This means that if a view contains fields and none of those are marked as [PK], then that view does not have a defined primary key in the schema's definition.
        Or if a field does not contain [NOT NULL], then technically that field is defined as nullable.
        This is important because if the user is technical he might want to know the exact schema definition behind a view."""
    artifact = response
    return (content, artifact)

def format_data_agent_output_mcp(response):
    content, _ = format_data_agent_output(response, include_graph=False)
    return content

def format_metadata_search_output_mcp(response):
    content, _ = format_metadata_search_output(response)
    return content

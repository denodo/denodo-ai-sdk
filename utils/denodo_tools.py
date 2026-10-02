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
            detail = error_data.get('detail', error_data)
            if isinstance(detail, dict):
                detail = detail.get('error') or detail.get('message') or str(detail)
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
    allow_external_associations=False,
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

def generate_vql(
    natural_language_query,
    api_host,
    auth,
    vdp_database_names=None,
    vdp_tag_names=None,
    allow_external_associations=False,
    limit=None,
    custom_instructions='',
    view_names=None,
    auto_fixing=True,
    auto_fixing_attempts=None,
    check_ambiguity=None,
    verify_ssl=False,
    timeout=1200,
    cancel_event=None,
    **llm_params
):
    request_body = {
        'custom_instructions': custom_instructions,
        'allow_external_associations': allow_external_associations,
    }

    if vdp_database_names:
        request_body['vdp_database_names'] = vdp_database_names
    if vdp_tag_names:
        request_body['vdp_tag_names'] = vdp_tag_names

    llm_params.pop("filter_logic", None)
    request_body.update(llm_params)

    # Set after the update so llm_params can never override the explicit arguments.
    request_body['request'] = natural_language_query
    request_body['auto_fixing'] = auto_fixing
    request_body['view_names'] = view_names or []
    if auto_fixing_attempts is not None:
        request_body['auto_fixing_attempts'] = int(auto_fixing_attempts)
    if check_ambiguity is not None:
        request_body['check_ambiguity'] = check_ambiguity
    if limit not in (None, ''):
        request_body['vql_execute_rows_limit'] = int(limit)

    endpoint = f'{api_host}/generateVQL'
    return make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

def execute_vql(
    vql,
    api_host,
    auth,
    limit=None,
    verify_ssl=False,
    timeout=1200,
    cancel_event=None,
):
    request_body = {'vql': vql}
    if limit not in (None, ''):
        request_body['limit'] = int(limit)

    endpoint = f'{api_host}/executeVQL'
    return make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

def generate_graph(
    vql,
    api_host,
    auth,
    plot_details='',
    limit=None,
    verify_ssl=False,
    timeout=1200,
    cancel_event=None,
    **llm_params
):
    request_body = {
        'vql': vql,
        'plot_details': plot_details,
    }
    if limit not in (None, ''):
        request_body['limit'] = int(limit)

    request_body.update(llm_params)

    endpoint = f'{api_host}/generateGraph'
    return make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl, timeout=timeout, cancel_event=cancel_event)

def _response_vql(response):
    return response.get("vql") or response.get("sql_query", "")

def _build_error_data_agent_output(response):
    content = f"Data query failed: {response.get('error', 'Unknown error')}"
    return (content, response)

def _build_empty_data_agent_content(response):
    content = f"""Response: {response.get("answer", "No answer was provided.")}"""

    vql = _response_vql(response)
    if vql:
        content += "\n" + _wrap_tagged_block("vql_query", vql)

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

def _wrap_tagged_block(tag, content):
    return f"<{tag}>\n{str(content).rstrip()}\n</{tag}>"

def _build_success_data_agent_content(response, include_query_explanation=True):
    execution_result_views = _get_execution_result_views(response)
    full_rows = execution_result_views["full_rows"]
    llm_rows = execution_result_views["llm_rows"]
    llm_csv = execution_result_views["llm_csv"]
    row_count = len(full_rows)

    header = f"Execution result returned {row_count} row{'s' if row_count != 1 else ''}."
    if llm_csv and len(llm_rows) < row_count:
        header += f"""\nNOTE: Only the first {len(llm_rows)} row{'s' if len(llm_rows) != 1 else ''} were included here out of a total of {row_count} rows returned.
This limit is set to avoid LLM context saturation."""

    if response.get("is_masked", False):
        header += "\nNOTE: The data in this execution result contains masked or redacted values due to security policies."

    tagged_blocks = [
        _wrap_tagged_block("execution_result_csv", llm_csv),
        _wrap_tagged_block("vql_query", _response_vql(response) or "No VQL query was generated."),
    ]
    if include_query_explanation:
        tagged_blocks.append(
            _wrap_tagged_block("query_explanation", response.get("query_explanation") or "No query explanation was provided.")
        )
    return f"{header}\n\n" + "\n\n".join(tagged_blocks)

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
        "vql": _response_vql(response),
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
        "is_masked": response.get("is_masked", False),
    }

def format_data_agent_output(response, include_graph=True):
    # CASE 1: No schema found/endpoint error => returns 'Data query failed' message
    if 'error' in response:
        return _build_error_data_agent_output(response)

    # CASE 2: Ambiguity detected => returns answer with the ambiguity message
    # CASE 3: Empty execution result => returns answer with the empty execution result message + vql_query + query_explanation
    if not _response_vql(response) or not response.get("execution_result"):
        content = _build_empty_data_agent_content(response)
    else:
        # CASE 4: All ok => returns vql_query + execution_result + query_explanation
        content = _build_success_data_agent_content(response)

    # Graph output is only relevant for UI clients (chatbot), not for MCP
    if include_graph:
        content = _append_graph_output(content, response)

    artifact = _build_data_agent_artifact(response)
    return (content, artifact)

def format_generate_vql_output(response):
    return format_data_agent_output(response, include_graph=False)

def format_execute_vql_output(response):
    if 'error' in response:
        return (f"VQL execution failed: {response.get('error', 'Unknown error')}", response)

    if not response.get("execution_result"):
        content = "The VQL executed correctly but returned no rows.\n\n" + _wrap_tagged_block(
            "vql_query",
            _response_vql(response) or "No VQL was provided.",
        )
    else:
        execution_result_views = _get_execution_result_views(response)
        full_rows = execution_result_views["full_rows"]
        llm_rows = execution_result_views["llm_rows"]
        full_csv = execution_result_views["full_csv"]
        llm_csv = execution_result_views["llm_csv"]
        row_count = len(full_rows)

        header = f"Execution result returned {row_count} row{'s' if row_count != 1 else ''}."
        if full_csv and llm_csv and full_csv != llm_csv:
            header += (
                f"\nNOTE: Only the first {len(llm_rows)} row{'s' if len(llm_rows) != 1 else ''} "
                f"were included here out of a total of {row_count} rows returned.\n"
                "This limit is set to avoid LLM context saturation."
            )

        if response.get("is_masked", False):
            header += "\nNOTE: The data in this execution result contains masked or redacted values due to security policies."

        tagged_blocks = [
            _wrap_tagged_block("execution_result_csv", llm_csv),
            _wrap_tagged_block("vql_query", _response_vql(response) or "No VQL was provided."),
        ]
        content = f"{header}\n\n" + "\n\n".join(tagged_blocks)

    artifact = _build_data_agent_artifact(response)
    return (content, artifact)

def format_generate_graph_output(response):
    if 'error' in response:
        return (f"Graph generation failed: {response.get('error', 'Unknown error')}", response)

    if not response.get("execution_result"):
        content = f"""The VQL executed correctly but returned no rows, so no graph could be generated.
<vql_query>
{_response_vql(response) or "No VQL was provided."}
</vql_query>"""
    else:
        content = _build_success_data_agent_content(response, include_query_explanation=False)

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

def format_generate_vql_output_mcp(response):
    content, _ = format_generate_vql_output(response)
    return content

def format_execute_vql_output_mcp(response):
    content, _ = format_execute_vql_output(response)
    return content

def format_metadata_search_output_mcp(response):
    content, _ = format_metadata_search_output(response)
    return content

import base64
import logging
import requests
import traceback

def create_basic_auth_header(username, password):
    """Create a Basic Authorization header value from username and password."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"

def make_ai_sdk_request(endpoint, payload, auth, method="POST", verify_ssl=False):
    """Helper function to make AI SDK requests with standardized error handling.

    Args:
        endpoint: The API endpoint URL
        payload: Request body (POST) or params (GET)
        auth: Authorization header value (e.g., "Basic xyz..." or "Bearer xyz...")
        method: HTTP method (POST or GET)
        verify_ssl: Whether to verify SSL certificates
    """
    headers = {"Authorization": auth}

    try:
        if method == "GET":
            response = requests.get(
                endpoint,
                params=payload,
                headers=headers,
                verify=verify_ssl,
                timeout=1200
            )
        else:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                verify=verify_ssl,
                timeout=1200
            )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
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
    response = make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl)

    return response

def metadata_query(
    search_query,
    api_host,
    auth,
    vdp_database_names=None,
    vdp_tag_names=None,
    n_results=5,
    verify_ssl=False,
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
    response = make_ai_sdk_request(endpoint, request_body, auth, "GET", verify_ssl=verify_ssl)

    return response

def data_query(
    natural_language_query,
    api_host,
    auth,
    vdp_database_names=None,
    vdp_tag_names=None,
    allow_external_associations=True,
    plot=0,
    plot_details='',
    custom_instructions='',
    verify_ssl=False,
    **llm_params
):
    request_body = {
        'question': natural_language_query,
        'mode': 'data',
        'verbose': False,
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

    endpoint = f'{api_host}/answerQuestion'
    response = make_ai_sdk_request(endpoint, request_body, auth, verify_ssl=verify_ssl)

    return response

def format_data_query_output(response, include_graph=True):
    # CASE 1: No schema found/endpoint error => returns 'Data query failed' message
    if 'error' in response:
        content = f"Data query failed: {response.get('error', 'Unknown error')}"
        artifact = response
        return (content, artifact)

    # CASE 2: Ambiguity detected => returns answer with the ambiguity message
    # CASE 3: Empty execution result => returns answer with the empty execution result message + sql_query + query_explanation
    if not response.get("sql_query") or not response.get("execution_result"):
        content = f"""Response: {response.get("answer", "No answer was provided.")}"""

        sql_query = response.get("sql_query", "")
        if sql_query:
            content += f"\nSQL query: {sql_query}"

        query_explanation = response.get("query_explanation", "")
        if query_explanation:
            content += f"\nQuery explanation: {query_explanation}"
    else:
        # CASE 4: All ok => returns sql_query + execution_result + query_explanation
        content = f"""Execution result: {str(response.get("execution_result", {}))}
        SQL query: {response.get("sql_query", "No SQL query was generated.")}
        Query explanation: {response.get("query_explanation", "No query explanation was provided.")}"""

    # Graph output is only relevant for UI clients (chatbot), not for MCP
    if include_graph:
        raw_graph = response.get("raw_graph", "")
        if raw_graph:
            if raw_graph.startswith("data:image/svg+xml;base64,"):
                content += "\n\nPlot generated successfully and added to the UI."
            else:
                content += f"\n\nGraph generation failed. Error: {raw_graph}"

    artifact = {
        "vql": response.get("sql_query", ""),
        "execution_result": response.get("execution_result", {}),
        "raw_graph": response.get("raw_graph", ""),
        "tables_used": response.get("tables_used", []),
        "query_explanation": response.get("query_explanation", ""),
        "tokens": response.get("tokens", {}).get("total_tokens", 0),
        "ai_sdk_time": response.get("total_execution_time", 0),
        "llm_provider": response.get("llm_provider", ""),
        "llm_model": response.get("llm_model", ""),
    }
    return (content, artifact)

def format_metadata_query_output(response):
    if 'error' in response:
        content = f"Metadata query failed: {response.get('error', 'Unknown error')}"
        artifact = response
        return (content, artifact)

    if 'execution_result' in response:
        response_dump = [entry.get('view_json', {}) for entry in response['execution_result']['views']]
        for entry in response['execution_result']['views']:
            view_json = entry.get('view_json', {}).get('schema', [])
            for column in view_json:
                if 'sample_data' in column:
                    # Limit sample data to only the first 3 entries to avoid context overload
                    column['sample_data'] = column['sample_data'][:3]
    else:
        response_dump = []

    content = f"""Metadata query executed. Remember this tool is not meant for exhaustive searches.
        When answering the user's question, take into account this tool's functionality to not mislead the user.
        If the user is looking for exhaustive searches (not similarity search over n_results), point them to the Denodo Data Marketplace.
        Response: {response_dump}"""
    artifact = response
    return (content, artifact)

def format_data_query_output_mcp(response):
    content, _ = format_data_query_output(response, include_graph=False)
    return content

def format_metadata_query_output_mcp(response):
    content, _ = format_metadata_query_output(response)
    return content
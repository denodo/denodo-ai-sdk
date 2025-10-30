from utils.utils import timed
from sample_chatbot.chatbot_utils import make_ai_sdk_request

@timed
def deep_query(analysis_request, api_host, username, password, verify_ssl=False, **llm_params):
    """
    Call the DeepQuery endpoint to perform advanced analysis.

    Args:
        analysis_request: The detailed analysis to perform
        api_host: AI SDK host URL
        username: Authentication username
        password: Authentication password
        **llm_params: Additional LLM parameters (thinking_llm_*, llm_*)

    Returns:
        Dict containing the analysis result and deepquery_metadata
    """
    request_body = {
        'question': analysis_request
    }

    # Add LLM parameters if provided
    request_body.update(llm_params)

    endpoint = f'{api_host}/deepQuery'
    response = make_ai_sdk_request(endpoint, request_body, (username, password), verify_ssl=verify_ssl)

    return response

@timed
def kb_lookup(search_query, vector_store, k = 5, result_limit = 10000):
    result = vector_store.search(query = search_query, k = k, scores = False)
    information = [f"Result {i+1}: {document.page_content[:result_limit]}\n" for i, document in enumerate(result)]
    information = '\n'.join(information)
    return information

@timed
def metadata_query(search_query, api_host, username, password, database_names = None, tag_names = None, n_results = 5, verify_ssl=False):
    request_body = {
        'query': search_query,
        'n_results': n_results,
    }

    if database_names:
        request_body['vdp_database_names'] = ",".join(database_names)
    if tag_names:
        request_body['vdp_tag_names'] = ",".join(tag_names)

    endpoint = f'{api_host}/similaritySearch'
    response = make_ai_sdk_request(endpoint, request_body, (username, password), "GET", verify_ssl=verify_ssl)

    if isinstance(response, dict) and 'views' in response:
        return [entry.get('view_json', {}) for entry in response['views']]
    return response

@timed
def denodo_query(natural_language_query, api_host, username, password, database_names = None, tag_names = None, plot = 0, plot_details = '', custom_instructions = '', verify_ssl=False, **llm_params):
    request_body = {
        'question': natural_language_query,
        'mode': 'data',
        'verbose': False,
        'plot': bool(int(plot)),
        'plot_details': plot_details,
        'custom_instructions': custom_instructions,
    }

    if database_names:
        request_body['vdp_database_names'] = ",".join(database_names)
    if tag_names:
        request_body['vdp_tag_names'] = ",".join(tag_names)

    # Add LLM parameters if provided
    request_body.update(llm_params)

    endpoint = f'{api_host}/answerQuestion'
    response = make_ai_sdk_request(endpoint, request_body, (username, password), verify_ssl=verify_ssl)

    if isinstance(response, dict):
        # Remove unwanted keys
        keys_to_remove = {
            'answer',
            'sql_execution_time',
            'vector_store_search_time',
            'llm_time',
        }

        for key in keys_to_remove:
            response.pop(key, None)

    return response
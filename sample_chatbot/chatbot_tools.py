from sample_chatbot.chatbot_utils import timed, make_ai_sdk_request
    
@timed
def kb_lookup(search_query, vector_store, k = 5, result_limit = 10000):
    result = vector_store.search(query = search_query, k = k, scores = False)
    information = [f"Result {i+1}: {document.page_content[:result_limit]}\n" for i, document in enumerate(result)]
    information = '\n'.join(information)
    return information

@timed
def metadata_query(search_query, api_host, username, password, database_names = None, tag_names = None, k = 5):
    request_body = {
        'query': search_query,
        'n_results': k,
    }
    
    if database_names:
        request_body['vdp_database_names'] = ",".join(database_names)
    if tag_names:
        request_body['vdp_tag_names'] = ",".join(tag_names)

    endpoint = f'{api_host}/similaritySearch'
    response = make_ai_sdk_request(endpoint, request_body, (username, password), "GET")
    
    if isinstance(response, dict) and 'views' in response:
        return [entry.get('view_json', {}) for entry in response['views']]
    return response

@timed
def denodo_query(natural_language_query, api_host, username, password, database_names = None, tag_names = None, plot = 0, plot_details = '', custom_instructions = ''):
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
    
    endpoint = f'{api_host}/answerQuestion'
    response = make_ai_sdk_request(endpoint, request_body, (username, password))
    
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

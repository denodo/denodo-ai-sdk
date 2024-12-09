import requests
from sample_chatbot.chatbot_utils import timed
    
@timed
def kb_lookup(search_query, vector_store, k = 10, result_limit = 10000):
    result = vector_store.search(query = search_query, k = k, scores = False)
    information = [f"Result {i+1}: {document.page_content[:result_limit]}\n" for i, document in enumerate(result)]
    information = '\n'.join(information)
    return information

@timed
def metadata_query(search_query, api_host, username, password, k = 5):
    request_params = {
        'query': search_query,
        'n_results': k
    }

    try:
        response = requests.get(
            f'{api_host}/similaritySearch',
            params=request_params,
            auth=(username, password),
            verify=False
        )
        response.raise_for_status()
        json_data = response.json()
        
        if 'views' in json_data:
            return [entry.get('view_json', {}) for entry in json_data['views']]
        return json_data
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            return "Authentication failed. Please check your Denodo Data Catalog credentials."
        else:
            return f"An unexpected error occurred when connecting to VDP: {e}"
    except Exception as e:
        return f"Failed to lookup the Denodo database: {e}"
    
@timed
def denodo_query(natural_language_query, api_host, username, password, plot = 0, plot_details = ''):
    request_params = {
        'question': natural_language_query,
        'mode': 'data',
        'verbose': True,
        'plot': bool(plot),
        'plot_details': plot_details
    }

    try:
        response = requests.get(
            f'{api_host}/answerQuestion',
            params=request_params,
            auth=(username, password),
            verify=False
        )
        response.raise_for_status()
        json_data = response.json()
        keys_to_remove = {
            'answer', 
            'tokens', 
            'sql_execution_time', 
            'vector_store_search_time', 
            'llm_time', 
            'total_execution_time'
        }
        
        # Remove unwanted keys
        for key in keys_to_remove:
            json_data.pop(key, None)

        return json_data
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            return "Authentication failed. Please check your Denodo Data Catalog credentials."
        else:
            return f"An unexpected error occurred when connecting to VDP: {e}"
    except Exception as e:
        return f"Failed to lookup the Denodo database: {e}"

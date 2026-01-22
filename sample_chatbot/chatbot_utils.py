import os
import sys
import logging
import requests

from utils.utils import calculate_tokens
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore
from langchain_community.document_loaders.csv_loader import CSVLoader

def setup_user_details(user_details, username=''):
    if not user_details and not username:
        return ""

    prefix = "These are the details about the user you are talking to:"

    if username and user_details:
        return f"{prefix} Username: {username}\n\n{user_details}"
    elif username:
        return f"{prefix} Username: {username}"
    else:
        return f"{prefix} {user_details}"

def trim_conversation(conversation_history, token_limit = 7000):
    # If empty history, return as is
    if not conversation_history:
        return conversation_history

    # Calculate total tokens in conversation
    total_tokens = sum(calculate_tokens(message.content) for message in conversation_history)

    # If already under limit, return as is
    if total_tokens <= token_limit:
        return conversation_history

    # Try removing messages from start until under token limit
    trimmed_history = conversation_history.copy()
    while trimmed_history and total_tokens > token_limit:
        # Remove oldest message
        removed_message = trimmed_history.pop(0)
        # Subtract its tokens from total
        total_tokens -= calculate_tokens(removed_message.content)

    # If we still can't get under limit, return empty list
    if total_tokens > token_limit:
        return []

    return trimmed_history

def get_user_views(api_host, username, password, query, views = 200, verify_ssl=False):
    try:
        request_params = {
            'query': query,
            'scores': False,
            'n_results': views
        }

        response = requests.get(
            f'{api_host}/similaritySearch',
            params=request_params,
            auth=(username, password),
            verify=verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        data = data.get('views', [])
        if len(data) > 0:
            table_names = [view['view_name'] for view in data]
        else:
            table_names = []
        return 200, table_names
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        try:
            response_json = e.response.json()
            detail = response_json.get('detail')
            if isinstance(detail, dict):
                error_message = detail.get('error')
            else:
                error_message = str(detail)
            if not error_message:
                raise ValueError
        except (requests.exceptions.JSONDecodeError, ValueError):
            try:
                error_message = str(e.response.text)
            except Exception:
                error_message = f"AI SDK failed with HTTP status code {status_code}"

        return status_code, error_message

def ai_sdk_health_check(api_host, verify_ssl=False):
    try:
        response = requests.get(f'{api_host}/health', verify=verify_ssl, timeout=10)
        return response.status_code == 200
    except Exception as e:
        return False

def connect_to_ai_sdk(api_host, username, password, insert=True, examples_per_table=100, parallel=True, vdp_database_names = None, incremental=True, vdp_tag_names = None, tags_to_ignore = None, verify_ssl=False):
    try:
        request_params = {
            'insert': insert,
            'examples_per_table': examples_per_table,
            'parallel': parallel,
            'incremental': incremental
        }

        if vdp_database_names is not None:
            request_params['vdp_database_names'] = ",".join(vdp_database_names)

        if vdp_tag_names is not None:
            request_params['vdp_tag_names'] = ",".join(vdp_tag_names)

        if tags_to_ignore is not None:
            request_params['tags_to_ignore'] = ",".join(tags_to_ignore)

        response = requests.get(
            f'{api_host}/getMetadata',
            params=request_params,
            auth=(username, password),
            verify=verify_ssl
        )

        if response.status_code == 204:
            return 204, "No Content"

        if not (200 <= response.status_code < 300):
            if 400 <= response.status_code < 500:
                error_type = "Client Error"
            elif response.status_code >= 500:
                error_type = "Server Error"
            else:
                error_type = "Error"
            return response.status_code, f"{error_type} ({response.status_code}): Please check the AI SDK API logs."

        data = response.json()
        db_schema = data.get('db_schema_json')
        vdbs = ','.join(data.get('vdb_list', []))

        if db_schema is None:
            return 500, "Query didn't fail, but it returned no data. Check the Data Marketplace logs."

        return 200, vdbs
    except Exception as e:
        return 500, f"Unexpected error: {str(e)}"


# Function to check for required environment variables
def check_env_variables(required_vars):
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("ERROR. The following required environment variables are missing:")
        for var in missing_vars:
            print(f"- {var}")
        print("Please set these variables before starting the application.")
        sys.exit(1)

def csv_to_documents(csv_file, delimiter = ";", quotechar = '"'):
    loader = CSVLoader(file_path = csv_file, csv_args = {
            "delimiter": delimiter,
            "quotechar": quotechar,
        }, encoding = "utf-8"
    )

    documents = loader.load()

    if len(documents) == 0:
        logging.error("No data was found in the CSV file.")
        return False
    else:
        for i, document in enumerate(documents):
            document.id = str(i)
            document.metadata['view_name'] = str(i)
            document.metadata['database_name'] = "unstructured"

    return documents

def prepare_unstructured_vector_store(csv_file_path, vector_store_provider, embeddings_provider, embeddings_model, delimiter = ";", quotechar = '"'):
    csv_documents = csv_to_documents(csv_file_path, delimiter, quotechar)

    if not csv_documents:
        return False

    # Extract the filename without extension and remove non-alphabetic characters
    filename = os.path.basename(csv_file_path)
    filename = os.path.splitext(filename)[0]
    filename = ''.join(filter(str.isalpha, filename))
    unstructured_index_name = f"unstructured_{filename}"
    embeddings = UniformEmbeddings(embeddings_provider, embeddings_model).model
    unstructured_vector_store = UniformVectorStore(
        provider=vector_store_provider,
        embeddings=embeddings,
        index_name=unstructured_index_name,
    )

    unstructured_vector_store.add_views(csv_documents, parallel = True)

    return unstructured_vector_store

def truncate_tool_output(tool_output, char_limit):
    tool_output_str = str(tool_output)
    if len(tool_output_str) > char_limit:
        return tool_output_str[:char_limit] + f"\n\n[Note: The output was truncated to {char_limit} characters. Please re-execute the tool to see more.]"
    return tool_output_str


def setup_directories(upload_folder="uploads", report_folder="reports"):
    """Create upload and report directories if they don't exist."""
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(report_folder, exist_ok=True)

def get_synced_resources(api_host, username, password, verify_ssl=False):
    """
    Fetches the synced VDB/Tag info for a user from the AI SDK.
    """
    synced_resources = {}
    try:
        auth_tuple = (username, password)
        info_response = requests.get(
            f"{api_host}/getVectorDBInfo",
            auth=auth_tuple,
            verify=verify_ssl,
            timeout=30
        )

        if info_response.status_code == 200:
            synced_resources = info_response.json().get('syncedResources', {})
            partial_resources = info_response.json().get('partialResources', {})
        else:
            logging.warning(f"Could not retrieve Vector DB info for user {username}: {info_response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to connect to /getVectorDBInfo: {str(e)}")

    return synced_resources, partial_resources
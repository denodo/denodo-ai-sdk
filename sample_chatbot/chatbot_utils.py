import re
import os
import sys
import logging
import requests

from time import time
from functools import wraps
from utils.uniformVectorStore import UniformVectorStore
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.document_loaders.csv_loader import CSVLoader

def dummy_login(api_host, username, password):
    params = {
        'vdp_database_names': 'fake_vdb'
    }
    response = requests.get(f'{api_host}/getMetadata', params = params, auth = (username, password), verify=False)
    return response.status_code == 204

def get_relevant_tables(api_host, username, password, query, vdp_database_names):
    try:
        request_params = {
            'query': query,
            'vdp_database_names': vdp_database_names,
            'scores': False
        }
        response = requests.get(f'{api_host}/similaritySearch', params=request_params, auth=(username, password), verify=False)
        response.raise_for_status()
        data = response.json()
        data = data.get('views', [])
        if len(data) > 0:
            table_names = [view['view_name'] for view in data]
        else:
            table_names = []
        return True, table_names
    except Exception as e:
        return False, {str(e)}

def connect_to_ai_sdk(api_host, username, password, overwrite=False, examples_per_table=3):
    try:
        request_params = {
            'insert': True,
            'overwrite': overwrite,
            'examples_per_table': examples_per_table,
        }
        response = requests.get(f'{api_host}/getMetadata', params=request_params, auth=(username, password), verify=False)
        
        if response.status_code != 200:
            error_detail = response.text
            return False, f"Server Error ({response.status_code}): {error_detail}"

        data = response.json()
        db_schema = data.get('db_schema_json')
        vdbs = data.get('vdb_list')

        if db_schema is None:
            return False, "Query didn't fail, but it returned no data. Check the Data Catalog logs."

        return True, vdbs
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def parse_xml_tags(query):
    # Some LLMs escape their _ because they're trained on markdown
    query = query.replace("\\_", "_")
    def parse_recursive(text):
        pattern = r'<(\w+)>(.*?)</\1>'
        matches = re.findall(pattern, text, re.DOTALL)
        result = {}
        for tag, content in matches:
            if '<' in content and '>' in content:
                result[tag] = parse_recursive(content)
            else:
                result[tag] = content.strip()
        return result

    return parse_recursive(query)

def process_tool_query(query, tools=None):
    if not tools or not isinstance(tools, dict):
        return False

    try:
        parsed_query = parse_xml_tags(query)
    except Exception as e:
        return False

    for tool_name, tool_info in tools.items():
        if tool_name in parsed_query:
            try:
                tool_function = tool_info.get('function')
                tool_params = tool_info.get('params', {})
                
                if not callable(tool_function):
                    continue
                
                query_params = parsed_query[tool_name]
                result = tool_function(**query_params, **tool_params)

                # Reconstruct the original XML call
                original_xml_call = f"<{tool_name}>\n"
                for param, value in query_params.items():
                    original_xml_call += f"<{param}>{value}</{param}>\n"
                original_xml_call += f"</{tool_name}>"

                return tool_name, result, original_xml_call
            except Exception as e:
                return tool_name, str(e), None

    return False

# Timer Decorator
def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        end = time()
        elapsed_time = round(end - start, 2)
        logging.info("{} ran in {}s".format(func.__name__, elapsed_time))

        wrapper.elapsed_time = elapsed_time
        return result

    return wrapper

# Function to check for required environment variables
def check_env_variables(required_vars):
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("ERROR. The following required environment variables are missing:")
        for var in missing_vars:
            print(f"- {var}")
        print("Please set these variables before starting the application.")
        sys.exit(1)

@timed
def csv_to_documents(csv_file, delimiter = ",", quotechar = '"', encoding = 'utf-8-sig'):    
    loader = CSVLoader(file_path = csv_file, csv_args = {
            "delimiter": delimiter,
            "quotechar": quotechar,
        }, encoding = encoding
    )

    documents = loader.load()

    if len(documents) == 0:
        logging.error("No data was found in the CSV file.")
        return False
    else:
        for i, document in enumerate(documents):
            document.id = str(i)
            document.metadata['view_name'] = str(i)

    return documents

def prepare_unstructured_vector_store(csv_file_path, vector_store_provider, embeddings_provider, embeddings_model, delimiter = ",", quotechar = '"', encoding = 'utf-8-sig'):
    csv_documents = csv_to_documents(csv_file_path, delimiter, quotechar, encoding)

    if not csv_documents:
        return False

    # Extract the filename without extension and remove non-alphabetic characters
    filename = os.path.basename(csv_file_path)
    filename = os.path.splitext(filename)[0]
    filename = ''.join(filter(str.isalpha, filename))
    unstructured_index_name = f"unstructured_{filename}"
    unstructured_vector_store = UniformVectorStore(
        provider=vector_store_provider,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        index_name=unstructured_index_name,
        manager_db = "unstructured_vectorstore_manager.db"
    )
    unstructured_vector_store.add_views(csv_documents, database_name = "unstructured", overwrite = True)

    return unstructured_vector_store

def process_chunk(chunk):
    return chunk.replace("\n", "<NEWLINE>")

def add_to_chat_history(chat_history, human_query, ai_response, tool_name, tool_output, original_xml_call):
    if tool_name == "database_query":
        execution_result = tool_output.get('execution_result', {})
        if isinstance(execution_result, dict) and len(execution_result.items()) > 15:
            llm_execution_result = dict(list(execution_result.items())[:15])
            llm_execution_result = str(llm_execution_result) + "... Showing only the first 15 rows of the execution result."
        else:
            llm_execution_result = execution_result
        sql_query = tool_output.get('sql_query', '')
        human_query = f"""{human_query}
        
        ## TOOL DETAILS
        I used the {tool_name} tool:

        {original_xml_call}

        Output:
            SQL Query: {sql_query}
            Execution result: {llm_execution_result}
        """
    elif tool_name in ["metadata_query", "kb_lookup"]:
        human_query = f"""{human_query}
        
        ## TOOL DETAILS
        I used the {tool_name} tool:

        {original_xml_call}

        Output:
            {str(tool_output)[:1000]}
        """
    chat_history.extend([HumanMessage(content = human_query), AIMessage(content = ai_response)])

def readable_tool_result(tool_name, tool_params):
    if isinstance(tool_params, dict):
        if tool_name == "database_query":
            execution_result = tool_params.get('execution_result', {})
            if isinstance(execution_result, dict) and len(execution_result.items()) > 15:
                llm_execution_result = dict(list(execution_result.items())[:15])
                llm_execution_result = str(llm_execution_result) + "... Showing only the first 15 rows of the execution result."
            else:
                llm_execution_result = execution_result
            
            graph_data = tool_params.get('raw_graph', '')
            if len(graph_data) > 300:
                graph_text = "Graph generated succesfully and shown to the user through the chatbot UI, I will not include it in the response."
            else:
                graph_text = "Graph generation failed or not requested."
            
            return_string = f"""
            ## TOOL EXECUTION DETAILS FOR ASSISTANT
            
            I used the {tool_name} tool.

                Output:
                SQL Query: {tool_params.get('sql_query')}
                Execution result: {llm_execution_result}
                Graph: {graph_text}

            Even if the tool failed, I will answer the user's query directly because I cannot execute a new tool.
            Now that I have executed the tool, I will answer the user's query based on the tool output:"""
        elif tool_name == "metadata_query":
            return_string = f"""
            ## TOOL EXECUTION DETAILS FOR ASSISTANT

            I used the {tool_name} tool.

                Output:
                {tool_params}

            Even if the tool failed, I will answer the user's query directly because I cannot execute a new tool.
            Now that I have executed the tool, I will answer the user's query based on the tool output:"""
    else:
        return_string = f"""
        ## TOOL EXECUTION DETAILS FOR ASSISTANT
        I used the {tool_name} tool.

        Output:
        {tool_params}

            Even if the tool failed, I will answer the user's query directly because I cannot execute a new tool.
            Now that I have executed the tool, I will answer the user's query based on the tool output:"""
    return return_string.strip()

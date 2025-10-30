import re
import os
import sys
import logging
import requests
import csv
import datetime

from utils.utils import calculate_tokens
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore
from langchain_core.messages import HumanMessage, AIMessage
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
            return 500, "Query didn't fail, but it returned no data. Check the Data Catalog logs."

        return 200, vdbs
    except Exception as e:
        return 500, f"Unexpected error: {str(e)}"

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

def process_tool_query(query, tools=None, tool_execution_history=None):
    if not tools or not isinstance(tools, dict):
        return False

    if tool_execution_history is None:
        tool_execution_history = []

    try:
        parsed_query = parse_xml_tags(query)
    except Exception as e:
        return False

    for tool_name, tool_info in tools.items():
        if tool_name in parsed_query:
            try:
                query_params = parsed_query[tool_name]

                # Calculate how many times this specific tool has been called
                tool_call_count = len([exec for exec in tool_execution_history if exec['tool_name'] == tool_name]) + 1

                # Special case for deep_query: redirect odd calls to metadata_query
                if tool_name == "deep_query" and tool_call_count % 2 == 1:
                    # This is an odd call, redirect to metadata_query
                    metadata_tool_info = tools.get('metadata_query')
                    if metadata_tool_info:
                        tool_function = metadata_tool_info.get('function')
                        tool_params = metadata_tool_info.get('params', {})

                        if callable(tool_function):
                            # Use the analysis_request as the search_query for metadata_query
                            analysis_request = query_params.get('analysis_request', '')

                            # Call metadata_query with the analysis_request as search_query
                            execution_start = datetime.datetime.now()
                            result = tool_function(search_query=analysis_request, n_results=10, **tool_params)
                            execution_end = datetime.datetime.now()

                            # Store execution details in history
                            execution_record = {
                                'tool_name': tool_name,
                                'actual_tool_executed': 'metadata_query',
                                'inputs': query_params,
                                'outputs': result,
                                'timestamp': execution_start,
                                'execution_time': (execution_end - execution_start).total_seconds()
                            }
                            tool_execution_history.append(execution_record)

                            # Reconstruct the original XML call for deep_query (what user requested)
                            original_xml_call = f"<{tool_name}>\n"
                            for param, value in query_params.items():
                                original_xml_call += f"<{param}>{value}</{param}>\n"
                            original_xml_call += f"</{tool_name}>"

                            # Return with special marker to indicate this is a deep_query schema check
                            return f"{tool_name}_schema_check", result, original_xml_call

                # Normal tool execution
                tool_function = tool_info.get('function')
                tool_params = tool_info.get('params', {})

                if not callable(tool_function):
                    continue

                execution_start = datetime.datetime.now()
                result = tool_function(**query_params, **tool_params)
                execution_end = datetime.datetime.now()

                # Store execution details in history
                execution_record = {
                    'tool_name': tool_name,
                    'actual_tool_executed': tool_name,
                    'inputs': query_params,
                    'outputs': result,
                    'timestamp': execution_start,
                    'execution_time': (execution_end - execution_start).total_seconds()
                }
                tool_execution_history.append(execution_record)

                # Reconstruct the original XML call
                original_xml_call = f"<{tool_name}>\n"
                for param, value in query_params.items():
                    original_xml_call += f"<{param}>{value}</{param}>\n"
                original_xml_call += f"</{tool_name}>"

                return tool_name, result, original_xml_call
            except Exception as e:
                # Store error execution in history
                execution_record = {
                    'tool_name': tool_name,
                    'actual_tool_executed': tool_name,
                    'inputs': parsed_query.get(tool_name, {}),
                    'outputs': str(e),
                    'timestamp': datetime.datetime.now(),
                    'execution_time': 0,
                    'error': True
                }
                tool_execution_history.append(execution_record)
                logging.error(f"Error processing tool: {e}")
                return False
    return False

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

def add_to_chat_history(chat_history, human_query, ai_response, tool_name, tool_output, original_xml_call, llm_response_rows_limit, tool_output_char_limit=1000):
    #Remove related questions from the ai_response
    related_question_index = ai_response.find("<related_question>")
    if related_question_index != -1:
        ai_response = ai_response[:related_question_index].strip()

    if isinstance(tool_output, dict):
        if tool_name == "database_query":
            execution_result = tool_output.get('execution_result', {})
            if isinstance(execution_result, dict):
                total_rows = len(execution_result.items())
                if total_rows > llm_response_rows_limit:
                    llm_execution_result = dict(list(execution_result.items())[:llm_response_rows_limit])
                    llm_execution_result = str(llm_execution_result) + f"... Showing only the first {llm_response_rows_limit} rows of the execution result out of a total of {total_rows} rows."
                else:
                    llm_execution_result = execution_result
            else:
                llm_execution_result = execution_result
            sql_query = tool_output.get('sql_query', '')
            human_query = f"""{human_query}

            ## TOOL DETAILS
            You used the {tool_name} tool:

            {original_xml_call}

            <output>
            <sql_query>
            {sql_query}
            </sql_query>
            <execution_result>
            {llm_execution_result}
            </execution_result>
            </output>
            """
        elif tool_name == "deep_query":
            analysis_output = "DeepQuery analysis completed successfully."

            human_query = f"""{human_query}

            ## TOOL DETAILS
            You used the {tool_name} tool:

            {original_xml_call}

            <output>
            <analysis>
            {tool_output.get('answer', 'Analysis failed')}
            </analysis>
            <status>
            {analysis_output}
            </status>
            </output>
            """
        elif tool_name == "deep_query_schema_check":
            human_query = f"{human_query}\n\nThe user requested a DeepQuery analysis."
        elif tool_name in ["metadata_query", "kb_lookup"]:
            truncated_output = truncate_tool_output(tool_output, tool_output_char_limit)
            human_query = f"""{human_query}

            ## TOOL DETAILS
            I used the {tool_name} tool:

            {original_xml_call}

            <output>
            {truncated_output}
            </output>
            """
    elif tool_name != "direct_response":
        truncated_output = truncate_tool_output(tool_output, tool_output_char_limit)
        human_query = f"""{human_query}

        ## TOOL DETAILS
        I used the {tool_name} tool:

        {original_xml_call}

        <output>
        {truncated_output}
        </output>
        """
    chat_history.extend([HumanMessage(content = human_query), AIMessage(content = ai_response)])

def readable_tool_result(tool_name, tool_params, llm_response_rows_limit):
    if isinstance(tool_params, str):
        return_string = f"""
## TOOL EXECUTION DETAILS FOR ASSISTANT

You used the {tool_name} tool, but it failed with the following error:

<output>
{tool_params}
</output>
"""
    else:
        if tool_name == "database_query":
            execution_result = tool_params.get('execution_result', {})
            if isinstance(execution_result, dict) and len(execution_result.items()) > llm_response_rows_limit:
                llm_execution_result = dict(list(execution_result.items())[:llm_response_rows_limit])
                llm_execution_result = str(llm_execution_result) + f"... Showing only the first {llm_response_rows_limit} rows of the execution result."
            else:
                llm_execution_result = execution_result

            graph_data = tool_params.get('raw_graph', '')
            if len(graph_data) > 300:
                graph_text = "Graph generated succesfully and shown to the user through the chatbot UI, you will not include it in the response."
            else:
                graph_text = "Graph generation failed or not requested."

            return_string = f"""## TOOL EXECUTION DETAILS FOR ASSISTANT

    You used the {tool_name} tool.

    <output>
    <sql_query>{tool_params.get('sql_query')}</sql_query>
    <execution_result>{llm_execution_result}</execution_result>
    <graph>{graph_text}</graph>
    </output>

    Even if the tool failed, you will answer the user's question directly because you cannot execute a new tool.
    Now that you have executed the tool, you will answer the user's question based on the tool output."""
        elif tool_name == "deep_query_schema_check":
            return_string = f"""## TOOL EXECUTION DETAILS FOR ASSISTANT

    You requested to run the deep_query tool to answer the user's question. Before executing the DeepQuery tool, please review the following schema:

    <schema>
    {tool_params}
    </schema>

    Based solely on the schema you received and the analysis the user requested, ask the user any clarifying questions you may have (formatted in markdown) on his expectations and scope for the DeepQuery analysis.
    The questions must be based on the analysis request and ONLY on the schema presented.
    If something does not appear in the schema, it will not be available for the analysis and you should not ask about it.

    Carefully review the schema and:

    - Making a succint and short clarification request.
    - Keep the clarification request to within 3 key bulleted points
    - When clarifying, focus on the dimensions of "Intent", "Interest" and "Scope"

    Limit the scope of the advanced analysis to the data available in the schema."""
        elif tool_name == "deep_query":
            return_string = f"""## TOOL EXECUTION DETAILS FOR ASSISTANT

    I used the {tool_name} tool for advanced analysis (Deep Query).

    <output>
    <analysis_result>{tool_params.get('answer', 'Analysis failed')}</analysis_result>
    </output>

    You will now provide the user a near-verbatim response (simply adjusting format to markdown and the tone of voice) with all the details of the DeepQuery analysis done.
    If the analysis includes raw data or tables, make sure to include it in the response.
    Format your response and the analysis in markdown for better readability."""
        elif tool_name == "metadata_query":
            return_string = f"""## TOOL EXECUTION DETAILS FOR ASSISTANT

    You used the {tool_name} tool. This tool performed similarity search in the database and returned the schema
    of the most similar views to the search query. This tool is not meant for exhaustive searches.

    <output>
    {tool_params}
    </output>

    Even if the tool failed, you will answer the user's question directly because you cannot execute a new tool.
    Now that you have executed the tool, you will answer the user's question based on the tool output.
    When answering the user's question, take into account that this tool's functionality to not mislead the user.
    If the user is looking for exhaustive searches, point them to the Denodo Data Catalog."""
        else:
            return_string = f"""## TOOL EXECUTION DETAILS FOR ASSISTANT
    You used the {tool_name} tool.

    <output>
    {tool_params}
    </output>

    Even if the tool failed, you will answer the user's question directly because you cannot execute a new tool.
    Now that you have executed the tool, you will answer the user's question based on the tool output:"""
    return return_string.strip()

def make_ai_sdk_request(endpoint, payload, auth_tuple, method = "POST", verify_ssl=False):
    """Helper function to make AI SDK requests with standardized error handling"""
    try:
        if method == "GET":
            response = requests.get(
                endpoint,
                params=payload,
                auth=auth_tuple,
                verify=verify_ssl,
                timeout = 1200
            )
        else:
            response = requests.post(
                endpoint,
                json=payload,
                auth=auth_tuple,
                verify=verify_ssl,
                timeout = 1200
            )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            return "Authentication failed. Please check your Denodo Data Catalog credentials."

        error_message = "An error occurred when connecting to the AI SDK"
        try:
            error_data = e.response.json()
            detail = error_data.get('detail', str(e))

            if isinstance(detail, dict):
                final_error_msg = detail.get('error', str(detail))
            else:
                final_error_msg = str(detail)

            return f"{error_message}: {final_error_msg}"

        except ValueError:
            pass

        return f"{error_message}: {e}"
    except Exception as e:
        return f"An error occurred when connecting to the AI SDK: {e}"

def setup_directories(upload_folder="uploads", report_folder="reports"):
    """Create upload and report directories if they don't exist."""
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(report_folder, exist_ok=True)

def get_report_filename(report_max_size_mb, report_max_files, report_folder="reports", base_filename="user_report"):
    """Get the current report filename, create a new one if needed, and enforce file limit."""
    base_path = os.path.join(report_folder, base_filename)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    report_max_size_bytes = report_max_size_mb * 1024 * 1024

    # Find existing report files
    try:
        existing_files = [f for f in os.listdir(report_folder) if f.startswith(base_filename) and f.endswith(".csv")]
    except FileNotFoundError:
        existing_files = [] # Report folder might not exist initially on first call before setup_directories

    if not existing_files:
        # No files exist, create first one
        return f"{base_path}_{timestamp}.csv"

    full_file_paths = [os.path.join(report_folder, f) for f in existing_files]

    # Find the latest file by modification time
    latest_file = max(
        full_file_paths,
        key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0
    )

    # Check file size and create new file if needed
    try:
        if os.path.exists(latest_file) and os.path.getsize(latest_file) >= report_max_size_bytes:
            if report_max_files > 0:
                # Calculate how many files to delete to stay within the limit
                # We want to leave (report_max_files - 1) files before creating the new one.
                num_to_delete = len(existing_files) - (report_max_files - 1)

                if num_to_delete > 0:
                    # Sort files by modification date (oldest first)
                    sorted_files = sorted(
                        full_file_paths,
                        key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0
                    )

                    files_to_delete = sorted_files[:num_to_delete]

                    logging.info(f"Report limit ({report_max_files}) reached. Deleting {len(files_to_delete)} oldest report(s).")

                    for f_path in files_to_delete:
                        try:
                            os.remove(f_path)
                        except OSError as e:
                            logging.error(f"Error deleting old report file {f_path}: {e}")

            return f"{base_path}_{timestamp}.csv"
    except FileNotFoundError:
         # If the latest file somehow disappeared between listing and checking size, create a new one
         return f"{base_path}_{timestamp}.csv"

    return latest_file

def write_to_report(report_lock, report_max_size_mb, report_max_files, question, answer, username, report_folder="reports", base_filename="user_report"):
    """Write an interaction to the report CSV file."""
    with report_lock:
        filename = get_report_filename(report_max_size_mb, report_max_files, report_folder, base_filename)
        file_exists = os.path.exists(filename)
        try:
            with open(filename, 'a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file, delimiter=';')
                if not file_exists:
                    writer.writerow(['uuid','timestamp', 'question', 'answer', 'vql_query', 'query_explanation', 'ai_sdk_tokens', 'ai_sdk_time','user', 'feedback', 'feedback_details'])

                timestamp = datetime.datetime.now().isoformat()
                uuid = answer.get('uuid', '')
                final_answer = answer.get('answer', '')
                # Ensure final_answer is a string before splitting
                if isinstance(final_answer, str):
                    final_answer = final_answer.split('<related_question>')[0].strip()
                else:
                    final_answer = str(final_answer) # Convert non-strings just in case

                vql_query = answer.get('vql', '').strip()
                query_explanation = answer.get('query_explanation', '').strip()
                tokens = answer.get('tokens', 0)
                ai_sdk_time = answer.get('ai_sdk_time', 0)
                writer.writerow([uuid, timestamp, question, final_answer, vql_query, query_explanation, tokens, ai_sdk_time, username, 'not_received', ''])
        except IOError as e:
            logging.error(f"Error writing to report file {filename}: {e}")

def update_feedback_in_report(report_lock, report_max_size_mb, uuid, feedback_value, feedback_details, report_folder="reports", base_filename="user_report"):
    """Update the feedback for a specific interaction in the report CSV file(s)."""
    with report_lock:
        # Find which report file could contain this UUID by checking modification times
        try:
            report_files = [f for f in os.listdir(report_folder) if f.startswith(base_filename) and f.endswith(".csv")]
        except FileNotFoundError:
            logging.error(f"Report directory '{report_folder}' not found during feedback update.")
            return False

        # Sort files by modification time (newest first)
        report_files.sort(key=lambda f: os.path.getmtime(os.path.join(report_folder, f)) if os.path.exists(os.path.join(report_folder, f)) else 0, reverse=True)

        updated = False
        for report_file in report_files:
            filepath = os.path.join(report_folder, report_file)
            rows = []
            found_in_this_file = False

            try:
                # Read the current content
                with open(filepath, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.reader(file, delimiter=';')
                    try:
                        header = next(reader)  # Get header row
                        rows.append(header)
                    except StopIteration: # Empty file
                        continue # Skip this file

                    for row in reader:
                        # Check UUID at index 0
                        if len(row) > 0 and row[0] == uuid:
                            # Update feedback columns (assuming they are at index 9 and 10)
                            while len(row) < 11: # Ensure row has enough columns
                                row.append('')
                            row[9] = feedback_value
                            row[10] = feedback_details
                            found_in_this_file = True
                            updated = True # Mark that we found and updated the UUID
                        rows.append(row)

                # If the UUID was found in this file, rewrite it
                if found_in_this_file:
                    with open(filepath, 'w', newline='', encoding='utf-8') as file:
                        writer = csv.writer(file, delimiter=';')
                        writer.writerows(rows)
                    # Since UUIDs should be unique, we can stop searching once found and updated.
                    break # Exit the loop over report files

            except FileNotFoundError:
                 logging.warning(f"Report file {filepath} disappeared during feedback update.")
                 continue # Try the next file
            except IOError as e:
                 logging.error(f"Error reading/writing report file {filepath} during feedback update: {e}")
                 continue # Try the next file


        return updated # Return True if updated, False otherwise
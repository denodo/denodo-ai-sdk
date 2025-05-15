import os
import re
import sys
import json
import random
import inspect
import uvicorn
import logging
import requests
import functools
import traceback

from time import time
from typing import Annotated
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBearer, HTTPBasicCredentials, HTTPAuthorizationCredentials
from contextlib import contextmanager

from utils.data_catalog import get_views_metadata_documents
from utils.uniformVectorStore import UniformVectorStore
from utils.utils import schema_summary, prepare_schema, flatten_list, prepare_sample_data_schema, calculate_tokens

security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)

def add_tokens(token_set1, token_set2):
    return {key: token_set1[key] + token_set2[key] for key in token_set1}

def generate_session_id(question):
    question_prefix = ''.join(c for c in question[:20] if c.isalpha() or c.isspace())
    question_prefix = question_prefix.replace(' ', '_')
    return f"{question_prefix}_{random.randint(1000,9999)}"

@contextmanager
def timing_context(name, timings):
    start_time = time()
    yield
    elapsed_time = time() - start_time
    if name in timings:
        timings[name] += elapsed_time
    else:
        timings[name] = elapsed_time
    
    for key, value in timings.items():
        timings[key] = round(value, 2)

def readable_tables(relevant_tables):
    readable_output = ""

    for table in relevant_tables:
        table_schema = table['view_json']['schema']
        table_columns = [column['columnName'] for column in table_schema]
        readable_output += f'<table>Table {table["view_name"]} with columns {", ".join(table_columns)}\n</table>\n'
    
    return readable_output

def is_data_complex(data):
    if isinstance(data, dict) and len(data) > 3:
        if len(data['Row 1']) > 1:
            return True 
    return False

def match_nested_parentheses(text):
    def find_closing_paren(s, start):
        count = 0
        for i, c in enumerate(s[start:], start):
            if c == '(':
                count += 1
            elif c == ')':
                count -= 1
                if count == 0:
                    return i
        return -1

    matches = []
    start = 0
    while True:
        start = text.find('(', start)
        if start == -1:
            break
        end = find_closing_paren(text, start)
        if end == -1:
            break
        matches.append(text[start:end+1])
        start = end + 1

    return matches

# Prepare VQL
def prepare_vql(vql):    
    error_log = ''
    error_categories = []

    # Convert VQL to single line for regex processing
    vql_single_line = vql.replace('\n', ' ')

    # Look for LLM code styling
    if '```' in vql:
        logging.info("Backward ticks detected in VQL, fixing...")
        vql = vql.replace('```vql', '').replace('```sql', '').replace('```', '')

    if '\\_' in vql:
        logging.info("Markdown underscore detected in VQL, fixing...")
        vql = vql.replace('\\_', '_')
    
    # Protected words for aliases
    protected_words = (
        'ADD|ALL|ALTER|AND|ANY|AS|ASC|BASE|BOTH|CASE|CONNECT|CONTEXT|CREATE|CROSS|'
        'CURRENT_DATE|CURRENT_TIMESTAMP|CUSTOM|DATABASE|DEFAULT|DESC|DF|DISTINCT|DROP|'
        'EXISTS|FALSE|FETCH|FLATTEN|FROM|FULL|GRANT|GROUP BY|HASH|HAVING|HTML|IF|INNER|'
        'INTERSECT|INTO|IS|JDBC|JOIN|LDAP|LEADING|LEFT|LIMIT|LOCALTIME|LOCALTIMESTAMP|'
        'MERGE|MINUS|MY|NATURAL|NESTED|NOS|NOT|NULL|OBL|ODBC|OF|OFF|OFFSET|ON|ONE|OPT|'
        'OR|ORDER BY|ORDERED|PRIVILEGES|READ|REVERSEORDER|REVOKE|RIGHT|ROW|SELECT|SWAP|'
        'TABLE|TO|TRACE|TRAILING|TRUE|UNION|USER|USING|VIEW|WHEN|WHERE|WITH|WRITE|WS|ZERO'
    )
    
    # Pattern to match protected words used as aliases
    pattern = fr'\s+AS\s+({protected_words})\s+'
    matches = re.finditer(pattern, vql_single_line, re.IGNORECASE)
    
    # Track all replacements
    replacements = {}
    for match in matches:
        protected_word = match.group(1)
        new_alias = f"{protected_word}_"
        replacements[protected_word] = new_alias
        logging.info(f"Protected word '{protected_word}' used as alias, appending underscore")
        
    # Apply replacements
    modified_vql = vql
    for old_word, new_word in replacements.items():
        # Pattern to match the exact alias after AS
        replace_pattern = fr'(\s+AS\s+){old_word}(\s+)'
        modified_vql = re.sub(replace_pattern, fr'\1{new_word}\2', modified_vql, flags=re.IGNORECASE)
    
    vql = modified_vql
    
    # Look for forbidden functions
    forbidden_functions = [
        'LENGTH',
        'CHAR_LENGTH',
        'CHARACTER_LENGTH',
        'CURRENT_TIME',
        'DIVIDE',
        'MULTIPLY',
        'DATE',
        'STRFTIME',
        'SUBSTRING',
        'DATE_SUB',
        'DATE_ADD',
        'DATE_TRUNC',
        'INTERVAL',
        'ADDDATE',
        'TO_CHAR',
        'LPAD',
        'STRING_AGG',
        'ARRAY_AGG',
    ]

    for forbidden_function in forbidden_functions:
        if f" {forbidden_function} " in vql.upper() or f" {forbidden_function} ( " in vql.upper() or f" {forbidden_function}(" in vql.upper() or f"({forbidden_function}(" in vql.upper():
            error_log += f"{forbidden_function} is not permitted in VQL.\n"
            if "FORBIDDEN_FUNCTION" not in error_categories:
                #error_categories.append('FORBIDDEN_FUNCTION')
                continue

    # Look for LIMIT in subquery
    matches = match_nested_parentheses(vql_single_line)
    
    for match in matches:
        if ' LIMIT ' in match:
            error_log += "There is a LIMIT in subquery, which is not permitted in VQL. Use ROW_NUMBER () instead.\n"
            if "LIMIT_SUBQUERY" not in error_categories:
                error_categories.append('LIMIT_SUBQUERY')
        
        if ' FETCH ' in match:
            error_log += "There is a FETCH in subquery, which is not permitted in VQL. Use ROW_NUMBER () instead.\n"
            if "LIMIT_SUBQUERY" not in error_categories:
                error_categories.append('LIMIT_SUBQUERY')

    if " OFFSET " in vql_single_line:
        error_log += "There is a LIMIT OFFSET in the main query, which is not permitted in VQL. Use ROW_NUMBER () instead.\n"
        if "LIMIT_OFFSET" not in error_categories:
            error_categories.append('LIMIT_OFFSET')

    if error_log == "":
        error_log = False
        
    logging.info(f"prepare_vql vql: {vql} error log: {error_log} and categories: {error_categories}")
    return vql.strip(), error_log, error_categories

def generate_vql_restrictions(prompt_parts, vql_rules_prompt, groupby_vql_prompt, having_vql_prompt, dates_vql_prompt, arithmetic_vql_prompt):
    if prompt_parts is None:
        return vql_rules_prompt.replace("{EXTRA_RESTRICTIONS}", "")

    vql_prompt_parts = {
        "groupby": groupby_vql_prompt if prompt_parts.get("groupby") else "",
        "having": having_vql_prompt if prompt_parts.get("having") else "",
        "dates": dates_vql_prompt if prompt_parts.get("dates") else "",
        "arithmetic": arithmetic_vql_prompt if prompt_parts.get("arithmetic") else ""
    }

    extra_restrictions = '\n'.join(vql_prompt_parts[key] for key in vql_prompt_parts if prompt_parts.get(key))
    return vql_rules_prompt.replace("{EXTRA_RESTRICTIONS}", extra_restrictions)

def get_response_format(markdown_response):
    if markdown_response:
        response_format = """
        - Use bold, italics and tables in markdown when appropiate to better illustrate the response.
        - You cannot use markdown headings, instead use titles in bold to separate sections, if needed.
        """
        response_example = "**Cristiano Ronaldo** was the player who scored the most goals last year, with a total of **23 goals**."
    else:
        response_format = "- Use plain text to answer, don't use markdown or any other formatting."
        response_example = "Cristiano Ronaldo was the player who scored the most goals last year, with a total of 23 goals."
    return response_format, response_example

def check_env_variables(required_vars):
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("ERROR. The following required environment variables are missing:")
        for var in missing_vars:
            print(f"- {var}")
        print("Please set these variables before starting the application.")
        sys.exit(1)

def test_data_catalog_connection(data_catalog_url, verify_ssl):
    try:
        response = requests.get(data_catalog_url, verify=verify_ssl, timeout=10)
        response.raise_for_status()
        return True
    except Exception:
        return False
    
def filter_non_allowed_associations(view_json, valid_view_ids):
    # If valid_view_ids is None, return the original view_json unchanged
    if valid_view_ids is None:
        return view_json
    
    # Create a new view_json with filtered associations
    filtered_view_json = view_json.copy()
    filtered_view_json['associations'] = [
        assoc for assoc in view_json['associations']
        if str(assoc['table_id']) in valid_view_ids
    ]
    
    return filtered_view_json

def configure_uvicorn_logging():
    """Configure Uvicorn's logging to use our format."""
    log_config = uvicorn.config.LOGGING_CONFIG
    timestamp_fmt = "[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S %z"

    # Update all formatters
    for formatter in log_config["formatters"].values():
        formatter["fmt"] = timestamp_fmt
        formatter["datefmt"] = date_fmt

    # The access formatter needs special handling to preserve request information
    log_config["formatters"]["access"]["fmt"] = "[%(asctime)s] [%(process)d] [%(levelname)s] %(client_addr)s - \"%(request_line)s\" %(status_code)s"
    
    return log_config

def handle_endpoint_error(endpoint_name):
    def decorator(func):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as he:
                if he.response.status_code == 401:
                    raise HTTPException(status_code=401, detail="Unauthorized")
                else:
                    error_details = {
                        'error': str(he),
                        'traceback': traceback.format_exc()
                    }
                    logging.error(f"HTTP Error in {endpoint_name}: {error_details}")
                    raise HTTPException(status_code=he.response.status_code, detail=error_details)
            except HTTPException as hex:
                # Log the HTTPException but pass it through
                logging.error(f"HTTPException in {endpoint_name}: {str(hex.detail)}")
                raise
            except Exception as e:
                error_details = {
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
                logging.error(f"Error in {endpoint_name}: {error_details}")
                raise HTTPException(status_code=500, detail=error_details)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except requests.exceptions.HTTPError as he:
                if he.response.status_code == 401:
                    logging.error(f"Authentication error in {endpoint_name}: {str(he)}")
                    raise HTTPException(status_code=401, detail="Unauthorized")
                else:
                    error_details = {
                        'error': str(he),
                        'traceback': traceback.format_exc()
                    }
                    logging.error(f"HTTP Error in {endpoint_name}: {error_details}")
                    raise HTTPException(status_code=he.response.status_code, detail=error_details)
            except HTTPException as hex:
                # Log the HTTPException but pass it through
                logging.error(f"HTTPException in {endpoint_name}: {str(hex.detail)}")
                raise
            except Exception as e:
                error_details = {
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
                logging.error(f"Error in {endpoint_name}: {error_details}")
                raise HTTPException(status_code=500, detail=error_details)

        # Choose the appropriate wrapper based on whether the function is a coroutine
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

async def stats_about_data(data_file, unique_values_limit = 20):
    with open(data_file, 'r') as f:
        data = json.load(f)

    # Transform into a flat list of rows
    rows = []
    for _, columns in data.items():
        row = {col["columnName"]: col["value"] for col in columns}
        rows.append(row)

    # Now you have a list of dicts
    column_names = set()
    for row in rows:
        column_names.update(row.keys())
    column_names = list(column_names)

    # Analysis
    info = {
        "num_rows": len(rows),
        "num_columns": len(column_names),
        "columns": {}
    }

    for col in column_names:
        values = [row.get(col) for row in rows]
        non_null_values = [v for v in values if v is not None]
        unique_values = list(set(non_null_values))
        num_unique = len(unique_values)

        # Try to infer type
        try:
            floats = [float(v) for v in non_null_values]
            inferred_type = "float"
            min_val = min(floats)
            max_val = max(floats)
        except (ValueError, TypeError):
            inferred_type = "string"
            min_val = None
            max_val = None

        info["columns"][col] = {
            "inferred_type": inferred_type,
            "num_unique": num_unique,
            "min": min_val,
            "max": max_val,
            "num_missing": values.count(None),
        }
        
        # Only add all unique_values if num_unique <= unique_values_limit
        if num_unique <= unique_values_limit:
            info["columns"][col]["unique_values"] = unique_values

    return str(info)

def authenticate(
        basic_credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]
        ):
    if bearer_credentials is not None:
        return bearer_credentials.credentials
    elif basic_credentials is not None:
        return (basic_credentials.username, basic_credentials.password)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

def initialize_vector_stores(
    vector_store_provider,
    embeddings_provider,
    embeddings_model,
    rate_limit_rpm,
    sample_data_enabled
):
    """
    Initialize vector stores for metadata and optionally for sample data.
    
    Args:
        vector_store_provider: Provider for the vector store
        embeddings_provider: Provider for embeddings
        embeddings_model: Model for embeddings
        rate_limit_rpm: Rate limit in requests per minute
        sample_data_enabled: Whether to initialize a sample data vector store
        
    Returns:
        Tuple of (metadata_vector_store, sample_data_vector_store)
    """
    vector_store = UniformVectorStore(
        provider=vector_store_provider,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        rate_limit_rpm=rate_limit_rpm,
    )
    
    sample_data_vector_store = None
    if sample_data_enabled:
        sample_data_vector_store = UniformVectorStore(
            provider=vector_store_provider,
            embeddings_provider=embeddings_provider,
            embeddings_model=embeddings_model,
            rate_limit_rpm=rate_limit_rpm,
            index_name="ai_sdk_sample_data"
        )
    
    return vector_store, sample_data_vector_store

def process_metadata_source(
    source_type,
    source_name,
    request,
    auth,
    vector_store,
    sample_data_vector_store
):
    """
    Process metadata from a source (tag or database).
    
    Args:
        source_type: 'TAG' or 'DATABASE'
        source_name: Name of the tag or database
        request: Request object with processing parameters
        auth: Authentication credentials
        vector_store: Vector store for metadata
        sample_data_vector_store: Vector store for sample data
        
    Returns:
        Tuple of (db_schema, db_schema_text)
    """
    
    if vector_store and request.incremental:
        last_update = vector_store.get_last_update(source_type=source_type, source_name=source_name)
    else:
        last_update = None
    
    # Prepare arguments for get_views_metadata_documents
    kwargs = {
        "auth": auth,
        "examples_per_table": request.examples_per_table,
        "table_descriptions": request.view_descriptions,
        "table_associations": request.associations,
        "table_column_descriptions": request.column_descriptions,
        "last_update_timestamp_ms": last_update,
        "view_prefix_filter": request.view_prefix_filter,
        "view_suffix_filter": request.view_suffix_filter
    }
    
    # Add source-specific parameter
    if source_type == "TAG":
        kwargs["tag_name"] = source_name
    elif source_type == "DATABASE":
        kwargs["database_name"] = source_name
    else:
        raise ValueError(f"Invalid source type: {source_type}")

    # Get metadata documents
    result, delete_view_ids = get_views_metadata_documents(**kwargs)

    # Handle view deletions if needed
    if delete_view_ids and vector_store:
        vector_store.delete(ids=delete_view_ids)
    
    # Validate response
    if not result:
        raise ValueError(f"Empty response from the Denodo Data Catalog for {source_type.lower()} {source_name}")
    
    # Process schema
    if isinstance(result, dict):
        db_schema = result
        logging.info(f"{source_type} schema for {source_name} has {calculate_tokens(str(db_schema))} tokens.")
        db_schema_text = [schema_summary(table) for table in db_schema['views']]
        
        # Add to vector store if provided
        if vector_store:
            views = flatten_list(prepare_schema(db_schema, request.embeddings_token_limit))
            vector_store.add_views(
                views=views,
                parallel=request.parallel,
                source_type=source_type,
                source_name=source_name
            )

        # Add sample data if enabled
        if sample_data_vector_store:
            views = flatten_list(prepare_sample_data_schema(db_schema))
            sample_data_vector_store.add_views(
                views=views,
                parallel=request.parallel,
                source_type=source_type,
                source_name=source_name,
            )
        
        return db_schema, db_schema_text
    
    # If not a dict, return empty results
    return {}, []

def format_metadata_response(
    all_db_schemas,
    all_db_schema_texts,
    vdb_database_names,
    vdb_tag_names
):
    return {
        'db_schema_json': all_db_schemas,
        'db_schema_text': all_db_schema_texts,
        'vdb_list': vdb_database_names,
        'tag_list': vdb_tag_names
    }
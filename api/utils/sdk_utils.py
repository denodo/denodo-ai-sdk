import os
import re
import sys
import random
import inspect
import logging
import requests
import functools
import traceback
import pandas as pd

from time import time
from typing import Annotated
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBearer, HTTPBasicCredentials, HTTPAuthorizationCredentials
from contextlib import contextmanager
from langchain_core.documents.base import Document

from utils.data_catalog import get_views_metadata_documents
from utils.utils import schema_summary, prepare_schema, flatten_list, prepare_sample_data_schema, calculate_tokens, current_endpoint

security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)

def add_tokens(token_set1, token_set2):
    return {key: token_set1[key] + token_set2[key] for key in ['input_tokens', 'output_tokens', 'total_tokens']}

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
        'UNNEST'
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

def generate_vql_restrictions(
    prompt_parts,
    vql_rules_prompt,
    dates_vql_prompt,
    arithmetic_vql_prompt,
    spatial_vql_prompt = '',
    ai_vql_prompt = '',
    json_vql_prompt = '',
    xml_vql_prompt = '',
    text_vql_prompt = '',
    aggregate_vql_prompt = '',
    cast_vql_prompt = '',
    window_vql_prompt = ''
):
    if prompt_parts is None:
        return vql_rules_prompt.replace("{EXTRA_RESTRICTIONS}", "")

    vql_prompt_catalog = {
        "dates": dates_vql_prompt,
        "arithmetic": arithmetic_vql_prompt,
        "spatial": spatial_vql_prompt,
        "ai": ai_vql_prompt,
        "json": json_vql_prompt,
        "xml": xml_vql_prompt,
        "text": text_vql_prompt,
        "aggregate": aggregate_vql_prompt,
        "cast": cast_vql_prompt,
        "window": window_vql_prompt,
    }

    selected_prompts = [
        vql_prompt_catalog[key]
        for key, enabled in prompt_parts.items()
        if enabled and vql_prompt_catalog.get(key)
    ]

    extra_restrictions = '\n'.join(selected_prompts)
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
    missing_items = []
    for item in required_vars:
        if isinstance(item, str):
            if not os.getenv(item):
                missing_items.append(item)

        elif isinstance(item, (tuple, list)):
            if not any(os.getenv(var) for var in item):
                missing_items.append(" or ".join(item))

    if missing_items:
        print("ERROR. The following required environment variables are missing:")
        for var_name in missing_items:
            print(f"- {var_name}")
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

def handle_endpoint_error(endpoint_name):
    def decorator(func):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Set the endpoint context
            current_endpoint.set(endpoint_name)
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
            # Set the endpoint context
            current_endpoint.set(endpoint_name)
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

async def stats_about_data(data, unique_values_limit = 20):
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

def dataframe_stats(df, unique_values_limit=20):
    info = {
        "num_rows": len(df),
        "num_columns": len(df.columns),
        "columns": {}
    }

    for col in df.columns:
        values = df[col]
        non_null_values = values.dropna()
        unique_values = non_null_values.unique()
        num_unique = len(unique_values)

        # Determine type and min/max values
        if pd.api.types.is_numeric_dtype(df[col]):
            dtype = str(df[col].dtype)
            min_val = float(non_null_values.min()) if len(non_null_values) > 0 else None
            max_val = float(non_null_values.max()) if len(non_null_values) > 0 else None
        else:
            dtype = str(df[col].dtype)

        info["columns"][col] = {
            "dtype": dtype,
            "num_unique_values": num_unique,
            "num_missing": int(values.isna().sum()),
        }

        if pd.api.types.is_numeric_dtype(df[col]):
            info["columns"][col]["min"] = min_val
            info["columns"][col]["max"] = max_val

        # Only add unique values if number is below the limit
        if num_unique <= unique_values_limit:
            # Convert values to Python native types for serialization
            if pd.api.types.is_numeric_dtype(unique_values):
                info["columns"][col]["unique_values"] = unique_values.tolist()
            else:
                info["columns"][col]["unique_values"] = [str(v) for v in unique_values]

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

def process_metadata_source(
    source_type,
    source_name,
    request,
    auth,
    vector_store,
    sample_data_vector_store,
    tagged_views=None,
    incremental=True,
    tags_to_ignore=None
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
        "view_suffix_filter": request.view_suffix_filter,
        "incremental": incremental,
        "views_per_request": request.views_per_request
    }

    if tags_to_ignore:
        kwargs["tags_to_ignore"] = tags_to_ignore

    # Add source-specific parameter
    if source_type == "TAG":
        kwargs["tag_name"] = source_name
        if tagged_views is not None:
            kwargs["tagged_views"] = tagged_views
    elif source_type == "DATABASE":
        kwargs["database_name"] = source_name
    else:
        raise ValueError(f"Invalid source type: {source_type}")

    # Get metadata documents
    result, delete_view_ids, detagged_view_ids = get_views_metadata_documents(**kwargs)

    # Handle view deletions if needed
    if delete_view_ids and vector_store:
        vector_store.delete_by_view_id(view_ids = delete_view_ids)
        if sample_data_vector_store:
            sample_data_vector_store.delete_by_view_id(view_ids = delete_view_ids)

    # Handle detagged views if needed
    if detagged_view_ids and source_type == 'TAG' and vector_store:
        handle_detagged_views(
            detagged_view_ids=detagged_view_ids,
            tag_name=source_name,
            vector_store=vector_store,
            sample_data_vector_store=sample_data_vector_store,
            incremental=incremental
        )

    # Validate response
    if not result:
        logging.info(f"Empty response from the Denodo Data Catalog for {source_type.lower()} {source_name}")
        return {}, []

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
                sample_data=True
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

def is_non_conflicting_doc(doc, databases_to_delete, tags_to_delete, last_update_dict):
        """
        Determines whether a document can be safely deleted without conflicting metadata.

        A document is considered non-conflicting if both of these are true:
        - Its 'database_name' is either:
            - in the databases_to_delete list, or
            - not present in last_update_dict["DATABASE"].
        - For each of its active tags ('tag_' fields with value '1'):
            - If the tag is NOT in tags_to_delete, it must also NOT be in last_update_dict["TAG"].

        This ensures that we don't delete documents whose metadata partially overlaps
        with deletion criteria, unless they're fully safe to remove.
        """
        metadata = doc.metadata or {}

        db_name = metadata.get("database_name")
        last_updated_dbs = set(last_update_dict.get("DATABASE", []))
        last_updated_tags = set(last_update_dict.get("TAG", []))

        db_match = (
            db_name in databases_to_delete or
            db_name not in last_updated_dbs
        )

        tags_to_delete_full = {f"tag_{tag}" for tag in tags_to_delete}
        last_updated_tags_full = {f"tag_{tag}" for tag in last_updated_tags}

        for k, v in metadata.items():
            if k.startswith("tag_") and v == "1":
                if k not in tags_to_delete_full and k in last_updated_tags_full:
                    return False

        return db_match

def delete_by_db_or_tag(vector_store, sample_data_vector_store, vdp_database_names, vdp_tag_names, delete_conflicting, allowed_view_ids=None):
    """
    Deletes views based on database/tag names.
    """
    K_BATCH_SIZE = 1000
    total_deleted_ids = 0
    more_results_left = True

    while more_results_left:
        results = vector_store.search_by_vector(
            vector=[0]*vector_store.dimensions,
            k=K_BATCH_SIZE,
            database_names=vdp_database_names,
            tag_names=vdp_tag_names,
            view_ids=allowed_view_ids,
            view_names=None
        )

        if not results:
            break

        view_ids_to_delete = set()
        document_ids_to_delete = set()

        last_update_dict = vector_store.get_last_update_dict()
        for doc in results:
            if not delete_conflicting:
                if not is_non_conflicting_doc(doc, vdp_database_names, vdp_tag_names, last_update_dict):
                    continue

            view_id = doc.metadata.get('view_id')
            doc_id = doc.metadata.get('document_id')

            if view_id:
                view_ids_to_delete.add(view_id)
            if doc_id:
                document_ids_to_delete.add(doc_id)


        if document_ids_to_delete:
            vector_store.delete(ids=list(document_ids_to_delete))

        if view_ids_to_delete:
            total_deleted_ids += len(view_ids_to_delete)
            if sample_data_vector_store:
                sample_data_vector_store.delete_by_view_id(view_ids=list(view_ids_to_delete))

        more_results_left = len(results) == K_BATCH_SIZE

    if total_deleted_ids > 0:
        vector_store.remove_from_last_update(
            database_names=vdp_database_names,
            tag_names=vdp_tag_names
        )

    return total_deleted_ids

def get_by_db_or_tag(
    vector_store,
    vdp_database_names,
    vdp_tag_names,
    initial_k=1000,
    increment_factor=2,
    max_results_limit=1000000
):
    """
    Retrieves all distinct view_ids associated with a list of databases or tags
    using an exponentially increasing 'k' strategy.

    Args:
        vector_store: The vector store instance.
        vdp_database_names: List of database names to search for.
        vdp_tag_names: List of tag names to search for.
        initial_k: The initial size for 'k'.
        increment_factor: The factor by which to multiply 'k' in each
                          iteration (e.g., 2 for doubling).
        max_results_limit: A safety limit to stop the search.

    Returns:
        A list of unique view_ids that match the criteria.
    """
    current_k = initial_k
    all_results = []

    while True:
        if current_k > max_results_limit:
            logging.warning(f"K limit ({max_results_limit}) reached. Returning partial results.")
            all_results = vector_store.search_by_vector(
                vector=[0] * vector_store.dimensions,
                k=max_results_limit,
                database_names=vdp_database_names,
                tag_names=vdp_tag_names
            )
            break

        results = vector_store.search_by_vector(
            vector=[0] * vector_store.dimensions,
            k=current_k,
            database_names=vdp_database_names,
            tag_names=vdp_tag_names
        )

        if len(results) < current_k:
            all_results = results
            break

        current_k = int(current_k * increment_factor)

    unique_view_ids = set()
    for doc in all_results:
        view_id_str = doc.metadata.get('view_id')
        if view_id_str:
            try:
                view_id_int = int(view_id_str)
                unique_view_ids.add(view_id_int)
            except (ValueError, TypeError):
                continue

    return list(unique_view_ids)

def execution_result_to_dataframe(data):
    # Initialize an empty list to store row data
    rows = []

    # Sort the keys to preserve order (e.g., "Row 1", "Row 2", etc.)
    sorted_keys = sorted(data.keys(), key=lambda k: int(re.search(r'\d+', k).group()) if re.search(r'\d+', k) else float('inf'))

    # Process each row in the JSON data in order
    for row_key in sorted_keys:
        columns = data[row_key]

        # Create a dictionary for the current row
        row_dict = {}

        # Extract column name and value for each item in the row
        for item in columns:
            column_name = item["columnName"]
            value = item["value"]

            # Try to convert numeric values
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass

            row_dict[column_name] = value

        # Add the row dictionary to our list
        rows.append(row_dict)

    # Create DataFrame from the list of dictionaries
    df = pd.DataFrame(rows)

    return df

def handle_detagged_views(
    detagged_view_ids,
    tag_name,
    vector_store,
    sample_data_vector_store,
    incremental=True
):
    """
    Processes a list of detagged view IDs for a specific tag.

    - If a view is not conflicting, it gets deleted.
    - If a view is conflicting, all of its associated documents have their
      metadata updated to remove the current tag and are then re-indexed.
    """
    view_ids_to_delete = []
    conflicting_docs_to_update = []
    last_update_dict = vector_store.get_last_update_dict()

    for view_id in detagged_view_ids:
        # Fetch all documents/chunks associated with this view_id
        docs = vector_store.search_by_vector(vector=[0] * vector_store.dimensions, k=100, view_ids=[view_id])
        if not docs:
            continue

        if not incremental:
            conflicting_docs_to_update.extend(docs)
            continue

        first_doc = docs[0]

        is_safe_to_delete = is_non_conflicting_doc(
            doc=first_doc,
            databases_to_delete=[],
            tags_to_delete=[tag_name],
            last_update_dict=last_update_dict
        )

        if is_safe_to_delete:
            view_ids_to_delete.append(view_id)
        else:
            conflicting_docs_to_update.extend(docs)

    if view_ids_to_delete:
        vector_store.delete_by_view_id(view_ids=view_ids_to_delete)
        if sample_data_vector_store:
            sample_data_vector_store.delete_by_view_id(view_ids=view_ids_to_delete)

    if conflicting_docs_to_update:
        documents_to_reindex = []
        for doc in conflicting_docs_to_update:
            updated_metadata = doc.metadata.copy()
            tag_key = f"tag_{tag_name}"
            if tag_key in updated_metadata:
                del updated_metadata[tag_key]

            updated_document = Document(
                id=doc.id,
                page_content=doc.page_content,
                metadata=updated_metadata
            )
            documents_to_reindex.append(updated_document)

        if documents_to_reindex:
            ids_for_upsert = [doc.id for doc in documents_to_reindex]
            vector_store.client.add_documents(documents=documents_to_reindex, ids=ids_for_upsert)

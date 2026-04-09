"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import re
import os
import sys
import pytz
import json
import asyncio
import logging
import tiktoken
import functools
import contextvars

from fastapi import Request
from time import time
from uuid import uuid4
from boto3 import Session
from datetime import datetime
from functools import wraps
from botocore.session import get_session
from langchain_core.documents.base import Document
from botocore.credentials import RefreshableCredentials
from utils.schema_catalog import SchemaCatalog, SchemaTable

# ContextVar to store the current endpoint name
current_endpoint: contextvars.ContextVar[str] = contextvars.ContextVar('current_endpoint', default=None)

def is_in_venv():
    """
    Check if the current Python interpreter is running inside a virtual environment.
    Returns True if in a virtual environment, False otherwise.
    """
    return sys.prefix != sys.base_prefix

def log_params(func=None, *, truncate_input_chars=500, truncate_output_chars=500):
    if func is None:
        return functools.partial(log_params, truncate_input_chars=truncate_input_chars, truncate_output_chars=truncate_output_chars)

    def _safe_str(value, max_chars):
        """Converts to string, flattens newlines and truncates if longer than max_chars (unless max_chars is None)."""
        str_value = str(value)
        str_value = str_value.replace('\n', ' ').replace('\r', '').strip()
        if max_chars is not None and len(str_value) > max_chars:
            return str_value[:max_chars] + '...'
        return str_value

    def _format_input_arg(key, value):
        if key == "auth":
            return f"{key}=<redacted>"
        return f"{key}={_safe_str(value, truncate_input_chars)}"

    def _format_output_result(result):
        if isinstance(result, (list, tuple)):
            max_items = 20
            items_to_show = result[:max_items]

            formatted_items = [_safe_str(item, truncate_output_chars) for item in items_to_show]

            if len(result) > max_items:
                formatted_items.append(f"... and {len(result) - max_items} more")

            if isinstance(result, tuple):
                return "(" + ", ".join(formatted_items) + ")"
            else:
                return "[" + ", ".join(formatted_items) + "]"
        return _safe_str(result, truncate_output_chars)

    def _build_params_str(args, kwargs):
        return ", ".join(
            [_format_input_arg(f"arg{i}", arg) for i, arg in enumerate(args)] +
            [_format_input_arg(k, v) for k, v in kwargs.items()]
        )

    def _get_log_prefix():
        """Constructs the standard log prefix [endpoint] [func_name]."""
        func_name = func.__name__
        endpoint_name = current_endpoint.get()
        if endpoint_name:
            return f"[{endpoint_name}] [{func_name}]"
        return func_name

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        if os.getenv('SENSITIVE_DATA_LOGGING', '0') != '1':
            return await func(*args, **kwargs)

        # Format the log prefix
        log_prefix = _get_log_prefix()

        # Log entry
        logging.info(f"{log_prefix} - Entry: Parameters({_build_params_str(args, kwargs)})")

        # Call the original function
        result = await func(*args, **kwargs)

        # Log exit
        logging.info(f"{log_prefix} - Exit: Returned({_format_output_result(result)})")

        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        if os.getenv('SENSITIVE_DATA_LOGGING', '0') != '1':
            return func(*args, **kwargs)

        # Format the log prefix
        log_prefix = _get_log_prefix()

        # Log entry
        logging.info(f"{log_prefix} - Entry: Parameters({_build_params_str(args, kwargs)})")

        # Call the original function
        result = func(*args, **kwargs)

        # Log exit
        logging.info(f"{log_prefix} - Exit: Returned({_format_output_result(result)})")

        return result

    # Check if the function is a coroutine function
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

def generate_transaction_id():
    """Generates a unique transaction ID (UUID4) for tracking a request."""
    return str(uuid4())

# Timer Decorator
def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        endpoint_name = current_endpoint.get()

        # Format the log prefix
        if endpoint_name:
            log_prefix = f"[{endpoint_name}] [{func_name}]"
        else:
            log_prefix = func_name

        start = time()
        result = func(*args, **kwargs)
        end = time()
        elapsed_time = round(end - start, 2)
        logging.info(f"{log_prefix} ran in {elapsed_time}s")

        wrapper.elapsed_time = elapsed_time
        return result

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__name__
        endpoint_name = current_endpoint.get()

        # Format the log prefix
        if endpoint_name:
            log_prefix = f"[{endpoint_name}] [{func_name}]"
        else:
            log_prefix = func_name

        start = time()
        result = await func(*args, **kwargs)
        end = time()
        elapsed_time = round(end - start, 2)
        logging.info(f"{log_prefix} ran in {elapsed_time}s")

        async_wrapper.elapsed_time = elapsed_time
        return result

    # Check if the function is a coroutine function
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return wrapper

# Get the associations for a given table
def get_table_associations(table_name, table_json):
    if table_name != table_json['tableName']:
        return []

    return SchemaTable.from_dict(table_json).get_association_ids()

# Summarize a schema
def schema_summary(schema):
    return SchemaTable.from_dict(schema).render_embedding_text()

# Calculate the tokens of a given string
def calculate_tokens(string, encoding = 'cl100k_base'):
    encoding = tiktoken.get_encoding(encoding)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# Parse the XML tags in the LLM's response
def custom_tag_parser(text, tag, default=[]):
    if text is None:
        return [default] if not isinstance(default, list) else []

    pattern = re.compile(fr'<{tag}>(.*?)</{tag}>', re.DOTALL)
    matches = re.findall(pattern, text)

    if not matches:
        return [default] if not isinstance(default, list) else []

    return matches

def flatten_list(list_of_lists):
    flattened_list = [x for item in list_of_lists for x in (item if isinstance(item, list) else [item])]
    return flattened_list

def create_chunks(table, embeddings_token_limit):
    return SchemaTable.from_dict(table).to_embedding_documents(embeddings_token_limit)

@timed
def prepare_sample_data_schema(schema):
    def create_sample_data_document(table):
        table_id = str(table['id'])
        columns = []
        examples = []
        max_sample_data_length = 0
        for column in table['schema']:
            columns.append(column.get('columnName'))
            examples.append(column.get('sample_data', []))
            max_sample_data_length = max(max_sample_data_length, len(column.get('sample_data', [])))

        for example in examples:
            if len(example) < max_sample_data_length:
                example.extend([''] * (max_sample_data_length - len(example)))

        base_metadata = {
            "columns": ','.join(columns),
            "view_id": table_id
        }

        tuples = list(map(list, zip(*examples)))
        return [Document(
            id=f"{table_id}_tuple_{i}",
            page_content=','.join(tuple),
            metadata={**base_metadata, "document_id": f"{table_id}_tuple_{i}"}
        ) for i, tuple in enumerate(tuples)]

    return [create_sample_data_document(table) for table in schema['views']]

@timed
def prepare_last_update_vector(
    last_update_dict,
    partial_resources_dict,
    new_partial_resources=None,
    last_update=None,
    source_type=None,
    source_name=None,
    filter_dict=None
):
    if last_update_dict is None:
        last_update_dict = {}

    if all(param is not None for param in [last_update, source_type, source_name]):
        if source_type in last_update_dict:
            last_update_dict[source_type][source_name] = last_update
        else:
            last_update_dict[source_type] = {
                source_name: last_update
            }

    if partial_resources_dict is None:
        partial_resources_dict = {}

    if new_partial_resources:
        if "partial_tags_by_db" not in partial_resources_dict:
            partial_resources_dict["partial_tags_by_db"] = {}
        if "partial_dbs_by_tag" not in partial_resources_dict:
            partial_resources_dict["partial_dbs_by_tag"] = {}
        if "partial_tags_by_tag" not in partial_resources_dict:
            partial_resources_dict["partial_tags_by_tag"] = {}

        new_tags_by_db = new_partial_resources.get("partial_tags_by_db", {})
        for db_name, tags in new_tags_by_db.items():
            existing = set(partial_resources_dict["partial_tags_by_db"].get(db_name, []))
            existing.update(tags)
            partial_resources_dict["partial_tags_by_db"][db_name] = list(existing)

        new_dbs_by_tag = new_partial_resources.get("partial_dbs_by_tag", {})
        for tag_name, db_list in new_dbs_by_tag.items():
            existing = set(partial_resources_dict["partial_dbs_by_tag"].get(tag_name, []))
            existing.update(db_list)
            partial_resources_dict["partial_dbs_by_tag"][tag_name] = list(existing)

        new_tags_by_tag = new_partial_resources.get("partial_tags_by_tag", {})
        for tag_name, tags in new_tags_by_tag.items():
            existing = set(partial_resources_dict["partial_tags_by_tag"].get(tag_name, []))
            existing.update(tags)
            partial_resources_dict["partial_tags_by_tag"][tag_name] = list(existing)

    metadata = {
        "view_id": "last_update",
        "document_id": "last_update",
        "last_update_dict": json.dumps(last_update_dict),
        "partial_resources_dict": json.dumps(partial_resources_dict)
    }

    if filter_dict is not None:
        metadata["filter_dict"] = json.dumps(filter_dict)

    return [Document(
        id="last_update",
        page_content="last_update",
        metadata=metadata
    )]

@timed
def prepare_schema(schema, embeddings_token_limit = 0):
    return SchemaCatalog.from_storage_json(schema).to_embedding_documents(embeddings_token_limit)

def normalize_root_path(root_path):
    if not root_path:
        return ""

    if not root_path.startswith("/"):
        root_path = "/" + root_path

    return root_path.rstrip('/')

def format_comma_separated_list(raw_string):
    """
    Takes a raw comma-separated string, removes extra spaces,
    and returns a cleanly formatted string joined by ', '.
    """
    if not raw_string:
        return ""
    return ", ".join([item.strip() for item in raw_string.split(",") if item.strip()])

def filter_allowed_headers(headers_dict):
    allowed_headers = [h.strip().lower() for h in os.getenv("FORWARD_CUSTOM_HEADERS", "").split(",") if h.strip()]
    return {k: v for k, v in headers_dict.items() if k.lower() in allowed_headers}

def get_custom_request_headers(request: Request):
    """
    Dependency function to extract custom headers from the incoming FastAPI Request
    based on the FORWARD_CUSTOM_HEADERS environment variable.
    """
    return filter_allowed_headers(request.headers)

def get_custom_headers_from_env(provider_name):
    """
    Retrieves custom headers from environment variables for a given provider.
    Headers are expected in the format: {PROVIDER_NAME}_HEADER_{HEADER_NAME}={HEADER_VALUE}
    """
    headers = {}
    prefix = f"{provider_name.upper()}_HEADER_"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            header_name = key[len(prefix):]
            headers[header_name] = value
            logging.info(f"Loaded custom header for {provider_name}: {header_name}")
    return headers

class RefreshableBotoSession:
    def __init__(
        self,
        region_name: str = None,
        access_key: str = None,
        secret_key: str = None,
        profile_name: str = None,
        sts_arn: str = None,
        session_name: str = None,
        session_ttl: int = 3000
    ):
        self.region_name = region_name
        self.access_key = access_key
        self.secret_key = secret_key
        self.profile_name = profile_name
        self.sts_arn = sts_arn
        self.session_name = session_name or uuid4().hex
        self.session_ttl = session_ttl

    def __get_session_credentials(self):
        if self.access_key and self.secret_key:
            session = Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region_name
            )
        else:
            session = Session(
                region_name = self.region_name,
                profile_name = self.profile_name
            )

        if self.sts_arn:
            sts_client = session.client(service_name = "sts", region_name = self.region_name)
            response = sts_client.assume_role(
                RoleArn = self.sts_arn,
                RoleSessionName = self.session_name,
                DurationSeconds = self.session_ttl,
            ).get("Credentials")

            credentials = {
                "access_key": response.get("AccessKeyId"),
                "secret_key": response.get("SecretAccessKey"),
                "token": response.get("SessionToken"),
                "expiry_time": response.get("Expiration").isoformat(),
            }
        else:
            session_credentials = session.get_credentials().get_frozen_credentials()
            credentials = {
                "access_key": session_credentials.access_key,
                "secret_key": session_credentials.secret_key,
                "token": session_credentials.token,
                "expiry_time": datetime.fromtimestamp(time() + self.session_ttl, tz=pytz.utc).isoformat(),
            }

        return credentials

    def refreshable_session(self) -> Session:
        refreshable_credentials = RefreshableCredentials.create_from_metadata(
            metadata = self.__get_session_credentials(),
            refresh_using = self.__get_session_credentials,
            method = "sts-assume-role",
        )

        session = get_session()
        session._credentials = refreshable_credentials
        session.set_config_variable("region", self.region_name)
        autorefresh_session = Session(botocore_session = session)

        return autorefresh_session

def delete_documents_by_database_name(vector_store, database_names):
    """
    Delete all documents from a vector store that match the given database names.

    This is used for deleting CSV source documents from a shared unstructured vector store,
    where each CSV source is identified by its database_name in the document metadata.

    Args:
        vector_store: UniformVectorStore instance
        database_names: List of database names to delete (e.g., ['denodo_community', 'sample_data'])

    Returns:
        Number of documents deleted
    """
    if not database_names:
        return 0

    K_BATCH_SIZE = 1000
    total_deleted = 0
    more_results_left = True

    while more_results_left:
        # Search for documents matching the database names
        results = vector_store.search_batched(
            vector=vector_store.search_vector,
            k=K_BATCH_SIZE,
            database_names=database_names
        )

        if not results:
            break

        # Collect document IDs to delete
        document_ids_to_delete = set()
        for doc in results:
            doc_id = doc.metadata.get('document_id')
            if doc_id:
                document_ids_to_delete.add(doc_id)

        if document_ids_to_delete:
            vector_store.delete(ids=list(document_ids_to_delete))
            total_deleted += len(document_ids_to_delete)

        more_results_left = len(results) == K_BATCH_SIZE

    return total_deleted
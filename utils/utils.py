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

from time import time
from uuid import uuid4
from boto3 import Session
from datetime import datetime
from functools import wraps
from botocore.session import get_session
from langchain_core.documents.base import Document
from botocore.credentials import RefreshableCredentials

# ContextVar to store the current endpoint name
current_endpoint: contextvars.ContextVar[str] = contextvars.ContextVar('current_endpoint', default=None)

def is_in_venv():
    """
    Check if the current Python interpreter is running inside a virtual environment.
    Returns True if in a virtual environment, False otherwise.
    """
    return sys.prefix != sys.base_prefix

def log_params(func):
    def _safe_str(value):
        """Converts to string, flattens newlines and truncates if longer than 500 characters."""
        str_value = str(value)
        str_value = str_value.replace('\n', ' ').replace('\r', '').strip()
        max_chars = 500
        if len(str_value) > max_chars:
            return str_value[:max_chars] + '...'
        return str_value

    def _format_input_arg(key, value):
        if key == "auth":
            return f"{key}=<redacted>"
        return f"{key}={_safe_str(value)}"

    def _format_output_result(result):
        if isinstance(result, (list, tuple)):
            max_items = 20
            items_to_show = result[:max_items]

            formatted_items = [_safe_str(item) for item in items_to_show]

            if len(result) > max_items:
                formatted_items.append(f"... and {len(result) - max_items} more")

            if isinstance(result, tuple):
                return "(" + ", ".join(formatted_items) + ")"
            else:
                return "[" + ", ".join(formatted_items) + "]"
        return _safe_str(result)

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
    table_associations = []
    schema_table_name = table_json['tableName']
    if table_name == schema_table_name:
        if 'associations' in table_json:
            for association in table_json['associations']:
                table_associations.append(str(association['table_id']))
    return table_associations

# Summarize a schema
def schema_summary(schema):
    summary = "====="
    table_name = schema['tableName']
    if "description" in schema and schema['description'] and schema['description'].strip():
        table_description = schema['description'].replace("\n", " ").strip()
        summary += f"Table {table_name}=====\nDescription: {table_description}\nColumns:\n"
    else:
        summary += f"Table {table_name}=====\nColumns:\n"
    for column_info in schema['schema']:
        column_name = column_info['columnName']
        column_type = column_info['type']
        if "logicalName" in column_info:
            column_logical_name = column_info['logicalName']
        else:
            column_logical_name = None
        if "description" in column_info:
            column_description = column_info['description'].replace("\n", " ").strip()
        else:
            column_description = None

        if column_logical_name is not None and column_description is not None:
            summary += f"- {column_name} ({column_type}) -> {column_logical_name}: {column_description}.\n"
        elif column_logical_name is None and column_description is not None:
            summary += f"- {column_name} ({column_type}) -> {column_description}.\n"
        elif column_logical_name is not None and column_description is None:
            summary += f"- {column_name} ({column_type}) -> {column_logical_name}.\n"
        else:
            summary += f"- {column_name} ({column_type})\n"

    if "associations" in schema and len(schema['associations']) != 0:
        summary += "\n"
        for association in schema['associations']:
            summary += f"This table is also associated with table {association['table_name']} on {association['where']}\n"
    summary += "\n"
    return summary

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
    """
    This function takes a string (schema_summary) and keeps everything before the line with Columns:
    Everything before that is the header and will be kept in every chunk.
    After Columns: you get every line and distribute it evenly so that all chunks have similar token counts.
    Function returns a list of Documents
    """
    # Split into header and content
    summary = schema_summary(table)
    parts = summary.split("Columns:\n", 1)
    header = parts[0] + "Columns:\n"
    content = parts[1] if len(parts) > 1 else ""

    # Split content into individual column lines and associations
    lines = content.split("\n")
    column_lines = []
    association_lines = []

    # Separate column lines from association information
    for line in lines:
        if line.startswith("This table is also associated"):
            association_lines.append(line)
        elif line.strip():  # Only add non-empty lines
            column_lines.append(line)

    # Association footer that will be added to all chunks
    association_footer = "\n" + "\n".join(association_lines) if association_lines else ""

    # Calculate optimal chunk size based on 8000 token limit
    # Account for header and association footer in token calculation
    base_content = header + association_footer
    base_tokens = calculate_tokens(base_content)
    available_tokens = (embeddings_token_limit - 500) - base_tokens

    column_content = "\n".join(column_lines)
    total_tokens = calculate_tokens(column_content)
    target_chunks = (total_tokens // available_tokens) + 1
    chunk_size = max(1, len(column_lines) // target_chunks)

    chunks = []
    base_id = str(table['id'])

    for i in range(0, len(column_lines), chunk_size):
        current_lines = column_lines[i:i + chunk_size]
        chunk_content = header + "\n".join(current_lines) + association_footer + "\n"

        document_id = f"{base_id}_{len(chunks)}"

        # Create metadata for the chunk
        base_metadata = {
            "view_name": table['tableName'],
            "view_json": json.dumps(table),
            "view_id": base_id,  # Same ID for all chunks of the same table
            "document_id": document_id,
            "database_name": table['tableName'].split('.')[0]
        }

        for tag in table.get('tagDetails', []):
            base_metadata[f"tag_{tag['name']}"] = "1"

        chunks.append(Document(
            id=document_id,  # Unique ID for each chunk
            page_content=chunk_content,
            metadata=base_metadata
        ))

    return chunks

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
    def create_document(table, embeddings_token_limit):
        table_summary = schema_summary(table)
        table_summary_tokens = calculate_tokens(table_summary)
        if embeddings_token_limit and table_summary_tokens > embeddings_token_limit:
            return create_chunks(table, embeddings_token_limit)

        id = str(table['id'])

        base_metadata = {
            "view_name": table['tableName'],
            "view_json": json.dumps(table),
            "view_id": id,
            "document_id": id,
            "database_name": table['tableName'].split('.')[0],
            "last_update": int(time() * 1000)
        }

        for tag in table.get('tagDetails', []):
            base_metadata[f"tag_{tag['name']}"] = "1"

        return Document(
            id=id,
            page_content=schema_summary(table),
            metadata=base_metadata
        )

    return [create_document(table, embeddings_token_limit) for table in schema['views']]

def normalize_root_path(root_path):
    if not root_path:
        return ""

    if not root_path.startswith("/"):
        root_path = "/" + root_path

    return root_path.rstrip('/')

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
                "expiry_time": datetime.fromtimestamp(time() + self.session_ttl).replace(tzinfo = pytz.utc).isoformat(),
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
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
from datetime import datetime
from functools import wraps
from langchain_core.documents.base import Document
from rich.console import Console
from utils.schema_catalog import SchemaCatalog, SchemaTable

console = Console()

# ContextVar to store the current endpoint name
current_endpoint: contextvars.ContextVar[str] = contextvars.ContextVar('current_endpoint', default=None)

# Module-level cache to ensure validate_data_dir() runs migration only once
_validated_data_dir = None

def is_in_venv():
    """
    Check if the current Python interpreter is running inside a virtual environment.
    Returns True if in a virtual environment, False otherwise.
    """
    return sys.prefix != sys.base_prefix

def _migrate_legacy_data(data_dir_abs):
    """
    Automatically migrate legacy data directories and files from the repository
    root or flat data directory to the new data directory structure on startup.

    This handles:
    - Transition from the old default (.) to the new default (data/)
    - Transition from a flat AI_SDK_DATA_DIR layout to the subdirectory structure
      (api/, sample_chatbot/, windows_service/)
    - Migration of api/agents/ to data/api/agents/

    When a destination directory already exists, its contents are merged so
    pre-populated files shipped in the repository do not block user data migration.

    Uses print() instead of logging because this runs in the parent process (run.py)
    before any logging handlers are configured.
    """
    import shutil

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _rel_path(path):
        try:
            return os.path.relpath(path, repo_root).replace("\\", "/")
        except ValueError:
            return path.replace("\\", "/")

    def _merge_move_dir(src_dir, dst_dir):
        """
        Move src_dir to dst_dir, or recursively merge children when dst_dir
        already exists. Leaves conflicting files in place with a warning.
        Returns True if at least one item was moved.
        """
        if not os.path.exists(src_dir):
            return False
        if os.path.realpath(src_dir) == os.path.realpath(dst_dir):
            return False

        if not os.path.exists(dst_dir):
            os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
            shutil.move(src_dir, dst_dir)
            return True

        moved_any = False
        for child in os.listdir(src_dir):
            src_child = os.path.join(src_dir, child)
            dst_child = os.path.join(dst_dir, child)

            if not os.path.exists(dst_child):
                shutil.move(src_child, dst_child)
                moved_any = True
            elif os.path.isdir(src_child) and os.path.isdir(dst_child):
                if _merge_move_dir(src_child, dst_child):
                    moved_any = True
            else:
                console.print(
                    f"[yellow]WARNING:[/yellow] Skipping migration of '{_rel_path(src_child)}' "
                    f"because '{_rel_path(dst_child)}' already exists."
                )

        try:
            if not os.listdir(src_dir):
                os.rmdir(src_dir)
        except OSError:
            pass

        return moved_any

    # Directories that lived in the repository root or flat inside AI_SDK_DATA_DIR
    legacy_dirs = [
        ("skills", "sample_chatbot/skills"),
        ("reports", "sample_chatbot/reports"),
        ("cache", "api/cache"),
        ("uploads", "sample_chatbot/uploads"),
        ("conversations_history", "sample_chatbot/conversations_history"),
        ("unstructured_chatbot_kb", "sample_chatbot/unstructured_chatbot_kb"),
        ("ai_sdk_vector_store", "api/ai_sdk_vector_store"),
        ("ai_sdk_sample_data", "api/ai_sdk_sample_data"),
        ("embeddings", "api/cache/embeddings"),
    ]

    migrated = False
    for base_dir in (repo_root, data_dir_abs):
        for item, target_subdir in legacy_dirs:
            src = os.path.join(base_dir, item)
            dst = os.path.join(data_dir_abs, target_subdir)
            if os.path.exists(src):
                try:
                    if _merge_move_dir(src, dst):
                        console.print(f"[green]INFO:[/green] Migrated legacy '{_rel_path(src)}/' to '{_rel_path(dst)}/'")
                        migrated = True
                except Exception as e:
                    console.print(f"[yellow]WARNING:[/yellow] Failed to migrate '{_rel_path(src)}/' to data directory: {e}")

        # Migrate logs/ from root or flat AI_SDK_DATA_DIR by filename pattern (logs are process-specific)
        legacy_logs = os.path.join(base_dir, "logs")
        if os.path.isdir(legacy_logs):
            try:
                log_files = [f for f in os.listdir(legacy_logs)]
                migrated_logs = []
                for log_file in log_files:
                    src_file = os.path.join(legacy_logs, log_file)
                    if log_file == "runtime_config.json":
                        dst_dir = data_dir_abs
                    elif log_file.startswith("service"):
                        dst_dir = os.path.join(data_dir_abs, "windows_service", "logs")
                    elif log_file.startswith("api"):
                        dst_dir = os.path.join(data_dir_abs, "api", "logs")
                    elif log_file.startswith("sample_chatbot"):
                        dst_dir = os.path.join(data_dir_abs, "sample_chatbot", "logs")
                    else:
                        dst_dir = os.path.join(data_dir_abs, "api", "logs")
                    try:
                        os.makedirs(dst_dir, exist_ok=True)
                        dst_file = os.path.join(dst_dir, log_file)
                        if os.path.exists(dst_file):
                            console.print(
                                f"[yellow]WARNING:[/yellow] Skipping migration of '{_rel_path(src_file)}' "
                                f"because '{_rel_path(dst_file)}' already exists."
                            )
                            continue
                        shutil.move(src_file, dst_file)
                        migrated_logs.append(log_file)
                        migrated = True
                    except Exception as e:
                        console.print(f"[yellow]WARNING:[/yellow] Failed to migrate log '{log_file}': {e}")
                if migrated_logs:
                    console.print(f"[green]INFO:[/green] Migrated {len(migrated_logs)} file(s) from '{_rel_path(legacy_logs)}/' to data/ subdirectories")
                # Remove empty legacy logs directory if possible
                try:
                    if not os.listdir(legacy_logs):
                        os.rmdir(legacy_logs)
                except OSError:
                    pass
            except OSError:
                pass

    # Migrate api/agents/ (source tree) and flat <AI_SDK_DATA_DIR>/agents/ to data/api/agents/
    agents_dst = os.path.join(data_dir_abs, "api", "agents")
    for agents_src in (os.path.join(repo_root, "api", "agents"), os.path.join(data_dir_abs, "agents")):
        if os.path.exists(agents_src):
            try:
                if _merge_move_dir(agents_src, agents_dst):
                    console.print(f"[green]INFO:[/green] Migrated legacy '{_rel_path(agents_src)}/' to '{_rel_path(agents_dst)}/'")
                    migrated = True
            except Exception as e:
                console.print(f"[yellow]WARNING:[/yellow] Failed to migrate '{_rel_path(agents_src)}/' to data directory: {e}")

    if migrated:
        console.print("[green]INFO:[/green] Legacy data migration completed. Consider removing any remaining empty directories from the root.")

def get_api_data_dir():
    """Return the API-specific data subdirectory (<AI_SDK_DATA_DIR>/api/)."""
    data_dir = os.environ.get("AI_SDK_DATA_DIR", "data/")
    return os.path.join(data_dir, "api")

def get_chatbot_data_dir():
    """Return the chatbot-specific data subdirectory (<AI_SDK_DATA_DIR>/sample_chatbot/)."""
    data_dir = os.environ.get("AI_SDK_DATA_DIR", "data/")
    return os.path.join(data_dir, "sample_chatbot")

def get_agents_dir():
    """
    Return the agents directory path.

    By default, agents live under <AI_SDK_DATA_DIR>/api/agents/ so that container
    deployments can manage all agent configurations via a single persistent
    volume (data/).  Falls back to api/agents/ for backward compatibility
    when the data directory has not been initialized yet.
    """
    agents_dir = os.path.join(get_api_data_dir(), "agents")
    if os.path.isdir(agents_dir):
        return agents_dir

    # Fallback: legacy location inside the repository source tree
    return "api/agents"

def get_agents_custom_dir():
    """Return the path to the custom agents directory (agents/custom/)."""
    return os.path.join(get_agents_dir(), "custom")

def get_agents_spaces_dir():
    """Return the path to the AI Spaces directory (agents/spaces/)."""
    return os.path.join(get_agents_dir(), "spaces")

def get_agents_icons_dir():
    """Return the path to the agents icons directory (agents/custom/icons/)."""
    return os.path.join(get_agents_custom_dir(), "icons")

def validate_data_dir():
    """
    Validates and returns the centralized data directory (AI_SDK_DATA_DIR).
    Defaults to 'data/' if not set. The root directory (.) is not allowed.
    If the directory doesn't exist, it attempts to create it.
    On failure, raises an error (no fallback to root directory).
    Automatically migrates legacy data from the repository root to data/ on first startup.
    """
    global _validated_data_dir
    if _validated_data_dir is not None:
        return _validated_data_dir
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.getenv("AI_SDK_DATA_DIR", "data/")
    data_dir = os.path.abspath(data_dir)

    # Disallow root directory (.) as it complicates container deployments
    if os.path.realpath(data_dir) == os.path.realpath(repo_root):
        raise ValueError(
            "AI_SDK_DATA_DIR cannot be set to '.' (root directory). "
            "Please use a subdirectory such as 'data/' to keep generated files organized. "
            "Example: AI_SDK_DATA_DIR=data/"
        )

    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Could not create AI_SDK_DATA_DIR '{data_dir}': {e}") from e

    if not os.access(data_dir, os.W_OK):
        raise PermissionError(f"AI_SDK_DATA_DIR '{data_dir}' is not writable.")

    # Migrate any legacy data from the repository root to the new data directory
    _migrate_legacy_data(data_dir)

    os.environ["AI_SDK_DATA_DIR"] = data_dir
    _validated_data_dir = data_dir
    return data_dir

def safe_str(value, max_chars=None):
    """Converts to string, flattens newlines and truncates if longer than max_chars (unless max_chars is None)."""
    if value is None:
        return ""
    str_value = str(value)
    str_value = str_value.replace('\n', ' ').replace('\r', '').strip()
    if max_chars is not None and len(str_value) > max_chars:
        return str_value[:max_chars] + '... (truncated)'
    return str_value

def log_params(func=None, *, truncate_input_chars=500, truncate_output_chars=500):
    if func is None:
        return functools.partial(log_params, truncate_input_chars=truncate_input_chars, truncate_output_chars=truncate_output_chars)

    def _format_input_arg(key, value):
        if key == "auth":
            return f"{key}=<redacted>"
        return f"{key}={safe_str(value, truncate_input_chars)}"

    def _format_output_result(result):
        if isinstance(result, (list, tuple)):
            max_items = 20
            items_to_show = result[:max_items]

            formatted_items = [safe_str(item, truncate_output_chars) for item in items_to_show]

            if len(result) > max_items:
                formatted_items.append(f"... and {len(result) - max_items} more")

            if isinstance(result, tuple):
                return "(" + ", ".join(formatted_items) + ")"
            else:
                return "[" + ", ".join(formatted_items) + "]"
        return safe_str(result, truncate_output_chars)

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

MAX_TRANSACTION_ID_LENGTH = 128

def resolve_transaction_id(headers):
    """
    Use the caller-supplied correlation header when it is present and valid,
    otherwise generate a UUID. Invalid means empty, longer than
    MAX_TRANSACTION_ID_LENGTH, or containing control characters.
    """
    header_name = os.getenv("CUSTOM_TRANSACTION_HEADER", "X-Correlation-ID")
    value = headers.get(header_name) if headers is not None else None
    if value is None:
        return generate_transaction_id()

    transaction_id = value.strip()
    if (
        not transaction_id
        or len(transaction_id) > MAX_TRANSACTION_ID_LENGTH
        or any(ord(char) < 32 for char in transaction_id)
    ):
        logging.warning(
            f"Ignoring invalid {header_name} header; generating a new transaction ID."
        )
        return generate_transaction_id()

    return transaction_id

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

@timed
def prepare_sample_data_schema(schema):
    """Store complete JSON rows and embed labeled values, keeping sample positions."""
    def create_sample_data_document(table):
        table_id = str(table['id'])
        columns = []
        labels = []
        examples = []
        max_sample_data_length = 0
        for column in table['schema']:
            columns.append(column.get('columnName'))
            labels.append((column.get('logicalName') or '').strip() or column.get('columnName'))
            # Pad a copy so building the sample index never changes the schema.
            examples.append(list(column.get('sample_data') or []))
            max_sample_data_length = max(max_sample_data_length, len(examples[-1]))

        for example in examples:
            if len(example) < max_sample_data_length:
                example.extend([''] * (max_sample_data_length - len(example)))

        base_metadata = {
            "columns": json.dumps(columns, ensure_ascii=False),
            "view_id": table_id
        }

        documents = []
        for index, row in enumerate(zip(*examples)):
            document_id = f"{table_id}_tuple_{index}"
            documents.append(Document(
                id=document_id,
                page_content=' · '.join(
                    f"{label}: {json.dumps(value, ensure_ascii=False)}"
                    for label, value in zip(labels, row)
                ),
                metadata={
                    **base_metadata,
                    "document_id": document_id,
                    "row_json": json.dumps(dict(zip(columns, row)), ensure_ascii=False),
                },
            ))
        return documents

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
        from boto3 import Session

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

    def refreshable_session(self):
        from boto3 import Session
        from botocore.session import get_session
        from botocore.credentials import RefreshableCredentials

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

"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import os
import json
import base64
import logging
import aiohttp
import asyncio
from async_lru import alru_cache
from utils.utils import timed, log_params
from utils.schema_catalog import SchemaCatalog

DATA_MARKETPLACE_URL = (os.getenv("AI_SDK_DATA_MARKETPLACE_URL") or 'http://localhost:9090/denodo-data-catalog').rstrip('/') + '/'
DATA_MARKETPLACE_VERIFY_SSL = os.getenv('DATA_MARKETPLACE_VERIFY_SSL', '0') == '1'
DATA_MARKETPLACE_SERVER_ID = int(os.getenv('DATA_MARKETPLACE_SERVER_ID', 1))
DATA_MARKETPLACE_METADATA_URL = f"{DATA_MARKETPLACE_URL}public/api/askaquestion/data"
DATA_MARKETPLACE_EXECUTION_URL = f"{DATA_MARKETPLACE_URL}public/api/askaquestion/execute"
DATA_MARKETPLACE_ALLOWED_VIEWS_URL = f"{DATA_MARKETPLACE_URL}public/api/views/allowed-identifiers"
DATA_MARKETPLACE_USER_PERMISSIONS_URL = f"{DATA_MARKETPLACE_URL}public/api/ai-sdk/user-permissions"
DATA_MARKETPLACE_INCREMENTAL_UPDATE_URL = f"{DATA_MARKETPLACE_URL}public/api/ai-sdk/configuration"
ENABLE_PERMISSIONS_CACHE = os.getenv("AI_SDK_PERMISSIONS_CACHE", "1") == "1"
CACHE_MAX_SIZE = int(os.getenv("AI_SDK_PERMISSIONS_CACHE_MAX_SIZE", "1000"))
CACHE_TTL = int(os.getenv("AI_SDK_PERMISSIONS_CACHE_TTL", "300"))

class DataCatalogAuthError(Exception):
    """Custom exception for Data Marketplace authentication failures."""
    pass

@timed
async def get_views_metadata_documents(
    auth,
    tag_name=None,
    database_name=None,
    examples_per_table=3,
    table_associations=True,
    table_descriptions=True,
    table_column_descriptions=True,
    filter_tables=None,
    server_id=DATA_MARKETPLACE_SERVER_ID,
    verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
    last_update_timestamp_ms=None,
    view_prefix_filter='',
    view_suffix_filter='',
    tagged_views=None,
    incremental=False,
    tags_to_ignore=None,
    views_per_request=50,
    custom_headers=None
):
    """
    Retrieve JSON documents from views metadata with support for OAuth token or Basic auth.
    Handles both legacy and paginated API versions automatically.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        tag_name: Name of the tag to query (mutually exclusive with database_name)
        database_name: Name of the database to query (mutually exclusive with tag_name)
        examples_per_table: Number of example rows to fetch per table (0 to disable)
        table_associations: Whether to include table associations
        table_descriptions: Whether to include descriptions
        table_column_descriptions: Whether to include column descriptions
        filter_tables: List of tables to exclude (default: None)
        server_id: Server identifier
        verify_ssl: Whether to verify SSL certificates (default: DATA_MARKETPLACE_VERIFY_SSL)
        last_update_timestamp_ms: Epoch timestamp in milliseconds used during incremental loading to fetch only views modified after this date
        view_prefix_filter: String used to filter and include only views whose names start with this prefix
        view_suffix_filter: String used to filter and include only views whose names end with this suffix
        tagged_views: List of views with the requested tag
        incremental: Whether to do incremental sync
        tags_to_ignore: List of tags to exclude from vectorization
        views_per_request: Maximum number of views to query in a single request
        custom_headers: Custom HTTP headers to forward

    Returns:
        Parsed metadata JSON response
    """

    # Validate that only one of database_name or tag_name is provided
    if (database_name is None and tag_name is None) or (database_name is not None and tag_name is not None):
        raise ValueError("Exactly one of database_name or tag_name must be provided")

    # Set data_mode based on which parameter is provided
    data_mode = 'DATABASE' if database_name is not None else 'TAG'

    # Set the appropriate logging message based on which parameter is provided
    entity_name = database_name if database_name is not None else tag_name
    entity_type = "database" if database_name is not None else "tag"

    logging.info(f"Starting to retrieve views metadata with {examples_per_table} examples per view on {entity_type} '{entity_name}'")

    delete_view_ids = []
    detagged_view_ids = []
    data_usage_errors = []

    def prepare_request_data(limit, offset):
        data = {
            "dataMode": data_mode,
            "dataUsage": examples_per_table > 0,
        }

        if last_update_timestamp_ms:
            data["updatedSince"] = last_update_timestamp_ms

        # Add the appropriate parameter based on data_mode
        if data_mode == 'DATABASE':
            data["databaseName"] = database_name
        else:  # data_mode == 'TAG'
            data["tagName"] = tag_name
            if incremental and tagged_views:
                data["taggedViewIdentifiers"] = tagged_views

        if examples_per_table > 0:
            data["dataUsageConfiguration"] = {
                "tuplesToUse": examples_per_table,
                "samplingMethod": "random"
            }

        # Add pagination parameters only if specified
        if offset is not None:
            data["offset"] = offset
        if limit is not None:
            data["limit"] = limit

        return data

    async def make_request(data, session):
        headers = {'Content-Type': 'application/json'}
        if isinstance(auth, tuple):
            headers['Authorization'] = calculate_basic_auth_authorization_header(*auth)
        else:
            headers['Authorization'] = f'Bearer {auth}'

        if custom_headers:
            headers.update(custom_headers)

        # 1. Make request and raise any connection/HTTP errors
        async with session.post(
            f"{DATA_MARKETPLACE_METADATA_URL}?serverId={server_id}",
            json=data,
            headers=headers,
            ssl=verify_ssl
        ) as response:

            response_text = await response.text()

            if response.status >= 400:
                try:
                    error_response = json.loads(response_text)
                    error_message = str(error_response.get('message', 'Data Marketplace did not return further details'))
                except (json.JSONDecodeError, AttributeError):
                    error_message = response_text

                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=error_message,
                    headers=response.headers
                )

            # 2. Try to parse JSON response
            try:
                json_response = json.loads(response_text)
            except ValueError as e:
                logging.error(f"Failed to parse JSON response: {str(e)}")
                raise ValueError(f"Invalid JSON response from server: {response_text}") from e

            # 3. Validate response structure
            if not isinstance(json_response, list) and 'viewsDetails' not in json_response:
                error_msg = f"Unexpected response format from server: {response_text}"
                logging.error(error_msg)
                raise ValueError(error_msg)

            return json_response

    try:
        # Initial request without pagination to detect DC API version
        async with aiohttp.ClientSession() as session:
            initial_response = await make_request(prepare_request_data(limit=views_per_request, offset=0), session)

            # If it's a list, it's the old DC API (<9.1.0)
            if not isinstance(initial_response, list):
                views = initial_response.get('viewsDetails', initial_response)
                delete_view_ids.extend(initial_response.get('deletedViewIdentifiers', []))

                if 'dataUsageErrors' in initial_response:
                    data_usage_errors.extend(initial_response['dataUsageErrors'])

                if incremental and data_mode == 'TAG':
                    detagged_view_ids.extend(initial_response.get('detaggedViewIdentifiers', []))

                total_views = len(views)
                logging.info(f"Total views retrieved: {total_views}")

                # If we got less than views_per_request views we can exit
                if total_views < views_per_request:
                    logging.info(f"Retrieved {total_views} views in single request. No pagination needed")
                    all_views = views
                else:
                    # We're dealing with the new API version - need to paginate
                    logging.info("Dealing with the pagination API. Making requests with pagination.")
                    all_views = views
                    offset = views_per_request

                    while True:
                        data = prepare_request_data(offset=offset, limit=views_per_request)
                        page_response = await make_request(data, session)
                        page_views = page_response.get('viewsDetails', page_response)

                        if 'dataUsageErrors' in page_response:
                            data_usage_errors.extend(page_response['dataUsageErrors'])

                        logging.info(f"Received response for request with offset {offset} and limit {views_per_request}.")
                        if not page_views:
                            break

                        all_views.extend(page_views)
                        offset += views_per_request
                        logging.info(f"Retrieved {len(all_views)} views so far.")

                        if len(page_views) < views_per_request:
                            logging.info(f"Received less than {views_per_request} views. Stopping pagination.")
                            break
            else:
                all_views = initial_response

        if not incremental and data_mode == 'TAG' and tagged_views is not None:
            current_view_ids = {view['id'] for view in all_views if 'id' in view}
            detagged_ids_set = set(tagged_views) - current_view_ids
            detagged_view_ids = list(detagged_ids_set)

        logging.info(f"Total views retrieved: {len(all_views)}")

        # Filter out views that have any of the tags to be ignored.
        if tags_to_ignore:
            tags_to_ignore_set = set(tags_to_ignore)
            original_count = len(all_views)

            views_to_keep = []

            for view in all_views:
                view_tags = {tag_info['name'] for tag_info in view.get('tagDetails', []) if 'name' in tag_info}

                if not tags_to_ignore_set.intersection(view_tags):
                    views_to_keep.append(view)

            all_views = views_to_keep

            filtered_count = original_count - len(all_views)
            if filtered_count > 0:
                logging.info(f"Filtered out {filtered_count} views based on tags_to_ignore.")

        processed_views = parse_metadata_json(
            json_response=all_views,
            use_associations=table_associations,
            use_table_descriptions=table_descriptions,
            use_column_descriptions=table_column_descriptions,
            filter_tables=filter_tables or [],
            view_prefix_filter=view_prefix_filter,
            view_suffix_filter=view_suffix_filter
        )

        return processed_views, list(set(delete_view_ids)), list(set(detagged_view_ids)), data_usage_errors

    except aiohttp.ClientResponseError as e:
        logging.error("Data Marketplace views metadata request failed: %s", e.message)
        raise

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.error("Failed to connect to the server: %s", str(e))
        raise

async def is_empty_result(json_response):
    if not json_response.get('rows'):
        return True, "Query executed successfully but returned an empty result (no rows)."

    # Check for single row with single column containing 0 or null
    if (len(json_response['rows']) == 1 and  # Single row
        len(json_response['rows'][0]['values']) == 1 and  # Single column
        (str(json_response['rows'][0]['values'][0]['value']) == '0' or  # Value is 0
            json_response['rows'][0]['values'][0]['value'] is None)):  # Value is null/None
        return True, f"Query executed successfully but returned a single row with a value of 0 or null: {parse_execution_json(json_response)}"

    return False, ""

@log_params(truncate_input_chars=None, truncate_output_chars=None)
@timed
async def execute_vql(vql, auth, limit, truncate_vectors=True, execution_url=DATA_MARKETPLACE_EXECUTION_URL,
                server_id=DATA_MARKETPLACE_SERVER_ID, verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
                custom_headers=None):
    """
    Execute VQL against Data Marketplace with support for OAuth token or Basic auth.

    Args:
        vql: VQL query to execute
        auth: Either (username, password) tuple for basic auth or OAuth token string
        limit: Maximum number of rows to return
        execution_url: Data Marketplace execution endpoint
        server_id: Server identifier
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Status code and parsed response or error message
    """

    # Prepare headers based on auth type
    headers = {'Content-Type': 'application/json'}
    if isinstance(auth, tuple):
        headers['Authorization'] = calculate_basic_auth_authorization_header(*auth)
    else:
        headers['Authorization'] = f'Bearer {auth}'

    if custom_headers:
        headers.update(custom_headers)

    data = {
        "vql": vql,
        "truncateVectors": truncate_vectors,
        "limit": limit
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{execution_url}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                status_code = response.status
                # Try to parse as JSON first
                try:
                    json_response = await response.json()

                    # Success case
                    if 200 <= status_code < 300:
                        # Check for empty results
                        is_empty, empty_message = await is_empty_result(json_response)
                        if is_empty:
                            return 499, empty_message

                        return status_code, parse_execution_json(json_response)

                    # Error case with JSON response
                    if isinstance(json_response, dict) and 'message' in json_response:
                        return status_code, json_response.get('message')
                    else:
                        return status_code, str(json_response)

                except json.JSONDecodeError:
                    # Non-JSON response
                    text_response = await response.text()
                    return status_code, text_response
    except aiohttp.ClientResponseError as e:
        try:
            error_text = await e.response.text()
            error_json = json.loads(error_text)
            # If we have a structured JSON error with a message field, return that
            if isinstance(error_json, dict) and 'message' in error_json:
                return e.status, error_json.get('message')
            else:
                return e.status, str(error_json)
        except (json.JSONDecodeError, AttributeError):
            return e.status, f"HTTP Error: {e.status} - {e.message}"

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        error_message = f"Failed to connect to the server: {str(e)}"
        logging.error(f"{error_message}. VQL: {vql}")
        return 500, error_message

@log_params
@timed
async def get_allowed_view_ids(
    auth,
    server_id=DATA_MARKETPLACE_SERVER_ID,
    permissions_url=DATA_MARKETPLACE_ALLOWED_VIEWS_URL,
    verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
    custom_headers=None
):
    """
    Retrieve allowed view IDs for all views accessible to the user.
    This is the legacy permissions method.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        server_id: The server ID (default is DATA_MARKETPLACE_SERVER_ID)
        permissions_url: The Data Marketplace legacy permissions URL
        verify_ssl: Whether to verify SSL certificates
        custom_headers: Optional custom headers to include in the request

    Returns:
        List of unique allowed view IDs across all accessible views
    """
    # Prepare headers based on auth type
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': (
            calculate_basic_auth_authorization_header(*auth)
            if isinstance(auth, tuple)
            else f'Bearer {auth}'
        )
    }

    if custom_headers:
        headers.update(custom_headers)

    # Use "ALL" data mode to fetch all accessible view IDs in a single request
    data = {"dataMode": "ALL"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{permissions_url}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                response.raise_for_status()
                view_ids = await response.json()

                if not isinstance(view_ids, list) or not all(isinstance(id, int) for id in view_ids):
                    raise ValueError("Unexpected get_allowed_view_ids response format: not a list of integers")

                # Ensure unique values
                unique_view_ids = list(set(view_ids))
                return unique_view_ids

    except aiohttp.ClientResponseError as e:
        if e.status == 401:
            msg = "Authentication failed: Invalid credentials for Data Marketplace."
            logging.error(msg)
            raise DataCatalogAuthError(msg) from e
        else:
            msg = f"Get allowed view IDs from Data Marketplace failed: HTTP Error {e.status} - {e.message}"
            logging.error(msg)
            raise
    except (aiohttp.ClientError, ValueError) as e:
        logging.error(f"Get allowed view IDs from Data Marketplace failed: {str(e)}")
        raise

async def _fetch_user_permissions_from_dm(
    auth,
    data_mode,
    database_name,
    tag_name,
    server_id,
    permissions_url,
    verify_ssl,
    custom_headers
):
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': (
            calculate_basic_auth_authorization_header(*auth)
            if isinstance(auth, tuple)
            else f'Bearer {auth}'
        )
    }

    if custom_headers:
        headers.update(custom_headers)

    data = {"dataMode": data_mode}
    if data_mode == "DATABASE" and database_name:
        data["databaseName"] = database_name
    elif data_mode == "TAG" and tag_name:
        data["tagName"] = tag_name

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{permissions_url}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                response.raise_for_status()
                permissions_data = await response.json()

                if not isinstance(permissions_data, dict):
                    raise ValueError("Unexpected get_user_permissions response format: expected a dictionary")

                permissions_data["legacyEndpoint"] = False
                return permissions_data

    except aiohttp.ClientResponseError as e:
        if e.status == 401:
            msg = "Authentication failed: Invalid credentials for Data Marketplace."
            logging.error(msg)
            raise DataCatalogAuthError(msg) from e

        elif e.status == 404: # For Data Marketplace <= 9.4.1
            logging.info("New user permissions endpoint not found (404). Falling back to legacy get_allowed_view_ids endpoint.")

            legacy_view_ids = await get_allowed_view_ids(
                auth=auth,
                server_id=server_id,
                permissions_url=DATA_MARKETPLACE_ALLOWED_VIEWS_URL,
                verify_ssl=verify_ssl,
                custom_headers=custom_headers
            )

            fallback_username = auth[0] if isinstance(auth, tuple) else "unknown"

            return {
                "legacyEndpoint": True,
                "username": fallback_username,
                "isAdmin": False,
                "roles": [],
                "viewsPermissions": [
                    {
                        "viewId": vid,
                        "hasRowRestrictions": False,
                        "restrictedColumns": []
                    } for vid in legacy_view_ids
                ]
            }

        else:
            msg = f"Get user permissions from Data Marketplace failed: HTTP Error {e.status} - {e.message}"
            logging.error(msg)
            raise
    except (aiohttp.ClientError, ValueError) as e:
        logging.error(f"Get user permissions from Data Marketplace failed: {str(e)}")
        raise

@alru_cache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL)
async def _get_cached_user_permissions(
    auth, data_mode, database_name, tag_name, server_id, permissions_url, verify_ssl, custom_headers_frozen
):
    logging.info("Permissions not found in cache. Fetching permissions from Data Marketplace.")
    custom_headers = dict(custom_headers_frozen) if custom_headers_frozen else None
    return await _fetch_user_permissions_from_dm(
        auth, data_mode, database_name, tag_name, server_id, permissions_url, verify_ssl, custom_headers
    )

@log_params
@timed
async def get_user_permissions(
    auth,
    data_mode="ALL",
    database_name=None,
    tag_name=None,
    server_id=DATA_MARKETPLACE_SERVER_ID,
    permissions_url=DATA_MARKETPLACE_USER_PERMISSIONS_URL,
    verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
    custom_headers=None,
):
    """
    Retrieve user permissions, roles, global admin status, and specific view restrictions.
    Falls back to the legacy allowed-identifiers endpoint if the new one is not available (DM <= 9.4.1).
    Results are cached automatically if AI_SDK_PERMISSIONS_CACHE is 1.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        data_mode: The scope of the request ('ALL', 'DATABASE', or 'TAG')
        database_name: The database name if data_mode is 'DATABASE'
        tag_name: The tag name if data_mode is 'TAG'
        server_id: The server ID (default is DATA_MARKETPLACE_SERVER_ID)
        permissions_url: The Data Marketplace user permissions URL
        verify_ssl: Whether to verify SSL certificates
        custom_headers: Optional custom headers to include in the request

    Returns:
        A dictionary containing:
        - legacyEndpoint (bool)
        - username (str)
        - isAdmin (bool)
        - roles (list)
        - viewsPermissions (list of dicts with viewId, hasRowRestrictions, restrictedColumns)
    """
    if not ENABLE_PERMISSIONS_CACHE:
        logging.info("Permissions cache is disabled. Fetching permissions from Data Marketplace.")
        return await _fetch_user_permissions_from_dm(
            auth, data_mode, database_name, tag_name, server_id, permissions_url, verify_ssl, custom_headers
        )

    logging.info("Checking permissions cache...")
    custom_headers_frozen = frozenset(custom_headers.items()) if custom_headers else frozenset()

    return await _get_cached_user_permissions(
        auth, data_mode, database_name, tag_name, server_id, permissions_url, verify_ssl, custom_headers_frozen
    )

# This method calculates the authorization header for the Data Catalog REST API
def calculate_basic_auth_authorization_header(user, password):
    user_pass = user + ':' + password
    ascii_bytes = user_pass.encode('ascii')
    return 'Basic' + ' ' + base64.b64encode(ascii_bytes).decode('utf-8')

# Remove None Values from Metadata Views
def remove_none_values(json_dict):
    if isinstance(json_dict, dict):
        return {k: remove_none_values(v) for k, v in json_dict.items() if v is not None and v != ''}
    elif isinstance(json_dict, list):
        return [remove_none_values(item) for item in json_dict if item is not None and item != '']
    else:
        return json_dict

# Parse the Metadata JSON with more readable format
def parse_metadata_json(
    json_response,
    use_associations = True,
    use_table_descriptions = True,
    use_column_descriptions = True,
    filter_tables = [],
    view_prefix_filter='',
    view_suffix_filter=''
):
    schema_catalog = SchemaCatalog.from_marketplace_json(
        json_response=json_response,
        use_associations=use_associations,
        use_table_descriptions=use_table_descriptions,
        use_column_descriptions=use_column_descriptions,
        filter_tables=filter_tables,
        view_prefix_filter=view_prefix_filter,
        view_suffix_filter=view_suffix_filter
    )
    return schema_catalog.to_storage_json()

# Parse the result of the Execution to a more readable format
def parse_execution_json(json_response):
    parsed_data = {}

    for i, row in enumerate(json_response['rows']):
        parsed_data[f'Row {i + 1}'] = []
        for value in row['values']:
            parsed_data[f'Row {i + 1}'].append({
                'columnName': value['column'],
                'value': value['value']
            })

    return parsed_data

@timed
async def activate_incremental(
    auth,
    enabled=True,
    server_id=DATA_MARKETPLACE_SERVER_ID,
    verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
    custom_headers=None
):
    """
    Enable or disable incremental metadata updates for the Data Marketplace.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        enabled: Boolean flag to enable (True) or disable (False) incremental metadata updates
        server_id: Server identifier (default is DATA_MARKETPLACE_SERVER_ID)
        incremental_update_url: The Data Marketplace incremental update configuration URL
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Tuple containing (status_code, response_message)
    """
    # Prepare headers based on auth type
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': (
            calculate_basic_auth_authorization_header(*auth)
            if isinstance(auth, tuple)
            else f'Bearer {auth}'
        )
    }

    if custom_headers:
        headers.update(custom_headers)

    # Prepare request data
    data = {
        "metadataChangesEnabled": enabled
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{DATA_MARKETPLACE_INCREMENTAL_UPDATE_URL}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                response_text = await response.text()

                if response.status >= 400:
                    try:
                        error_response = json.loads(response_text)
                        error_message = str(error_response.get('message', 'Data Marketplace did not return further details'))
                    except (json.JSONDecodeError, AttributeError):
                        error_message = f"HTTP Error {response.status}: {response_text}"
                    logging.error(f"Failed to configure incremental metadata updates: {error_message}")
                    return response.status, error_message

                logging.info(f"Incremental metadata updates {'enabled' if enabled else 'disabled'} successfully")
                return response.status, f"Incremental metadata updates {'enabled' if enabled else 'disabled'} successfully"

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        error_message = f"Failed to connect to the server: {str(e)}"
        logging.error(error_message)
        return 500, error_message

@log_params
@timed
async def get_username_from_denodo(
    auth,
    server_id=DATA_MARKETPLACE_SERVER_ID,
    verify_ssl=DATA_MARKETPLACE_VERIFY_SSL,
    custom_headers=None
):
    """
    Fallback method to extract the username querying Denodo directly.
    Useful when the provided auth is an opaque OAuth token.
    """
    vql = "SELECT getsession('user') as username"

    status, response = await execute_vql(
        vql=vql,
        auth=auth,
        limit=1,
        server_id=server_id,
        verify_ssl=verify_ssl,
        custom_headers=custom_headers
    )

    if status == 200 and isinstance(response, dict):
        try:
            row_1 = response.get('Row 1', [])
            if row_1 and len(row_1) > 0:
                return row_1[0].get('value')
        except Exception as e:
            logging.info(f"Failed to parse getsession response: {e}")

    return None

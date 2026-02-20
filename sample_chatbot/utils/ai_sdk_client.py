"""
AI SDK client utilities.
"""

import logging
import requests

def ai_sdk_health_check(api_host, verify_ssl=False):
    """
    Check if the AI SDK is healthy and reachable.

    Args:
        api_host: AI SDK host URL
        verify_ssl: Whether to verify SSL certificates

    Returns:
        True if healthy, False otherwise
    """
    try:
        response = requests.get(f'{api_host}/health', verify=verify_ssl, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def get_user_views(api_host, username, password, query, views=200, verify_ssl=False):
    """
    Get views available to a user via similarity search.

    Args:
        api_host: AI SDK host URL
        username: User's username
        password: User's password
        query: Search query
        views: Maximum number of views to return
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Tuple of (status_code, table_names or error_message)
    """
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

def connect_to_ai_sdk(api_host, username, password, insert=True, examples_per_table=100,
                      parallel=True, vdp_database_names=None, incremental=True,
                      vdp_tag_names=None, tags_to_ignore=None, verify_ssl=False):
    """
    Connect to AI SDK and fetch/sync metadata.

    Args:
        api_host: AI SDK host URL
        username: User's username
        password: User's password
        insert: Whether to insert metadata
        examples_per_table: Number of examples per table
        parallel: Whether to process in parallel
        vdp_database_names: List of VDP database names to sync
        incremental: Whether to do incremental sync
        vdp_tag_names: List of VDP tag names to sync
        tags_to_ignore: List of tags to ignore
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Tuple of (status_code, result or error_message)
    """
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
        data_usage_errors = data.get('data_usage_errors', [])

        if db_schema is None:
            return 500, "Query didn't fail, but it returned no data. Check the Data Marketplace logs."

        return 200, {"vdbs": vdbs, "data_usage_errors": data_usage_errors}

    except Exception as e:
        return 500, f"Unexpected error: {str(e)}"

def get_ai_sdk_info(api_host, username, password, verify_ssl=False):
    """
    Fetch the AI SDK LLM configuration (providers, models, temperatures, etc.).

    Args:
        api_host: AI SDK host URL
        username: User's username
        password: User's password
        verify_ssl: Whether to verify SSL certificates

    Returns:
        dict with AI SDK info, or None if the call fails
    """
    try:
        response = requests.get(
            f"{api_host}/getAISDKInfo",
            auth=(username, password),
            verify=verify_ssl,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Could not retrieve AI SDK info: HTTP {response.status_code}")
        return None
    except requests.exceptions.RequestException as e:
        logging.warning(f"Failed to connect to /getAISDKInfo: {str(e)}")
        return None


def get_synced_resources(api_host, username, password, verify_ssl=False):
    """
    Fetch the synced VDB/Tag info for a user from the AI SDK.

    Args:
        api_host: AI SDK host URL
        username: User's username
        password: User's password
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Tuple of (synced_resources, partial_resources, user_sync_permissions) where
        user_sync_permissions is a bool indicating if the user can use metadata endpoints.
    """
    synced_resources = {}
    partial_resources = {}
    user_sync_permissions = True
    try:
        auth_tuple = (username, password)
        info_response = requests.get(
            f"{api_host}/getVectorDBInfo",
            auth=auth_tuple,
            verify=verify_ssl,
            timeout=30
        )

        if info_response.status_code == 200:
            data = info_response.json()
            synced_resources = data.get('syncedResources', {})
            partial_resources = data.get('partialResources', {})
            user_sync_permissions = data.get('userSyncPermissions', True)
        else:
            logging.warning(f"Could not retrieve Vector DB info for user {username}: {info_response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to connect to /getVectorDBInfo: {str(e)}")

    return synced_resources, partial_resources, user_sync_permissions
"""
AI SDK client utilities.
"""

import logging
import time
import requests

def ai_sdk_health_check(api_host, verify_ssl=False, timeout=10):
    """
    Check if the AI SDK is healthy and reachable.

    Args:
        api_host: AI SDK host URL
        verify_ssl: Whether to verify SSL certificates
        timeout: Per-request HTTP timeout (seconds).

    Returns:
        True if healthy, False otherwise.
    """
    try:
        response = requests.get(f'{api_host}/health', verify=verify_ssl, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False

def ai_sdk_wait_until_healthy(api_host, verify_ssl=False, total_timeout=30.0, poll_interval=0.5):
    """
    Poll the AI SDK /health endpoint until it returns 200 or `total_timeout`
    elapses. Intended for sample_chatbot startup so the chatbot can begin
    serving even while the API is still warming up in a sibling process.

    Returns True if the API became healthy within the budget, False otherwise.
    """
    deadline = time.monotonic() + total_timeout
    attempt = 0
    while True:
        attempt += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        # Per-attempt timeout is bounded so we don't overshoot the deadline.
        per_request_timeout = max(0.5, min(2.0, remaining))
        if ai_sdk_health_check(api_host, verify_ssl=verify_ssl, timeout=per_request_timeout):
            if attempt > 1:
                logging.info(f"AI SDK became healthy after {attempt} attempt(s).")
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(poll_interval, remaining))

def get_user_access_info(api_host, username, password, verify_ssl=False):
    """
    Get user permissions and roles.

    Args:
        api_host: AI SDK host URL
        username: User's username
        password: User's password
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Tuple of (status_code, permissions_dict or error_message)
    """
    try:
        response = requests.get(
            f'{api_host}/getUserPermissions',
            auth=(username, password),
            verify=verify_ssl,
            timeout=30
        )

        if response.status_code == 200:
            return 200, response.json()
        elif response.status_code == 401:
            return 401, "Invalid credentials"
        else:
            return response.status_code, f"API Error: {response.text}"

    except requests.exceptions.RequestException as e:
        return 500, f"Failed to connect to AI SDK: {str(e)}"

def connect_to_ai_sdk(api_host, username, password, insert=True, examples_per_table=100,
                      parallel=True, vdp_database_names=None, incremental=False,
                      vdp_tag_names=None, tags_to_ignore=None, verify_ssl=False,
                      timeout_seconds=300):
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
        timeout_seconds: Request timeout in seconds

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
            verify=verify_ssl,
            timeout=timeout_seconds
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
        timings = data.get('timings', {})

        if db_schema is None:
            return 500, "Query didn't fail, but it returned no data. Check the Data Marketplace logs."

        return 200, {"vdbs": vdbs, "data_usage_errors": data_usage_errors,
                     "timings": timings}

    except requests.exceptions.Timeout:
        return 408, f"The synchronization timed out after {timeout_seconds} seconds."
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

def filter_synced_resources(raw_synced, allowed_databases=None, allowed_tags=None):
    """
    Filters raw synced resources based on allowed databases and tags.
    """
    synced_resources = {}

    if "DATABASE" in raw_synced:
        dbs = raw_synced["DATABASE"]
        if allowed_databases:
            dbs = {k: v for k, v in dbs.items() if k in allowed_databases}
        if dbs:
            synced_resources["DATABASE"] = dbs

    if "TAG" in raw_synced:
        tags = raw_synced["TAG"]
        if allowed_tags:
            tags = {k: v for k, v in tags.items() if k in allowed_tags}
        if tags:
            synced_resources["TAG"] = tags

    return synced_resources

def filter_partial_resources(raw_partial, allowed_databases=None, allowed_tags=None):
    """
    Filters raw partial resources based on allowed databases and tags.
    """
    partial_resources = {
        "partial_tags_by_db": {},
        "partial_dbs_by_tag": {},
        "partial_tags_by_tag": {}
    }

    p_tags_by_db = raw_partial.get("partial_tags_by_db", {})
    p_dbs_by_tag = raw_partial.get("partial_dbs_by_tag", {})
    p_tags_by_tag = raw_partial.get("partial_tags_by_tag", {})

    # Filter partial_tags_by_db
    for db, tags_list in p_tags_by_db.items():
        if not allowed_databases or db in allowed_databases:
            valid_tags = [t for t in tags_list if (not allowed_tags or t in allowed_tags)]
            if valid_tags:
                partial_resources["partial_tags_by_db"][db] = valid_tags

    # Filter partial_dbs_by_tag
    for tag, dbs_list in p_dbs_by_tag.items():
        if not allowed_tags or tag in allowed_tags:
            valid_dbs = [d for d in dbs_list if (not allowed_databases or d in allowed_databases)]
            if valid_dbs:
                partial_resources["partial_dbs_by_tag"][tag] = valid_dbs

    # Filter partial_tags_by_tag
    for tag, tags_list in p_tags_by_tag.items():
        if not allowed_tags or tag in allowed_tags:
            valid_tags = [t for t in tags_list if (not allowed_tags or t in allowed_tags)]
            if valid_tags:
                partial_resources["partial_tags_by_tag"][tag] = valid_tags

    return partial_resources

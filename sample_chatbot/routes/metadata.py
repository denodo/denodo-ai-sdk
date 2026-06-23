"""
Handles metadata sync and deletion endpoints.
"""

import logging
import requests

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.config import get_config
from sample_chatbot.utils.ai_sdk_client import connect_to_ai_sdk, get_synced_resources

metadata_bp = Blueprint('metadata', __name__)

def _refresh_user_synced_resources(config, user):
    """Reload synced/partial resource lists from the AI SDK and drop the cached chatbot."""
    synced_resources, partial_resources, user_sync_permissions = get_synced_resources(
        api_host=config.ai_sdk_host,
        username=user.id,
        password=user.password,
        verify_ssl=config.ai_sdk_verify_ssl
    )
    user.synced_resources = synced_resources
    user.partial_resources = partial_resources
    user.user_sync_permissions = user_sync_permissions
    user.chatbot = None

    return synced_resources, partial_resources

def _get_sync_credentials(config):
    """Get the credentials to use for metadata sync/delete operations.
    Uses AI SDK credentials if configured, otherwise falls back to the logged-in user's credentials."""
    if config.has_ai_sdk_credentials:
        return config.ai_sdk_username, config.ai_sdk_password
    return current_user.id, current_user.password

@metadata_bp.route("/api/delete_metadata", methods=["DELETE"])
@login_required
def delete_metadata():
    """Delete metadata from the AI SDK."""
    config = get_config()

    if not config.allow_sync:
        return jsonify({
            "success": False,
            "message": "Vector DB synchronization is disabled."
        }), 403

    data = request.json
    vdp_database_names = data.get('vdp_database_names', '')
    vdp_tag_names = data.get('vdp_tag_names', '')
    delete_conflicting = data.get('delete_conflicting', False)

    if not vdp_database_names and not vdp_tag_names:
        return jsonify({
            "success": False,
            "message": "At least one database or tag must be provided for deletion."
        }), 400

    try:
        username, password = _get_sync_credentials(config)
        auth = (username, password)
        payload = {
            "vdp_database_names": vdp_database_names,
            "vdp_tag_names": vdp_tag_names,
            "delete_conflicting": delete_conflicting
        }

        response = requests.delete(
            f"{config.ai_sdk_host}/deleteMetadata",
            params=payload,
            auth=auth,
            verify=config.ai_sdk_verify_ssl,
            timeout=300
        )

        if response.status_code == 200:
            synced_resources, partial_resources = _refresh_user_synced_resources(
                config, current_user
            )

            return jsonify({
                "success": True,
                "message": response.json().get('message', 'Deletion successful.'),
                "syncedResources": synced_resources,
                "partialResources": partial_resources
            }), 200

        elif response.status_code == 204:
            from flask import Response
            return Response(status=204)
        else:
            error_message = response.json().get('detail', 'An unknown error occurred during deletion.')
            return jsonify({"success": False, "message": error_message}), response.status_code

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling deleteMetadata endpoint: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to connect to AI SDK: {str(e)}"}), 500

@metadata_bp.route("/api/sync_vdbs", methods=["POST"])
@login_required
def sync_vdbs():
    """Synchronize VDBs with the AI SDK."""
    config = get_config()

    if not config.allow_sync:
        return jsonify({
            "success": False,
            "message": "Vector DB synchronization is disabled."
        }), 403

    vdbs_to_sync = request.json.get('vdbs', [])
    tags_to_sync = request.json.get('tags', [])
    tags_to_ignore = request.json.get('tags_to_ignore', [])
    examples_per_table = request.json.get('examples_per_table', 100)
    incremental = request.json.get('incremental', True)
    parallel = request.json.get('parallel', True)
    timeout_seconds = request.json.get('timeout_seconds', 300)

    username, password = _get_sync_credentials(config)

    status, result = connect_to_ai_sdk(
        api_host=config.ai_sdk_host,
        username=username,
        password=password,
        insert=True,
        examples_per_table=examples_per_table,
        incremental=incremental,
        parallel=parallel,
        vdp_database_names=vdbs_to_sync,
        vdp_tag_names=tags_to_sync,
        tags_to_ignore=tags_to_ignore,
        verify_ssl=config.ai_sdk_verify_ssl,
        timeout_seconds=timeout_seconds
    )

    if status == 200:
        data_usage_errors = result.get("data_usage_errors", [])

        synced_resources, partial_resources = _refresh_user_synced_resources(
            config, current_user
        )

        # Build success message
        message_suffix_parts = []

        if vdbs_to_sync:
            db_label = "database" if len(vdbs_to_sync) == 1 else "databases"
            message_suffix_parts.append(f"{db_label} {', '.join(vdbs_to_sync)}")

        if tags_to_sync:
            tag_label = "tag" if len(tags_to_sync) == 1 else "tags"
            message_suffix_parts.append(f"{tag_label} {', '.join(tags_to_sync)}")

        message_suffix = " and ".join(message_suffix_parts)

        success_message = (
            f"Metadata associated with {message_suffix} successfully synchronized."
            if message_suffix else "Metadata successfully synchronized."
        )

        timings = result.get("timings", {})
        return jsonify({
            "success": True,
            "message": success_message,
            "syncedResources": synced_resources,
            "partialResources": partial_resources,
            "dataUsageErrors": data_usage_errors,
            "timings": timings,
        }), status

    elif status == 204:
        return jsonify({
            "success": True,
            "message": result if result else "Synchronization successful (No Content)"
        }), status
    else:
        return jsonify({"success": False, "message": result}), status

"""
Handles login, logout, and current user endpoints.
"""
import logging

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from sample_chatbot.config import get_config, get_agents_metadata_by_user
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.ai_sdk_client import (
    get_user_access_info,
    get_synced_resources,
    get_ai_sdk_info,
    filter_synced_resources,
    filter_partial_resources
)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/api/login", methods=["POST"])
def login():
    """Authenticate user and create session."""
    config = get_config()
    data = request.json
    username = data.get('username')
    password = data.get('password')
    user_details = data.get('user_details', '')
    custom_instructions = data.get('custom_instructions')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    status, access_info = get_user_access_info(
        api_host=config.ai_sdk_host,
        username=username,
        password=password,
        verify_ssl=config.ai_sdk_verify_ssl
    )

    if status != 200:
        return jsonify({"success": False, "message": access_info}), status

    roles = access_info.get("roles", [])
    is_admin = access_info.get("is_admin", False)
    legacy_permissions_endpoint = access_info.get("legacy_permissions_endpoint", False)

    synced_resources, partial_resources, user_sync_permissions = get_synced_resources(
        api_host=config.ai_sdk_host,
        username=username,
        password=password,
        verify_ssl=config.ai_sdk_verify_ssl
    )

    ai_sdk_info = get_ai_sdk_info(
        api_host=config.ai_sdk_host,
        username=username,
        password=password,
        verify_ssl=config.ai_sdk_verify_ssl
    )

    user = user_store.create_user(username, password, config)
    user.synced_resources = synced_resources
    user.partial_resources = partial_resources
    user.ai_sdk_info = ai_sdk_info
    user.user_sync_permissions = user_sync_permissions
    user.thread_id = str(username)
    user.roles = roles
    user.is_admin = is_admin
    user.legacy_permissions_endpoint = legacy_permissions_endpoint

    if custom_instructions is not None or user_details:
        user.set_custom_instructions(user_details, custom_instructions)

    login_user(user)
    logging.info(f"[Auth] Login successful for user: {username} | Roles: {roles} | Global admin: {is_admin} | Legacy DM: {legacy_permissions_endpoint}")

    can_use_deepquery = ai_sdk_info.get("can_use_deepquery", True)

    return jsonify({
        "success": True,
        "syncedResources": synced_resources,
        "partialResources": partial_resources,
        "userSyncPermissions": user_sync_permissions,
        "globalEnabled": True,
        "agents": get_agents_metadata_by_user(username, roles=roles, is_admin=is_admin, legacy_permissions_endpoint=legacy_permissions_endpoint),
        "config": {
            "can_edit_instructions": config.user_edit_instructions,
            "chatbot_feedback": config.feedback_enabled,
            "unstructured_mode": config.is_unstructured_mode_allowed_for_user(
                username=username,
                roles=roles,
                is_admin=is_admin,
                legacy_permissions_endpoint=legacy_permissions_endpoint
            ),
            "llm_response_rows_limit": config.llm_response_rows_limit,
            "user_edit_llm": config.user_edit_llm,
            "filters_enabled": config.filters_enabled,
            "enable_deep_query": config.deepquery_enabled if can_use_deepquery else False,
            "default_custom_instructions": {
                "ai_sdk": config.custom_instructions_ai_sdk,
                "chatbot": config.custom_instructions_chatbot,
            },
        }
    }), 200

@auth_bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    """Log out current user and destroy session."""
    username = current_user.id
    user_store.remove(username)
    logout_user()
    logging.info(f"[Auth] Logout successful for user: {username}")
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

@auth_bp.route('/api/current_user', methods=['GET'])
@login_required
def get_current_user_info():
    """Get current user information."""
    return jsonify({"username": current_user.id}), 200

@auth_bp.route('/api/change_agent', methods=['POST'])
@login_required
def change_agent():
    data = request.json
    agent_id = data.get('id')
    user_details = data.get('user_details', '')
    custom_instructions = data.get('custom_instructions')
    active_csvs = data.get('active_csvs')
    llm_settings = data.get('llm_settings', {})

    agent_config = get_config(agent_id)

    if not agent_config.is_user_allowed(
        username=current_user.id,
        roles=current_user.roles,
        is_admin=current_user.is_admin,
        legacy_permissions_endpoint=current_user.legacy_permissions_endpoint
    ):
        return jsonify({"success": False, "message": "User is not allowed to use this agent"}), 403

    if current_user.agent_id != agent_config.id:
        current_user.set_agent_config(agent_config)
        current_user.thread_id = str(current_user.id) + '-' + str(agent_config.id)

    try:
        current_user.update_llm_preferences(llm_settings)
    except ValueError as e:
        return jsonify({"success": False, "message": f"Invalid LLM settings: {str(e)}"}), 400

    if user_details:
        current_user.user_details = user_details
        current_user.chatbot = None

    if custom_instructions is not None and agent_config.user_edit_instructions:
        current_user.merge_custom_instructions_for_agent(agent_config.id, custom_instructions)

    if active_csvs is not None:
        current_user.set_active_csvs(active_csvs)

    filtered_synced = current_user.synced_resources
    filtered_partial = current_user.partial_resources

    if agent_config.databases is not None or agent_config.tags is not None:
        filtered_synced = filter_synced_resources(
            current_user.synced_resources,
            allowed_databases=agent_config.databases,
            allowed_tags=agent_config.tags
        )
        filtered_partial = filter_partial_resources(
            current_user.partial_resources,
            allowed_databases=agent_config.databases,
            allowed_tags=agent_config.tags
        )

    can_use_deepquery = current_user.ai_sdk_info.get("can_use_deepquery", True) if current_user.ai_sdk_info else True

    return jsonify({
        "success": True,
        "message": f"Agent switched to {agent_id}",
        "syncedResources": filtered_synced,
        "partialResources": filtered_partial,
        "config": {
            "can_edit_instructions": agent_config.user_edit_instructions,
            "chatbot_feedback": agent_config.feedback_enabled,
            "unstructured_mode": agent_config.is_unstructured_mode_allowed_for_user(
                username=current_user.id,
                roles=current_user.roles,
                is_admin=current_user.is_admin,
                legacy_permissions_endpoint=current_user.legacy_permissions_endpoint
            ),
            "llm_response_rows_limit": agent_config.llm_response_rows_limit,
            "user_edit_llm": agent_config.user_edit_llm,
            "filters_enabled": agent_config.filters_enabled,
            "enable_deep_query": agent_config.deepquery_enabled if can_use_deepquery else False,
            "default_custom_instructions": {
                "ai_sdk": agent_config.custom_instructions_ai_sdk,
                "chatbot": agent_config.custom_instructions_chatbot,
            },
        }
    }), 200

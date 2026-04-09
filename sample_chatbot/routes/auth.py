"""
Handles login, logout, and current user endpoints.
"""
import logging

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from sample_chatbot.config import get_config, get_agents_metadata_by_user
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.ai_sdk_client import (
    get_user_views,
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
    custom_instructions = data.get('custom_instructions', '')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    status, response_data = get_user_views(
        api_host=config.ai_sdk_host,
        username=username,
        password=password,
        query="tables",
        verify_ssl=config.ai_sdk_verify_ssl
    )

    if status != 200:
        if status == 401:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401
        else:
            return jsonify({"success": False, "message": response_data}), status

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

    if response_data:
        user.denodo_tables = (
            "Here are some of the tables available in the user's Denodo instance:\n- " +
            "\n- ".join(response_data) +
            "\n\nThis is not an exhaustive list, you can use the metadata_query tool to query more."
        )
    else:
        user.denodo_tables = (
            "No tables where found in the user's Denodo instance. Either the user has no views, "
            "the connection is failing or they do not have enough permissions."
        )

    if user_details or custom_instructions:
        user.user_details = user_details
        user.custom_instructions = custom_instructions
        user.set_custom_instructions()

    login_user(user)
    logging.info(f"[Auth] Login successful for user: {username}")

    return jsonify({
        "success": True,
        "syncedResources": synced_resources,
        "partialResources": partial_resources,
        "userSyncPermissions": user_sync_permissions,
        "globalEnabled": True,
        "agents": get_agents_metadata_by_user(username),
        "config": {
            "can_add_custom_instructions": config.user_add_custom_instructions,
            "chatbot_feedback": config.feedback_enabled,
            "unstructured_mode": config.unstructured_mode,
            "llm_response_rows_limit": config.llm_response_rows_limit,
            "user_edit_llm": config.user_edit_llm,
            "filters_enabled": config.filters_enabled,
            "enable_deep_query": config.deepquery_enabled,
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
    custom_instructions = data.get('custom_instructions', '')
    active_csvs = data.get('active_csvs')
    llm_settings = data.get('llm_settings', {})

    agent_config = get_config(agent_id)

    if agent_config.allowed_users is not None and current_user.id not in agent_config.allowed_users:
        return jsonify({"success": False, "message": "User is not allowed to use this agent"}), 403


    current_user.set_agent_config(agent_config)

    status, response_data = get_user_views(
        api_host=agent_config.ai_sdk_host,
        username=current_user.id,
        password=current_user.password,
        query="tables",
        verify_ssl=agent_config.ai_sdk_verify_ssl,
        tags=agent_config.tags,
        databases=agent_config.databases
    )

    if status != 200:
        return jsonify({"success": False, "message": response_data}), status

    current_user.thread_id = str(current_user.id) + '-' + str(agent_config.id)

    try:
        current_user.update_llm_preferences(llm_settings)
    except ValueError as e:
        return jsonify({"success": False, "message": f"Invalid LLM settings: {str(e)}"}), 400

    if response_data:
        current_user.denodo_tables = (
            "Here are some of the tables available in the user's Denodo instance:\n- " +
            "\n- ".join(response_data) +
            "\n\nThis is not an exhaustive list, you can use the metadata_query tool to query more."
        )
    else:
        current_user.denodo_tables = (
            "No tables where found in the user's Denodo instance. Either the user has no views, "
            "the connection is failing or they do not have enough permissions."
        )

    if user_details or custom_instructions:
        custom_instructions = custom_instructions if agent_config.user_add_custom_instructions else ''
        current_user.set_custom_instructions(user_details, custom_instructions)

    if active_csvs is not None:
        current_user.active_csv_sources = active_csvs
        for src in current_user.csv_sources:
            current_user.csv_sources[src]['active'] = (src in active_csvs)

        current_user._update_csv_description()

        current_user.chatbot = None

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

    return jsonify({
        "success": True,
        "message": f"Agent switched to {agent_id}",
        "syncedResources": filtered_synced,
        "partialResources": filtered_partial,
        "config": {
            "can_add_custom_instructions": agent_config.user_add_custom_instructions,
            "chatbot_feedback": agent_config.feedback_enabled,
            "unstructured_mode": agent_config.unstructured_mode,
            "llm_response_rows_limit": agent_config.llm_response_rows_limit,
            "user_edit_llm": agent_config.user_edit_llm,
            "filters_enabled": agent_config.filters_enabled,
            "enable_deep_query": agent_config.deepquery_enabled,
        }
    }), 200

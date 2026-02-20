"""
Handles login, logout, and current user endpoints.
"""
import logging

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from sample_chatbot.config import get_config
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.ai_sdk_client import get_user_views, get_synced_resources, get_ai_sdk_info

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["POST"])
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
        "userSyncPermissions": user_sync_permissions
    }), 200

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Log out current user and destroy session."""
    username = current_user.id
    user_store.remove(username)
    logout_user()
    logging.info(f"[Auth] Logout successful for user: {username}")
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

@auth_bp.route('/current_user', methods=['GET'])
@login_required
def get_current_user_info():
    """Get current user information."""
    return jsonify({"username": current_user.id}), 200

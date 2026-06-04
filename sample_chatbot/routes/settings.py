"""
Handles user settings, custom instructions, and LLM configuration endpoints.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.config import get_config

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/config', methods=['GET'])
def get_frontend_config():
    """Endpoint to expose configuration variables to the frontend."""

    agent_id = 'global' if not current_user.is_authenticated else current_user.agent_id

    config = get_config(agent_id)

    from sample_chatbot.engine.context import TOOL_DEFINITIONS

    frontend_config = {
        "has_ai_sdk_credentials": config.has_ai_sdk_credentials,
        "allow_sync": config.allow_sync,
        "chatbot_feedback": config.effective_feedback_enabled,
        "unstructured_mode": config.unstructured_mode,
        "user_edit_llm": config.user_edit_llm,
        "enable_deep_query": config.deepquery_enabled,
        "chatbot_tools": [
            {
                "name": name,
                "pretty_name": tool_cfg["pretty_name"],
                "aliases": tool_cfg["aliases"],
                "optional": tool_cfg["optional"],
                "tool_public_text_key": tool_cfg["tool_public_text_key"],
            }
            for name, tool_cfg in TOOL_DEFINITIONS.items()
        ],
    }

    frontend_config["chatbot_llm_defaults"] = {
        "provider": config.llm_provider.lower(),
        "model": config.llm_model,
        "temperature": config.llm_temperature,
        "max_tokens": config.llm_max_tokens,
    }

    if config.data_marketplace_url:
        frontend_config["data_marketplace_url"] = config.data_marketplace_url.rstrip('/')

    frontend_config["default_custom_instructions"] = {
        "ai_sdk": config.custom_instructions_ai_sdk,
        "chatbot": config.custom_instructions_chatbot,
    }
    frontend_config["can_edit_instructions"] = config.user_edit_instructions

    return jsonify(frontend_config)

@settings_bp.route('/api/update_custom_instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    """Update user's custom instructions and profile."""
    data = request.json
    custom_instructions = data.get('custom_instructions')
    user_details = data.get('user_details', '')

    current_user.set_custom_instructions(user_details, custom_instructions)

    return jsonify({"message": "Profile updated successfully"}), 200

@settings_bp.route('/api/llm_settings', methods=['GET'])
@login_required
def get_llm_settings():
    """Return the user's current LLM preferences and cached AI SDK configuration."""
    agent_id = 'global' if not current_user.is_authenticated else current_user.agent_id

    config = get_config(agent_id)

    ai_sdk_base_llm_defaults = {}
    if getattr(config, 'ai_sdk_base_llm_model', None):
        ai_sdk_base_llm_defaults = {
            "provider": config.ai_sdk_base_llm_provider,
            "model": config.ai_sdk_base_llm_model,
            "temperature": config.ai_sdk_base_llm_temperature,
            "max_tokens": config.ai_sdk_base_llm_max_tokens,
        }

    ai_sdk_thinking_llm_defaults = {}
    if getattr(config, 'ai_sdk_thinking_llm_model', None):
        ai_sdk_thinking_llm_defaults = {
            "provider": config.ai_sdk_thinking_llm_provider,
            "model": config.ai_sdk_thinking_llm_model,
            "temperature": config.ai_sdk_thinking_llm_temperature,
            "max_tokens": config.ai_sdk_thinking_llm_max_tokens,
        }

    return jsonify({
        "chatbot_llm_defaults": {
            "provider": config.llm_provider.lower(),
            "model": config.llm_model,
            "temperature": config.llm_temperature,
            "max_tokens": config.llm_max_tokens,
        },
        "ai_sdk_base_llm_defaults": ai_sdk_base_llm_defaults,
        "ai_sdk_thinking_llm_defaults": ai_sdk_thinking_llm_defaults,
        "use_base_llm_for_execution_default": config.use_base_llm_for_execution,
        "check_ambiguity_default": config.check_ambiguity,
        "use_base_llm_for_execution": current_user.use_base_llm_for_execution,
        "chatbot_llm_preferences": current_user.chatbot_llm_preferences,
        "ai_sdk_base_llm_preferences": current_user.ai_sdk_base_llm_preferences,
        "ai_sdk_thinking_llm_preferences": current_user.ai_sdk_thinking_llm_preferences,
        "check_ambiguity": current_user.check_ambiguity,
        "ai_sdk_info": current_user.ai_sdk_info,
        "chatbot_deepquery": config.deepquery_enabled,
        "default_custom_instructions": {
            "ai_sdk": config.custom_instructions_ai_sdk,
            "chatbot": config.custom_instructions_chatbot,
        },
    }), 200


@settings_bp.route('/api/reset_llm_settings', methods=['POST'])
@login_required
def reset_llm_settings():
    """Reset all user LLM preferences back to server defaults."""
    agent_id = 'global' if not current_user.is_authenticated else current_user.agent_id

    config = get_config(agent_id)

    if not config.user_edit_llm:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    # Determine which component to reset based on the request body
    data = request.json or {}
    component = data.get('component', 'all')

    if component in ('chatbot', 'all'):
        current_user.chatbot_llm_preferences = {}

    if component in ('ai_sdk', 'all'):
        current_user.ai_sdk_base_llm_preferences = {}
        if getattr(config, 'ai_sdk_base_llm_model', None):
            current_user.ai_sdk_base_llm_preferences = {
                'provider': config.ai_sdk_base_llm_provider,
                'model': config.ai_sdk_base_llm_model,
                'temperature': config.ai_sdk_base_llm_temperature,
                'max_tokens': config.ai_sdk_base_llm_max_tokens
            }

        current_user.ai_sdk_thinking_llm_preferences = {}
        if getattr(config, 'ai_sdk_thinking_llm_model', None):
            current_user.ai_sdk_thinking_llm_preferences = {
                'provider': config.ai_sdk_thinking_llm_provider,
                'model': config.ai_sdk_thinking_llm_model,
                'temperature': config.ai_sdk_thinking_llm_temperature,
                'max_tokens': config.ai_sdk_thinking_llm_max_tokens
            }

        current_user.check_ambiguity = config.check_ambiguity

    # Reset chatbot to force recreation with default settings
    current_user.chatbot = None

    return jsonify({"message": "LLM settings reset to defaults"}), 200


@settings_bp.route('/api/update_llm_settings', methods=['POST'])
@login_required
def update_llm_settings():
    """Update user's LLM preferences."""
    agent_id = 'global' if not current_user.is_authenticated else current_user.agent_id

    config = get_config(agent_id)

    if not config.user_edit_llm:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    try:
        data = request.json

        current_user.update_llm_preferences(data)

        # Reset chatbot to force recreation with new LLM settings
        current_user.chatbot = None

        return jsonify({"message": "LLM settings updated successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400
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
    config = get_config()

    from sample_chatbot.engine import TOOL_DEFINITIONS

    frontend_config = {
        "has_ai_sdk_credentials": config.has_ai_sdk_credentials,
        "allow_sync": config.allow_sync,
        "chatbot_feedback": config.effective_feedback_enabled,
        "unstructured_mode": config.unstructured_mode,
        "sync_timeout": config.sync_vdbs_timeout,
        "llm_response_rows_limit": config.llm_response_rows_limit,
        "user_edit_llm": config.user_edit_llm,
        "enable_deep_query": config.deepquery_enabled,
        "chatbot_tools": [
            {
                "name": name,
                "pretty_name": tool_cfg["pretty_name"],
                "aliases": tool_cfg["aliases"],
                "optional": tool_cfg["optional"],
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

    return jsonify(frontend_config)

@settings_bp.route('/update_custom_instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    """Update user's custom instructions and profile."""
    data = request.json
    custom_instructions = data.get('custom_instructions', '')
    user_details = data.get('user_details', '')

    current_user.custom_instructions = custom_instructions
    current_user.user_details = user_details
    current_user.set_custom_instructions()

    return jsonify({"message": "Profile updated successfully"}), 200

@settings_bp.route('/api/llm_settings', methods=['GET'])
@login_required
def get_llm_settings():
    """Return the user's current LLM preferences and cached AI SDK configuration."""
    config = get_config()

    return jsonify({
        "chatbot_llm_defaults": {
            "provider": config.llm_provider.lower(),
            "model": config.llm_model,
            "temperature": config.llm_temperature,
            "max_tokens": config.llm_max_tokens,
        },
        "chatbot_llm_preferences": current_user.chatbot_llm_preferences,
        "ai_sdk_base_llm_preferences": current_user.ai_sdk_base_llm_preferences,
        "ai_sdk_thinking_llm_preferences": current_user.ai_sdk_thinking_llm_preferences,
        "check_ambiguity": current_user.check_ambiguity,
        "ai_sdk_info": current_user.ai_sdk_info,
        "chatbot_deepquery": config.deepquery_enabled,
    }), 200


@settings_bp.route('/reset_llm_settings', methods=['POST'])
@login_required
def reset_llm_settings():
    """Reset all user LLM preferences back to server defaults."""
    config = get_config()

    if not config.user_edit_llm:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    # Determine which component to reset based on the request body
    data = request.json or {}
    component = data.get('component', 'all')

    if component in ('chatbot', 'all'):
        current_user.chatbot_llm_preferences = {}

    if component in ('ai_sdk', 'all'):
        current_user.ai_sdk_base_llm_preferences = {}
        current_user.ai_sdk_thinking_llm_preferences = {}
        current_user.check_ambiguity = True

    # Reset chatbot to force recreation with default settings
    current_user.chatbot = None

    return jsonify({"message": "LLM settings reset to defaults"}), 200


@settings_bp.route('/update_llm_settings', methods=['POST'])
@login_required
def update_llm_settings():
    """Update user's LLM preferences."""
    config = get_config()

    if not config.user_edit_llm:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    try:
        data = request.json

        # Validation helpers
        def validate_temperature(temp):
            if temp is not None and temp != '':
                temp_float = float(temp)
                if not (0.0 <= temp_float <= 2.0):
                    raise ValueError("Temperature must be between 0.0 and 2.0")
                return temp_float
            return None

        def validate_max_tokens(tokens):
            if tokens is not None and tokens != '':
                tokens_int = int(tokens)
                if not (1024 <= tokens_int <= 20000):
                    raise ValueError("Max tokens must be between 1024 and 20000")
                return tokens_int
            return None

        # Update chatbot LLM preferences
        chatbot_llm = data.get('chatbot_llm', {})
        if any(chatbot_llm.values()):
            current_user.chatbot_llm_preferences = {
                'provider': chatbot_llm.get('provider') or None,
                'model': chatbot_llm.get('model') or None,
                'temperature': validate_temperature(chatbot_llm.get('temperature')),
                'max_tokens': validate_max_tokens(chatbot_llm.get('max_tokens'))
            }
            # Remove None values
            current_user.chatbot_llm_preferences = {
                k: v for k, v in current_user.chatbot_llm_preferences.items() if v is not None
            }

        # Update AI SDK base LLM preferences
        ai_sdk_base_llm = data.get('ai_sdk_base_llm', {})
        if any(ai_sdk_base_llm.values()):
            current_user.ai_sdk_base_llm_preferences = {
                'provider': ai_sdk_base_llm.get('provider') or None,
                'model': ai_sdk_base_llm.get('model') or None,
                'temperature': validate_temperature(ai_sdk_base_llm.get('temperature')),
                'max_tokens': validate_max_tokens(ai_sdk_base_llm.get('max_tokens'))
            }
            current_user.ai_sdk_base_llm_preferences = {
                k: v for k, v in current_user.ai_sdk_base_llm_preferences.items() if v is not None
            }

        # Update AI SDK thinking LLM preferences
        ai_sdk_thinking_llm = data.get('ai_sdk_thinking_llm', {})
        if any(ai_sdk_thinking_llm.values()):
            current_user.ai_sdk_thinking_llm_preferences = {
                'provider': ai_sdk_thinking_llm.get('provider') or None,
                'model': ai_sdk_thinking_llm.get('model') or None,
                'temperature': validate_temperature(ai_sdk_thinking_llm.get('temperature')),
                'max_tokens': validate_max_tokens(ai_sdk_thinking_llm.get('max_tokens'))
            }
            current_user.ai_sdk_thinking_llm_preferences = {
                k: v for k, v in current_user.ai_sdk_thinking_llm_preferences.items() if v is not None
            }

        # Update check_ambiguity preference
        check_ambiguity = data.get('check_ambiguity')
        if check_ambiguity is not None:
            current_user.check_ambiguity = bool(check_ambiguity)
            if current_user.chatbot:
                current_user.chatbot.ai_sdk_params['check_ambiguity'] = current_user.check_ambiguity

        # Reset chatbot to force recreation with new LLM settings
        current_user.chatbot = None

        return jsonify({"message": "LLM settings updated successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400

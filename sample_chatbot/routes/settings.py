"""
Handles user settings, custom instructions, and LLM configuration endpoints.
"""

import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.config import get_config
from sample_chatbot.services.ui_preferences import (
    agent_row,
    drop_saved_llm,
    save_agent_instructions,
    save_agent_llm,
    save_profile,
    validate_llm_settings,
)

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
        "input_method": config.input_method,
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
        "context_window": config.llm_context_window,
    }

    if config.data_marketplace_url:
        frontend_config["data_marketplace_url"] = config.data_marketplace_url.rstrip('/')

    frontend_config["default_custom_instructions"] = {
        "ai_sdk": config.custom_instructions_ai_sdk,
        "chatbot": config.custom_instructions_chatbot,
    }
    frontend_config["can_edit_instructions"] = config.user_edit_instructions

    if current_user.is_authenticated and current_user.ai_sdk_info:
        frontend_config["embeddings_token_limit"] = current_user.ai_sdk_info.get("embeddings_token_limit", 0)
    else:
        frontend_config["embeddings_token_limit"] = 0

    frontend_config["is_admin"] = bool(
        current_user.is_authenticated and current_user.is_admin
    )

    return jsonify(frontend_config)

@settings_bp.route('/api/update_custom_instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    """Update user's custom instructions and profile."""
    data = request.json or {}
    custom_instructions = data.get("custom_instructions")
    instruction_entries = None
    if custom_instructions is not None:
        try:
            instruction_entries = _instruction_entries(custom_instructions, data.get("agent_id"))
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except LookupError:
            return jsonify({"error": "Unknown agent."}), 404

    save_profile(
        current_user.id,
        user_details=data.get("user_details") if "user_details" in data else None,
        input_method=data.get("input_method"),
        number_format=data.get("number_format"),
    )
    if "user_details" in data:
        current_user.user_details = data.get("user_details") or ""
        current_user.chatbot = None

    if instruction_entries is not None:
        for agent_id, entry in instruction_entries.items():
            saved_entry = save_agent_instructions(current_user.id, agent_id, entry)
            if agent_id == current_user.agent_id:
                current_user.merge_custom_instructions_for_agent(agent_id, saved_entry)

    return jsonify({"message": "Profile updated successfully"}), 200

def _instruction_entries(custom_instructions, requested_agent):
    """Return {agent_id: entry} after checking each agent can take the edit."""
    if isinstance(custom_instructions, dict) and set(custom_instructions.keys()) <= {"ai_sdk", "chatbot"}:
        config = _require_editable_instructions(requested_agent)
        return {config.id: custom_instructions}

    from sample_chatbot.models.user import _normalize_instruction_map
    normalized = _normalize_instruction_map(custom_instructions)
    entries = {}
    for agent_id, entry in normalized.items():
        config = _require_editable_instructions(agent_id)
        entries[config.id] = entry
    return entries

def _require_editable_instructions(agent_id):
    """Return the agent config, or raise when this user cannot edit its instructions."""
    try:
        config = _resolve_settings_agent(agent_id)
    except PermissionError:
        raise PermissionError("You are not allowed to use this agent.")
    if config is None:
        raise LookupError(agent_id)
    if not config.user_edit_instructions:
        raise PermissionError("Instruction editing is not enabled.")
    return config

@settings_bp.route('/api/llm_settings', methods=['GET'])
@login_required
def get_llm_settings():
    """Return the user's current LLM preferences and cached AI SDK configuration.

    Accepts an optional agent_id so the per-agent Settings modal can show any
    agent's defaults without switching agents. Session preferences only apply
    to the user's current agent; for other agents the frontend falls back to
    its stored per-agent settings.
    """
    agent_id = 'global' if not current_user.is_authenticated else current_user.agent_id

    requested_agent = request.args.get('agent_id')
    is_current_agent = not requested_agent or requested_agent == agent_id
    if not is_current_agent:
        from sample_chatbot import config as chatbot_configs
        requested_config = chatbot_configs._configs.get(requested_agent)
        if requested_config is None:
            return jsonify({"success": False, "error": "Unknown agent."}), 404
        if not requested_config.is_user_allowed(
            username=current_user.id,
            roles=current_user.roles,
            is_admin=current_user.is_admin,
            legacy_permissions_endpoint=current_user.legacy_permissions_endpoint,
        ):
            return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
        agent_id = requested_agent

    config = get_config(agent_id)

    ai_sdk_base_llm_defaults = {}
    if config.ai_sdk_base_llm_model:
        ai_sdk_base_llm_defaults = {
            "provider": config.ai_sdk_base_llm_provider,
            "model": config.ai_sdk_base_llm_model,
            "temperature": config.ai_sdk_base_llm_temperature,
            "max_tokens": config.ai_sdk_base_llm_max_tokens,
        }

    ai_sdk_thinking_llm_defaults = {}
    if config.ai_sdk_thinking_llm_model:
        ai_sdk_thinking_llm_defaults = {
            "provider": config.ai_sdk_thinking_llm_provider,
            "model": config.ai_sdk_thinking_llm_model,
            "temperature": config.ai_sdk_thinking_llm_temperature,
            "max_tokens": config.ai_sdk_thinking_llm_max_tokens,
        }

    sdk_info = current_user.ai_sdk_info or {}
    agent_check_ambiguity = config.check_ambiguity
    check_ambiguity_default = (
        agent_check_ambiguity if agent_check_ambiguity is not None
        else sdk_info.get("check_ambiguity", True)
    )
    saved = agent_row(current_user.id, agent_id)
    saved_llm = saved.get("llm_settings") or {}
    if is_current_agent:
        chatbot_prefs = current_user.chatbot_llm_preferences
        base_prefs = current_user.ai_sdk_base_llm_preferences
        thinking_prefs = current_user.ai_sdk_thinking_llm_preferences
        check_ambiguity = current_user.check_ambiguity
        auto_fixing = current_user.auto_fixing
        auto_fixing_attempts = current_user.auto_fixing_attempts
        use_base = current_user.use_base_llm_for_execution
    else:
        chatbot_prefs = saved_llm.get("chatbot_llm") or {}
        base_prefs = saved_llm.get("ai_sdk_base_llm") or {}
        thinking_prefs = saved_llm.get("ai_sdk_thinking_llm") or {}
        check_ambiguity = saved_llm.get("check_ambiguity")
        auto_fixing = saved_llm.get("auto_fixing")
        auto_fixing_attempts = saved_llm.get("auto_fixing_attempts")
        use_base = saved_llm.get("use_base_llm_for_execution")
    return jsonify({
        "chatbot_llm_defaults": {
            "provider": config.llm_provider.lower(),
            "model": config.llm_model,
            "temperature": config.llm_temperature,
            "max_tokens": config.llm_max_tokens,
            "context_window": config.llm_context_window,
        },
        "ai_sdk_base_llm_defaults": ai_sdk_base_llm_defaults,
        "ai_sdk_thinking_llm_defaults": ai_sdk_thinking_llm_defaults,
        "use_base_llm_for_execution_default": config.use_base_llm_for_execution,
        "check_ambiguity_default": check_ambiguity_default,
        "auto_fixing_default": sdk_info.get("auto_fixing", True),
        "auto_fixing_attempts_default": sdk_info.get("auto_fixing_attempts", 2),
        "use_base_llm_for_execution": use_base,
        "chatbot_llm_preferences": chatbot_prefs,
        "ai_sdk_base_llm_preferences": base_prefs,
        "ai_sdk_thinking_llm_preferences": thinking_prefs,
        "check_ambiguity": check_ambiguity,
        "auto_fixing": auto_fixing,
        "auto_fixing_attempts": auto_fixing_attempts,
        "custom_instructions": saved.get("custom_instructions"),
        "user_edit_llm": config.user_edit_llm,
        "user_edit_instructions": config.user_edit_instructions,
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
        if config.ai_sdk_base_llm_model:
            current_user.ai_sdk_base_llm_preferences = {
                'provider': config.ai_sdk_base_llm_provider,
                'model': config.ai_sdk_base_llm_model,
                'temperature': config.ai_sdk_base_llm_temperature,
                'max_tokens': config.ai_sdk_base_llm_max_tokens
            }

        current_user.ai_sdk_thinking_llm_preferences = {}
        if config.ai_sdk_thinking_llm_model:
            current_user.ai_sdk_thinking_llm_preferences = {
                'provider': config.ai_sdk_thinking_llm_provider,
                'model': config.ai_sdk_thinking_llm_model,
                'temperature': config.ai_sdk_thinking_llm_temperature,
                'max_tokens': config.ai_sdk_thinking_llm_max_tokens
            }

        current_user.apply_ai_sdk_defaults()

    drop_saved_llm(current_user.id, agent_id, component)

    # Reset chatbot to force recreation with default settings
    current_user.chatbot = None

    return jsonify({"message": "LLM settings reset to defaults"}), 200

@settings_bp.route('/api/update_llm_settings', methods=['POST'])
@login_required
def update_llm_settings():
    """Update user's LLM preferences and store them for the next session."""
    data = request.json or {}
    requested_agent = data.get("agent_id")
    try:
        config = _resolve_settings_agent(requested_agent)
    except PermissionError:
        return jsonify({"error": "You are not allowed to use this agent."}), 403
    if config is None:
        return jsonify({"error": "Unknown agent."}), 404

    if not config.user_edit_llm:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    payload = {key: value for key, value in data.items() if key != "agent_id"}

    try:
        if config.id == current_user.agent_id:
            current_user.update_llm_preferences(payload)
            # A null value means "drop this override". update_llm_preferences
            # leaves the previous value in place when the key is null.
            if "ai_sdk_thinking_llm" in payload and payload["ai_sdk_thinking_llm"] is None:
                current_user.ai_sdk_thinking_llm_preferences = {}
            if "use_base_llm_for_execution" in payload and payload["use_base_llm_for_execution"] is None:
                current_user.use_base_llm_for_execution = config.use_base_llm_for_execution
            current_user.chatbot = None
        else:
            validate_llm_settings(config, payload)
        save_agent_llm(current_user.id, config.id, payload)
        return jsonify({"message": "LLM settings updated successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400

def _resolve_settings_agent(agent_id):
    """Return the config for agent_id, or the user's current agent when omitted.

    Raises PermissionError when the user cannot use that agent. Returns None
    when the agent does not exist. Does not create a config for an unknown id.
    """
    from sample_chatbot import config as chatbot_configs

    if not agent_id or agent_id == current_user.agent_id:
        return chatbot_configs._configs.get(current_user.agent_id) or get_config(current_user.agent_id or "global")

    config = chatbot_configs._configs.get(agent_id)
    if config is None:
        return None
    if not config.is_user_allowed(
        username=current_user.id,
        roles=current_user.roles,
        is_admin=current_user.is_admin,
        legacy_permissions_endpoint=current_user.legacy_permissions_endpoint,
    ):
        raise PermissionError(agent_id)
    return config

@settings_bp.route('/api/reset_agent_resources', methods=['POST'])
@login_required
def reset_agent_resources():
    """Restore modifiable skill and knowledge-base toggles for one agent.

    Defaults match a user who has never changed them: user-toggleable skills
    on, user-toggleable knowledge bases off. Agent-managed items stay as the
    agent configured them.
    """
    from utils.database_utils import UserSkills

    data = request.json or {}
    try:
        config = _resolve_settings_agent(data.get('agent_id'))
    except PermissionError:
        return jsonify({"error": "You are not allowed to use this agent."}), 403
    if config is None:
        return jsonify({"error": "Unknown agent."}), 404

    if config.is_unstructured_mode_allowed_for_user(
        username=current_user.id,
        roles=current_user.roles,
        is_admin=current_user.is_admin,
        legacy_permissions_endpoint=current_user.legacy_permissions_endpoint,
    ):
        try:
            from sample_chatbot.services.kb_registry import get_registry_for
            get_registry_for(config).set_active_set(current_user.id, config.id, [])
        except Exception:
            logging.exception(f"[Settings] Could not reset knowledge bases for '{current_user.id}' on '{config.id}'")
            return jsonify({"error": "Knowledge bases could not be reset."}), 500

    UserSkills.clear_agent_prefs(current_user.id, config.id)

    if config.id == current_user.agent_id:
        current_user.chatbot = None

    logging.info(f"[Settings] '{current_user.id}' reset skills and knowledge bases for agent '{config.id}'")
    return jsonify({"message": "Skills and knowledge bases reset to defaults"}), 200


"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import logging

from utils.database_utils import UserUiPreferences
from sample_chatbot.models.user import User, _normalize_instruction_entry

PROFILE_SCOPE = UserUiPreferences.PROFILE_SCOPE
_INPUT_METHODS = ("enter", "ctrl_enter")
_NUMBER_FORMATS = ("1,234.56", "1.234,56")

def profile_for(user_id):
    return UserUiPreferences.get(user_id, PROFILE_SCOPE)

def save_profile(user_id, user_details=None, input_method=None, number_format=None):
    patch = {}
    if user_details is not None:
        patch["user_details"] = user_details
    if input_method in _INPUT_METHODS:
        patch["input_method"] = input_method
    if number_format in _NUMBER_FORMATS:
        patch["number_format"] = number_format
    if patch:
        UserUiPreferences.merge(user_id, PROFILE_SCOPE, patch)
    return profile_for(user_id)

def apply_profile(user):
    """Copy the saved profile onto the in-memory user. Returns the stored row."""
    saved = profile_for(user.id)
    if "user_details" in saved:
        user.user_details = saved.get("user_details") or ""
    return saved

def agent_scope(agent_id):
    """Scope for one agent's row. Kept off the profile scope, which is "user"."""
    return f"agent:{agent_id}"

def agent_row(user_id, agent_id):
    return UserUiPreferences.get(user_id, agent_scope(agent_id))

def save_agent_instructions(user_id, agent_id, entry):
    normalized = _normalize_instruction_entry(entry)
    UserUiPreferences.merge(user_id, agent_scope(agent_id), {"custom_instructions": normalized})
    return normalized

# Each of these is checked and stored on its own. A bad value in one
# does not throw away the others.
_LLM_PARTS = (
    "chatbot_llm",
    "ai_sdk_base_llm",
    "ai_sdk_thinking_llm",
    "check_ambiguity",
    "auto_fixing",
    "auto_fixing_attempts",
    "use_base_llm_for_execution",
)

def save_agent_llm(user_id, agent_id, llm_settings):
    """Update the keys that were sent and leave the rest of the saved LLM row."""
    current = dict(agent_row(user_id, agent_id).get("llm_settings") or {})
    for key, value in (llm_settings or {}).items():
        if key not in _LLM_PARTS:
            continue
        if value is None:
            current.pop(key, None)
        else:
            current[key] = value
    UserUiPreferences.merge(user_id, agent_scope(agent_id), {"llm_settings": current})
    return current

def drop_saved_llm(user_id, agent_id, component):
    """Remove saved LLM overrides so the next session uses config defaults."""
    saved = agent_row(user_id, agent_id)
    llm = dict(saved.get("llm_settings") or {})
    if component in ("chatbot", "all"):
        llm.pop("chatbot_llm", None)
    if component in ("ai_sdk", "all"):
        for key in (
            "ai_sdk_base_llm",
            "ai_sdk_thinking_llm",
            "check_ambiguity",
            "auto_fixing",
            "auto_fixing_attempts",
            "use_base_llm_for_execution",
        ):
            llm.pop(key, None)
    UserUiPreferences.merge(user_id, agent_scope(agent_id), {"llm_settings": llm})

def apply_saved_llm(user, agent_id, llm_settings):
    """Copy each saved LLM option on its own.

    One rejected value is skipped. The options that are still valid are kept.
    """
    if not llm_settings or not getattr(user._config, "user_edit_llm", True):
        return
    applied = False
    for key in _LLM_PARTS:
        if key not in llm_settings:
            continue
        try:
            user.update_llm_preferences({key: llm_settings[key]})
        except (TypeError, ValueError) as e:
            logging.warning(
                f"[Preferences] Ignoring stored {key} for {user.id} on {agent_id}: {e}"
            )
        else:
            applied = True
    if applied:
        user.chatbot = None

def apply_saved_instructions(user, agent_id, instructions):
    """Copy saved instructions only while this agent still lets the user edit them.

    When editing is off, drop any overlay already on the session so the agent
    text from its configuration is what the chat uses.
    """
    if not getattr(user._config, "user_edit_instructions", True):
        current = getattr(user, "custom_instructions_map", None) or {}
        if agent_id in current:
            updated = dict(current)
            updated.pop(agent_id, None)
            user.custom_instructions_map = updated
            user.chatbot = None
        return
    if instructions is not None:
        user.merge_custom_instructions_for_agent(agent_id, instructions)

def apply_agent(user, agent_id):
    """Copy one agent's saved instructions and LLM options onto the user."""
    saved = agent_row(user.id, agent_id)
    apply_saved_instructions(user, agent_id, saved.get("custom_instructions"))
    apply_saved_llm(user, agent_id, saved.get("llm_settings") or {})
    return saved

def validate_llm_settings(config, llm_settings):
    """Raise ValueError when the payload is not a valid LLM preference update.

    Uses a throwaway object so checking another agent's settings does not
    change the session the user is currently in.
    """
    holder = type("LlmCheck", (), {})()
    holder._config = config
    holder.chatbot_llm_preferences = {}
    holder.ai_sdk_base_llm_preferences = {}
    holder.ai_sdk_thinking_llm_preferences = {}
    holder.check_ambiguity = True
    holder.auto_fixing = True
    holder.auto_fixing_attempts = 2
    holder.use_base_llm_for_execution = False
    User.update_llm_preferences(holder, llm_settings)

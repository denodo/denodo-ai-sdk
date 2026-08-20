"""
Skills management endpoints.

System skills live on disk under the AI SDK skills/ directory and are shared
by every user; personal skills are created/uploaded per user and stored in the
same database as the conversation history. Every logged-in user can list and
read the skills that apply to them and manage their own personal skills.

Activation is configured per agent from each agent's Settings modal, so the
list/activate endpoints accept an optional agent_id (defaulting to the user's
current agent). System skill files themselves are managed on disk (or via the
chat tools by authorized users), not through these endpoints.
"""

import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from utils.database_utils import UserSkills
from sample_chatbot import config as chatbot_configs
from sample_chatbot.engine import skills as skills_engine
from sample_chatbot.engine.skills import SkillError

logger = logging.getLogger(__name__)

skills_bp = Blueprint('skills', __name__)

UserSkills.init_db()

def _user():
    """Resolve the underlying user (not the LocalProxy)."""
    return current_user._get_current_object()

def _resolve_agent_config(user, agent_id):
    """Return the ChatbotConfig for agent_id (default: the user's current agent).

    Raises PermissionError if the user may not use that agent, KeyError if the
    agent does not exist.
    """
    if not agent_id or agent_id == user._config.id:
        return user._config
    # Look up without creating: get_config() would silently instantiate an
    # env-based config for unknown ids.
    config = chatbot_configs._configs.get(agent_id)
    if config is None:
        raise KeyError(agent_id)
    if not config.is_user_allowed(
        username=user.id,
        roles=getattr(user, 'roles', []),
        is_admin=getattr(user, 'is_admin', False),
        legacy_permissions_endpoint=getattr(user, 'legacy_permissions_endpoint', False),
    ):
        raise PermissionError(agent_id)
    return config

def _invalidate_chatbot_if_current(user, config):
    """Rebuild the engine only when the change affects the user's current agent."""
    if config.id == user._config.id:
        user.chatbot = None

@skills_bp.route('/api/skills/list', methods=['GET'])
@login_required
def list_skills():
    """List the skills that apply to the user on an agent (system + personal)."""
    user = _user()
    try:
        config = _resolve_agent_config(user, request.args.get('agent_id'))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403

    merged = skills_engine.discover_skills_for_user(user.id, config.id, config.agent_skills, config.disabled_skills)
    skills_list = [
        {
            "skill_name": name,
            "description": meta["description"],
            "references": meta["references"],
            "scope": meta["scope"],
            "active": meta["active"],
            "agent_managed": meta["agent_managed"],
            "feature_disabled": meta.get("feature_disabled", False),
            "valid": meta.get("valid", True),
            "error": meta.get("error"),
        }
        for name, meta in merged.items()
    ]
    return jsonify({
        "success": True,
        "skills": skills_list,
        "agent_id": config.id,
        "can_manage_skills": config.is_skill_management_allowed_for_user(
            username=user.id,
            roles=getattr(user, 'roles', []),
            is_admin=getattr(user, 'is_admin', False),
            legacy_permissions_endpoint=getattr(user, 'legacy_permissions_endpoint', False),
        ),
    })

@skills_bp.route('/api/skills/read/<skill_name>', methods=['GET'])
@login_required
def read_skill(skill_name):
    """Return the full content of one of the user's skills (personal or system)."""
    user = _user()
    try:
        config = _resolve_agent_config(user, request.args.get('agent_id'))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403

    try:
        # Only expose skills that actually apply to this user/agent.
        merged = skills_engine.discover_skills_for_user(user.id, config.id, config.agent_skills, config.disabled_skills)
        if skill_name not in merged:
            return jsonify({"success": False, "error": f"Skill '{skill_name}' was not found."}), 404
        content = skills_engine.read_skill_for_user(user.id, skill_name)
        return jsonify({
            "success": True,
            "skill_name": skill_name,
            "scope": merged[skill_name]["scope"],
            "content": content,
        })
    except SkillError as e:
        return jsonify({"success": False, "error": str(e)}), 400

@skills_bp.route('/api/skills/create', methods=['POST'])
@login_required
def create_skill():
    """Create (or upload) a personal skill for the current user."""
    user = _user()
    data = request.get_json() or {}
    skill_name = (data.get('skill_name') or '').strip()
    content = data.get('content') or ''
    try:
        skills_engine.create_personal_skill(user.id, skill_name, content)
    except SkillError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    user.chatbot = None
    logger.info(f"User '{user.id}' created personal skill '{skill_name}'.")
    return jsonify({"success": True, "skill_name": skill_name, "scope": "personal"})

@skills_bp.route('/api/skills/update/<skill_name>', methods=['PUT'])
@login_required
def update_skill(skill_name):
    """Replace the content of one of the current user's personal skills."""
    user = _user()
    data = request.get_json() or {}
    content = data.get('content') or ''
    try:
        skills_engine.update_personal_skill(user.id, skill_name, content)
    except SkillError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    user.chatbot = None
    return jsonify({"success": True, "skill_name": skill_name, "scope": "personal"})

@skills_bp.route('/api/skills/delete/<skill_name>', methods=['DELETE'])
@login_required
def delete_skill(skill_name):
    """Delete one of the current user's personal skills."""
    user = _user()
    try:
        skills_engine.delete_personal_skill(user.id, skill_name)
    except SkillError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    user.chatbot = None
    logger.info(f"User '{user.id}' deleted personal skill '{skill_name}'.")
    return jsonify({"success": True, "skill_name": skill_name})

@skills_bp.route('/api/skills/activate', methods=['POST'])
@login_required
def activate_skill():
    """Activate/deactivate a skill for the current user on an agent."""
    user = _user()
    data = request.get_json() or {}
    skill_name = (data.get('skill_name') or '').strip()
    active = bool(data.get('active', True))
    try:
        config = _resolve_agent_config(user, data.get('agent_id'))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403

    try:
        # Only skills that apply to this user/agent can be toggled.
        merged = skills_engine.discover_skills_for_user(user.id, config.id, config.agent_skills, config.disabled_skills)
        if skill_name not in merged:
            return jsonify({"success": False, "error": f"Skill '{skill_name}' was not found."}), 404
        if merged[skill_name].get("feature_disabled"):
            return jsonify({"success": False, "error": f"Skill '{skill_name}' is disabled by this agent's configuration and cannot be activated."}), 400
        if merged[skill_name]["agent_managed"]:
            return jsonify({"success": False, "error": f"Skill '{skill_name}' is managed by this agent and cannot be toggled."}), 400
        skills_engine.set_skill_active(user.id, config.id, skill_name, active)
    except SkillError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    _invalidate_chatbot_if_current(user, config)
    return jsonify({"success": True, "skill_name": skill_name, "active": active, "agent_id": config.id})

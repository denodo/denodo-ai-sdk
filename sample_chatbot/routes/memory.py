"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

"""
Memory endpoints for the sample chatbot.

Every logged-in user can list, read, update, and delete the memories they
own for the current agent: 'user' (no link) and 'user-metadata' (personal,
linked). 'metadata' (a fact about the metadata, linked) belongs to the user
and is listed for every agent. Only the agent creates memories. There is no
admin memory UI, but two resource endpoints below stay available to admins
at the API level for a future enhancement where an AI agent will propose semantic layer improvements
based on the user's memories.
"""

import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.engine.memory import (
    MemoryError,
    delete_memory,
    is_memory_enabled,
    list_memories,
    list_metadata_for_resource,
    metadata_link_index,
    read_memory,
    set_memory_enabled,
    user_index_status,
    write_memory,
)
from sample_chatbot.routes.skills import _invalidate_chatbot_if_current, _resolve_agent_config

logger = logging.getLogger(__name__)

memory_bp = Blueprint("memory", __name__)

def _user():
    return current_user._get_current_object()

def _is_admin(user):
    return user.is_admin

def _current_config(user, agent_id=None):
    """Config of the agent whose memories are being viewed (default: current)."""
    return _resolve_agent_config(user, agent_id)

def _share_general(config):
    return config.share_general_memory

def _resolve_scope(user, raw_scope):
    """Config for a client-supplied memory scope; the current agent by default."""
    scope = (raw_scope or "").strip()
    return _resolve_agent_config(user, scope or None)

@memory_bp.route("/api/memories", methods=["GET"])
@login_required
def list_user_memories():
    """List the memories owned by the current user for an agent."""
    user = _user()
    memory_type = (request.args.get("type") or "").strip() or None
    try:
        config = _current_config(user, request.args.get("agent_id"))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    try:
        memories = list_memories(
            user.id,
            memory_type=memory_type,
            link_kind=request.args.get("link_kind"),
            link_name=request.args.get("link_name"),
            query=request.args.get("q"),
            agent_id=config.id,
            include_shared_general=_share_general(config),
        )
        index = user_index_status(user.id, config.id, _share_general(config))
    except MemoryError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({
        "success": True,
        "is_admin": _is_admin(user),
        "agent_id": config.id,
        "share_general_memory": _share_general(config),
        "memories": memories,
        "index": index,
    })

@memory_bp.route("/api/memories/by_resource", methods=["GET"])
@login_required
def list_resource_memories():
    """List metadata memories attached to a view, database, or tag."""
    user = _user()
    if not _is_admin(user):
        return jsonify({"success": False, "error": "Only an admin can browse metadata memories for a resource."}), 403
    try:
        memories = list_metadata_for_resource(
            request.args.get("kind"),
            request.args.get("name"),
        )
    except MemoryError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, "memories": memories})

@memory_bp.route("/api/memories/links", methods=["GET"])
@login_required
def metadata_links():
    """Databases, tags, and views that already have a metadata memory."""
    user = _user()
    if not _is_admin(user):
        return jsonify({"success": False, "error": "Only an admin can browse metadata memories for a resource."}), 403
    try:
        index = metadata_link_index()
    except MemoryError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, **index})

@memory_bp.route("/api/memories/activation", methods=["GET"])
@login_required
def memory_activation():
    """Whether memory formation is on for the current user on an agent."""
    user = _user()
    try:
        config = _resolve_agent_config(user, request.args.get("agent_id"))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    return jsonify({
        "success": True,
        "active": is_memory_enabled(user.id, config.id),
        "agent_id": config.id,
    })

@memory_bp.route("/api/memories/activation", methods=["POST"])
@login_required
def set_memory_activation():
    """Turn memory formation on or off for the current user on an agent."""
    user = _user()
    data = request.get_json() or {}
    try:
        config = _resolve_agent_config(user, data.get("agent_id"))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    active = bool(data.get("active", True))
    set_memory_enabled(user.id, config.id, active)
    _invalidate_chatbot_if_current(user, config)
    logger.info(f"User '{user.id}' set memory formation to {active} for agent '{config.id}'.")
    return jsonify({"success": True, "active": active, "agent_id": config.id})

@memory_bp.route("/api/memories/<memory_type>/<name>", methods=["GET"])
@login_required
def get_memory(memory_type, name):
    """Return one memory owned by the current user.

    ``agent_id`` names the scope the memory lives in (the UI passes the
    listed record's agent). Without it, the current agent is searched,
    including the general agent's shared kinds when sharing is on.
    """
    user = _user()
    scope = (request.args.get("agent_id") or "").strip()
    try:
        config = _resolve_scope(user, scope)
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    try:
        if scope:
            memory = read_memory(user.id, memory_type, name, agent_id=config.id)
        else:
            memory = read_memory(
                user.id, memory_type, name,
                agent_id=config.id, include_shared_general=_share_general(config),
            )
    except MemoryError as exc:
        message = str(exc)
        status = 404 if message.startswith("No ") else 400
        return jsonify({"success": False, "error": message}), status
    return jsonify({"success": True, "memory": memory})

@memory_bp.route("/api/memories", methods=["POST"])
@login_required
def save_memory():
    """Replace a memory the agent already created for the current user."""
    user = _user()
    data = request.get_json() or {}
    try:
        config = _resolve_scope(user, data.get("agent_id"))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    try:
        result = write_memory(
            user.id,
            data.get("memory_type"),
            data.get("name"),
            data.get("description"),
            data.get("body"),
            links=data.get("links"),
            allow_create=False,
            agent_id=config.id,
        )
    except MemoryError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    logger.info(f"User '{user.id}' saved {data.get('memory_type')} memory '{data.get('name')}'.")
    return jsonify({"success": True, **result})

@memory_bp.route("/api/memories/<memory_type>/<name>", methods=["DELETE"])
@login_required
def remove_memory(memory_type, name):
    """Delete a memory owned by the current user from one agent's scope."""
    user = _user()
    try:
        config = _resolve_scope(user, request.args.get("agent_id"))
    except KeyError:
        return jsonify({"success": False, "error": "Unknown agent."}), 404
    except PermissionError:
        return jsonify({"success": False, "error": "You are not allowed to use this agent."}), 403
    try:
        result = delete_memory(user.id, memory_type, name, agent_id=config.id)
    except MemoryError as exc:
        message = str(exc)
        status = 404 if message.startswith("No ") else 400
        return jsonify({"success": False, "error": message}), status
    return jsonify({"success": True, **result})

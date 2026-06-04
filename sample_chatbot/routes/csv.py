"""
Knowledge-base / CSV management endpoints.

The KB is one shared vector store per chatbot (agent). All registered
collections live in that store; per-user activation is tracked in a special
config doc via KBRegistry. Users see every collection in the chatbot — they
subscribe (activate) the ones they want included in their knowledge_query.
"""

import io
import os
import re
import json
import logging

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user

from utils.utils import delete_documents_by_database_name
from sample_chatbot.services.csv_service import CSVService
from sample_chatbot.services.kb_registry import get_registry_for
from sample_chatbot.extensions import get_unstructured_vector_store
from sample_chatbot.utils.csv_utils import (
    collection_to_csv_bytes,
    csv_to_documents,
    detect_csv_delimiter,
    generate_csv_description,
    validate_csv_path,
)

logger = logging.getLogger(__name__)

csv_bp = Blueprint('csv', __name__)

@csv_bp.before_request
def check_csv_permissions():
    """
    Intercepts ALL calls to /api/csv/* and blocks them
    if the user lacks the required roles or permissions for unstructured mode.
    """
    if request.method == 'OPTIONS':
        return

    if not current_user.is_authenticated:
        return

    user = current_user._get_current_object()
    config = user._config

    # Evaluate if the user is allowed to use the CSV
    if not config.is_unstructured_mode_allowed_for_user(
        username=user.id,
        roles=getattr(user, 'roles', []),
        is_admin=getattr(user, 'is_admin', False),
        legacy_permissions_endpoint=getattr(user, 'legacy_permissions_endpoint', False)
    ):
        logger.warning(f"[Security] User '{user.id}' attempted to access '{request.path}' without CSV permissions.")
        return jsonify({"success": False, "error": "You do not have permission to use the CSV Knowledge Base."}), 403

def get_csv_service():
    return CSVService(current_app.config.get('UPLOAD_FOLDER', 'uploads'))

def _user():
    """Resolve the underlying user (not the LocalProxy)."""
    return current_user._get_current_object()

def _present_source(meta, user, agent_id):
    """Shape a registry entry for the API."""
    csv_path = meta.get("csv_path") or ""
    path_valid, _ = validate_csv_path(csv_path) if csv_path else (False, None)
    active_by_user = meta.get("active_by_user") or {}
    user_agents = active_by_user.get(user.id) or []
    can_subscribe = _can_subscribe(meta, user)
    return {
        "source_name": meta["name"],
        "description": meta.get("description", ""),
        "delimiter": meta.get("delimiter", ";"),
        "document_count": meta.get("num_rows", 0),
        "last_vectorized": meta.get("last_vectorized"),
        # `active` is whether this collection is on for THIS user on THIS agent.
        # If the user cannot subscribe (e.g. admin viewing someone else's
        # private collection) it's never active regardless of registry state.
        "active": can_subscribe and (agent_id in user_agents),
        "owner": meta.get("owner"),
        "is_owner": meta.get("owner") == user.id,
        "vectorized_columns": meta.get("vectorized_columns", []),
        "private": bool(meta.get("private", False)),
        "path_valid": path_valid,
        # Per-row capability flags so the UI can render the right controls.
        "can_subscribe": can_subscribe,
        "can_delete": _can_delete(meta, user),
        "can_edit": _can_edit(meta, user),
        "can_make_public": _can_make_public(meta, user),
        "can_make_private": _can_make_private(meta, user),
    }


def _is_admin(user):
    return bool(getattr(user, "is_admin", False))


def _is_visible_to(meta, user):
    """Public collections are visible to everyone; private ones to their owner
    AND to admins (admins see them so they can clean them up)."""
    if not meta.get("private"):
        return True
    if meta.get("owner") == user.id:
        return True
    return _is_admin(user)


def _can_subscribe(meta, user):
    """May this user activate/deactivate or download this collection?"""
    if not meta.get("private"):
        return True
    return meta.get("owner") == user.id


def _can_delete(meta, user):
    """Owner or any admin may delete a collection."""
    if meta.get("owner") == user.id:
        return True
    return _is_admin(user)


def _can_edit(meta, user):
    """Description edits — owner only (same intent as before)."""
    return meta.get("owner") == user.id


def _can_make_public(meta, user):
    """Toggling a collection to public requires admin + ownership."""
    return _is_admin(user) and meta.get("owner") == user.id


def _can_make_private(meta, user):
    """Owner may always make their own collection private."""
    return meta.get("owner") == user.id


# Collection names are used as identifiers in the vector store, in metadata
# filters, in URLs (e.g. /api/csv/download/<name>) and in the system prompt;
# we want them safe across all of those layers.
_SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _validate_source_name(name):
    """Return (ok_name, error_message)."""
    if not name or not isinstance(name, str):
        return None, "source_name is required"
    if not _SOURCE_NAME_RE.match(name):
        return None, (
            "source_name must be 1-80 characters and may only contain letters, "
            "digits, underscore, hyphen, or dot."
        )
    if ".." in name or name in {".", ".."}:
        return None, "source_name cannot contain '..'"
    return name, None

@csv_bp.route('/api/csv/list', methods=['GET'])
@login_required
def list_csv_sources():
    user = _user()
    agent_id = user._config.id
    registry = get_registry_for(user._config)
    collections = registry.list_collections()
    sources = [
        _present_source(meta, user, agent_id)
        for meta in collections.values()
        if _is_visible_to(meta, user)
    ]
    sources.sort(key=lambda s: s["source_name"])
    active_sources = [s["source_name"] for s in sources if s["active"]]
    logger.info(f"[CSV] '{user.id}' on agent '{agent_id}': {len(sources)} collections, {len(active_sources)} active")
    return jsonify({
        "success": True,
        "sources": sources,
        "active_sources": active_sources,
        "agent_id": agent_id,
        "current_user_is_admin": _is_admin(user),
    }), 200


@csv_bp.route('/api/csv/scan', methods=['GET'])
@login_required
def scan_csv_folder():
    """Files in sample_data/unstructured/ that aren't registered yet."""
    user = _user()
    registry = get_registry_for(user._config)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scan_folder = os.path.join(base_dir, 'sample_data', 'unstructured')

    if not os.path.exists(scan_folder):
        return jsonify({"success": True, "files": [], "message": "Scan folder does not exist"}), 200

    existing = set(registry.list_collections().keys())
    scanned = []
    try:
        for filename in os.listdir(scan_folder):
            if not filename.lower().endswith('.csv'):
                continue
            source_name = os.path.splitext(filename)[0]
            if source_name in existing:
                continue
            scanned.append({
                "source_name": source_name,
                "path": os.path.join(scan_folder, filename),
                "filename": filename,
            })
    except Exception as e:
        logger.exception(f"[CSV] Error scanning folder {scan_folder}: {e}")
        return jsonify({"success": False, "error": f"Error scanning folder: {str(e)}"}), 500

    return jsonify({"success": True, "files": scanned, "scan_folder": scan_folder}), 200

@csv_bp.route('/api/csv/preview', methods=['POST'])
@login_required
def preview_csv():
    """Return columns + sample rows so the UI can offer the multi-select."""
    csv_service = get_csv_service()
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        file_path, is_temp = csv_service.save_temp_file(file)
    else:
        data = request.json or {}
        file_path = data.get('path')
        is_temp = False
        if not file_path:
            return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400

    try:
        result = csv_service.get_preview(file_path, num_rows=5, allow_temp=is_temp)
        return jsonify(result), 200 if result.get("success") else 400
    finally:
        if is_temp:
            csv_service.cleanup_temp_file(file_path)

@csv_bp.route('/api/csv/generate_description', methods=['POST'])
@login_required
def generate_csv_description_endpoint():
    user = _user()
    llm = user.get_chatbot_llm()
    csv_service = get_csv_service()

    vectorized_columns = None
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        file_path, is_temp = csv_service.save_temp_file(file)
        delimiter = request.form.get('delimiter')
        vectorized_columns = _parse_columns(request.form.get('vectorized_columns'))
    else:
        data = request.json or {}
        file_path = data.get('path')
        delimiter = data.get('delimiter')
        is_temp = False
        if not file_path:
            return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400
        vectorized_columns = _parse_columns(data.get('vectorized_columns'))

    try:
        result = csv_service.generate_description(
            llm, file_path, delimiter, allow_temp=is_temp,
            vectorized_columns=vectorized_columns,
        )
        return jsonify(result), 200 if result.get("success") else 400
    finally:
        if is_temp:
            csv_service.cleanup_temp_file(file_path)

def _parse_columns(value):
    if value is None:
        return None
    if isinstance(value, list):
        return [str(c) for c in value if c]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(c) for c in decoded if c]
        except ValueError:
            return [c.strip() for c in value.split(",") if c.strip()]
    return None


@csv_bp.route('/api/csv/add', methods=['POST'])
@login_required
def add_csv_source():
    """
    Register a new collection in the chatbot's KB. If a collection with the
    same name already exists the request is rejected (collision detection).
    """
    user = _user()
    config = user._config
    registry = get_registry_for(config)
    store = get_unstructured_vector_store(config)
    csv_service = get_csv_service()

    def _truthy(val, default=False):
        if isinstance(val, bool):
            return val
        if val is None:
            return default
        return str(val).lower() in ("1", "true", "yes", "on")

    try:
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({"success": False, "error": "No file selected"}), 400
            file_path = csv_service.save_uploaded_file(file)
            raw_source_name = request.form.get('source_name') or os.path.splitext(file.filename)[0]
            auto_detect = request.form.get('auto_detect_delimiter', 'true').lower() == 'true'
            auto_describe = request.form.get('auto_generate_description', 'false').lower() == 'true'
            delimiter_arg = request.form.get('delimiter', ';')
            description_arg = request.form.get('description', '')
            vectorized_columns = _parse_columns(request.form.get('vectorized_columns'))
            private = _truthy(request.form.get('private'), default=False)
        else:
            data = request.json or {}
            file_path = data.get('path')
            if not file_path:
                return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400
            raw_source_name = data.get('source_name') or os.path.splitext(os.path.basename(file_path))[0]
            auto_detect = data.get('auto_detect_delimiter', True)
            auto_describe = data.get('auto_generate_description', False)
            delimiter_arg = data.get('delimiter', ';')
            description_arg = data.get('description', '')
            vectorized_columns = _parse_columns(data.get('vectorized_columns'))
            private = _truthy(data.get('private'), default=False)

        # The path must always be inside an allowed root (uploads/ or
        # sample_data/unstructured/) regardless of which branch we came from.
        path_ok, path_err = validate_csv_path(file_path)
        if not path_ok:
            return jsonify({"success": False, "error": path_err}), 400

        # Stop early on names that would break URL routing, metadata filters
        # or the system prompt.
        source_name, name_err = _validate_source_name(raw_source_name)
        if name_err:
            return jsonify({"success": False, "error": name_err}), 400

        delimiter = detect_csv_delimiter(file_path) if auto_detect else delimiter_arg
        description = (generate_csv_description(user.get_chatbot_llm(), file_path, delimiter,
                                                vectorized_columns=vectorized_columns)
                       if auto_describe else description_arg)

        if not description:
            return jsonify({"success": False, "error": "Description is required"}), 400

        if registry.has_collection(source_name):
            return jsonify({
                "success": False,
                "error": f"A collection named '{source_name}' already exists in this chatbot. "
                         f"Rename your CSV or activate the existing one.",
            }), 409

        # Non-admin users can only create private collections.
        if not _is_admin(user) and not private:
            logger.info(f"[CSV] forcing private=True for non-admin user '{user.id}'")
            private = True

        docs = csv_to_documents(
            file_path,
            delimiter=delimiter,
            source_name=source_name,
            vectorized_columns=vectorized_columns,
            embeddings=store.embeddings,
        )
        if not docs:
            return jsonify({"success": False, "error": "Failed to create documents from CSV"}), 400

        logger.info(f"[CSV] User '{user.id}' adding collection '{source_name}' ({len(docs)} rows)")
        store.add_views(docs, parallel=True)

        # Re-derive the actually vectorized columns from the first doc (in case
        # the request list referenced columns that don't exist in the CSV).
        actual_columns = json.loads(docs[0].metadata.get("vectorized_columns") or "[]")

        meta = registry.register_collection(
            name=source_name,
            csv_path=file_path,
            description=description,
            delimiter=delimiter,
            vectorized_columns=actual_columns,
            owner=user.id,
            num_rows=len(docs),
            auto_activate_for=user.id,
            auto_activate_agent=user._config.id,
            private=private,
        )
        return jsonify({
            "success": True,
            "source_name": source_name,
            "metadata": _present_source(meta, user, user._config.id),
        }), 200
    except Exception as e:  # noqa: BLE001
        logger.exception("[CSV] add_csv_source failed")
        return jsonify({"success": False, "error": f"Could not add CSV: {e}"}), 400


# --------------------------------------------------------------------------- delete

@csv_bp.route('/api/csv/delete/<source_name>', methods=['DELETE'])
@login_required
def delete_csv_source(source_name):
    """Only the owner may delete the underlying collection."""
    user = _user()
    config = user._config
    registry = get_registry_for(config)
    store = get_unstructured_vector_store(config)
    data = request.json or {}
    delete_file = data.get('delete_file', False)

    meta = registry.get_collection(source_name)
    if meta is None:
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    if not _can_delete(meta, user):
        return jsonify({
            "success": False,
            "error": f"Only the owner ('{meta.get('owner')}') or an admin can delete this collection. "
                     f"Deactivate it instead.",
        }), 403

    deleted = delete_documents_by_database_name(store, [source_name])
    logger.info(f"[CSV] Deleted {deleted} docs for collection '{source_name}'")
    registry.delete_collection(source_name)

    if delete_file:
        path = meta.get("csv_path")
        if path:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Could not delete CSV file: {e}")

    return jsonify({"success": True}), 200


# --------------------------------------------------------------------------- activate

@csv_bp.route('/api/csv/activate', methods=['POST'])
@login_required
def activate_csv_sources():
    user = _user()
    registry = get_registry_for(user._config)
    data = request.json or {}
    source_name = data.get('source_name')
    active = bool(data.get('active', True))
    if not source_name:
        return jsonify({"success": False, "error": "source_name is required"}), 400

    existing = registry.get_collection(source_name)
    if existing is None or not _is_visible_to(existing, user):
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    if not _can_subscribe(existing, user):
        return jsonify({
            "success": False,
            "error": "You can't activate this collection. It belongs to another user and is private.",
        }), 403

    agent_id = user._config.id
    meta = registry.set_active(source_name, user.id, agent_id, active)
    if meta is None:
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    return jsonify({
        "success": True,
        "source_name": source_name,
        "active": active,
        "agent_id": agent_id,
        "active_sources": registry.active_for_user(user.id, agent_id),
    }), 200


# --------------------------------------------------------------------------- description

@csv_bp.route('/api/csv/update_description', methods=['POST'])
@login_required
def update_csv_description():
    """Only the owner can rewrite the description."""
    user = _user()
    registry = get_registry_for(user._config)
    data = request.json or {}
    source_name = data.get('source_name')
    description = (data.get('description') or '').strip()
    if not source_name:
        return jsonify({"success": False, "error": "source_name is required"}), 400
    if not description:
        return jsonify({"success": False, "error": "description is required"}), 400

    meta = registry.get_collection(source_name)
    if meta is None:
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    if meta.get("owner") and meta["owner"] != user.id:
        return jsonify({"success": False, "error": "Only the owner can edit the description."}), 403

    registry.update_description(source_name, description)
    return jsonify({"success": True, "description": description}), 200


# --------------------------------------------------------------------------- access

@csv_bp.route('/api/csv/set_private', methods=['POST'])
@login_required
def set_csv_private():
    """Owner-only: toggle the private flag of a collection."""
    user = _user()
    registry = get_registry_for(user._config)
    data = request.json or {}
    source_name = data.get('source_name')
    private = bool(data.get('private'))
    if not source_name:
        return jsonify({"success": False, "error": "source_name is required"}), 400

    meta = registry.get_collection(source_name)
    if meta is None:
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    if meta.get("owner") != user.id:
        return jsonify({"success": False, "error": "Only the owner can change visibility."}), 403
    # Making a collection public is an admin-only action.
    if not private and not _is_admin(user):
        return jsonify({
            "success": False,
            "error": "Only an admin can publish a collection. You can keep it private.",
        }), 403

    updated = registry.set_private(source_name, private)
    return jsonify({"success": True, "metadata": _present_source(updated, user, user._config.id)}), 200

# --------------------------------------------------------------------------- download

@csv_bp.route('/api/csv/download/<source_name>', methods=['GET'])
@login_required
def download_csv(source_name):
    """Return the CSV with an extra `embedding` column reconstructed from the vector store."""
    user = _user()
    config = user._config
    registry = get_registry_for(config)
    store = get_unstructured_vector_store(config)

    meta = registry.get_collection(source_name)
    if meta is None or not _is_visible_to(meta, user):
        return jsonify({"success": False, "error": f"Source '{source_name}' not found"}), 404
    # Admins can see other people's private collections so they can delete
    # them, but they can't download the contents.
    if not _can_subscribe(meta, user):
        return jsonify({
            "success": False,
            "error": "You don't have access to download this private collection.",
        }), 403

    num_rows = int(meta.get("num_rows") or 0)
    if num_rows == 0:
        return jsonify({"success": False, "error": "Collection has no rows"}), 400

    csv_bytes = collection_to_csv_bytes(store, source_name, num_rows)
    if not csv_bytes:
        return jsonify({"success": False, "error": "No rows could be reconstructed"}), 500

    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{source_name}_with_embeddings.csv",
    )

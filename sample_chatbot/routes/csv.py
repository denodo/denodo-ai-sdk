"""
Handles CSV file upload, management, and preview endpoints.
"""

import os
import logging

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from sample_chatbot.services.csv_service import CSVService
from sample_chatbot.utils.csv_utils import (
    detect_csv_delimiter,
    generate_csv_description,
)

logger = logging.getLogger(__name__)

csv_bp = Blueprint('csv', __name__)

def get_csv_service():
    """Get CSV service instance."""
    return CSVService(current_app.config.get('UPLOAD_FOLDER', 'uploads'))

@csv_bp.route('/csv/list', methods=['GET'])
@login_required
def list_csv_sources():
    """List all CSV sources for the current user."""
    logger.debug(f"[CSV] Listing sources for user '{current_user.id}'")
    sources = current_user.get_csv_sources_metadata()
    logger.info(f"[CSV] User '{current_user.id}' has {len(sources)} CSV sources, {len(current_user.active_csv_sources)} active")
    return jsonify({
        "success": True,
        "sources": sources,
        "active_sources": current_user.active_csv_sources
    }), 200

@csv_bp.route('/csv/add', methods=['POST'])
@login_required
def add_csv_source():
    """
    Add a new CSV source. Supports both file upload and path reference.

    For file upload: multipart/form-data with 'file', 'description', optional 'delimiter',
                     'auto_detect_delimiter', 'auto_generate_description'
    For path reference: JSON with 'path', 'description', optional 'delimiter', 'source_name'
    """
    csv_service = get_csv_service()
    llm = current_app.config.get('LLM')

    # Check if this is a file upload or path reference
    if 'file' in request.files:
        # File upload mode
        file = request.files['file']
        if file.filename == '':
            logger.warning(f"[CSV] User '{current_user.id}' attempted to add CSV with no file selected")
            return jsonify({"success": False, "error": "No file selected"}), 400

        logger.info(f"[CSV] User '{current_user.id}' uploading CSV file: {file.filename}")

        # Save the file
        file_path = csv_service.save_uploaded_file(file)
        logger.debug(f"[CSV] File saved to: {file_path}")

        # Get parameters
        source_name = request.form.get('source_name') or os.path.splitext(file.filename)[0]
        auto_detect = request.form.get('auto_detect_delimiter', 'true').lower() == 'true'
        auto_describe = request.form.get('auto_generate_description', 'false').lower() == 'true'

        # Auto-detect delimiter if requested
        if auto_detect:
            delimiter = detect_csv_delimiter(file_path)
            logger.debug(f"[CSV] Auto-detected delimiter: '{delimiter}'")
        else:
            delimiter = request.form.get('delimiter', ';')

        # Auto-generate description if requested
        if auto_describe:
            logger.debug(f"[CSV] Auto-generating description for '{source_name}'")
            description = generate_csv_description(llm, file_path, delimiter)
        else:
            description = request.form.get('description', '')

        if not description:
            logger.warning(f"[CSV] User '{current_user.id}' attempted to add CSV '{source_name}' without description")
            return jsonify({"success": False, "error": "Description is required"}), 400

    else:
        # Path reference mode (JSON body)
        data = request.json or {}
        file_path = data.get('path')
        if not file_path:
            logger.warning(f"[CSV] User '{current_user.id}' attempted to add CSV without file or path")
            return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400

        logger.info(f"[CSV] User '{current_user.id}' adding CSV from path: {file_path}")

        source_name = data.get('source_name') or os.path.splitext(os.path.basename(file_path))[0]
        auto_detect = data.get('auto_detect_delimiter', True)
        auto_describe = data.get('auto_generate_description', False)

        if auto_detect:
            delimiter = detect_csv_delimiter(file_path)
            logger.debug(f"[CSV] Auto-detected delimiter: '{delimiter}'")
        else:
            delimiter = data.get('delimiter', ';')

        if auto_describe:
            logger.debug(f"[CSV] Auto-generating description for '{source_name}'")
            description = generate_csv_description(llm, file_path, delimiter)
        else:
            description = data.get('description', '')

        if not description:
            logger.warning(f"[CSV] User '{current_user.id}' attempted to add CSV '{source_name}' without description")
            return jsonify({"success": False, "error": "Description is required"}), 400

    # Add the CSV source
    logger.info(f"[CSV] Adding source '{source_name}' for user '{current_user.id}' (delimiter='{delimiter}')")
    result = current_user.add_csv_source(
        source_name=source_name,
        csv_file_path=file_path,
        description=description,
        delimiter=delimiter,
        auto_activate=True
    )

    if result.get("success"):
        logger.info(f"[CSV] Successfully added source '{source_name}' for user '{current_user.id}'")
        return jsonify(result), 200
    else:
        logger.error(f"[CSV] Failed to add source '{source_name}': {result.get('error')}")
        return jsonify(result), 400

@csv_bp.route('/csv/delete/<source_name>', methods=['DELETE'])
@login_required
def delete_csv_source(source_name):
    """Delete a CSV source."""
    data = request.json or {}
    delete_file = data.get('delete_file', False)

    logger.info(f"[CSV] User '{current_user.id}' deleting source '{source_name}' (delete_file={delete_file})")
    result = current_user.remove_csv_source(source_name, delete_file=delete_file)

    if result.get("success"):
        logger.info(f"[CSV] Successfully deleted source '{source_name}' for user '{current_user.id}'")
        return jsonify(result), 200
    else:
        logger.warning(f"[CSV] Failed to delete source '{source_name}': {result.get('error')}")
        return jsonify(result), 404

@csv_bp.route('/csv/activate', methods=['POST'])
@login_required
def activate_csv_sources():
    """Activate or deactivate a single CSV source."""
    data = request.json or {}
    source_name = data.get('source_name')
    active = data.get('active', True)

    if not source_name:
        return jsonify({"success": False, "error": "source_name is required"}), 400

    action = "activating" if active else "deactivating"
    logger.info(f"[CSV] User '{current_user.id}' {action} source '{source_name}'")
    result = current_user.set_csv_active(source_name, active)

    if result.get("success"):
        logger.info(f"[CSV] Source '{source_name}' is now {'active' if active else 'inactive'} for user '{current_user.id}'")
        return jsonify({
            "success": True,
            "source_name": source_name,
            "active": active,
            "active_sources": current_user.active_csv_sources
        }), 200
    else:
        logger.warning(f"[CSV] Failed to {action[:-3]}e source '{source_name}': {result.get('error')}")
        return jsonify(result), 404

@csv_bp.route('/csv/update_description', methods=['POST'])
@login_required
def update_csv_description():
    """Update the description of a CSV source."""
    data = request.json or {}
    source_name = data.get('source_name')
    description = data.get('description')

    if not source_name:
        return jsonify({"success": False, "error": "source_name is required"}), 400

    if not description:
        return jsonify({"success": False, "error": "description is required"}), 400

    logger.info(f"[CSV] User '{current_user.id}' updating description for source '{source_name}'")
    result = current_user.update_csv_description(source_name, description)

    if result.get("success"):
        logger.debug(f"[CSV] Description updated for source '{source_name}'")
        return jsonify(result), 200
    else:
        logger.warning(f"[CSV] Failed to update description for '{source_name}': {result.get('error')}")
        return jsonify(result), 404

@csv_bp.route('/csv/restore', methods=['POST'])
@login_required
def restore_csv_sources():
    """
    Restore CSV sources from saved configurations (from localStorage).
    """
    data = request.json or {}
    csv_configs = data.get('csv_configs', [])

    if not csv_configs:
        logger.debug(f"[CSV] User '{current_user.id}' restore called with no configs")
        return jsonify({"success": True, "restored": [], "failed": [], "skipped": []}), 200

    logger.info(f"[CSV] User '{current_user.id}' restoring {len(csv_configs)} CSV sources")
    result = current_user.restore_csv_sources(csv_configs)

    logger.info(f"[CSV] Restore complete: {len(result['restored'])} restored, {len(result['failed'])} failed, {len(result['skipped'])} skipped")
    return jsonify({
        "success": True,
        "restored": result["restored"],
        "failed": result["failed"],
        "skipped": result["skipped"],
        "active_sources": current_user.active_csv_sources
    }), 200

@csv_bp.route('/csv/preview', methods=['POST'])
@login_required
def preview_csv():
    """Get a preview of a CSV file (for UI display before adding)."""
    csv_service = get_csv_service()

    # Handle both file upload and path
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        logger.debug(f"[CSV] User '{current_user.id}' previewing uploaded file: {file.filename}")
        file_path, is_temp = csv_service.save_temp_file(file)
    else:
        data = request.json or {}
        file_path = data.get('path')
        is_temp = False
        if not file_path:
            return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400
        logger.debug(f"[CSV] User '{current_user.id}' previewing file at path: {file_path}")

    try:
        result = csv_service.get_preview(file_path, num_rows=5)
        if result.get("success"):
            logger.debug(f"[CSV] Preview successful: {len(result.get('columns', []))} columns, {len(result.get('rows', []))} rows")
        else:
            logger.warning(f"[CSV] Preview failed: {result.get('error')}")
        return jsonify(result), 200 if result.get("success") else 400
    finally:
        if is_temp:
            csv_service.cleanup_temp_file(file_path)

@csv_bp.route('/csv/generate_description', methods=['POST'])
@login_required
def generate_csv_description_endpoint():
    """Generate a description for a CSV file using the LLM."""
    csv_service = get_csv_service()
    llm = current_app.config.get('LLM')

    # Handle both file upload and path
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        logger.info(f"[CSV] User '{current_user.id}' generating description for uploaded file: {file.filename}")
        file_path, is_temp = csv_service.save_temp_file(file)
        delimiter = request.form.get('delimiter')
    else:
        data = request.json or {}
        file_path = data.get('path')
        delimiter = data.get('delimiter')
        is_temp = False
        if not file_path:
            return jsonify({"success": False, "error": "Either 'file' or 'path' is required"}), 400
        logger.info(f"[CSV] User '{current_user.id}' generating description for file: {file_path}")

    try:
        result = csv_service.generate_description(llm, file_path, delimiter)
        if result.get("success"):
            logger.info(f"[CSV] Description generated successfully for user '{current_user.id}'")
            logger.debug(f"[CSV] Generated description: {result.get('description', '')[:100]}...")
        else:
            logger.warning(f"[CSV] Description generation failed: {result.get('error')}")
        return jsonify(result), 200 if result.get("success") else 400
    finally:
        if is_temp:
            csv_service.cleanup_temp_file(file_path)

@csv_bp.route('/csv/scan', methods=['GET'])
@login_required
def scan_csv_folder():
    """
    Scan the sample_data/unstructured folder for CSV files.

    Returns files that are not yet added as sources, with their names
    (filename without .csv extension) and paths.
    """
    # Get the path to the sample_data/unstructured folder
    # This is relative to the sample_chatbot directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scan_folder = os.path.join(base_dir, 'sample_data', 'unstructured')

    logger.debug(f"[CSV] User '{current_user.id}' scanning folder: {scan_folder}")

    if not os.path.exists(scan_folder):
        logger.debug(f"[CSV] Scan folder does not exist: {scan_folder}")
        return jsonify({
            "success": True,
            "files": [],
            "message": "Scan folder does not exist"
        }), 200

    # Get currently configured source names
    existing_sources = {s["source_name"] for s in current_user.get_csv_sources_metadata()}

    # Scan for CSV files
    scanned_files = []
    try:
        for filename in os.listdir(scan_folder):
            if filename.lower().endswith('.csv'):
                source_name = os.path.splitext(filename)[0]
                # Only include if not already configured
                if source_name not in existing_sources:
                    file_path = os.path.join(scan_folder, filename)
                    scanned_files.append({
                        "source_name": source_name,
                        "path": file_path,
                        "filename": filename
                    })
    except Exception as e:
        logger.error(f"[CSV] Error scanning folder {scan_folder}: {e}")
        return jsonify({
            "success": False,
            "error": f"Error scanning folder: {str(e)}"
        }), 500

    logger.info(f"[CSV] Scanned sample_data/unstructured folder for user '{current_user.id}': found {len(scanned_files)} new CSV files")
    return jsonify({
        "success": True,
        "files": scanned_files,
        "scan_folder": scan_folder
    }), 200

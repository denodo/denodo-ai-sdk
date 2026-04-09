"""
Handles feedback submission endpoints.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.config import get_config
from sample_chatbot.reporting import update_feedback_in_report
from sample_chatbot.extensions import report_lock

reporting_bp = Blueprint('reporting', __name__)

_HTTP_STATUS_BY_ERROR = {
    "uuid_not_found": 404,
    "report_directory_missing": 500,
    "report_csv_field_limit": 500,
    "report_csv_parse_error": 500,
    "report_memory_limit": 500,
}

@reporting_bp.route('/api/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Submit feedback for a chatbot response."""

    # Capture the actual user object, not the proxy
    user_obj = current_user._get_current_object()
    config = get_config(user_obj.agent_id)

    if not config.reporting_enabled:
        return jsonify({"success": False, "message": "Feedback reporting is disabled"}), 400

    data = request.json
    uuid = data.get('uuid')
    feedback_value = data.get('feedback_value', '')  # 'positive', 'negative'
    feedback_details = data.get('feedback_details', '')

    if not uuid:
        return jsonify({"success": False, "message": "Missing UUID"}), 400

    result = update_feedback_in_report(
        report_lock,
        config.report_max_size,
        uuid,
        feedback_value,
        feedback_details,
        config.reports_folder
    )

    if result.get("success"):
        return jsonify({"success": True, "message": "Feedback saved successfully"}), 200

    error = result.get("error", "unknown")
    message = result.get("message", "Failed to save feedback.")
    status = _HTTP_STATUS_BY_ERROR.get(error, 500)
    return jsonify({"success": False, "message": message, "error": error}), status

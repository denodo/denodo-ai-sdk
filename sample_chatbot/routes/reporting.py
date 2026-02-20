"""
Handles feedback submission endpoints.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required

from sample_chatbot.config import get_config
from sample_chatbot.reporting import update_feedback_in_report
from sample_chatbot.extensions import report_lock

reporting_bp = Blueprint('reporting', __name__)

@reporting_bp.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Submit feedback for a chatbot response."""
    config = get_config()

    if not config.reporting_enabled:
        return jsonify({"success": False, "message": "Feedback reporting is disabled"}), 400

    data = request.json
    uuid = data.get('uuid')
    feedback_value = data.get('feedback_value', '')  # 'positive', 'negative'
    feedback_details = data.get('feedback_details', '')

    if not uuid:
        return jsonify({"success": False, "message": "Missing UUID"}), 400

    success = update_feedback_in_report(
        report_lock,
        config.report_max_size,
        uuid,
        feedback_value,
        feedback_details
    )

    if success:
        return jsonify({"success": True, "message": "Feedback saved successfully"}), 200
    else:
        return jsonify({"success": False, "message": "Failed to save feedback. UUID not found."}), 404

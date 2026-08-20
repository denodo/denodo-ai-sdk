"""
Handles DeepQuery report generation endpoints.
"""

import logging
import requests

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sample_chatbot.config import get_config

deepquery_bp = Blueprint('deepquery', __name__)

@deepquery_bp.route('/api/generate_report', methods=['POST'])
@login_required
def generate_report():
    """Generate an HTML report from DeepQuery metadata by calling the generateDeepQueryReport endpoint."""

    # Capture the actual user object, not the proxy
    user_obj = current_user._get_current_object()
    config = get_config(user_obj.agent_id)

    try:
        data = request.json
        deepquery_metadata = data.get('deepquery_metadata')
        color_palette = data.get('color_palette', 'red')
        language = data.get('language', 'English')

        if not deepquery_metadata:
            return jsonify({"error": "Missing deepquery_metadata"}), 400

        # Make request to the generateDeepQueryReport endpoint using the logged-in
        # user's credentials, matching the analysis (/deepQuery) flow
        auth = (user_obj.id, user_obj.password)
        response = requests.post(
            f"{config.ai_sdk_host}/generateDeepQueryReport",
            json={
                "deepquery_metadata": deepquery_metadata,
                "color_palette": color_palette,
                "language": language
            },
            auth=auth,
            verify=config.ai_sdk_verify_ssl,
            timeout=config.chatbot_timeout
        )

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({
                "error": f"Report generation failed with status {response.status_code}"
            }), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Report generation timeout"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request failed: {str(e)}"}), 500
    except Exception as e:
        logging.error(f"Error in generate_report: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.

Handles the health check endpoint.
"""

from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for container orchestration and for run.py's
    startup readiness probe. Returns status 200 if the service is running.
    """
    return jsonify({"status": "OK"}), 200

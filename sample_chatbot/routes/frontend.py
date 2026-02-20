"""
Handles static file serving for the React frontend.
"""

import os

from flask import Blueprint, send_from_directory, current_app

frontend_bp = Blueprint('frontend', __name__)

@frontend_bp.route('/', defaults={'path': ''})
@frontend_bp.route('/<path:path>')
def serve_frontend(path):
    """Serve the React frontend application."""
    static_folder = current_app.static_folder

    if path != "" and os.path.exists(os.path.join(static_folder, path)):
        return send_from_directory(static_folder, path)
    else:
        return send_from_directory(static_folder, 'index.html')

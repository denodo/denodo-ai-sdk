"""
Registers all blueprints with the Flask application.
"""

from flask import Blueprint

from sample_chatbot.routes.auth import auth_bp
from sample_chatbot.routes.chat import chat_bp
from sample_chatbot.routes.health import health_bp
from sample_chatbot.routes.csv import csv_bp
from sample_chatbot.routes.metadata import metadata_bp
from sample_chatbot.routes.settings import settings_bp
from sample_chatbot.routes.reporting import reporting_bp
from sample_chatbot.routes.skills import skills_bp
from sample_chatbot.routes.deepquery import deepquery_bp
from sample_chatbot.routes.frontend import frontend_bp

def register_blueprints(app, url_prefix=""):
    """
    Register all blueprints with the Flask application.

    Args:
        app: Flask application instance
        url_prefix: URL prefix for all routes
    """
    # Create main chatbot blueprint that groups all sub-blueprints
    chatbot_bp = Blueprint('chatbot', __name__)

    # Register sub-blueprints with the main chatbot blueprint
    chatbot_bp.register_blueprint(health_bp)
    chatbot_bp.register_blueprint(auth_bp)
    chatbot_bp.register_blueprint(chat_bp)
    chatbot_bp.register_blueprint(csv_bp)
    chatbot_bp.register_blueprint(metadata_bp)
    chatbot_bp.register_blueprint(settings_bp)
    chatbot_bp.register_blueprint(reporting_bp)
    chatbot_bp.register_blueprint(skills_bp)
    chatbot_bp.register_blueprint(deepquery_bp)
    chatbot_bp.register_blueprint(frontend_bp)

    # Register transaction ID middleware on the main blueprint
    from sample_chatbot.routes.middleware import register_middleware
    register_middleware(chatbot_bp)

    # Register main blueprint with the app
    app.register_blueprint(chatbot_bp, url_prefix=url_prefix)

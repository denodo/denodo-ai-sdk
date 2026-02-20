"""
Creates and configures the Flask application.
"""

import os
import hashlib
import logging
import warnings
import logging.config

from flask import Flask
from utils.uniformLLM import UniformLLM
from utils.logging_utils import get_logging_config
from sample_chatbot.config import init_config
from sample_chatbot.extensions import login_manager
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.helpers import check_env_variables, setup_directories
from sample_chatbot.utils.ai_sdk_client import ai_sdk_health_check

# Required environment variables (prompts are now in engine/prompts.py)
REQUIRED_VARS = [
    'CHATBOT_LLM_PROVIDER',
    'CHATBOT_LLM_MODEL',
    'CHATBOT_EMBEDDINGS_PROVIDER',
    'CHATBOT_EMBEDDINGS_MODEL',
    'AI_SDK_URL',
]

def create_app(config=None):
    """
    Create and configure the Flask application.

    Args:
        config: Optional configuration object. If None, loads from environment.

    Returns:
        Configured Flask application instance.
    """
    # Ignore warnings
    warnings.filterwarnings("ignore")

    # Check required environment variables
    check_env_variables(REQUIRED_VARS)

    # Set up logging
    log_config = get_logging_config()
    logging.config.dictConfig(log_config)

    # Create upload and report directories
    setup_directories()

    # Initialize configuration
    if config is None:
        config = init_config()

    # Log configuration
    config.log_config(logging)

    # Connect to AI SDK
    logging.info("Connecting to AI SDK...")
    success = ai_sdk_health_check(config.ai_sdk_host, verify_ssl=config.ai_sdk_verify_ssl)
    if success:
        logging.info(f"Connected to AI SDK successfully at {config.ai_sdk_host}")
    else:
        logging.error(f"WARNING: Failed to connect to AI SDK at {config.ai_sdk_host}. Health check failed.")

    # Create Flask app
    app = Flask(__name__, static_folder='frontend/build')
    app.config['UPLOAD_FOLDER'] = "uploads"
    app.config['APPLICATION_ROOT'] = config.root_path
    app.secret_key = os.urandom(24)
    app.session_interface.digest_method = staticmethod(hashlib.sha256)

    # Store config in app for access from routes
    app.config['CHATBOT_CONFIG'] = config

    # Initialize LLM and store in app config
    llm = UniformLLM(
        config.llm_provider,
        config.llm_model,
        config.llm_temperature,
        config.llm_max_tokens
    )
    app.config['LLM'] = llm

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'chatbot.auth.login'

    # Configure user loader
    @login_manager.user_loader
    def load_user(user_id):
        return user_store.get(user_id)

    # Register blueprints
    from sample_chatbot.routes import register_blueprints
    register_blueprints(app, url_prefix=config.root_path)

    return app

def run_app(app=None):
    """
    Run the Flask application.

    Args:
        app: Optional Flask application instance. If None, creates a new one.
    """
    if app is None:
        app = create_app()

    config = app.config.get('CHATBOT_CONFIG')

    if config.ssl_enabled:
        app.run(
            host=config.host,
            debug=False,
            port=config.port,
            ssl_context=(config.ssl_cert, config.ssl_key)
        )
    else:
        app.run(
            host=config.host,
            debug=False,
            port=config.port
        )

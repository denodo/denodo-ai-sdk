"""
Creates and configures the Flask application.
"""

import os
import hashlib
import logging
import warnings
import logging.config

from flask import Flask
from utils.utils import validate_data_dir
from utils.logging_utils import get_logging_config
from utils.yaml.validate_and_parse import load_and_validate_agents
from sample_chatbot.config import init_agents, setup_agents_directories, log_agents_config
from sample_chatbot.engine.skills import log_skills
from sample_chatbot.extensions import login_manager
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.helpers import check_env_variables, setup_directories
from sample_chatbot.utils.ai_sdk_client import ai_sdk_health_check, ai_sdk_wait_until_healthy
from utils.database_utils import HistoryMetadata

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
    from utils.langfuse import init_langfuse

    init_langfuse()

    # Ignore warnings
    warnings.filterwarnings("ignore")

    # Check required environment variables
    check_env_variables(REQUIRED_VARS)

    data_dir = validate_data_dir()

    # Set up logging
    log_config = get_logging_config()
    logging.config.dictConfig(log_config)

    #Load agents configuration:
    agents_config = load_and_validate_agents()

    # Initialize configuration
    if config is None:
        config = init_agents(agents_config)

    # Create upload and report directories
    upload_folder = os.path.join(data_dir, "uploads")

    setup_directories(
        upload_folder=upload_folder,
        report_folder=os.path.join(data_dir, "reports")
    )
    setup_agents_directories()

    # Log agents configuration
    log_agents_config(logging)

    # Log discovered skills
    log_skills(logging)

    # Create Flask app first so all the Python-side initialization (blueprints,
    # login manager, agent configs) is done. The AI SDK reachability probe is
    # the last thing we do before returning the app.
    app = Flask(__name__, static_folder='frontend/build')
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['APPLICATION_ROOT'] = config.root_path
    app.secret_key = os.urandom(24)
    app.session_interface.digest_method = staticmethod(hashlib.sha256)

    # Store config in app for access from routes
    app.config['CHATBOT_CONFIG'] = config

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'chatbot.auth.login'

    # Configure user loader
    @login_manager.user_loader
    def load_user(user_id):
        return user_store.get(user_id)

    # Database initialization
    try:
        HistoryMetadata.init_db()
        logging.info("Chat history database metadata initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize database gracefully. Chat history may be unavailable: {e}")

    # Register blueprints
    from sample_chatbot.routes import register_blueprints
    register_blueprints(app, url_prefix=config.root_path)

    # AI SDK reachability check — moved to the very end of startup so that all
    # of the chatbot's own initialization runs in parallel with the AI SDK's
    # startup. When launched from run.py with mode `both`, the API and the
    # chatbot subprocesses are spawned concurrently; this poll lets the
    # chatbot wait the remaining startup budget for the API to come up
    # instead of failing the probe immediately.
    try:
        wait_budget = float(os.getenv("CHATBOT_AI_SDK_WAIT_TIMEOUT", "10"))
    except ValueError:
        wait_budget = 10.0

    logging.info(f"Connecting to AI SDK (waiting up to {wait_budget:.0f}s)...")
    if wait_budget > 0:
        success = ai_sdk_wait_until_healthy(
            config.ai_sdk_host,
            verify_ssl=config.ai_sdk_verify_ssl,
            total_timeout=wait_budget,
        )
    else:
        success = ai_sdk_health_check(config.ai_sdk_host, verify_ssl=config.ai_sdk_verify_ssl)

    if success:
        logging.info(f"Connected to AI SDK successfully at {config.ai_sdk_host}")
    else:
        logging.error(f"WARNING: Failed to connect to AI SDK at {config.ai_sdk_host}. Health check failed.")

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

"""
Creates and configures the Flask application.
"""

import os
import hashlib
import logging
import warnings

from flask import Flask, jsonify, redirect, request, url_for
from utils.utils import validate_data_dir, get_chatbot_data_dir
from utils.logging_utils import setup_logging, run_once
from utils.runtime_config import reconcile_runtime_config_with_cli
from utils.yaml.validate_and_parse import load_and_validate_agents
from sample_chatbot.config import init_agents, setup_agents_directories, log_agents_config
from sample_chatbot.engine.skills import log_skills
from sample_chatbot.extensions import login_manager
from sample_chatbot.services.user_store import user_store
from sample_chatbot.utils.helpers import check_env_variables, setup_directories
from sample_chatbot.utils.ai_sdk_client import ai_sdk_health_check, ai_sdk_wait_until_healthy
from utils.database_utils import HistoryMetadata, DeepQueryReports
from sample_chatbot.engine.memory import ensure_memory_store

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

    validate_data_dir()
    chatbot_data_dir = get_chatbot_data_dir()

    # Set up logging
    setup_logging(max_files_env="CHATBOT_LOG_MAX_FILES")
    reconcile_runtime_config_with_cli()

    # Check required environment variables
    check_env_variables(REQUIRED_VARS)

    # Load agents configuration:
    agents_config = load_and_validate_agents()

    # Initialize configuration
    if config is None:
        config = init_agents(agents_config)

    # Create upload and report directories
    upload_folder = os.path.join(chatbot_data_dir, "uploads")

    setup_directories(
        upload_folder=upload_folder,
        report_folder=os.path.join(chatbot_data_dir, "reports")
    )
    setup_agents_directories()

    # Log agents configuration and discovered skills (once per launch, not per worker)
    if run_once("chatbot.agents_skills"):
        log_agents_config(logging)
        log_skills(logging)

    # Create Flask app first so all the Python-side initialization (blueprints,
    # login manager, agent configs) is done. The AI SDK reachability probe is
    # the last thing we do before returning the app.
    app = Flask(__name__, static_folder='frontend/build')
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['APPLICATION_ROOT'] = config.root_path
    app.secret_key = os.urandom(24)
    app.session_interface.digest_method = hashlib.sha256

    # Store config in app for access from routes
    app.config['CHATBOT_CONFIG'] = config

    from sample_chatbot.routes.middleware import register_security_headers
    register_security_headers(app)

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'chatbot.auth.login'

    # Configure user loader
    @login_manager.user_loader
    def load_user(user_id):
        return user_store.get(user_id)

    # API calls made by the SPA must get a 401 instead of a redirect to the login page
    @login_manager.unauthorized_handler
    def unauthorized():
        api_prefix = f"{config.root_path or ''}/api"
        accepts_html = request.accept_mimetypes.best == 'text/html'
        if request.path.startswith(api_prefix) and (
            not accepts_html or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        ):
            return jsonify(error='unauthorized'), 401
        return redirect(url_for(login_manager.login_view, next=request.url))

    class _QuietStatusPolling(logging.Filter):
        """Hide the very frequent report status polling from the access log."""
        def filter(self, record):
            return '/api/reports/status' not in record.getMessage()

    logging.getLogger('werkzeug').addFilter(_QuietStatusPolling())
    for handler in logging.getLogger().handlers:
        handler.addFilter(_QuietStatusPolling())

    # Database initialization
    try:
        HistoryMetadata.init_db()
        logging.info("Chat history database metadata initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize database gracefully. Chat history may be unavailable: {e}")

    try:
        ensure_memory_store()
    except Exception as e:
        logging.error(f"Failed to initialize chatbot memories. Memories may be unavailable: {e}")

    try:
        DeepQueryReports.init_db()
        DeepQueryReports.fail_stale_jobs()
        logging.info("DeepQuery reports database initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize DeepQuery reports storage. Reports may be unavailable: {e}")

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

    announce = run_once("chatbot.ai_sdk_connection")
    if announce:
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
        if announce:
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

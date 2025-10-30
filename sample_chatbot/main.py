import os
import json
import hashlib
import logging
import warnings
import requests
import threading
import logging.config

from flask_httpauth import HTTPBasicAuth
from flask import Flask, Response, request, jsonify, send_from_directory, Blueprint
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from utils.logging_utils import get_logging_config, transaction_id_var
from utils.uniformLLM import UniformLLM
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore
from utils.utils import normalize_root_path, generate_transaction_id
from sample_chatbot.chatbot_engine import ChatbotEngine
from sample_chatbot.chatbot_config_loader import load_config
from sample_chatbot.chatbot_tools import deep_query, denodo_query, metadata_query, kb_lookup
from sample_chatbot.chatbot_utils import ai_sdk_health_check, get_user_views, setup_user_details
from sample_chatbot.chatbot_utils import prepare_unstructured_vector_store, check_env_variables, connect_to_ai_sdk, setup_directories, write_to_report, update_feedback_in_report

required_vars = [
    'CHATBOT_LLM_PROVIDER',
    'CHATBOT_LLM_MODEL',
    'CHATBOT_EMBEDDINGS_PROVIDER',
    'CHATBOT_EMBEDDINGS_MODEL',
    'CHATBOT_SYSTEM_PROMPT',
    'CHATBOT_TOOL_SELECTION_PROMPT',
    'AI_SDK_URL',
    'CHATBOT_DATABASE_QUERY_TOOL',
    'CHATBOT_KNOWLEDGE_BASE_TOOL',
    'CHATBOT_METADATA_QUERY_TOOL',
    'CHATBOT_DEEPQUERY_TOOL'
]

# Ignore warnings
warnings.filterwarnings("ignore")

# Load configuration variables
load_config()

# Check that the minimum required variables are set
check_env_variables(required_vars)

# Set up logging
log_config = get_logging_config()
logging.config.dictConfig(log_config)

# Create upload folder if it doesn't exist to store unstructured csv files
setup_directories()

# Environment variable lookup
CHATBOT_LLM_PROVIDER = os.environ['CHATBOT_LLM_PROVIDER']
CHATBOT_LLM_MODEL = os.environ['CHATBOT_LLM_MODEL']
CHATBOT_LLM_TEMPERATURE = float(os.getenv('CHATBOT_LLM_TEMPERATURE', '0'))
CHATBOT_LLM_MAX_TOKENS = int(os.getenv('CHATBOT_LLM_MAX_TOKENS', '4096'))
CHATBOT_LLM_RESPONSE_ROWS_LIMIT = int(os.getenv('CHATBOT_LLM_RESPONSE_ROWS_LIMIT', '15'))
CHATBOT_EMBEDDINGS_PROVIDER = os.environ['CHATBOT_EMBEDDINGS_PROVIDER']
CHATBOT_EMBEDDINGS_MODEL = os.environ['CHATBOT_EMBEDDINGS_MODEL']
CHATBOT_VECTOR_STORE_PROVIDER = os.environ['CHATBOT_VECTOR_STORE_PROVIDER']
CHATBOT_SYSTEM_PROMPT = os.environ['CHATBOT_SYSTEM_PROMPT']
CHATBOT_TOOL_SELECTION_PROMPT = os.environ['CHATBOT_TOOL_SELECTION_PROMPT']
CHATBOT_RELATED_QUESTIONS_PROMPT = os.environ['CHATBOT_RELATED_QUESTIONS_PROMPT']
CHATBOT_KNOWLEDGE_BASE_TOOL = os.environ['CHATBOT_KNOWLEDGE_BASE_TOOL']
CHATBOT_METADATA_QUERY_TOOL = os.environ['CHATBOT_METADATA_QUERY_TOOL']
CHATBOT_DATABASE_QUERY_TOOL = os.environ['CHATBOT_DATABASE_QUERY_TOOL']
CHATBOT_DEEPQUERY_TOOL = os.environ['CHATBOT_DEEPQUERY_TOOL']
CHATBOT_HOST = os.getenv('CHATBOT_HOST', '0.0.0.0')
CHATBOT_PORT = int(os.getenv('CHATBOT_PORT', 9992))
CHATBOT_ROOT_PATH = normalize_root_path(os.getenv("CHATBOT_ROOT_PATH", ""))
CHATBOT_SSL_CERT = os.getenv('CHATBOT_SSL_CERT')
CHATBOT_SSL_KEY = os.getenv('CHATBOT_SSL_KEY')
CHATBOT_REPORTING = bool(int(os.getenv('CHATBOT_REPORTING', '0')))
CHATBOT_REPORT_MAX_SIZE = int(os.getenv('CHATBOT_REPORT_MAX_SIZE', '10'))
CHATBOT_REPORT_MAX_FILES = int(os.getenv('CHATBOT_REPORT_MAX_FILES', '10'))
CHATBOT_FEEDBACK = bool(int(os.getenv('CHATBOT_FEEDBACK', '0')))
CHATBOT_UNSTRUCTURED_MODE = bool(int(os.getenv('CHATBOT_UNSTRUCTURED_MODE', '1')))
CHATBOT_UNSTRUCTURED_INDEX = os.getenv('CHATBOT_UNSTRUCTURED_INDEX')
CHATBOT_UNSTRUCTURED_DESCRIPTION = os.getenv('CHATBOT_UNSTRUCTURED_DESCRIPTION')
CHATBOT_USER_EDIT_LLM = bool(int(os.getenv('CHATBOT_USER_EDIT_LLM', '0')))
CHATBOT_AUTO_GRAPH = bool(int(os.getenv('CHATBOT_AUTO_GRAPH', '1')))
CHATBOT_SYNC_VDBS_TIMEOUT = int(os.getenv('CHATBOT_SYNC_VDBS_TIMEOUT', '600000'))
AI_SDK_HOST = os.getenv('AI_SDK_URL', 'http://localhost:8008')
AI_SDK_USERNAME = os.getenv('AI_SDK_USERNAME')
AI_SDK_PASSWORD = os.getenv('AI_SDK_PASSWORD')
DATA_CATALOG_URL = os.getenv("CHATBOT_DATA_CATALOG_URL") or os.getenv("DATA_CATALOG_URL")
AI_SDK_VERIFY_SSL = bool(int(os.getenv('AI_SDK_VERIFY_SSL', '0')))

logging.info("Chatbot parameters:")
logging.info(f"    - LLM Model: {CHATBOT_LLM_PROVIDER}/{CHATBOT_LLM_MODEL} (temp={CHATBOT_LLM_TEMPERATURE}, max_tokens={CHATBOT_LLM_MAX_TOKENS})")
logging.info(f"    - Embeddings Model: {CHATBOT_EMBEDDINGS_PROVIDER}/{CHATBOT_EMBEDDINGS_MODEL}")
logging.info(f"    - Vector Store Provider: {CHATBOT_VECTOR_STORE_PROVIDER}")
logging.info(f"    - AI SDK Host: {AI_SDK_HOST}")
logging.info(f"    - Using SSL: {bool(CHATBOT_SSL_CERT and CHATBOT_SSL_KEY)}")
logging.info(f"    - Reporting: {CHATBOT_REPORTING}")
logging.info(f"    - Report Max Size: {CHATBOT_REPORT_MAX_SIZE}mb")
logging.info(f"    - Report Max Files: {'unlimited' if CHATBOT_REPORT_MAX_FILES <= 0 else CHATBOT_REPORT_MAX_FILES}")
logging.info(f"    - Feedback: {CHATBOT_FEEDBACK if CHATBOT_REPORTING else False}")
logging.info(f"    - Auto Graph: {CHATBOT_AUTO_GRAPH}")
logging.info("Connecting to AI SDK...")

# Connect to AI SDK
success = ai_sdk_health_check(AI_SDK_HOST, verify_ssl=AI_SDK_VERIFY_SSL)
if success:
    logging.info(f"Connected to AI SDK successfully at {AI_SDK_HOST}")
else:
    logging.error(f"WARNING: Failed to connect to AI SDK at {AI_SDK_HOST}. Health check failed.")

app = Flask(__name__, static_folder = 'frontend/build')
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['APPLICATION_ROOT'] = CHATBOT_ROOT_PATH
app.secret_key = os.urandom(24)
app.session_interface.digest_method = staticmethod(hashlib.sha256)
auth = HTTPBasicAuth()
chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.before_request
def add_transaction_id_before_request():
    """Generate and store a transaction ID for the request."""
    transaction_id_var.set(generate_transaction_id())

@chatbot_bp.after_request
def add_transaction_id_after_request(response):
    """Add the transaction ID to the response headers."""
    response.headers['X-Transaction-ID'] = transaction_id_var.get()
    return response

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'chatbot.login'

# LLM
llm = UniformLLM(
        CHATBOT_LLM_PROVIDER,
        CHATBOT_LLM_MODEL,
        CHATBOT_LLM_TEMPERATURE,
        CHATBOT_LLM_MAX_TOKENS
    )

# Dictionary to store User instances
users = {}

class User(UserMixin):
    def __init__(self, username, password):
        self.id = username
        self.password = password
        self.csv_file_path = None
        self.csv_file_description = None
        self.unstructured_vector_store = None
        self.tools = None
        self.tools_prompt = None
        self.chatbot = None
        self.denodo_tables = None
        self.custom_instructions = ""
        self.user_details = ""

        # LLM preferences for different components
        self.chatbot_llm_preferences = {}
        self.ai_sdk_base_llm_preferences = {}
        self.ai_sdk_thinking_llm_preferences = {}

        ## Initialize tools
        self.check_custom_kb()
        self.update_tools()

    def check_custom_kb(self):
        if CHATBOT_UNSTRUCTURED_INDEX and CHATBOT_UNSTRUCTURED_DESCRIPTION:
            self.csv_file_description = CHATBOT_UNSTRUCTURED_DESCRIPTION
            embeddings = UniformEmbeddings(CHATBOT_EMBEDDINGS_PROVIDER, CHATBOT_EMBEDDINGS_MODEL).model
            self.unstructured_vector_store = UniformVectorStore(
                index_name=CHATBOT_UNSTRUCTURED_INDEX,
                provider=CHATBOT_VECTOR_STORE_PROVIDER,
                embeddings=embeddings
            )

    def set_csv_data(self, csv_file_path, csv_file_description, delimiter = ";"):
        self.csv_file_path = csv_file_path
        self.csv_file_description = csv_file_description
        self.unstructured_vector_store = prepare_unstructured_vector_store(
            csv_file_path=csv_file_path,
            vector_store_provider=CHATBOT_VECTOR_STORE_PROVIDER,
            embeddings_provider=CHATBOT_EMBEDDINGS_PROVIDER,
            embeddings_model=CHATBOT_EMBEDDINGS_MODEL,
            delimiter=delimiter
        )
        self.update_tools()

    def set_custom_instructions(self):
        self.custom_instructions = self.custom_instructions + "\n" + setup_user_details(self.user_details, username = self.id)
        self.update_tools()
        # Reset the chatbot to create a new one with updated tools and custom_instructions
        self.chatbot = None

    def update_tools(self):
        self.tools = self.generate_tools()
        self.tools_prompt = self.generate_tools_prompt()

    def generate_tools(self):
        # Prepare LLM parameters for AI SDK tools
        ai_sdk_llm_params = {}

        # Add base LLM preferences if set
        if self.ai_sdk_base_llm_preferences:
            if self.ai_sdk_base_llm_preferences.get('provider'):
                ai_sdk_llm_params['llm_provider'] = self.ai_sdk_base_llm_preferences['provider']
            if self.ai_sdk_base_llm_preferences.get('model'):
                ai_sdk_llm_params['llm_model'] = self.ai_sdk_base_llm_preferences['model']
            if self.ai_sdk_base_llm_preferences.get('temperature') is not None:
                ai_sdk_llm_params['llm_temperature'] = self.ai_sdk_base_llm_preferences['temperature']
            if self.ai_sdk_base_llm_preferences.get('max_tokens'):
                ai_sdk_llm_params['llm_max_tokens'] = self.ai_sdk_base_llm_preferences['max_tokens']

        # Add thinking LLM preferences if set
        thinking_llm_params = {}
        if self.ai_sdk_thinking_llm_preferences:
            if self.ai_sdk_thinking_llm_preferences.get('provider'):
                thinking_llm_params['thinking_llm_provider'] = self.ai_sdk_thinking_llm_preferences['provider']
            if self.ai_sdk_thinking_llm_preferences.get('model'):
                thinking_llm_params['thinking_llm_model'] = self.ai_sdk_thinking_llm_preferences['model']
            if self.ai_sdk_thinking_llm_preferences.get('temperature') is not None:
                thinking_llm_params['thinking_llm_temperature'] = self.ai_sdk_thinking_llm_preferences['temperature']
            if self.ai_sdk_thinking_llm_preferences.get('max_tokens'):
                thinking_llm_params['thinking_llm_max_tokens'] = self.ai_sdk_thinking_llm_preferences['max_tokens']

        tools = {
            "database_query": {
                "function": denodo_query,
            "params": {
                    "api_host": AI_SDK_HOST,
                    "username": self.id,
                    "password": self.password,
                    "custom_instructions": self.custom_instructions,
                    "verify_ssl": AI_SDK_VERIFY_SSL,
                    **ai_sdk_llm_params
                }
            },
            "metadata_query": {
                "function": metadata_query,
            "params": {
                    "api_host": AI_SDK_HOST,
                    "username": self.id,
                    "password": self.password,
                    "verify_ssl": AI_SDK_VERIFY_SSL
                }
            },
            "deep_query": {
                "function": deep_query,
            "params": {
                    "api_host": AI_SDK_HOST,
                    "username": self.id,
                    "password": self.password,
                    "verify_ssl": AI_SDK_VERIFY_SSL,
                    **ai_sdk_llm_params,
                    **thinking_llm_params
                }
            }
        }

        if self.unstructured_vector_store:
            tools["kb_lookup"] = {"function": kb_lookup, "params": {"vector_store": self.unstructured_vector_store}}

        return tools

    def generate_tools_prompt(self):
        if not CHATBOT_AUTO_GRAPH:
            database_query_tool = CHATBOT_DATABASE_QUERY_TOOL.format(auto_graph="If the data could benefit from a chart, you can request a plot to the tool. Generating a plot takes a few seconds, so do it if you think it will help the user understand the data better.")
        else:
            database_query_tool = CHATBOT_DATABASE_QUERY_TOOL.format(auto_graph="You can only request a plot of the data if explicitly requested by the user.")

        # Always include core tools
        core_tools = [database_query_tool, CHATBOT_METADATA_QUERY_TOOL, CHATBOT_DEEPQUERY_TOOL]

        if self.unstructured_vector_store:
            kb_tool_prompt = CHATBOT_KNOWLEDGE_BASE_TOOL.format(description=self.csv_file_description)
            final_tools = "\n\n".join(core_tools + [kb_tool_prompt])
        else:
            final_tools = "\n\n".join(core_tools)
        return CHATBOT_TOOL_SELECTION_PROMPT.format(tools=final_tools)

    def get_or_create_chatbot(self):
        if not self.chatbot:
            # Use user's chatbot LLM preferences or fall back to global defaults
            chatbot_llm = self._get_chatbot_llm()

            self.chatbot = ChatbotEngine(
                llm=chatbot_llm,
                llm_response_rows_limit=CHATBOT_LLM_RESPONSE_ROWS_LIMIT,
                related_questions_prompt=CHATBOT_RELATED_QUESTIONS_PROMPT,
                system_prompt=CHATBOT_SYSTEM_PROMPT,
                tool_selection_prompt=self.tools_prompt,
                tools=self.tools,
                api_host=AI_SDK_HOST,
                username=self.id,
                password=self.password,
                vector_store_provider=CHATBOT_VECTOR_STORE_PROVIDER,
                denodo_tables=self.denodo_tables,
                user_details=self.user_details
            )
        return self.chatbot

    def _get_chatbot_llm(self):
        """Get LLM instance for chatbot based on user preferences or global defaults"""
        if self.chatbot_llm_preferences:
            provider = self.chatbot_llm_preferences.get('provider', CHATBOT_LLM_PROVIDER)
            model = self.chatbot_llm_preferences.get('model', CHATBOT_LLM_MODEL)
            temperature = self.chatbot_llm_preferences.get('temperature', CHATBOT_LLM_TEMPERATURE)
            max_tokens = self.chatbot_llm_preferences.get('max_tokens', CHATBOT_LLM_MAX_TOKENS)

            return UniformLLM(
                provider,
                model,
                temperature=temperature,
                max_tokens=max_tokens
            )
        else:
            # Use global LLM instance
            return llm

# Thread lock for report file operations
report_lock = threading.Lock()

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

@chatbot_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    user_details = data.get('user_details', '')
    custom_instructions = data.get('custom_instructions', '')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    status, response_data = get_user_views(
        api_host=AI_SDK_HOST,
        username=username,
        password=password,
        query="tables",
        verify_ssl=AI_SDK_VERIFY_SSL
    )

    if status != 200:
        if status == 401:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401
        else:
            return jsonify({"success": False, "message": response_data}), status

    user = User(username, password)

    if response_data:
        user.denodo_tables = "Here are some of the views available in the user's Denodo instance:\n- " + "\n- ".join(response_data) + "\n\nThis is not an exhaustive list, you can use the Metadata tool to query more."
    else:
        user.denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is failing or he does not have enough permissions."

    if user_details or custom_instructions:
        user.user_details = user_details
        user.custom_instructions = custom_instructions
        user.set_custom_instructions()

    users[username] = user
    login_user(user)

    csv_file_path = request.json.get('csv_file_path')
    csv_file_description = request.json.get('csv_file_description')

    if csv_file_path and csv_file_description:
        user.set_csv_data(csv_file_path, csv_file_description)
        if not user.unstructured_vector_store:
            return jsonify({"success": False, "message": "Failed to prepare unstructured vector store"}), 500

    return jsonify({"success": True}), 200

@chatbot_bp.route('/update_csv', methods=['POST'])
@login_required
def update_csv():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    csv_file_description = request.form.get('description')
    csv_file_delimiter = request.form.get('delimiter', ';')

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and csv_file_description:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        current_user.set_csv_data(file_path, csv_file_description, csv_file_delimiter)
        current_user.chatbot = None  # Reset the chatbot to create a new one with updated tools

        return jsonify({"message": "CSV file uploaded, saved, and tools regenerated"}), 200

    return jsonify({"error": "Missing file or description"}), 400

@chatbot_bp.route('/question', methods=['GET'])
@login_required
def question():
    # Capture ALL request data first, before any try/except
    query = request.args.get('query')
    user_id = current_user.id
    question_type = request.args.get('type', 'default')
    # Capture the actual user object, not the proxy
    user_obj = current_user._get_current_object()

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400

    def generate(query, user_id, question_type, user_obj):
        try:
            chatbot = user_obj.get_or_create_chatbot()
        except Exception as e:

            logging.error(f"Error creating chatbot: {str(e)}", exc_info=True)
            yield f"data: There was an error configuring the chatbot: {str(e)}\n\n"
            yield "data: <STREAMOFF>\n\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        for chunk in chatbot.process_query(query=query, tool=question_type):
            if isinstance(chunk, dict):
                yield "data: <STREAMOFF>\n\n"
                chunk_json = json.dumps(chunk)
                yield f"data: {chunk_json}\n\n"
                # Write to report only if reporting is enabled
                if CHATBOT_REPORTING:
                    write_to_report(report_lock, CHATBOT_REPORT_MAX_SIZE, CHATBOT_REPORT_MAX_FILES, query, chunk, user_id)
            elif isinstance(chunk, str):
                chunk = chunk.replace('\n', '<NEWLINE>')
                yield f"data: {chunk}\n\n"
            else:
                yield f"data: {chunk}\n\n"

    return Response(generate(query, user_id, question_type, user_obj), mimetype='text/event-stream')

@chatbot_bp.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    current_user.chatbot = None
    return jsonify({"message": f"Chat history cleared for user {current_user.id}"})

@chatbot_bp.route("/delete_metadata", methods=["DELETE"])
@login_required
def delete_metadata():
    if not AI_SDK_USERNAME or not AI_SDK_PASSWORD:
        return jsonify({"success": False, "message": "AI SDK credentials are not configured. Please set the AI_SDK_USERNAME and AI_SDK_PASSWORD environment variables."}), 400

    data = request.json
    vdp_database_names = data.get('vdp_database_names', '')
    vdp_tag_names = data.get('vdp_tag_names', '')
    delete_conflicting = data.get('delete_conflicting', False)

    if not vdp_database_names and not vdp_tag_names:
        return jsonify({"success": False, "message": "At least one database or tag must be provided for deletion."}), 400

    try:
        auth = (AI_SDK_USERNAME, AI_SDK_PASSWORD)
        payload = {
            "vdp_database_names": vdp_database_names,
            "vdp_tag_names": vdp_tag_names,
            "delete_conflicting": delete_conflicting
        }

        response = requests.delete(
            f"{AI_SDK_HOST}/deleteMetadata",
            params=payload,
            auth=auth,
            verify=AI_SDK_VERIFY_SSL
        )

        if response.status_code == 200:
            status_code, table_names = get_user_views(
                api_host=AI_SDK_HOST,
                username=current_user.id,
                password=current_user.password,
                query="tables",
                verify_ssl=AI_SDK_VERIFY_SSL
            )
            if status_code == 200:
                if table_names:
                    current_user.denodo_tables = "Here are some of the views available in the user's Denodo instance:\n- " + "\n- ".join(table_names) + "\n\nThis is not an exhaustive list, you can use the Metadata tool to query more."
                else:
                    current_user.denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is failing or he does not have enough permissions."
                current_user.chatbot = None
            return jsonify({"success": True, "message": response.json().get('message', 'Deletion successful.')}), 200
        elif response.status_code == 204:
            return Response(status=204)
        else:
            error_message = response.json().get('detail', 'An unknown error occurred during deletion.')
            return jsonify({"success": False, "message": error_message}), response.status_code

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling deleteMetadata endpoint: {str(e)}")
        return jsonify({"success": False, "message": f"Failed to connect to AI SDK: {str(e)}"}), 500


@chatbot_bp.route("/sync_vdbs", methods=["POST"])
@login_required
def sync_vdbs():
    if not AI_SDK_USERNAME or not AI_SDK_PASSWORD:
        return jsonify({"success": False, "message": "AI SDK credentials are not configured. Please set the AI_SDK_USERNAME and AI_SDK_PASSWORD environment variables."}), 400

    vdbs_to_sync = request.json.get('vdbs', [])
    tags_to_sync = request.json.get('tags', [])
    tags_to_ignore = request.json.get('tags_to_ignore', [])
    examples_per_table = request.json.get('examples_per_table', 100)
    incremental = request.json.get('incremental', True)
    parallel = request.json.get('parallel', True)

    status, result = connect_to_ai_sdk(
        api_host=AI_SDK_HOST,
        username=AI_SDK_USERNAME,
        password=AI_SDK_PASSWORD,
        insert=True,
        examples_per_table=examples_per_table,
        incremental=incremental,
        parallel=parallel,
        vdp_database_names=vdbs_to_sync,
        vdp_tag_names=tags_to_sync,
        tags_to_ignore=tags_to_ignore,
        verify_ssl=AI_SDK_VERIFY_SSL
    )

    if status == 200:
        status_code, relevant_tables = get_user_views(
            api_host=AI_SDK_HOST,
            username=current_user.id,
            password=current_user.password,
            query="tables",
            verify_ssl=AI_SDK_VERIFY_SSL
        )

        if status_code == 200:
            if relevant_tables:
                current_user.denodo_tables = "Here are some of the views available in the user's Denodo instance:\n- " + "\n- ".join(relevant_tables) + "\n\nThis is not an exhaustive list, you can use the Metadata tool to query more."
            else:
                current_user.denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is failing or he does not have enough permissions."
            current_user.chatbot = None

        return jsonify({"success": True, "message": f"VectorDB synchronization successful for VDBs: {result}"}), status
    elif status == 204:
        return jsonify({"success": True, "message": result}), status
    else:
        return jsonify({"success": False, "message": result}), status

@chatbot_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    username = current_user.id
    users.pop(username, None)
    logout_user()
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

@chatbot_bp.route('/api/config', methods=['GET'])
def get_config():
    """Endpoint to expose configuration variables to the frontend."""
    # Only include dataCatalogUrl if it's explicitly set in the environment
    config = {
        "hasAISDKCredentials": bool(AI_SDK_USERNAME and AI_SDK_PASSWORD),
        "chatbotFeedback": CHATBOT_FEEDBACK if CHATBOT_REPORTING else False,
        "unstructuredMode": CHATBOT_UNSTRUCTURED_MODE,
        "syncTimeout": CHATBOT_SYNC_VDBS_TIMEOUT,
        "llm_response_rows_limit": CHATBOT_LLM_RESPONSE_ROWS_LIMIT,
        "userEditLLM": CHATBOT_USER_EDIT_LLM
    }
    if DATA_CATALOG_URL:
        config["dataCatalogUrl"] = DATA_CATALOG_URL.rstrip('/')
    return jsonify(config)

@chatbot_bp.route('/update_custom_instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    data = request.json
    custom_instructions = data.get('custom_instructions', '')
    user_details = data.get('user_details', '')

    current_user.custom_instructions = custom_instructions
    current_user.user_details = user_details
    current_user.set_custom_instructions()

    return jsonify({"message": "Profile updated successfully"}), 200

@chatbot_bp.route('/update_llm_settings', methods=['POST'])
@login_required
def update_llm_settings():
    if not CHATBOT_USER_EDIT_LLM:
        return jsonify({"error": "LLM editing is not enabled"}), 403

    try:
        data = request.json

        # Validate numeric fields
        def validate_temperature(temp):
            if temp is not None and temp != '':
                temp_float = float(temp)
                if not (0.0 <= temp_float <= 2.0):
                    raise ValueError("Temperature must be between 0.0 and 2.0")
                return temp_float
            return None

        def validate_max_tokens(tokens):
            if tokens is not None and tokens != '':
                tokens_int = int(tokens)
                if not (1024 <= tokens_int <= 20000):
                    raise ValueError("Max tokens must be between 1024 and 20000")
                return tokens_int
            return None

        # Update chatbot LLM preferences
        chatbot_llm = data.get('chatbot_llm', {})
        if any(chatbot_llm.values()):  # Only update if any values are provided
            current_user.chatbot_llm_preferences = {
                'provider': chatbot_llm.get('provider') or None,
                'model': chatbot_llm.get('model') or None,
                'temperature': validate_temperature(chatbot_llm.get('temperature')),
                'max_tokens': validate_max_tokens(chatbot_llm.get('max_tokens'))
            }
            # Remove None values
            current_user.chatbot_llm_preferences = {k: v for k, v in current_user.chatbot_llm_preferences.items() if v is not None}

        # Update AI SDK base LLM preferences
        ai_sdk_base_llm = data.get('ai_sdk_base_llm', {})
        if any(ai_sdk_base_llm.values()):  # Only update if any values are provided
            current_user.ai_sdk_base_llm_preferences = {
                'provider': ai_sdk_base_llm.get('provider') or None,
                'model': ai_sdk_base_llm.get('model') or None,
                'temperature': validate_temperature(ai_sdk_base_llm.get('temperature')),
                'max_tokens': validate_max_tokens(ai_sdk_base_llm.get('max_tokens'))
            }
            # Remove None values
            current_user.ai_sdk_base_llm_preferences = {k: v for k, v in current_user.ai_sdk_base_llm_preferences.items() if v is not None}

        # Update AI SDK thinking LLM preferences
        ai_sdk_thinking_llm = data.get('ai_sdk_thinking_llm', {})
        if any(ai_sdk_thinking_llm.values()):  # Only update if any values are provided
            current_user.ai_sdk_thinking_llm_preferences = {
                'provider': ai_sdk_thinking_llm.get('provider') or None,
                'model': ai_sdk_thinking_llm.get('model') or None,
                'temperature': validate_temperature(ai_sdk_thinking_llm.get('temperature')),
                'max_tokens': validate_max_tokens(ai_sdk_thinking_llm.get('max_tokens'))
            }
            # Remove None values
            current_user.ai_sdk_thinking_llm_preferences = {k: v for k, v in current_user.ai_sdk_thinking_llm_preferences.items() if v is not None}

        # Regenerate tools with new preferences
        current_user.update_tools()

        # Reset chatbot to force recreation with new LLM settings
        current_user.chatbot = None

        return jsonify({"message": "LLM settings updated successfully"}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Invalid input: {str(e)}"}), 400

@chatbot_bp.route('/current_user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({"username": current_user.id}), 200

@chatbot_bp.route('/generate_pdf', methods=['POST'])
@login_required
def generate_pdf():
    """Generate PDF from DeepQuery metadata by calling the generateDeepQueryPDF endpoint."""
    try:
        data = request.json
        deepquery_metadata = data.get('deepquery_metadata')
        color_palette = data.get('color_palette', 'red')

        if not deepquery_metadata:
            return jsonify({"error": "Missing deepquery_metadata"}), 400

        # Make request to the generateDeepQueryPDF endpoint
        auth = (AI_SDK_USERNAME, AI_SDK_PASSWORD)
        response = requests.post(
            f"{AI_SDK_HOST}/generateDeepQueryPDF",
            json={
                "deepquery_metadata": deepquery_metadata,
                "color_palette": color_palette
            },
            auth=auth,
            verify=AI_SDK_VERIFY_SSL,
            timeout=600
        )

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"PDF generation failed with status {response.status_code}"}), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "PDF generation timeout"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request failed: {str(e)}"}), 500
    except Exception as e:
        logging.error(f"Error in generate_pdf: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@chatbot_bp.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    if not CHATBOT_REPORTING:
        return jsonify({"success": False, "message": "Feedback reporting is disabled"}), 400

    data = request.json
    uuid = data.get('uuid')
    feedback_value = data.get('feedback_value', '')  # 'positive', 'negative'
    feedback_details = data.get('feedback_details', '')

    if not uuid:
        return jsonify({"success": False, "message": "Missing UUID"}), 400

    success = update_feedback_in_report(report_lock, CHATBOT_REPORT_MAX_SIZE, uuid, feedback_value, feedback_details)

    if success:
        return jsonify({"success": True, "message": "Feedback saved successfully"}), 200
    else:
        return jsonify({"success": False, "message": "Failed to save feedback. UUID not found."}), 404

@chatbot_bp.route('/', defaults = {'path': ''})
@chatbot_bp.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

app.register_blueprint(chatbot_bp, url_prefix=CHATBOT_ROOT_PATH)

if __name__ == '__main__':
    if bool(CHATBOT_SSL_CERT and CHATBOT_SSL_KEY):
        app.run(host = CHATBOT_HOST, debug = False, port = CHATBOT_PORT, ssl_context = (CHATBOT_SSL_CERT, CHATBOT_SSL_KEY))
    else:
        app.run(host = CHATBOT_HOST, debug = False, port = CHATBOT_PORT)
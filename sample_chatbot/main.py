import os
import sys
import json
import hashlib
import logging
import warnings
import threading

from flask_httpauth import HTTPBasicAuth
from flask import Flask, Response, request, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from utils.uniformLLM import UniformLLM
from utils.uniformVectorStore import UniformVectorStore
from sample_chatbot.chatbot_engine import ChatbotEngine
from sample_chatbot.chatbot_config_loader import load_config
from sample_chatbot.chatbot_tools import denodo_query, metadata_query, kb_lookup
from sample_chatbot.chatbot_utils import ai_sdk_health_check, get_relevant_tables, setup_user_details
from sample_chatbot.chatbot_utils import dummy_login, prepare_unstructured_vector_store, check_env_variables, connect_to_ai_sdk, process_chunk, setup_directories, write_to_report, update_feedback_in_report

required_vars = [
    'CHATBOT_LLM_PROVIDER',
    'CHATBOT_LLM_MODEL',
    'CHATBOT_EMBEDDINGS_PROVIDER',
    'CHATBOT_EMBEDDINGS_MODEL',
    'CHATBOT_SYSTEM_PROMPT',
    'CHATBOT_TOOL_SELECTION_PROMPT',
    'AI_SDK_URL',
    'DATABASE_QUERY_TOOL',
    'KNOWLEDGE_BASE_TOOL',
    'METADATA_QUERY_TOOL'
]

# Ignore warnings
warnings.filterwarnings("ignore")

# Load configuration variables
load_config()

# Check that the minimum required variables are set
check_env_variables(required_vars)

# Set up logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S %z',
    encoding='utf-8'
)

# Create upload folder if it doesn't exist to store unstructured csv files
setup_directories()

# Environment variable lookup
CHATBOT_LLM_PROVIDER = os.environ['CHATBOT_LLM_PROVIDER']
CHATBOT_LLM_MODEL = os.environ['CHATBOT_LLM_MODEL']
CHATBOT_EMBEDDINGS_PROVIDER = os.environ['CHATBOT_EMBEDDINGS_PROVIDER']
CHATBOT_EMBEDDINGS_MODEL = os.environ['CHATBOT_EMBEDDINGS_MODEL']
CHATBOT_VECTOR_STORE_PROVIDER = os.environ['CHATBOT_VECTOR_STORE_PROVIDER']
CHATBOT_SYSTEM_PROMPT = os.environ['CHATBOT_SYSTEM_PROMPT']
CHATBOT_TOOL_SELECTION_PROMPT = os.environ['CHATBOT_TOOL_SELECTION_PROMPT']
CHATBOT_KNOWLEDGE_BASE_TOOL = os.environ['KNOWLEDGE_BASE_TOOL']
CHATBOT_METADATA_QUERY_TOOL = os.environ['METADATA_QUERY_TOOL']
CHATBOT_DATABASE_QUERY_TOOL = os.environ['DATABASE_QUERY_TOOL']
CHATBOT_HOST = os.getenv('CHATBOT_HOST', '0.0.0.0')
CHATBOT_PORT = int(os.getenv('CHATBOT_PORT', 9992))
CHATBOT_SSL_CERT = os.getenv('CHATBOT_SSL_CERT')
CHATBOT_SSL_KEY = os.getenv('CHATBOT_SSL_KEY')
CHATBOT_REPORTING = bool(int(os.getenv('CHATBOT_REPORTING', '0')))
CHATBOT_REPORT_MAX_SIZE = int(os.getenv('CHATBOT_REPORT_MAX_SIZE', '10'))
CHATBOT_FEEDBACK = bool(int(os.getenv('CHATBOT_FEEDBACK', '0')))
CHATBOT_UNSTRUCTURED_MODE = bool(int(os.getenv('CHATBOT_UNSTRUCTURED_MODE', '1')))
CHATBOT_UNSTRUCTURED_INDEX = os.getenv('CHATBOT_UNSTRUCTURED_INDEX')
CHATBOT_UNSTRUCTURED_DESCRIPTION = os.getenv('CHATBOT_UNSTRUCTURED_DESCRIPTION')
CHATBOT_AUTO_GRAPH = bool(int(os.getenv('CHATBOT_AUTO_GRAPH', '1')))
AI_SDK_HOST = os.getenv('AI_SDK_URL', 'http://localhost:8008')
AI_SDK_USERNAME = os.getenv('AI_SDK_USERNAME')
AI_SDK_PASSWORD = os.getenv('AI_SDK_PASSWORD')
DATA_CATALOG_URL = os.getenv('DATA_CATALOG_URL')

logging.info("Chatbot parameters:")
logging.info(f"    - LLM Provider: {CHATBOT_LLM_PROVIDER}")
logging.info(f"    - LLM Model: {CHATBOT_LLM_MODEL}")
logging.info(f"    - Embeddings Provider: {CHATBOT_EMBEDDINGS_PROVIDER}")
logging.info(f"    - Embeddings Model: {CHATBOT_EMBEDDINGS_MODEL}")
logging.info(f"    - Vector Store Provider: {CHATBOT_VECTOR_STORE_PROVIDER}")
logging.info(f"    - AI SDK Host: {AI_SDK_HOST}")
logging.info(f"    - Using SSL: {bool(CHATBOT_SSL_CERT and CHATBOT_SSL_KEY)}")
logging.info(f"    - Reporting: {CHATBOT_REPORTING}")
logging.info(f"    - Report Max Size: {CHATBOT_REPORT_MAX_SIZE}mb")
logging.info(f"    - Feedback: {CHATBOT_FEEDBACK if CHATBOT_REPORTING else False}")
logging.info(f"    - Auto Graph: {CHATBOT_AUTO_GRAPH}")
logging.info("Connecting to AI SDK...")

# Connect to AI SDK
success = ai_sdk_health_check(AI_SDK_HOST)
if success:
    logging.info(f"Connected to AI SDK successfully at {AI_SDK_HOST}")
else:
    logging.error(f"WARNING: Failed to connect to AI SDK at {AI_SDK_HOST}. Health check failed.")

app = Flask(__name__, static_folder = 'frontend/build')
app.config['UPLOAD_FOLDER'] = "uploads"
app.secret_key = os.urandom(24)
app.session_interface.digest_method = staticmethod(hashlib.sha256)
auth = HTTPBasicAuth()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# LLM
llm = UniformLLM(
        CHATBOT_LLM_PROVIDER,
        CHATBOT_LLM_MODEL,
        temperature = 0
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

        ## Initialize tools
        self.check_custom_kb()
        self.update_tools()

    def check_custom_kb(self):
        if CHATBOT_UNSTRUCTURED_INDEX and CHATBOT_UNSTRUCTURED_DESCRIPTION:
            self.csv_file_description = CHATBOT_UNSTRUCTURED_DESCRIPTION
            self.unstructured_vector_store = UniformVectorStore(
                index_name=CHATBOT_UNSTRUCTURED_INDEX,
                provider=CHATBOT_VECTOR_STORE_PROVIDER,
                embeddings_provider=CHATBOT_EMBEDDINGS_PROVIDER,
                embeddings_model=CHATBOT_EMBEDDINGS_MODEL
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
        tools = {
            "database_query": {"function": denodo_query, "params": {"api_host": AI_SDK_HOST, "username": self.id, "password": self.password, "custom_instructions": self.custom_instructions}},
            "metadata_query": {"function": metadata_query, "params": {"api_host": AI_SDK_HOST, "username": self.id, "password": self.password}}
        }
        
        if self.unstructured_vector_store:
            tools["kb_lookup"] = {"function": kb_lookup, "params": {"vector_store": self.unstructured_vector_store}}
        
        return tools

    def generate_tools_prompt(self):
        if CHATBOT_AUTO_GRAPH:
            database_query_tool = CHATBOT_DATABASE_QUERY_TOOL.format(auto_graph="I can request a plot of the data even if the user does not explicitly ask for it if I think it will help the user understand the data better.")
        else:
            database_query_tool = CHATBOT_DATABASE_QUERY_TOOL.format(auto_graph="I will only request a plot of the data if explicitly requested by the user.")

        if self.unstructured_vector_store:
            kb_tool_prompt = CHATBOT_KNOWLEDGE_BASE_TOOL.format(description=self.csv_file_description)
            final_tools = "\n".join([database_query_tool, CHATBOT_METADATA_QUERY_TOOL, kb_tool_prompt])
        else:
            final_tools = "\n".join([database_query_tool, CHATBOT_METADATA_QUERY_TOOL])
        return CHATBOT_TOOL_SELECTION_PROMPT.format(tools=final_tools)

    def get_or_create_chatbot(self):
        if not self.chatbot:
            self.chatbot = ChatbotEngine(
                llm=llm,
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

# Thread lock for report file operations
report_lock = threading.Lock()

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

@auth.verify_password
def verify_password(username, password):
    if dummy_login(AI_SDK_HOST, username, password):
        return username
    return None

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password or not verify_password(username, password):
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    
    csv_file_path = request.json.get('csv_file_path')
    csv_file_description = request.json.get('csv_file_description')
    
    user = User(username, password)
    users[username] = user
    login_user(user)
    result, relevant_tables = get_relevant_tables(
        api_host=AI_SDK_HOST,
        username=username,
        password=password,
        query="views"
    )

    if result and relevant_tables:
        user.denodo_tables = "Some of the views in the user's Denodo instance: " + ", ".join(relevant_tables) + "... Use the Metadata tool to query all."
    else:
        user.denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is failing or he does not have enough permissions. Use the Metadata tool to check."
    
    if csv_file_path and csv_file_description:
        user.set_csv_data(csv_file_path, csv_file_description)
        if not user.unstructured_vector_store:
            return jsonify({"success": False, "message": "Failed to prepare unstructured vector store"}), 500

    return jsonify({"success": True}), 200

@app.route('/update_csv', methods=['POST'])
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

@app.route('/question', methods=['GET'])
@login_required
def question():
    query = request.args.get('query')
    user_id = current_user.id
    question_type = request.args.get('type', 'default')

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    
    chatbot = current_user.get_or_create_chatbot()
        
    def generate():
        for chunk in chatbot.process_query(query=query, tool=question_type):
            if isinstance(chunk, dict):
                yield "data: <STREAMOFF>\n\n"
                chunk_json = json.dumps(chunk)
                yield f"data: {chunk_json}\n\n"
                # Write to report only if reporting is enabled
                if CHATBOT_REPORTING:
                    write_to_report(report_lock, CHATBOT_REPORT_MAX_SIZE, query, chunk, user_id)
            else:
                processed_chunk = process_chunk(chunk)
                yield f"data: {processed_chunk}\n\n"
            
    return Response(generate(), mimetype='text/event-stream')

@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    current_user.chatbot = None
    return jsonify({"message": f"Chat history cleared for user {current_user.id}"})

@app.route("/sync_vdbs", methods=["POST"])
@login_required
def sync_vdbs():
    if not AI_SDK_USERNAME or not AI_SDK_PASSWORD:
        return jsonify({"success": False, "message": "AI SDK credentials are not configured. Please set the AI_SDK_USERNAME and AI_SDK_PASSWORD environment variables."}), 400
    
    vdbs_to_sync = request.json.get('vdbs', [])    
    tags_to_sync = request.json.get('tags', [])
    examples_per_table = request.json.get('examples_per_table', 100)
    parallel = request.json.get('parallel', True)
    
    success, result = connect_to_ai_sdk(
        api_host=AI_SDK_HOST, 
        username=AI_SDK_USERNAME, 
        password=AI_SDK_PASSWORD, 
        insert=True,
        examples_per_table=examples_per_table,
        parallel=parallel,
        vdp_database_names=vdbs_to_sync,
        vdp_tag_names=tags_to_sync
    )

    if success:
        result, relevant_tables = get_relevant_tables(
            api_host=AI_SDK_HOST,
            username=current_user.id,
            password=current_user.password,
            query="views",
        )

        if result and relevant_tables:
            current_user.denodo_tables = "Some of the views in the user's Denodo instance: " + ", ".join(relevant_tables) + "... Use the Metadata tool to query all."
            current_user.chatbot = None
        else:
            current_user.denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is failing or he does not have enough permissions. Use the Metadata tool to check."

        return jsonify({"success": True, "message": f"VectorDB synchronization successful for VDBs: {result}"}), 200
    else:
        return jsonify({"success": False, "message": result}), 500
    
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    username = current_user.id
    users.pop(username, None)
    logout_user()
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

@app.route('/api/config', methods=['GET'])
def get_config():
    """Endpoint to expose configuration variables to the frontend."""
    # Only include dataCatalogUrl if it's explicitly set in the environment
    config = {
        "hasAISDKCredentials": bool(AI_SDK_USERNAME and AI_SDK_PASSWORD),
        "chatbotFeedback": CHATBOT_FEEDBACK if CHATBOT_REPORTING else False,
        "unstructuredMode": CHATBOT_UNSTRUCTURED_MODE
    }
    if DATA_CATALOG_URL:
        config["dataCatalogUrl"] = DATA_CATALOG_URL.rstrip('/')
    return jsonify(config)

@app.route('/update_custom_instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    data = request.json
    custom_instructions = data.get('custom_instructions', '')
    user_details = data.get('user_details', '')
    
    current_user.custom_instructions = custom_instructions
    current_user.user_details = user_details
    current_user.set_custom_instructions()
    
    return jsonify({"message": "Profile updated successfully"}), 200

@app.route('/current_user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({"username": current_user.id}), 200

@app.route('/submit_feedback', methods=['POST'])
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

@app.route('/', defaults = {'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')
    
if __name__ == '__main__':
    if bool(CHATBOT_SSL_CERT and CHATBOT_SSL_KEY):
        app.run(host = CHATBOT_HOST, debug = False, port = CHATBOT_PORT, ssl_context = (CHATBOT_SSL_CERT, CHATBOT_SSL_KEY))
    else:
        app.run(host = CHATBOT_HOST, debug = False, port = CHATBOT_PORT)
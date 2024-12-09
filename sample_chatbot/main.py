import os
import sys
import json
import requests
import logging
import warnings

from functools import lru_cache
from flask import Flask, Response, request, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_httpauth import HTTPBasicAuth

from utils.uniformLLM import UniformLLM
from sample_chatbot.chatbot_engine import ChatbotEngine
from sample_chatbot.chatbot_tools import denodo_query, metadata_query, kb_lookup
from sample_chatbot.chatbot_config_loader import load_config
from sample_chatbot.chatbot_utils import dummy_login, prepare_unstructured_vector_store, check_env_variables, connect_to_ai_sdk, process_chunk

required_vars = [
    'CHATBOT_LLM_PROVIDER',
    'CHATBOT_LLM_MODEL',
    'CHATBOT_EMBEDDINGS_PROVIDER',
    'CHATBOT_EMBEDDINGS_MODEL',
    'CHATBOT_SYSTEM_PROMPT',
    'CHATBOT_TOOL_SELECTION_PROMPT',
    'AI_SDK_HOST',
    'AI_SDK_USERNAME',
    'AI_SDK_PASSWORD',
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
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

# Create upload folder if it doesn't exist to store unstructured csv files
os.makedirs("uploads", exist_ok = True)

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
CHATBOT_OVERWRITE_ON_LOAD = bool(os.getenv('CHATBOT_OVERWRITE_ON_LOAD', True))
CHATBOT_EXAMPLES_PER_TABLE = int(os.getenv('CHATBOT_EXAMPLES_PER_TABLE', 3))
CHATBOT_HOST = os.getenv('CHATBOT_HOST', '0.0.0.0')
CHATBOT_PORT = int(os.getenv('CHATBOT_PORT', 9992))
CHATBOT_SSL_CERT = os.getenv('CHATBOT_SSL_CERT')
CHATBOT_SSL_KEY = os.getenv('CHATBOT_SSL_KEY')
AI_SDK_HOST = os.environ['AI_SDK_HOST']
AI_SDK_USERNAME = os.environ['AI_SDK_USERNAME']
AI_SDK_PASSWORD = os.environ['AI_SDK_PASSWORD']

logging.info("Chatbot parameters:")
logging.info(f"    - LLM Provider: {CHATBOT_LLM_PROVIDER}")
logging.info(f"    - LLM Model: {CHATBOT_LLM_MODEL}")
logging.info(f"    - Embeddings Provider: {CHATBOT_EMBEDDINGS_PROVIDER}")
logging.info(f"    - Embeddings Model: {CHATBOT_EMBEDDINGS_MODEL}")
logging.info(f"    - Vector Store Provider: {CHATBOT_VECTOR_STORE_PROVIDER}")
logging.info(f"    - AI SDK Host: {AI_SDK_HOST}")
logging.info(f"    - Overwrite AI SDK vector stores on load: {CHATBOT_OVERWRITE_ON_LOAD}")
logging.info(f"    - Examples per table: {CHATBOT_EXAMPLES_PER_TABLE}")
logging.info(f"    - Using SSL: {bool(CHATBOT_SSL_CERT and CHATBOT_SSL_KEY)}")
logging.info("Connecting to AI SDK...")

# Connect to AI SDK
success, result = connect_to_ai_sdk(
    api_host=AI_SDK_HOST, 
    username=AI_SDK_USERNAME, 
    password=AI_SDK_PASSWORD, 
    overwrite=CHATBOT_OVERWRITE_ON_LOAD,
    examples_per_table=CHATBOT_EXAMPLES_PER_TABLE
)

if success:
    VDB_LIST = result
    logging.info(f"Connected to AI SDK successfully. Accessible VDBs: {VDB_LIST}")
else:
    logging.error(f"Failed to connect to AI SDK: {result}")
    sys.exit(1)

app = Flask(__name__, static_folder = 'frontend/build')
app.config['UPLOAD_FOLDER'] = "uploads"
app.secret_key = os.urandom(24)
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

        ## Initialize tools
        self.update_tools()

    def set_csv_data(self, csv_file_path, csv_file_description):
        self.csv_file_path = csv_file_path
        self.csv_file_description = csv_file_description
        self.unstructured_vector_store = prepare_unstructured_vector_store(
            csv_file_path=csv_file_path, 
            vector_store_provider=CHATBOT_VECTOR_STORE_PROVIDER,
            embeddings_provider=CHATBOT_EMBEDDINGS_PROVIDER,
            embeddings_model=CHATBOT_EMBEDDINGS_MODEL
        )
        self.update_tools()

    def update_tools(self):
        self.tools = self.generate_tools()
        self.tools_prompt = self.generate_tools_prompt()

    def generate_tools(self):
        tools = {
            "database_query": {"function": denodo_query, "params": {"api_host": AI_SDK_HOST, "username": self.id, "password": self.password}},
            "metadata_query": {"function": metadata_query, "params": {"api_host": AI_SDK_HOST, "username": self.id, "password": self.password}}
        }
        
        if self.unstructured_vector_store:
            tools["kb_lookup"] = {"function": kb_lookup, "params": {"vector_store": self.unstructured_vector_store}}
        
        return tools

    def generate_tools_prompt(self):
        if self.unstructured_vector_store:
            kb_tool_prompt = CHATBOT_KNOWLEDGE_BASE_TOOL.format(description=self.csv_file_description)
            final_tools = "\n".join([CHATBOT_DATABASE_QUERY_TOOL, CHATBOT_METADATA_QUERY_TOOL, kb_tool_prompt])
        else:
            final_tools = "\n".join([CHATBOT_DATABASE_QUERY_TOOL, CHATBOT_METADATA_QUERY_TOOL])
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
                vdp_database_names=VDB_LIST,
                vector_store_provider=CHATBOT_VECTOR_STORE_PROVIDER
            )
        return self.chatbot

# Dictionary to store User instances
users = {}

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
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and csv_file_description:
        # Check if the file is UTF-8 encoded
        try:
            file_content = file.read()
            file_content.decode('utf-8')
            file.seek(0)  # Reset file pointer to the beginning
        except UnicodeDecodeError:
            return jsonify({"error": "The uploaded file is not UTF-8 encoded"}), 400

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        current_user.set_csv_data(file_path, csv_file_description)
        current_user.chatbot = None  # Reset the chatbot to create a new one with updated tools
        
        return jsonify({"message": "CSV file uploaded, saved, and tools regenerated"}), 200
    
    return jsonify({"error": "Missing file or description"}), 400

@app.route('/question', methods=['GET'])
@login_required
def question():
    query = request.args.get('query')
    question_type = request.args.get('type', 'default')

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    
    chatbot = current_user.get_or_create_chatbot()

    def generate():
        for chunk in chatbot.process_query(query=query, tool=question_type):
            if isinstance(chunk, dict):
                yield "data: <STREAMOFF>\n\n"
                yield f"data: {json.dumps(chunk)}\n\n"
            else:
                yield f"data: {process_chunk(chunk)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    current_user.chatbot = None
    return jsonify({"message": f"Chat history cleared for user {current_user.id}"})

@app.route("/get-vdbs", methods=["GET"])
@login_required
@lru_cache(maxsize = None)
def get_vdbs():
    return jsonify({"vdb_list": VDB_LIST}), 200

@app.route("/sync_vdp", methods=["POST"])
@login_required
def sync_vdp():
    vdbs_to_sync = request.json.get('vdbs', [])
    
    if not vdbs_to_sync:
        return jsonify({"success": False, "message": "No VDBs provided for synchronization"}), 400

    vdp_database_names = ",".join(vdbs_to_sync)
    
    request_params = {
        'insert_in_vector_db': True,
        'overwrite_vector_db': True,
        'examples_per_table': 3,
        'vdp_database_names': vdp_database_names
    }
    
    try:
        response = requests.get(f'{AI_SDK_HOST}/getMetadata', params=request_params, auth=(AI_SDK_USERNAME, AI_SDK_PASSWORD))
        if response.status_code == 404:
            raise ValueError(f"getMetadata returned 404: {response.content.decode('utf-8')}")	
        elif response.status_code == 500:
            raise ValueError(f"getMetadata returned 500: {response.content.decode('utf-8')}")
        else:
            response.raise_for_status()
        return jsonify({"success": True, "message": "VDP synchronization successful"}), 200
    except requests.RequestException as e:
        error_message = f"VDP synchronization failed: {str(e)}"
        return jsonify({"success": False, "message": error_message}), 500

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    username = current_user.id
    users.pop(username, None)
    logout_user()
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

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
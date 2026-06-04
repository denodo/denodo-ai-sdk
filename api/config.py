"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import os
import platform
import logging
from dotenv import load_dotenv

load_dotenv('api/utils/sdk_config.env')

from api.utils.sdk_utils import check_env_variables, test_data_catalog_connection
from utils.utils import normalize_root_path, format_comma_separated_list, validate_data_dir
from utils.version import AI_SDK_VERSION

DATA_DIR = validate_data_dir()

required_vars = [
    "AI_SDK_DATA_MARKETPLACE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "EMBEDDINGS_PROVIDER",
    "EMBEDDINGS_MODEL",
    "VECTOR_STORE"
]

# Load and check configuration variables
check_env_variables(required_vars)

AI_SDK_HOST = os.getenv("AI_SDK_HOST", "0.0.0.0")
AI_SDK_PORT = int(os.getenv("AI_SDK_PORT", 8008))
AI_SDK_ROOT_PATH = normalize_root_path(os.getenv("AI_SDK_ROOT_PATH", ""))
AI_SDK_WORKERS = int(os.getenv("AI_SDK_WORKERS", '1'))
AI_SDK_SSL_KEY = os.getenv("AI_SDK_SSL_KEY")
AI_SDK_SSL_CERT = os.getenv("AI_SDK_SSL_CERT")
AI_SDK_LLM_PROVIDER = os.getenv("LLM_PROVIDER")
AI_SDK_LLM_MODEL = os.getenv("LLM_MODEL")
AI_SDK_LLM_TEMPERATURE = os.getenv("LLM_TEMPERATURE")
AI_SDK_LLM_MAX_TOKENS = os.getenv("LLM_MAX_TOKENS")
AI_SDK_THINKING_LLM_PROVIDER = os.getenv("THINKING_LLM_PROVIDER")
AI_SDK_THINKING_LLM_MODEL = os.getenv("THINKING_LLM_MODEL")
THINKING_MODEL_AVAILABLE = bool(
    AI_SDK_THINKING_LLM_PROVIDER and AI_SDK_THINKING_LLM_MODEL
)
AI_SDK_EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER")
AI_SDK_EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL")
AI_SDK_VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE")
AI_SDK_DATA_MARKETPLACE_URL = os.getenv("AI_SDK_DATA_MARKETPLACE_URL")
AI_SDK_DATA_MARKETPLACE_VERIFY_SSL = bool(int(os.getenv("DATA_MARKETPLACE_VERIFY_SSL", 0)))
AI_SDK_CHECK_AMBIGUITY = bool(int(os.getenv("CHECK_AMBIGUITY", "1")))
AI_SDK_ALLOWED_METADATA_USERS = os.getenv("AI_SDK_ALLOWED_METADATA_USERS")
AI_SDK_ALLOWED_METADATA_ROLES = os.getenv("AI_SDK_ALLOWED_METADATA_ROLES")
AI_SDK_FORWARD_CUSTOM_HEADERS = os.getenv("FORWARD_CUSTOM_HEADERS")
AI_SDK_MCP_MODE = os.getenv("AI_SDK_MCP_MODE")
AI_SDK_PERMISSIONS_CACHE = os.getenv("AI_SDK_PERMISSIONS_CACHE", "1") == "1"
AI_SDK_PERMISSIONS_CACHE_MAX_SIZE = int(os.getenv("AI_SDK_PERMISSIONS_CACHE_MAX_SIZE", "1000"))
AI_SDK_PERMISSIONS_CACHE_TTL = int(os.getenv("AI_SDK_PERMISSIONS_CACHE_TTL", "300"))

if THINKING_MODEL_AVAILABLE:
    AI_SDK_THINKING_LLM_TEMPERATURE = os.getenv("THINKING_LLM_TEMPERATURE")
    AI_SDK_THINKING_LLM_MAX_TOKENS = os.getenv("THINKING_LLM_MAX_TOKENS")
    AI_SDK_DEEPQUERY_EXECUTION_MODEL = os.getenv("DEEPQUERY_EXECUTION_MODEL")
    AI_SDK_DEEPQUERY_DEFAULT_ROWS = os.getenv("DEEPQUERY_DEFAULT_ROWS")
    AI_SDK_DEEPQUERY_MAX_ANALYSIS_LOOPS = os.getenv("DEEPQUERY_MAX_ANALYSIS_LOOPS")
    AI_SDK_DEEPQUERY_MAX_REPORTING_LOOPS = os.getenv("DEEPQUERY_MAX_REPORTING_LOOPS")
else:
    AI_SDK_THINKING_LLM_TEMPERATURE = None
    AI_SDK_THINKING_LLM_MAX_TOKENS = None
    AI_SDK_DEEPQUERY_EXECUTION_MODEL = None
    AI_SDK_DEEPQUERY_DEFAULT_ROWS = None
    AI_SDK_DEEPQUERY_MAX_ANALYSIS_LOOPS = None
    AI_SDK_DEEPQUERY_MAX_REPORTING_LOOPS = None

# Set this for the tokenizers
os.environ["TOKENIZERS_PARALLELISM"] = "false"

def log_ai_sdk_parameters():
    """Logs the initialized SDK parameters."""

    access_control_log = []
    if AI_SDK_ALLOWED_METADATA_ROLES:
        access_control_log.append(f"Roles: [{AI_SDK_ALLOWED_METADATA_ROLES}]")
    if AI_SDK_ALLOWED_METADATA_USERS:
        suffix = " (Fallback)" if AI_SDK_ALLOWED_METADATA_ROLES else ""
        access_control_log.append(f"Users: [{AI_SDK_ALLOWED_METADATA_USERS}]{suffix}")

    access_msg = " | ".join(access_control_log) if access_control_log else "Open access (No restrictions configured)"

    cache_status = (
        f"Enabled (max_size={AI_SDK_PERMISSIONS_CACHE_MAX_SIZE}, ttl={AI_SDK_PERMISSIONS_CACHE_TTL}s)"
        if AI_SDK_PERMISSIONS_CACHE else "Disabled"
    )

    ai_sdk_params = {
        "OS": platform.platform(),
        "AI SDK Host": AI_SDK_HOST,
        "AI SDK Port": AI_SDK_PORT,
        "AI SDK Root Path": AI_SDK_ROOT_PATH or "/",
        "AI SDK Version": AI_SDK_VERSION,
        "AI SDK Data Dir (logs, cache, reports...)": DATA_DIR,
        "AI SDK Workers": AI_SDK_WORKERS,
        "Using SSL": bool(AI_SDK_SSL_KEY and AI_SDK_SSL_CERT),
        "LLM Model": f"{AI_SDK_LLM_PROVIDER}/{AI_SDK_LLM_MODEL} (temp={AI_SDK_LLM_TEMPERATURE}, max_tokens={AI_SDK_LLM_MAX_TOKENS})",
        "Thinking LLM Model": (
            f"{AI_SDK_THINKING_LLM_PROVIDER}/{AI_SDK_THINKING_LLM_MODEL} "
            f"(temp={AI_SDK_THINKING_LLM_TEMPERATURE}, max_tokens={AI_SDK_THINKING_LLM_MAX_TOKENS})"
            if THINKING_MODEL_AVAILABLE else "Not configured"
        ),
        "Embeddings Model": f"{AI_SDK_EMBEDDINGS_PROVIDER}/{AI_SDK_EMBEDDINGS_MODEL}",
        "Vector Store Provider": AI_SDK_VECTOR_STORE_PROVIDER,
        "Data Marketplace URL": AI_SDK_DATA_MARKETPLACE_URL,
        "Data Marketplace Connection": test_data_catalog_connection(AI_SDK_DATA_MARKETPLACE_URL, AI_SDK_DATA_MARKETPLACE_VERIFY_SSL),
        "Data Marketplace Verify SSL": AI_SDK_DATA_MARKETPLACE_VERIFY_SSL,
        "Check Ambiguity": AI_SDK_CHECK_AMBIGUITY,
        "Metadata Access Control": access_msg,
        "Permissions Cache": cache_status,
        "Forwarded Custom Headers": format_comma_separated_list(AI_SDK_FORWARD_CUSTOM_HEADERS) if AI_SDK_FORWARD_CUSTOM_HEADERS else "None"
    }

    if THINKING_MODEL_AVAILABLE:
        ai_sdk_params.update({
            "DeepQuery Execution Model": AI_SDK_DEEPQUERY_EXECUTION_MODEL,
            "DeepQuery Default Rows": AI_SDK_DEEPQUERY_DEFAULT_ROWS,
            "DeepQuery Max Analysis Loops": AI_SDK_DEEPQUERY_MAX_ANALYSIS_LOOPS,
            "DeepQuery Max Reporting Loops": AI_SDK_DEEPQUERY_MAX_REPORTING_LOOPS,
        })
    else:
        ai_sdk_params["DeepQuery"] = "Disabled (no thinking model configured)"

    logging.info("AI SDK parameters:")
    for key, value in ai_sdk_params.items():
        logging.info(f"    - {key}: {value}")

    if not ai_sdk_params["Data Marketplace Connection"]:
        logging.warning("Could not establish connection to Data Marketplace. Please check your configuration.")

    return ai_sdk_params["Data Marketplace Connection"]

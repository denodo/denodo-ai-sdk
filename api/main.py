import os
import sys
import logging
import logging.config
import uvicorn
import warnings
import platform
from contextlib import asynccontextmanager

from fastapi_offline import FastAPIOffline as FastAPI
from fastapi.responses import FileResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware

from api.utils import sdk_config_loader, state_manager
from api.utils.sdk_utils import check_env_variables, test_data_catalog_connection
from api.endpoints import (
    getMetadata,
    deleteMetadata,
    similaritySearch,
    streamAnswerQuestion,
    streamAnswerQuestionUsingViews,
    answerQuestion,
    answerQuestionUsingViews,
    answerDataQuestion,
    answerMetadataQuestion
)
from utils.logging_utils import get_logging_config
from utils.utils import normalize_root_path

required_vars = [
    "DATA_CATALOG_URL",
    "QUERY_TO_VQL",
    "ANSWER_VIEW",
    "SQL_CATEGORY",
    "METADATA_CATEGORY",
    "GENERATE_VISUALIZATION",
    "GENERATE_VISUALIZATION_PYTHON_TEMPLATE",
    "DATES_VQL",
    "ARITHMETIC_VQL",
    "VQL_RULES",
    "FIX_LIMIT",
    "FIX_OFFSET",
    "QUERY_FIXER",
    "QUERY_REVIEWER",
    "RELATED_QUESTIONS"
]

log_config = get_logging_config()
logging.config.dictConfig(log_config)

# Ignore warnings
warnings.filterwarnings("ignore")

# Load and check configuration variables
check_env_variables(required_vars)

# Suppress matplotlib font warnings for graph generation
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

# Suppress Chroma warnings related to embedding deletion
logging.getLogger('chromadb').setLevel(logging.ERROR)

AI_SDK_HOST = os.getenv("AI_SDK_HOST", "0.0.0.0")
AI_SDK_PORT = int(os.getenv("AI_SDK_PORT", 8008))
AI_SDK_ROOT_PATH = normalize_root_path(os.getenv("AI_SDK_ROOT_PATH", ""))
AI_SDK_WORKERS = int(os.getenv("AI_SDK_WORKERS", '1'))
AI_SDK_VERSION = os.getenv("AI_SDK_VER")
AI_SDK_SSL_KEY = os.getenv("AI_SDK_SSL_KEY")
AI_SDK_SSL_CERT = os.getenv("AI_SDK_SSL_CERT")
AI_SDK_CHAT_PROVIDER = os.getenv("CHAT_PROVIDER")
AI_SDK_CHAT_MODEL = os.getenv("CHAT_MODEL")
AI_SDK_SQL_GEN_PROVIDER = os.getenv("SQL_GENERATION_PROVIDER")
AI_SDK_SQL_GEN_MODEL = os.getenv("SQL_GENERATION_MODEL")
AI_SDK_EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER")
AI_SDK_EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL")
AI_SDK_VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE")
AI_SDK_DATA_CATALOG_URL = os.getenv("DATA_CATALOG_URL")
AI_SDK_DATA_CATALOG_VERIFY_SSL = bool(int(os.getenv("DATA_CATALOG_VERIFY_SSL", 0)))

# Set this for the tokenizers
os.environ["TOKENIZERS_PARALLELISM"] = "false"

def log_ai_sdk_parameters():
    ai_sdk_params = {
        "OS": platform.platform(),
        "AI SDK Host": AI_SDK_HOST,
        "AI SDK Port": AI_SDK_PORT,
        "AI SDK Root Path": AI_SDK_ROOT_PATH,
        "AI SDK Version": AI_SDK_VERSION,
        "AI SDK Workers": AI_SDK_WORKERS,
        "Using SSL": bool(AI_SDK_SSL_KEY and AI_SDK_SSL_CERT),
        "Chat Provider": AI_SDK_CHAT_PROVIDER,
        "Chat Model": AI_SDK_CHAT_MODEL,
        "SQL Gen Provider": AI_SDK_SQL_GEN_PROVIDER,
        "SQL Gen Model": AI_SDK_SQL_GEN_MODEL,
        "Embeddings Provider": AI_SDK_EMBEDDINGS_PROVIDER,
        "Embeddings Model": AI_SDK_EMBEDDINGS_MODEL,
        "Vector Store Provider": AI_SDK_VECTOR_STORE_PROVIDER,
        "Data Catalog URL": AI_SDK_DATA_CATALOG_URL,
        "Data Catalog Connection": test_data_catalog_connection(AI_SDK_DATA_CATALOG_URL, AI_SDK_DATA_CATALOG_VERIFY_SSL),
        "Data Catalog Verify SSL": AI_SDK_DATA_CATALOG_VERIFY_SSL,
    }

    logging.info("AI SDK parameters:")
    for key, value in ai_sdk_params.items():
        logging.info(f"    - {key}: {value}")

    if not ai_sdk_params["Data Catalog Connection"]:
        logging.warning("Could not establish connection to Data Catalog. Please check your configuration.")

    return ai_sdk_params["Data Catalog Connection"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the application.
    """
    # On startup, initialize all default resources
    state_manager.initialize_default_resources()
    yield
    logging.info("AI SDK has shut down.")

tags = [
    {"name": "Health Check"},
    {"name": "Vector Store"},
    {"name": "Ask a Question"},
    {"name": "Ask a Question - Streaming"},
    {"name": "Ask a Question - Custom Vector Store"},
    {"name": "Ask a Question - Streaming - Custom Vector Store"},
]

app = FastAPI(
    title = 'Denodo AI SDK',
    summary = 'Be fearless.',
    version = AI_SDK_VERSION,
    openapi_tags = tags,
    root_path = AI_SDK_ROOT_PATH,
    favicon_url = "/favicon.ico",
    lifespan = lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("api/static/favicon.ico")

@app.get("/health", tags=["Health Check"])
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns status 200 if the service is running.
    """
    return {"status": "OK"}

app.include_router(getMetadata.router)
app.include_router(deleteMetadata.router)
app.include_router(similaritySearch.router)
app.include_router(streamAnswerQuestion.router)
app.include_router(streamAnswerQuestionUsingViews.router)
app.include_router(answerQuestion.router)
app.include_router(answerDataQuestion.router)
app.include_router(answerMetadataQuestion.router)
app.include_router(answerQuestionUsingViews.router)

log_ai_sdk_parameters()

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host = AI_SDK_HOST,
        port = AI_SDK_PORT,
        ssl_keyfile = AI_SDK_SSL_KEY,
        ssl_certfile = AI_SDK_SSL_CERT,
        log_config = log_config,
        log_level = logging.INFO,
        workers = AI_SDK_WORKERS
    )
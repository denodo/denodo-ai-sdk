import os
import logging
import uvicorn
import warnings
import platform
from contextlib import asynccontextmanager

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline as FastAPI

from api.utils import sdk_config_loader, state_manager
sdk_config_loader.load_config()

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
    answerMetadataQuestion,
    deepQuery,
    generateDeepQueryPDF
)
from utils.logging_utils import get_logging_config, transaction_id_var
from utils.utils import normalize_root_path, generate_transaction_id
from utils.version import AI_SDK_VERSION

required_vars = [
    ("AI_SDK_DATA_CATALOG_URL", "DATA_CATALOG_URL"),
    "LLM_PROVIDER",
    "LLM_MODEL",
    "EMBEDDINGS_PROVIDER",
    "EMBEDDINGS_MODEL",
    "QUERY_TO_VQL",
    "ANSWER_VIEW",
    "SQL_CATEGORY",
    "DIRECT_SQL_CATEGORY",
    "METADATA_CATEGORY",
    "DIRECT_METADATA_CATEGORY",
    "GENERATE_VISUALIZATION",
    "GENERATE_VISUALIZATION_PYTHON_TEMPLATE",
    "DATES_VQL",
    "ARITHMETIC_VQL",
    "SPATIAL_VQL",
    "AI_VQL",
    "JSON_VQL",
    "XML_VQL",
    "TEXT_VQL",
    "AGGREGATE_VQL",
    "CAST_VQL",
    "WINDOW_VQL",
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
AI_SDK_DATA_CATALOG_URL = os.getenv("AI_SDK_DATA_CATALOG_URL") or os.getenv("DATA_CATALOG_URL")
AI_SDK_DATA_CATALOG_VERIFY_SSL = bool(int(os.getenv("DATA_CATALOG_VERIFY_SSL", 0)))

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
    ai_sdk_params = {
        "OS": platform.platform(),
        "AI SDK Host": AI_SDK_HOST,
        "AI SDK Port": AI_SDK_PORT,
        "AI SDK Root Path": AI_SDK_ROOT_PATH,
        "AI SDK Version": AI_SDK_VERSION,
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
        "Data Catalog URL": AI_SDK_DATA_CATALOG_URL,
        "Data Catalog Connection": test_data_catalog_connection(AI_SDK_DATA_CATALOG_URL, AI_SDK_DATA_CATALOG_VERIFY_SSL),
        "Data Catalog Verify SSL": AI_SDK_DATA_CATALOG_VERIFY_SSL,
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

base_app = FastAPI(
    title = 'Denodo AI SDK',
    summary = 'Be fearless.',
    version = AI_SDK_VERSION,
    openapi_tags = tags,
    root_path = AI_SDK_ROOT_PATH,
    favicon_url = "/favicon.ico",
    lifespan = lifespan,
)

@base_app.middleware("http")
async def add_transaction_id_middleware(request, call_next):
    """
    Middleware to generate a transaction ID for each request,
    store it in a context variable, and add it to the response headers.
    """
    transaction_id = generate_transaction_id()
    token = transaction_id_var.set(transaction_id)

    response = await call_next(request)
    response.headers["X-Transaction-ID"] = transaction_id

    transaction_id_var.reset(token)

    return response

base_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

reports_dir = "api/reports"
os.makedirs(reports_dir, exist_ok=True)
base_app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")

@base_app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("api/static/favicon.ico")

@base_app.get("/health", tags=["Health Check"])
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns status 200 if the service is running.
    """
    return {"status": "OK"}

base_app.include_router(getMetadata.router)
base_app.include_router(deleteMetadata.router)
base_app.include_router(similaritySearch.router)
base_app.include_router(streamAnswerQuestion.router)
base_app.include_router(streamAnswerQuestionUsingViews.router)
base_app.include_router(answerQuestion.router)
base_app.include_router(answerDataQuestion.router)
base_app.include_router(answerMetadataQuestion.router)
base_app.include_router(answerQuestionUsingViews.router)

if THINKING_MODEL_AVAILABLE:
    base_app.include_router(deepQuery.router)
    base_app.include_router(generateDeepQueryPDF.router)
    logging.info("DeepQuery endpoints enabled (thinking model configured).")
else:
    logging.warning("Thinking LLM model not configured — DeepQuery endpoints disabled.")

log_ai_sdk_parameters()

AI_SDK_MCP_MODE = os.getenv("AI_SDK_MCP_MODE")

if AI_SDK_MCP_MODE == "remote":
    logging.info("MCP Remote mode enabled - loading MCP server")
    from api.mcp.remote import get_mcp_app

    mcp_app = get_mcp_app(
        host=AI_SDK_HOST,
        port=AI_SDK_PORT,
        root_path=AI_SDK_ROOT_PATH,
    )

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        """
        Combined lifespan for both the main app and MCP app.
        """
        async with lifespan(app):
            async with mcp_app.lifespan(app):
                yield

    app = FastAPI(
        title="Denodo AI SDK",
        summary="Be fearless.",
        version=AI_SDK_VERSION,
        openapi_tags=tags,
        root_path=AI_SDK_ROOT_PATH,
        favicon_url="/favicon.ico",
        routes=[
            *mcp_app.routes,
            *base_app.routes,
        ],
        lifespan=combined_lifespan,
        middleware=mcp_app.user_middleware + base_app.user_middleware,
    )
    logging.info("MCP endpoints available at /mcp")
else:
    app = base_app
    logging.info("Running in standard mode without MCP")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host = AI_SDK_HOST,
        port = AI_SDK_PORT,
        ssl_keyfile = AI_SDK_SSL_KEY,
        ssl_certfile = AI_SDK_SSL_CERT,
        log_config = log_config,
        workers = AI_SDK_WORKERS
    )
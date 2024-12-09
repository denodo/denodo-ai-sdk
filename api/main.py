import os
import sys
import logging
import uvicorn
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware

from api.utils import sdk_config_loader
from api.utils.sdk_utils import check_env_variables, test_data_catalog_connection
from api.endpoints import (
    getMetadata,
    getConcepts,
    similaritySearch,
    streamAnswerQuestion,
    streamAnswerQuestionUsingViews,
    answerQuestion,
    answerQuestionUsingViews,
    answerDataQuestion,
    answerMetadataQuestion
)

required_vars = [
    "DATA_CATALOG_URL",
    "DATA_CATALOG_METADATA_USER",
    "DATA_CATALOG_METADATA_PWD",
    "QUERY_TO_VQL",
    "ANSWER_VIEW",
    "SQL_CATEGORY",
    "METADATA_CATEGORY",
    "GET_CONCEPTS",
    "GENERATE_VISUALIZATION",
    "VQL_RESTRICTIONS",
    "GROUPBY_VQL",
    "HAVING_VQL",
    "DATES_VQL",
    "ARITHMETIC_VQL",
    "VQL_RULES",
    "FIX_LIMIT",
    "FIX_OFFSET",
    "QUERY_FIXER"
]

# Ignore warnings
warnings.filterwarnings("ignore")

# Load and check configuration variables
check_env_variables(required_vars)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

AI_SDK_HOST = os.getenv("AI_SDK_HOST", "0.0.0.0")
AI_SDK_PORT = int(os.getenv("AI_SDK_PORT", 8008))
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
AI_SDK_VDB_NAMES = [db.strip() for db in os.getenv("VDB_NAMES", "").split(",")]
AI_SDK_DATA_CATALOG_URL = os.getenv("DATA_CATALOG_URL")
AI_SDK_DATA_CATALOG_VERIFY_SSL = bool(int(os.getenv("DATA_CATALOG_VERIFY_SSL", 0)))
AI_SDK_DATA_CATALOG_AUTH_TYPE = os.getenv("DATA_CATALOG_AUTH_TYPE", "http_basic")
AI_SDK_USER_PERMISSIONS = bool(int(os.getenv("USER_PERMISSIONS", 0)))

# Set this for the tokenizers
os.environ["TOKENIZERS_PARALLELISM"] = "false"

@asynccontextmanager
async def lifespan(app: FastAPI):
    ai_sdk_params = {
        "AI SDK Host": AI_SDK_HOST,
        "AI SDK Port": AI_SDK_PORT,
        "AI SDK Version": AI_SDK_VERSION,
        "Using SSL": bool(AI_SDK_SSL_KEY and AI_SDK_SSL_CERT),
        "Chat Provider": AI_SDK_CHAT_PROVIDER,
        "Chat Model": AI_SDK_CHAT_MODEL,
        "SQL Gen Provider": AI_SDK_SQL_GEN_PROVIDER,
        "SQL Gen Model": AI_SDK_SQL_GEN_MODEL,
        "Embeddings Provider": AI_SDK_EMBEDDINGS_PROVIDER,
        "Embeddings Model": AI_SDK_EMBEDDINGS_MODEL,
        "Vector Store Provider": AI_SDK_VECTOR_STORE_PROVIDER,
        "VDB Names": AI_SDK_VDB_NAMES,
        "Data Catalog URL": AI_SDK_DATA_CATALOG_URL,
        "Data Catalog Connection": test_data_catalog_connection(AI_SDK_DATA_CATALOG_URL, AI_SDK_DATA_CATALOG_VERIFY_SSL),
        "Data Catalog Verify SSL": AI_SDK_DATA_CATALOG_VERIFY_SSL,
        "Using user permissions": AI_SDK_USER_PERMISSIONS
    }

    logging.info("AI SDK parameters:")
    for key, value in ai_sdk_params.items():
        logging.info(f"    - {key}: {value}")

    if not ai_sdk_params["Data Catalog Connection"]:
        logging.error("Data Catalog connection failed. Exiting...")
        exit(1)

    yield

app = FastAPI(
    title = 'Denodo AI SDK',
    summary = 'Be fearless.',
    version = AI_SDK_VERSION,
    lifespan = lifespan,
    docs_url = None
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

@app.get("/docs", include_in_schema = False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url = "/openapi.json",
        title = "Denodo AI SDK - Documentation",
        swagger_favicon_url = "favicon.ico"
    )

app.include_router(getMetadata.router)
app.include_router(getConcepts.router)
app.include_router(similaritySearch.router)
app.include_router(streamAnswerQuestion.router)
app.include_router(streamAnswerQuestionUsingViews.router)
app.include_router(answerQuestion.router)
app.include_router(answerDataQuestion.router)
app.include_router(answerMetadataQuestion.router)
app.include_router(answerQuestionUsingViews.router)

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host = AI_SDK_HOST,
        port = AI_SDK_PORT,
        ssl_keyfile = AI_SDK_SSL_KEY,
        ssl_certfile = AI_SDK_SSL_CERT
    )
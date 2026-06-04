"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import os
import asyncio
import logging
import uvicorn
import warnings
from contextlib import asynccontextmanager

from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline as FastAPI

from api import config

from api.middleware import logging_context_middleware, RequestCancelledMiddleware
from api.utils import state_manager
from utils.logging_utils import get_logging_config
from utils.version import AI_SDK_VERSION

from api.endpoints import (
    deepQuery,
    getMetadata,
    deleteMetadata,
    similaritySearch,
    getVectorDBInfo,
    getAISDKInfo,
    streamAnswerQuestion,
    streamAnswerQuestionUsingViews,
    answerQuestion,
    answerDataQuestion,
    answerMetadataQuestion,
    answerQuestionUsingViews,
    generateDeepQueryReport,
    getUserPermissions
)

log_config = get_logging_config()
logging.config.dictConfig(log_config)

# Ignore warnings
warnings.filterwarnings("ignore")

# Suppress matplotlib font warnings for graph generation
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

# Suppress Chroma warnings related to embedding deletion
logging.getLogger('chromadb').setLevel(logging.ERROR)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events of the application.
    """
    init_task = asyncio.create_task(
        asyncio.to_thread(state_manager.initialize_default_resources)
    )
    yield
    if not init_task.done():
        init_task.cancel()
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
    title='Denodo AI SDK',
    summary='Be fearless.',
    version=AI_SDK_VERSION,
    openapi_tags=tags,
    root_path=config.AI_SDK_ROOT_PATH,
    favicon_url="/favicon.svg",
    lifespan=lifespan,
)

# Middlewares
base_app.add_middleware(RequestCancelledMiddleware)

base_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
base_app.middleware("http")(logging_context_middleware)

# Base routes
@base_app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    return FileResponse("api/static/favicon.svg")

@base_app.get("/health", tags=["Health Check"])
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns status 200 if the service is running.
    """
    return {"status": "OK"}

# Include routers
base_app.include_router(getMetadata.router)
base_app.include_router(deleteMetadata.router)
base_app.include_router(similaritySearch.router)
base_app.include_router(getVectorDBInfo.router)
base_app.include_router(getAISDKInfo.router)
base_app.include_router(streamAnswerQuestion.router)
base_app.include_router(streamAnswerQuestionUsingViews.router)
base_app.include_router(answerQuestion.router)
base_app.include_router(answerDataQuestion.router)
base_app.include_router(answerMetadataQuestion.router)
base_app.include_router(answerQuestionUsingViews.router)
base_app.include_router(getUserPermissions.router)

if config.THINKING_MODEL_AVAILABLE:
    base_app.include_router(deepQuery.router)
    base_app.include_router(generateDeepQueryReport.router)
    logging.info("DeepQuery endpoints enabled (thinking model configured).")
else:
    logging.warning("Thinking LLM model not configured — DeepQuery endpoints disabled.")

# Log parameters after setup
config.log_ai_sdk_parameters()

# MCP Server Logic
if config.AI_SDK_MCP_MODE == "remote":
    logging.info("MCP Remote mode enabled - loading MCP server")
    from api.mcp.remote import get_mcp_app

    mcp_app = get_mcp_app(
        host=config.AI_SDK_HOST,
        port=config.AI_SDK_PORT,
        root_path=config.AI_SDK_ROOT_PATH,
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
        root_path=config.AI_SDK_ROOT_PATH,
        favicon_url="/favicon.svg",
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
        "api.main:app",
        host=config.AI_SDK_HOST,
        port=config.AI_SDK_PORT,
        ssl_keyfile=config.AI_SDK_SSL_KEY,
        ssl_certfile=config.AI_SDK_SSL_CERT,
        log_config=log_config,
        workers=config.AI_SDK_WORKERS
    )

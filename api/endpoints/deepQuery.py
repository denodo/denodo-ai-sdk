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
import time
import logging
import traceback

from pydantic import BaseModel
from api.utils import state_manager
from api.utils import sdk_ai_tools
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from api.deepquery.main import process_analysis
from fastapi import APIRouter, Depends, HTTPException
from api.utils.sdk_utils import handle_endpoint_error, authenticate

router = APIRouter()

class deepQueryRequest(BaseModel):
    question: str
    execution_model: str = os.getenv("DEEPQUERY_EXECUTION_MODEL", "thinking")  # "thinking" or "base"
    default_rows: int = int(os.getenv("DEEPQUERY_DEFAULT_ROWS", "10"))
    max_analysis_loops: int = int(os.getenv("DEEPQUERY_MAX_ANALYSIS_LOOPS", "50"))
    max_concurrent_tool_calls: int = int(os.getenv("DEEPQUERY_MAX_CONCURRENT_TOOL_CALLS", "5"))
    thinking_llm_provider: str = os.getenv('THINKING_LLM_PROVIDER')
    thinking_llm_model: str = os.getenv('THINKING_LLM_MODEL')
    thinking_llm_temperature: float = float(os.getenv('THINKING_LLM_TEMPERATURE', '0.0'))
    thinking_llm_max_tokens: int = int(os.getenv('THINKING_LLM_MAX_TOKENS', '10240'))
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = int(os.getenv('LLM_MAX_TOKENS', '4096'))
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    vdp_database_names: str = ''
    vdp_tag_names: str = ''
    use_views: str = ''
    expand_set_views: bool = True
    vector_search_k: int = 5
    vector_search_sample_data_k: int = 3

class deepQueryResponse(BaseModel):
    answer: str
    deepquery_metadata: Optional[Dict[str, Any]] = None
    total_execution_time: float

@router.post(
    '/deepQuery',
    response_class=JSONResponse,
    response_model=deepQueryResponse,
    tags=['DeepQuery']
)
@handle_endpoint_error("deepQuery")
async def deep_query_post(
    endpoint_request: deepQueryRequest,
    auth: str = Depends(authenticate)
):
    """Process a a complex analysis question using deepQuery. This endpoint returns the analysis answer along with metadata that can be used for PDF generation
    in a separate endpoint call to generateDeepQueryPDF.
    """

    start_time = time.time()

    try:
        # Planning always uses thinking LLM (from request parameters)
        planning_llm_instance = state_manager.get_llm(
            provider_name=endpoint_request.thinking_llm_provider,
            model_name=endpoint_request.thinking_llm_model,
            temperature=endpoint_request.thinking_llm_temperature,
            max_tokens=endpoint_request.thinking_llm_max_tokens
        )
        planning_llm = planning_llm_instance.llm

        # Execution LLM depends on execution_model setting
        if endpoint_request.execution_model == "thinking":
            executing_llm_instance = planning_llm_instance
        else:  # "base"
            executing_llm_instance = state_manager.get_llm(
                provider_name=endpoint_request.llm_provider,
                model_name=endpoint_request.llm_model,
                temperature=endpoint_request.llm_temperature,
                max_tokens=endpoint_request.llm_max_tokens
            )

        executing_llm = executing_llm_instance.llm

        # Initialize vector stores for schema discovery (following answerQuestion.py pattern)
        vector_store = state_manager.get_vector_store(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model
        )
        sample_data_vector_store = state_manager.get_vector_store(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model,
            index_name="ai_sdk_sample_data"
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    # Get relevant tables using enhanced schema discovery
    vector_search_tables, sample_data, timings = await sdk_ai_tools.get_relevant_tables(
        query=endpoint_request.question,
        vector_store=vector_store,
        sample_data_vector_store=sample_data_vector_store,
        vdb_list=endpoint_request.vdp_database_names,
        tag_list=endpoint_request.vdp_tag_names,
        auth=auth,
        k=endpoint_request.vector_search_k,
        use_views=endpoint_request.use_views,
        expand_set_views=endpoint_request.expand_set_views,
        vector_search_sample_data_k=endpoint_request.vector_search_sample_data_k
    )

    # Format schema text using the same function as answerQuestion.py
    formatted_schema = sdk_ai_tools.format_schema_text(
        vector_search_tables=vector_search_tables,
        filtered_tables=[],
        sample_data=sample_data,
        examples_per_table=endpoint_request.vector_search_sample_data_k
    )

    # Process the analysis question with pre-formatted schema
    if endpoint_request.execution_model == "thinking":
        executing_provider = endpoint_request.thinking_llm_provider
        executing_model = endpoint_request.thinking_llm_model
    else:
        executing_provider = endpoint_request.llm_provider
        executing_model = endpoint_request.llm_model

    result = await process_analysis(
        question=endpoint_request.question,
        executing_llm=executing_llm,
        planning_llm=planning_llm,
        planning_provider=endpoint_request.thinking_llm_provider,
        planning_model=endpoint_request.thinking_llm_model,
        executing_provider=executing_provider,
        executing_model=executing_model,
        default_rows=endpoint_request.default_rows,
        max_analysis_loops=endpoint_request.max_analysis_loops,
        max_concurrent_tool_calls=endpoint_request.max_concurrent_tool_calls,
        formatted_schema=formatted_schema,
        auth=auth,
        thinking_llm_temperature=endpoint_request.thinking_llm_temperature,
        thinking_llm_max_tokens=endpoint_request.thinking_llm_max_tokens,
        llm_temperature=endpoint_request.llm_temperature,
        llm_max_tokens=endpoint_request.llm_max_tokens,
        execution_model=endpoint_request.execution_model
    )

    total_time = time.time() - start_time

    return JSONResponse(
        content=jsonable_encoder({
            "answer": result["answer"],
            "deepquery_metadata": result["deepquery_metadata"],
            "total_execution_time": round(total_time, 2)
        }),
        media_type="application/json"
    )
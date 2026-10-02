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

from pydantic import BaseModel, Field
from api.utils import state_manager
from api.utils import ai_tools
from typing import Optional, Dict, Any, List, Literal
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from api.deepquery.main import process_analysis
from fastapi import APIRouter, Depends, HTTPException
from utils.data_marketplace.connection import get_user_permissions_for_vector_store, DataCatalogAuthError
from api.utils.sdk_utils import (
    handle_endpoint_error,
    authenticate,
    get_custom_request_headers,
    check_deepquery_user_permission,
)
from api.utils import param_descriptions as desc

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
    thinking_llm_max_tokens: int = Field(
        default = int(os.getenv('THINKING_LLM_MAX_TOKENS', '10240')),
        description=desc.THINKING_LLM_MAX_TOKENS
    )
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = Field(
        default = int(os.getenv('LLM_MAX_TOKENS', '4096')),
        description=desc.LLM_MAX_TOKENS
    )
    check_ambiguity: bool = Field(
        default = bool(int(os.getenv('CHECK_AMBIGUITY', '1'))),
        description="If false, skip ambiguity detection in nested answerQuestion calls."
    )
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    vdp_database_names: List[str] = Field(
        default_factory=list,
        description=desc.VDP_DATABASE_NAMES
    )
    vdp_tag_names: List[str] = Field(
        default_factory=list,
        description=desc.VDP_TAG_NAMES
    )
    filter_logic: Literal["AND", "OR"] = Field(
        default = 'OR',
        description=desc.FILTER_LOGIC
    )
    allow_external_associations: bool = Field(
        default = False,
        description=desc.ALLOW_EXTERNAL_ASSOCIATIONS
    )
    use_views: List[str] = Field(
        default_factory=list,
        description=desc.USE_VIEWS
    )
    expand_set_views: bool = Field(
        default = True,
        description=desc.EXPAND_SET_VIEWS
    )
    vector_search_k: int = Field(
        default = 5,
        description=desc.VECTOR_SEARCH_K
    )
    vector_search_sample_data_k: int = Field(
        default = 3,
        description=desc.VECTOR_SEARCH_SAMPLE_DATA_K
    )

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
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """Process a a complex analysis question using deepQuery. This endpoint returns the analysis answer along with metadata that can be used for report generation
    in a separate endpoint call to generateDeepQueryReport.
    """
    start_time = time.time()

    endpoint_request.vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names if db.strip()]
    endpoint_request.vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names if tag.strip()]
    endpoint_request.use_views = [view.strip() for view in endpoint_request.use_views if view.strip()]

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

    try:
        permissions_data = await get_user_permissions_for_vector_store(
            auth=auth, vector_store=vector_store, custom_headers=custom_headers
        )
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during deepQuery: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve permissions: {str(e)}") from e

    if not check_deepquery_user_permission(auth, permissions_data):
        logging.warning("[Security] User unauthorized attempt to use deepQuery.")
        raise HTTPException(status_code=403, detail="You do not have authorization to use the DeepQuery feature. Contact your administrator.")

    vector_search_tables, sample_data, _, _, _ = await ai_tools.get_relevant_tables(
        query=endpoint_request.question,
        vector_store=vector_store,
        sample_data_vector_store=sample_data_vector_store,
        vdb_list=endpoint_request.vdp_database_names,
        tag_list=endpoint_request.vdp_tag_names,
        filter_logic=endpoint_request.filter_logic,
        auth=auth,
        custom_headers=custom_headers,
        vector_search_k=endpoint_request.vector_search_k,
        use_views=endpoint_request.use_views,
        expand_set_views=endpoint_request.expand_set_views,
        vector_search_sample_data_k=endpoint_request.vector_search_sample_data_k,
        allow_external_associations=endpoint_request.allow_external_associations
    )

    # Format schema text using the same function as answerQuestion.py
    formatted_schema = ai_tools.format_schema_text(
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
        llm_provider=endpoint_request.llm_provider,
        llm_model=endpoint_request.llm_model,
        llm_temperature=endpoint_request.llm_temperature,
        llm_max_tokens=endpoint_request.llm_max_tokens,
        check_ambiguity=endpoint_request.check_ambiguity,
        execution_model=endpoint_request.execution_model,
        vdp_database_names=endpoint_request.vdp_database_names,
        vdp_tag_names=endpoint_request.vdp_tag_names,
        allow_external_associations=endpoint_request.allow_external_associations,
        filter_logic=endpoint_request.filter_logic,
        custom_headers=custom_headers
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

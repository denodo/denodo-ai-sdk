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
import logging
import traceback

from pydantic import BaseModel, Field
from typing import Dict

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException

from api.utils.data_category.plot import graph_generator
from api.utils.data_category.serialize import build_execution_result_bundle
from api.utils.sdk_utils import (
    handle_endpoint_error, authenticate, get_custom_request_headers, timing_context
)
from api.utils import param_descriptions as desc
from api.utils import state_manager
from api.endpoints.executeVQL import execute_vql_or_raise

router = APIRouter()

class generateGraphRequest(BaseModel):
    vql: str = Field(
        description=desc.VQL
    )
    plot_details: str = Field(
        default='',
        description="Description of the graph to generate. For example, 'bar chart of customers by country'."
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description=desc.VQL_EXECUTE_ROWS_LIMIT
    )
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = Field(
        default=int(os.getenv('LLM_MAX_TOKENS', '4096')),
        description=desc.LLM_MAX_TOKENS
    )

class generateGraphResponse(BaseModel):
    vql: str
    execution_result: Dict
    raw_graph: str
    tokens: Dict
    sql_execution_time: float
    llm_time: float
    total_execution_time: float
    llm_provider: str
    llm_model: str
    is_masked: bool = Field(default=False)

@router.post(
        '/generateGraph',
        response_class=JSONResponse,
        response_model=generateGraphResponse,
        tags=['Agent Tools'])
@handle_endpoint_error("generateGraph")
async def generate_graph_post(
    endpoint_request: generateGraphRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """Execute a VQL query and generate a graph from the execution result."""
    return await process_generate_graph(endpoint_request, auth, custom_headers)

async def process_generate_graph(request_data: generateGraphRequest, auth: str, custom_headers: dict = None):
    timings = {}

    try:
        llm = state_manager.get_llm(
            provider_name=request_data.llm_provider,
            model_name=request_data.llm_model,
            temperature=request_data.llm_temperature,
            max_tokens=request_data.llm_max_tokens
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    with timing_context("vql_execution_time", timings):
        outcome = await execute_vql_or_raise(
            vql=request_data.vql,
            limit=request_data.limit,
            auth=auth,
            custom_headers=custom_headers,
        )

    execution_result = outcome.data if outcome.is_success else {}
    llm_response_rows_limit = int(os.getenv('LLM_RESPONSE_ROWS_LIMIT', '100'))
    execution_result_bundle = build_execution_result_bundle(execution_result, llm_response_rows_limit) if execution_result else {}

    raw_graph = ""
    tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    if execution_result:
        with timing_context("llm_time", timings):
            raw_graph, tokens = await graph_generator(
                query=request_data.plot_details or "Generate a visualization of the data.",
                plot_data=execution_result,
                llm=llm,
                details=request_data.plot_details or "No special requirements",
            )

    output = {
        "vql": request_data.vql,
        "execution_result": execution_result_bundle,
        "raw_graph": raw_graph,
        "tokens": tokens,
        "sql_execution_time": timings.get("vql_execution_time", 0),
        "llm_time": timings.get("llm_time", 0),
        "total_execution_time": round(sum(timings.values()), 2) if timings else 0,
        "llm_provider": request_data.llm_provider,
        "llm_model": request_data.llm_model,
        "is_masked": outcome.is_masked if execution_result else False,
    }

    return JSONResponse(content=jsonable_encoder(output), media_type="application/json")

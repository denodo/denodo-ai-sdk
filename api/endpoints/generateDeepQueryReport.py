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
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from api.utils.sdk_utils import handle_endpoint_error, authenticate
from api.deepquery.main import generate_report_from_deepquery_metadata

router = APIRouter()

class generateDeepQueryReportRequest(BaseModel):
    deepquery_metadata: Dict[str, Any]
    color_palette: str = "red"
    max_reporting_loops: int = int(os.getenv("DEEPQUERY_MAX_REPORTING_LOOPS", "25"))
    include_failed_tool_calls_appendix: bool = False
    thinking_llm_provider: str = os.getenv("THINKING_LLM_PROVIDER")
    thinking_llm_model: str = os.getenv("THINKING_LLM_MODEL")
    thinking_llm_temperature: float = float(os.getenv("THINKING_LLM_TEMPERATURE", "0.0"))
    thinking_llm_max_tokens: int = Field(
        default = int(os.getenv("THINKING_LLM_MAX_TOKENS", "10240")),
        description="The maximum OUTPUT tokens for the thinking LLM. Not recommended to decrease this value."
    )
    llm_provider: str = os.getenv("LLM_PROVIDER")
    llm_model: str = os.getenv("LLM_MODEL")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    llm_max_tokens: int = Field(
        default = int(os.getenv("LLM_MAX_TOKENS", "4096")),
        description="The maximum OUTPUT tokens for the general LLM. Not recommended to decrease this value."
    )

class generateDeepQueryReportResponse(BaseModel):
    html_report: Optional[str] = None
    total_execution_time: float


@router.post(
    "/generateDeepQueryReport",
    response_class=JSONResponse,
    response_model=generateDeepQueryReportResponse,
    tags=["DeepQuery"],
)
@handle_endpoint_error("generateDeepQueryReport")
async def generate_deep_query_report_post(
    endpoint_request: generateDeepQueryReportRequest,
    auth: str = Depends(authenticate),
):
    """Generate an HTML report from a DeepQuery analysis.

    This endpoint takes the metadata returned from the deepQuery endpoint and generates
    a comprehensive HTML report with visualizations and analysis details.

    The metadata should contain all the necessary information from the analysis phase
    including conversation history, tool calls, cohorts, and schema information.
    """

    start_time = time.time()

    deepquery_metadata = endpoint_request.deepquery_metadata

    if not deepquery_metadata:
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "html_report": None,
                    "total_execution_time": 0,
                    "error": "No deepquery_metadata provided",
                }
            ),
            status_code=400,
            media_type="application/json",
        )

    executing_provider = deepquery_metadata.get(
        "executing_provider", endpoint_request.thinking_llm_provider
    )
    executing_model = deepquery_metadata.get(
        "executing_model", endpoint_request.thinking_llm_model
    )

    try:
        executing_llm_instance = state_manager.get_llm(
            provider_name=executing_provider,
            model_name=executing_model,
            temperature=endpoint_request.thinking_llm_temperature,
            max_tokens=endpoint_request.thinking_llm_max_tokens,
        )
        executing_llm = executing_llm_instance.llm
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing LLM resources: {str(e)}") from e

    result = await generate_report_from_deepquery_metadata(
        deepquery_metadata=deepquery_metadata,
        executing_llm=executing_llm,
        color_palette=endpoint_request.color_palette,
        max_reporting_loops=endpoint_request.max_reporting_loops,
        include_failed_tool_calls_appendix=endpoint_request.include_failed_tool_calls_appendix,
        auth=auth,
    )

    total_time = time.time() - start_time

    return JSONResponse(
        content=jsonable_encoder(
            {
                "html_report": result.get("html_report"),
                "total_execution_time": round(total_time, 2),
            }
        ),
        media_type="application/json",
    )





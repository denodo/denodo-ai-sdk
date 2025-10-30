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
import uuid
import base64
import logging
import traceback

from pathlib import Path
from datetime import datetime
from pydantic import BaseModel
from api.utils import state_manager
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from api.utils.sdk_utils import handle_endpoint_error, authenticate
from api.deepquery.main import generate_pdf_from_deepquery_metadata

router = APIRouter()

class generateDeepQueryPDFRequest(BaseModel):
    deepquery_metadata: Dict[str, Any]
    color_palette: str = "red"
    max_reporting_loops: int = int(os.getenv("DEEPQUERY_MAX_REPORTING_LOOPS", "25"))
    include_failed_tool_calls_appendix: bool = False
    thinking_llm_provider: str = os.getenv('THINKING_LLM_PROVIDER')
    thinking_llm_model: str = os.getenv('THINKING_LLM_MODEL')
    thinking_llm_temperature: float = float(os.getenv('THINKING_LLM_TEMPERATURE', '0.0'))
    thinking_llm_max_tokens: int = int(os.getenv('THINKING_LLM_MAX_TOKENS', '10240'))
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = int(os.getenv('LLM_MAX_TOKENS', '4096'))

class generateDeepQueryPDFResponse(BaseModel):
    pdf_path: Optional[str] = None
    pdf_blob: Optional[str] = None
    total_execution_time: float

@router.post(
    '/generateDeepQueryPDF',
    response_class=JSONResponse,
    response_model=generateDeepQueryPDFResponse,
    tags=['DeepQuery']
)
@handle_endpoint_error("generateDeepQueryPDF")
async def generate_deep_query_pdf_post(
    endpoint_request: generateDeepQueryPDFRequest,
    auth: str = Depends(authenticate)
):
    """Generate a PDF report from a DeepQuery analysis.

    This endpoint takes the metadata returned from the deepQuery endpoint and generates
    a comprehensive PDF report with visualizations and analysis details.

    The metadata should contain all the necessary information from the analysis phase
    including conversation history, tool calls, cohorts, and schema information.
    """

    start_time = time.time()

    # Extract LLM configuration from metadata
    deepquery_metadata = endpoint_request.deepquery_metadata

    if not deepquery_metadata:
        return JSONResponse(
            content=jsonable_encoder({
                "pdf_path": None,
                "pdf_blob": None,
                "total_execution_time": 0,
                "error": "No deepquery_metadata provided"
            }),
            status_code=400,
            media_type="application/json"
        )

    # Get LLM configuration from metadata with fallback to request parameters
    executing_provider = deepquery_metadata.get("executing_provider", endpoint_request.thinking_llm_provider)
    executing_model = deepquery_metadata.get("executing_model", endpoint_request.thinking_llm_model)

    try:
        # Create LLM instance using state_manager with thinking LLM parameters
        executing_llm_instance = state_manager.get_llm(
            provider_name=executing_provider,
            model_name=executing_model,
            temperature=endpoint_request.thinking_llm_temperature,
            max_tokens=endpoint_request.thinking_llm_max_tokens
        )
        executing_llm = executing_llm_instance.llm
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing LLM resources: {str(e)}") from e

    # Generate unique PDF filename using datetime + analysis_title + unique_id
    reports_dir = Path("api/reports")
    unique_id = str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y%m%d")

    # Get report title from metadata, clean it for filename use
    analysis_title = deepquery_metadata.get("analysis_title", "UnknownReport")
    # Clean the report title for use in filename (remove special characters, limit length)
    clean_title = "".join(c for c in analysis_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    clean_title = clean_title.replace(' ', '_')[:50]  # Replace spaces with underscores and limit length

    pdf_filename = f"{current_date}_{clean_title}_{unique_id}.pdf"
    pdf_path = str(reports_dir / pdf_filename)

    # Generate PDF from metadata
    result = await generate_pdf_from_deepquery_metadata(
        deepquery_metadata=deepquery_metadata,
        executing_llm=executing_llm,
        output_pdf=pdf_path,
        color_palette=endpoint_request.color_palette,
        max_reporting_loops=endpoint_request.max_reporting_loops,
        include_failed_tool_calls_appendix=endpoint_request.include_failed_tool_calls_appendix,
        auth=auth
    )

    total_time = time.time() - start_time

    # Convert PDF blob to base64 if available
    pdf_blob_base64 = None
    if result["pdf_blob"]:
        pdf_blob_base64 = base64.b64encode(result["pdf_blob"]).decode('utf-8')

    return JSONResponse(
        content=jsonable_encoder({
            "pdf_path": pdf_filename if result["pdf_blob"] else None,
            "pdf_blob": pdf_blob_base64,
            "total_execution_time": round(total_time, 2)
        }),
        media_type="application/json"
    )
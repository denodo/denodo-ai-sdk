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

from pydantic import BaseModel, Field
from typing import Dict

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException

from utils.data_marketplace.connection import execute_vql
from utils.data_marketplace.vql_execution_outcomes import ExecutionStatus
from api.utils.data_category.serialize import build_execution_result_bundle
from api.utils.sdk_utils import handle_endpoint_error, authenticate
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

class executeVQLRequest(BaseModel):
    vql: str = Field(
        description="The VQL query to execute against the Denodo Platform."
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description="Maximum number of rows to return from the VQL execution result."
    )

class executeVQLResponse(BaseModel):
    vql: str
    execution_result: Dict

@router.post(
        '/executeVQL',
        response_class = JSONResponse,
        response_model = executeVQLResponse,
        tags = ['Utilities'])
@handle_endpoint_error("executeVQL")
async def execute_vql_post(
    request: executeVQLRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    This endpoint executes a raw VQL query against the Denodo Platform and returns the execution result.

    The query is executed with the credentials of the authenticated user, so it is subject to the same
    permissions and security policies as any other query run by that user.
    """
    outcome = await execute_vql(
        vql=request.vql,
        auth=auth,
        limit=request.limit,
        custom_headers=custom_headers
    )

    if outcome.is_success:
        execution_result = outcome.data
    elif outcome.is_empty:
        execution_result = {}
    elif outcome.status is ExecutionStatus.CONNECTION_ERROR:
        raise HTTPException(status_code=503, detail=f"VQL execution failed: {outcome.error}")
    else:
        status_code = outcome.http_status if outcome.http_status >= 400 else 400
        raise HTTPException(status_code=status_code, detail=f"VQL execution failed: {outcome.error}")

    # Use the same execution_result format as the answer endpoints: {full, full_csv, llm, llm_csv}.
    # Rows are already capped at request.limit by execute_vql, so the "llm" view matches "full".
    execution_result_bundle = build_execution_result_bundle(execution_result, request.limit) if execution_result else {}

    output = {
        "vql": request.vql,
        "execution_result": execution_result_bundle
    }

    return JSONResponse(content=jsonable_encoder(output), media_type="application/json")

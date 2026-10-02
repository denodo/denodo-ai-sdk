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
from api.utils import param_descriptions as desc

router = APIRouter()

async def execute_vql_or_raise(vql, limit, auth, custom_headers=None):
    """Execute VQL and raise HTTPException on connection or query errors. Empty results are returned as-is."""
    outcome = await execute_vql(
        vql=vql,
        auth=auth,
        limit=limit,
        custom_headers=custom_headers
    )

    if outcome.is_success or outcome.is_empty:
        return outcome
    if outcome.status is ExecutionStatus.CONNECTION_ERROR:
        raise HTTPException(status_code=503, detail=f"VQL execution failed: {outcome.error}")
    status_code = outcome.http_status if outcome.http_status >= 400 else 400
    raise HTTPException(status_code=status_code, detail=f"VQL execution failed: {outcome.error}")

class executeVQLRequest(BaseModel):
    vql: str = Field(
        description=desc.VQL
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description=desc.VQL_EXECUTE_ROWS_LIMIT
    )

class executeVQLResponse(BaseModel):
    vql: str
    execution_result: Dict
    is_masked: bool = Field(default=False)

@router.post(
        '/executeVQL',
        response_class = JSONResponse,
        response_model = executeVQLResponse,
        tags = ['Agent Tools'])
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
    return await process_execute_vql(request, auth, custom_headers)

async def process_execute_vql(request: executeVQLRequest, auth: str, custom_headers: dict = None):
    outcome = await execute_vql_or_raise(
        vql=request.vql,
        limit=request.limit,
        auth=auth,
        custom_headers=custom_headers
    )

    execution_result = outcome.data if outcome.is_success else {}
    llm_response_rows_limit = int(os.getenv('LLM_RESPONSE_ROWS_LIMIT', '100'))
    execution_result_bundle = build_execution_result_bundle(execution_result, llm_response_rows_limit) if execution_result else {}

    output = {
        "vql": request.vql,
        "execution_result": execution_result_bundle,
        "is_masked": outcome.is_masked
    }

    return JSONResponse(content=jsonable_encoder(output), media_type="application/json")

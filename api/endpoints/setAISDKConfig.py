"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException

from utils.data_marketplace.connection import get_user_permissions, DataCatalogAuthError
from api.utils.sdk_utils import (
    handle_endpoint_error, authenticate, get_custom_request_headers,
    check_log_level_user_permission
)
from utils.runtime_config import update_runtime_config

router = APIRouter()

class setAISDKConfigRequest(BaseModel):
    log_level: Optional[Literal["DEBUG", "INFO"]] = Field(
        default=None,
        description="The log level to set for the AI SDK and sample chatbot. Possible values: DEBUG, INFO."
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value):
        if isinstance(value, str):
            return value.strip().upper() or None
        return value

@router.post(
    '/setAISDKConfig',
    response_class=JSONResponse,
    tags=['Configuration']
)
@handle_endpoint_error("setAISDKConfig")
async def setAISDKConfig(
    endpoint_request: setAISDKConfigRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    Changes runtime-overridable AI SDK settings. No restart is required.

    You can read the current values from GET /getAISDKInfo.
    """
    try:
        permissions_data = await get_user_permissions(auth=auth, custom_headers=custom_headers)
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during setAISDKConfig: {str(e)}") from e

    if not check_log_level_user_permission(auth, permissions_data):
        logging.warning("[Security] User unauthorized attempt to use setAISDKConfig.")
        raise HTTPException(status_code=403, detail="You do not have authorization to change the AI SDK log level.")

    updates = endpoint_request.model_dump(exclude_unset=True)
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No configuration fields provided.")

    try:
        config = update_runtime_config(updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return JSONResponse(content={"log_level": config["log_level"]}, status_code=200)

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

from pydantic import BaseModel, Field
from typing import List, Optional

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends

from api.utils.sdk_utils import handle_endpoint_error, authenticate
from utils.uniformLLM import UniformLLM

router = APIRouter()


class LLMConfigResponse(BaseModel):
    provider: str = Field(description="The LLM provider name (lowercase).")
    model: str = Field(description="The LLM model identifier.")
    temperature: float = Field(description="The temperature setting for the LLM.")
    max_tokens: int = Field(description="The maximum output tokens for the LLM.")


class AISDKInfoResponse(BaseModel):
    base_llm: LLMConfigResponse = Field(description="Configuration for the base LLM used for general tasks.")
    thinking_llm: Optional[LLMConfigResponse] = Field(
        default=None,
        description="Configuration for the thinking/reasoning LLM. Null if not configured."
    )
    check_ambiguity: bool = Field(description="Whether ambiguity detection is enabled.")
    deepquery_execution_model: str = Field(
        description="Which LLM is used for DeepQuery execution: 'thinking' or 'base'."
    )
    valid_providers: List[str] = Field(description="List of supported LLM provider names.")


@router.get(
    '/getAISDKInfo',
    response_class=JSONResponse,
    response_model=AISDKInfoResponse,
    tags=['Configuration']
)
@handle_endpoint_error("getAISDKInfo")
async def get_ai_sdk_info(auth: str = Depends(authenticate)):
    """
    Returns the current AI SDK LLM configuration, including base LLM,
    thinking LLM settings, and the list of valid providers.
    This information can be used to pre-fill settings in client applications.
    """
    llm_provider = os.getenv("LLM_PROVIDER", "")
    base_llm = {
        "provider": llm_provider.lower(),
        "model": os.getenv("LLM_MODEL"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.0")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
    }

    thinking_provider = os.getenv("THINKING_LLM_PROVIDER")
    thinking_model = os.getenv("THINKING_LLM_MODEL")

    thinking_llm = None
    if thinking_provider and thinking_model:
        thinking_llm = {
            "provider": thinking_provider.lower(),
            "model": thinking_model,
            "temperature": float(os.getenv("THINKING_LLM_TEMPERATURE", "0.0")),
            "max_tokens": int(os.getenv("THINKING_LLM_MAX_TOKENS", "10240")),
        }

    deepquery_execution_model = os.getenv("DEEPQUERY_EXECUTION_MODEL", "thinking")

    return JSONResponse(content={
        "base_llm": base_llm,
        "thinking_llm": thinking_llm,
        "check_ambiguity": bool(int(os.getenv("CHECK_AMBIGUITY", "1"))),
        "deepquery_execution_model": deepquery_execution_model,
        "valid_providers": UniformLLM.get_providers(),
    }, status_code=200)

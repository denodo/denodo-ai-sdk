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
import logging
import traceback

from pydantic import BaseModel, Field
from typing import Dict, Annotated, List, Literal

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils.sdk_utils import timing_context, add_tokens, handle_endpoint_error, generate_session_id
from api.utils import sdk_ai_tools
from api.utils import sdk_answer_question
from api.utils import state_manager

router = APIRouter()
security_basic = HTTPBasic(auto_error = False)
security_bearer = HTTPBearer(auto_error = False)

def authenticate(
        basic_credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]
        ):
    if bearer_credentials is not None:
        return bearer_credentials.credentials
    elif basic_credentials is not None:
        return (basic_credentials.username, basic_credentials.password)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

class answerQuestionUsingViewsRequest(BaseModel):
    question: str
    vector_search_tables: List[str]
    plot: bool = False
    plot_details: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = int(os.getenv('LLM_MAX_TOKENS', '4096'))
    markdown_response: bool = True
    custom_instructions: str = ''
    vector_search_k: int = 5
    mode: Literal["default", "data", "metadata"] = Field(default = "default")
    disclaimer: bool = True
    verbose: bool = True
    vql_execute_rows_limit: int = int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '100'))
    llm_response_rows_limit: int = int(os.getenv('LLM_RESPONSE_ROWS_LIMIT', '15'))

class answerQuestionUsingViewsResponse(BaseModel):
    answer: str
    sql_query: str
    query_explanation: str
    tokens: Dict
    execution_result: Dict
    related_questions: List[str]
    tables_used: List[str]
    raw_graph: str
    sql_execution_time: float
    vector_store_search_time: float
    llm_time: float
    total_execution_time: float

@router.post(
        '/answerQuestionUsingViews',
        response_class = JSONResponse,
        response_model = answerQuestionUsingViewsResponse,
        tags = ['Ask a Question - Custom Vector Store'])
@handle_endpoint_error("answerQuestionUsingViews")
async def answerQuestionUsingViews(endpoint_request: answerQuestionUsingViewsRequest, auth: str = Depends(authenticate)):
    """
    The only difference between this endpoint and `answerQuestion` is that this endpoint
    expects the result of the vector search to be passed in as a parameter.

    To simply limit or force the LLM to use a specific set of views, please use answerQuestion.

    This is useful for implementations with custom vector stores.

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - LLM_PROVIDER
    - LLM_MODEL
    - LLM_TEMPERATURE
    - LLM_MAX_TOKENS

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior."""

    # Generate session ID for Langfuse debugging purposes
    session_id = generate_session_id(endpoint_request.question)

    try:
        llm = state_manager.get_llm(
            provider_name=endpoint_request.llm_provider,
            model_name=endpoint_request.llm_model,
            temperature=endpoint_request.llm_temperature,
            max_tokens=endpoint_request.llm_max_tokens
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    # Combine custom instructions from environment and request
    base_instructions = os.getenv('CUSTOM_INSTRUCTIONS', '')
    if endpoint_request.custom_instructions:
        endpoint_request.custom_instructions = f"{base_instructions}\n{endpoint_request.custom_instructions}".strip()
    else:
        endpoint_request.custom_instructions = base_instructions

    timings = {}
    with timing_context("llm_time", timings):
        category, category_response, category_related_questions, sql_category_tokens = await sdk_ai_tools.sql_category(
            query=endpoint_request.question,
            vector_search_tables=endpoint_request.vector_search_tables,
            llm=llm,
            mode=endpoint_request.mode,
            custom_instructions=endpoint_request.custom_instructions,
            session_id=session_id
        )

    if category == "SQL":
        response = await sdk_answer_question.process_sql_category(
            request=endpoint_request,
            vector_search_tables=endpoint_request.vector_search_tables,
            category_response=category_response,
            auth=auth,
            timings=timings,
            session_id=session_id,
            chat_llm=llm,
            sql_gen_llm=llm
        )
        response['tokens'] = add_tokens(response['tokens'], sql_category_tokens)
    elif category == "METADATA":
        response = sdk_answer_question.process_metadata_category(
            category_response=category_response,
            category_related_questions=category_related_questions,
            vector_search_tables=endpoint_request.vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens,
            disclaimer=endpoint_request.disclaimer
        )
    else:
        response = sdk_answer_question.process_unknown_category(timings=timings)

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')
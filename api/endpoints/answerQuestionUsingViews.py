"""
 Copyright (c) 2024. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import os

from pydantic import BaseModel, Field
from typing import Dict, Annotated, List, Literal

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils.sdk_utils import timing_context, add_tokens, handle_endpoint_error, generate_session_id
from api.utils import sdk_ai_tools
from api.utils import sdk_answer_question
from utils.uniformLLM import UniformLLM

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
    sql_gen_provider: str = os.getenv('SQL_GENERATION_PROVIDER')
    sql_gen_model: str = os.getenv('SQL_GENERATION_MODEL')
    chat_provider: str = os.getenv('CHAT_PROVIDER')
    chat_model: str = os.getenv('CHAT_MODEL')
    markdown_response: bool = True
    custom_instructions: str = os.getenv('CUSTOM_INSTRUCTIONS', '')
    vector_search_k: int = 5
    mode: Literal["default", "data", "metadata"] = Field(default = "default")
    disclaimer: bool = True
    verbose: bool = True

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
    - SQL_GENERATION_PROVIDER
    - SQL_GENERATION_MODEL
    - CHAT_PROVIDER
    - CHAT_MODEL

    As you can see, you can specify a different provider for SQL generation and chat generation. This is because generating a correct SQL query
    is a complex task that should be handled with a powerful LLM."""

    # Generate session ID for Langfuse debugging purposes
    session_id = generate_session_id(endpoint_request.question)
    chat_llm = UniformLLM(endpoint_request.chat_provider, endpoint_request.chat_model)
    sql_gen_llm = UniformLLM(endpoint_request.sql_gen_provider, endpoint_request.sql_gen_model)

    timings = {}
    with timing_context("llm_time", timings):
        category, category_response, category_related_questions, sql_category_tokens = await sdk_ai_tools.sql_category(
            query=endpoint_request.question, 
            vector_search_tables=endpoint_request.vector_search_tables, 
            llm=chat_llm,
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
            chat_llm=chat_llm,
            sql_gen_llm=sql_gen_llm
        )
        response['tokens'] = add_tokens(response['tokens'], sql_category_tokens)
    elif category == "METADATA":
        response = await sdk_answer_question.process_metadata_category(
            category_response=category_response, 
            category_related_questions=category_related_questions, 
            vector_search_tables=endpoint_request.vector_search_tables, 
            tokens=sql_category_tokens,
            timings=timings,
        )
    else:
        response = sdk_answer_question.process_unknown_category(timings=timings)

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')
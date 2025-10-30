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
from typing import Dict, Annotated, List

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils.sdk_utils import timing_context, handle_endpoint_error, generate_session_id
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

class answerMetadataQuestionRequest(BaseModel):
    question: str
    plot: bool = False
    plot_details: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = int(os.getenv('LLM_MAX_TOKENS', '4096'))
    vdp_database_names: str = ''
    vdp_tag_names: str = ''
    use_views: str = Field(
            default = '',
            description="Please specify a view you want the LLM to take into consideration when answering the question. Expected format is views separated by commas: database.view_name, database.view_name2"
        )
    expand_set_views: bool = Field(
            default = True,
            description="If set to true, the LLM will search for relevant views in the vector store. If set to false, the LLM will not search in the vector store and will only access those specified in use_views"
        )
    custom_instructions: str = ''
    markdown_response: bool = True
    vector_search_k: int = 5
    vector_search_sample_data_k: int = 3
    disclaimer: bool = True
    verbose: bool = True

class answerMetadataQuestionResponse(BaseModel):
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

@router.get(
        '/answerMetadataQuestion',
        response_class = JSONResponse,
        response_model = answerMetadataQuestionResponse,
        tags = ['Ask a Question']
)
@handle_endpoint_error("answerMetadataQuestion")
async def answer_metadata_question_get(
    request: answerMetadataQuestionRequest = Query(),
    auth: str = Depends(authenticate)
):
    '''This endpoint processes a natural language question and tries to answer it using the metadata in Denodo.
    It will do this by:

    - Searching for the relevant tables' schema using vector search
    - Generating an answer to the question using the metadata

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - LLM_PROVIDER
    - LLM_MODEL
    - LLM_TEMPERATURE
    - LLM_MAX_TOKENS
    - CUSTOM_INSTRUCTIONS

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior.'''
    return await process_metadata_question(request, auth)

@router.post(
        '/answerMetadataQuestion',
        response_class = JSONResponse,
        response_model = answerMetadataQuestionResponse,
        tags = ['Ask a Question'])
@handle_endpoint_error("answerMetadataQuestion")
async def answer_metadata_question_post(
    endpoint_request: answerMetadataQuestionRequest,
    auth: str = Depends(authenticate)
):
    '''This endpoint processes a natural language question and tries to answer it using the metadata in Denodo.
    It will do this by:

    - Searching for the relevant tables' schema using vector search
    - Generating an answer to the question using the metadata

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - LLM_PROVIDER
    - LLM_MODEL
    - LLM_TEMPERATURE
    - LLM_MAX_TOKENS
    - CUSTOM_INSTRUCTIONS

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior.'''
    return await process_metadata_question(endpoint_request, auth)

async def process_metadata_question(request_data: answerMetadataQuestionRequest, auth: str):
    """Main function to process the metadata question and return the answer"""

    # Generate session ID for Langfuse debugging purposes
    session_id = generate_session_id(request_data.question)

    try:
        llm = state_manager.get_llm(
            provider_name=request_data.llm_provider,
            model_name=request_data.llm_model,
            temperature=request_data.llm_temperature,
            max_tokens=request_data.llm_max_tokens
        )

        vector_store = state_manager.get_vector_store(
            provider=request_data.vector_store_provider,
            embeddings_provider=request_data.embeddings_provider,
            embeddings_model=request_data.embeddings_model
        )
        sample_data_vector_store = state_manager.get_vector_store(
            provider=request_data.vector_store_provider,
            embeddings_provider=request_data.embeddings_provider,
            embeddings_model=request_data.embeddings_model,
            index_name="ai_sdk_sample_data"
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    vector_search_tables, _, timings = await sdk_ai_tools.get_relevant_tables(
        query=request_data.question,
        vector_store=vector_store,
        sample_data_vector_store=sample_data_vector_store,
        vdb_list=request_data.vdp_database_names,
        tag_list=request_data.vdp_tag_names,
        auth=auth,
        k=request_data.vector_search_k,
        use_views=request_data.use_views,
        expand_set_views=request_data.expand_set_views,
        vector_search_sample_data_k=request_data.vector_search_sample_data_k
    )

    if not vector_search_tables:
        raise HTTPException(status_code=404, detail="The vector search result returned 0 views. This could be due to limited permissions or an empty vector store.")

    # Combine custom instructions from environment and request
    base_instructions = os.getenv('CUSTOM_INSTRUCTIONS', '')
    if request_data.custom_instructions:
        request_data.custom_instructions = f"{base_instructions}\n{request_data.custom_instructions}".strip()
    else:
        request_data.custom_instructions = base_instructions

    with timing_context("llm_time", timings):
        _, category_response, category_related_questions, sql_category_tokens = await sdk_ai_tools.sql_category(
            query=request_data.question,
            vector_search_tables=vector_search_tables,
            llm=llm,
            mode="metadata",
            custom_instructions=request_data.custom_instructions
        )

    response = sdk_answer_question.process_metadata_category(
        category_response=category_response,
        category_related_questions=category_related_questions,
        vector_search_tables=vector_search_tables,
        timings=timings,
        tokens=sql_category_tokens,
        disclaimer=request_data.disclaimer,
    )

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')
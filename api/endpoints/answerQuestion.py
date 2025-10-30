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
from typing import Dict, List, Literal

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query

from api.utils.sdk_utils import (
    timing_context, add_tokens, generate_session_id,
    handle_endpoint_error, authenticate
)
from api.utils import sdk_ai_tools
from api.utils import sdk_answer_question
from api.utils import state_manager

router = APIRouter()

class answerQuestionRequest(BaseModel):
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
    mode: Literal["default", "data", "metadata"] = Field(default = "default")
    disclaimer: bool = True
    verbose: bool = True
    vql_execute_rows_limit: int = int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '100'))
    llm_response_rows_limit: int = int(os.getenv('LLM_RESPONSE_ROWS_LIMIT', '15'))

class answerQuestionResponse(BaseModel):
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
        '/answerQuestion',
        response_class = JSONResponse,
        response_model=answerQuestionResponse,
        tags = ['Ask a Question']
)
@handle_endpoint_error("answerQuestion")
async def answer_question_get(
    request: answerQuestionRequest = Query(),
    auth: str = Depends(authenticate),
):
    """This endpoint processes a natural language question and:

    - Searches for relevant tables using vector search
    - Determines whether the question should be answered using a SQL query or a metadata search
    - Generates a VQL query using an LLM if the question should be answered using a SQL query
    - Executes the VQL query and gets the data
    - Generates an answer to the question using the data and the VQL query

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - LLM_PROVIDER
    - LLM_MODEL
    - LLM_TEMPERATURE
    - LLM_MAX_TOKENS
    - CUSTOM_INSTRUCTIONS
    - VQL_EXECUTE_ROWS_LIMIT
    - LLM_RESPONSE_ROWS_LIMIT

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior."""
    return await process_question(request, auth)

@router.post(
        '/answerQuestion',
        response_class = JSONResponse,
        response_model=answerQuestionResponse,
        tags = ['Ask a Question'])
@handle_endpoint_error("answerQuestion")
async def answer_question_post(
    endpoint_request: answerQuestionRequest,
    auth: str = Depends(authenticate),
):
    """This endpoint processes a natural language question and:

    - Searches for relevant tables using vector search
    - Determines whether the question should be answered using a SQL query or a metadata search
    - Generates a VQL query using an LLM if the question should be answered using a SQL query
    - Executes the VQL query and gets the data
    - Generates an answer to the question using the data and the VQL query

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - LLM_PROVIDER
    - LLM_MODEL
    - LLM_TEMPERATURE
    - LLM_MAX_TOKENS
    - CUSTOM_INSTRUCTIONS
    - VQL_EXECUTE_ROWS_LIMIT
    - LLM_RESPONSE_ROWS_LIMIT

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior."""
    return await process_question(endpoint_request, auth)

async def process_question(request_data: answerQuestionRequest, auth: str):
    """Main function to process the question and return the answer"""
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

    vector_search_tables, sample_data, timings = await sdk_ai_tools.get_relevant_tables(
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
        category, category_response, category_related_questions, sql_category_tokens = await sdk_ai_tools.sql_category(
            query=request_data.question,
            vector_search_tables=vector_search_tables,
            llm=llm,
            mode=request_data.mode,
            custom_instructions=request_data.custom_instructions,
            session_id=session_id
        )

    if category == "SQL":
        response = await sdk_answer_question.process_sql_category(
            request=request_data,
            vector_search_tables=vector_search_tables,
            category_response=category_response,
            auth=auth,
            timings=timings,
            session_id=session_id,
            sample_data=sample_data,
            chat_llm=llm,
            sql_gen_llm=llm
        )
        response['tokens'] = add_tokens(response['tokens'], sql_category_tokens)
    elif category == "METADATA":
        response = sdk_answer_question.process_metadata_category(
            category_response=category_response,
            category_related_questions=category_related_questions,
            vector_search_tables=vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens,
            disclaimer=request_data.disclaimer
        )
    else:
        response = sdk_answer_question.process_unknown_category(timings=timings)

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')
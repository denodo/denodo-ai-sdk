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

from api.utils.sdk_utils import timing_context, add_tokens, generate_session_id, handle_endpoint_error, authenticate, check_llm_permission
from api.utils import ai_tools
from api.utils import answer_question
from api.utils import param_descriptions as desc

from api.utils.data_category.pipeline import process_sql_category
from api.utils import state_manager
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

class answerDataQuestionRequest(BaseModel):
    question: str
    plot: bool = False
    plot_details: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = Field(
        default = int(os.getenv('LLM_MAX_TOKENS', '4096')),
        description=desc.LLM_MAX_TOKENS
    )
    vdp_database_names: List[str] = Field(
        default_factory=list,
        description=desc.VDP_DATABASE_NAMES
    )
    vdp_tag_names: List[str] = Field(
        default_factory=list,
        description=desc.VDP_TAG_NAMES
    )
    filter_logic: Literal["AND", "OR"] = Field(
        default = 'OR',
        description=desc.FILTER_LOGIC
    )
    allow_external_associations: bool = Field(
        default = False,
        description=desc.ALLOW_EXTERNAL_ASSOCIATIONS
    )
    use_views: List[str] = Field(
        default_factory=list,
        description=desc.USE_VIEWS
    )
    expand_set_views: bool = Field(
        default = True,
        description=desc.EXPAND_SET_VIEWS
    )
    custom_instructions: str = ''
    markdown_response: bool = True
    vector_search_k: int = Field(
        default = 5,
        description=desc.VECTOR_SEARCH_K
    )
    vector_search_sample_data_k: int = Field(
        default = 3,
        description=desc.VECTOR_SEARCH_SAMPLE_DATA_K
    )
    vector_search_total_limit: int = Field(
        default = 20,
        description=desc.VECTOR_SEARCH_TOTAL_LIMIT
    )
    vector_search_column_description_char_limit: int = Field(
        default = 200,
        description=desc.VECTOR_SEARCH_COLUMN_DESCRIPTION_CHAR_LIMIT
    )
    vector_search_table_description_char_limit: int = Field(
        default=1000,
        description=desc.VECTOR_SEARCH_TABLE_DESCRIPTION_CHAR_LIMIT
    )
    disclaimer: bool = True
    verbose: bool = Field(
        default = True,
        description=desc.VERBOSE_DATA
    )
    check_ambiguity: bool = Field(
        default = bool(int(os.getenv('CHECK_AMBIGUITY', '1'))),
        description=desc.CHECK_AMBIGUITY
    )
    vql_execute_rows_limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description=desc.VQL_EXECUTE_ROWS_LIMIT
    )
    enable_query_fixer: bool = Field(
        default=bool(int(os.getenv('AUTO_FIXING', '1'))),
        description=desc.ENABLE_QUERY_FIXER
    )
    auto_fixing_attempts: int = Field(
        default=max(1, min(5, int(os.getenv('AUTO_FIXING_ATTEMPTS', '2')))),
        ge=1,
        le=5,
        description="Maximum number of automatic VQL fixing attempts when enable_query_fixer is enabled."
    )
    enable_query_reviewer: bool = Field(
        default=False,
        description=desc.ENABLE_QUERY_REVIEWER
    )

class answerDataQuestionResponse(BaseModel):
    answer: str
    sql_query: str
    query_explanation: str
    tokens: Dict
    execution_result: Dict
    related_tables: List[Dict] = Field(default_factory=list)
    related_questions: List[str]
    tables_used: List[str]
    raw_graph: str
    sql_execution_time: float
    vector_store_search_time: float
    llm_time: float
    total_execution_time: float
    llm_provider: str
    llm_model: str
    is_masked: bool = Field(default=False)

@router.get(
        '/answerDataQuestion',
        response_class = JSONResponse,
        response_model = answerDataQuestionResponse,
        tags = ['Ask a Question']
)
@handle_endpoint_error("answerDataQuestion")
async def answer_data_question_get(
    request: answerDataQuestionRequest = Query(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    '''This endpoint processes a natural language question and tries to answer it using the data in Denodo.

    - Searches for relevant tables using vector search
    - Generates a VQL query using an LLM
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

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior.'''
    return await process_data_question(request, auth, custom_headers)

@router.post(
        '/answerDataQuestion',
        response_class = JSONResponse,
        response_model = answerDataQuestionResponse,
        tags = ['Ask a Question'])
@handle_endpoint_error("answerDataQuestion")
async def answer_data_question_post(
    endpoint_request: answerDataQuestionRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    '''This endpoint processes a natural language question and tries to answer it using the data in Denodo.

    - Searches for relevant tables using vector search
    - Generates a VQL query using an LLM
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

    You can also override the LLM temperature and max_tokens via API parameters for fine-tuning the model behavior.'''
    return await process_data_question(endpoint_request, auth, custom_headers)

async def process_data_question(request_data: answerDataQuestionRequest, auth: str, custom_headers: dict = None):
    """Main function to process the data question and return the answer"""
    # Generate session ID for Langfuse debugging purposes
    session_id = generate_session_id(request_data.question)

    request_data.vdp_database_names = [db.strip() for db in request_data.vdp_database_names if db.strip()]
    request_data.vdp_tag_names = [tag.strip() for tag in request_data.vdp_tag_names if tag.strip()]
    request_data.use_views = [view.strip() for view in request_data.use_views if view.strip()]

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

    vector_search_tables, sample_data, timings, error_message, permissions_data = await ai_tools.get_relevant_tables(
        query=request_data.question,
        vector_store=vector_store,
        sample_data_vector_store=sample_data_vector_store,
        vdb_list=request_data.vdp_database_names,
        tag_list=request_data.vdp_tag_names,
        filter_logic=request_data.filter_logic,
        auth=auth,
        custom_headers=custom_headers,
        vector_search_k=request_data.vector_search_k,
        use_views=request_data.use_views,
        expand_set_views=request_data.expand_set_views,
        vector_search_sample_data_k=request_data.vector_search_sample_data_k,
        allow_external_associations=request_data.allow_external_associations,
        vector_search_total_limit=request_data.vector_search_total_limit
    )

    if not vector_search_tables:
        raise HTTPException(status_code=404, detail = {
            "error": error_message,
            "traceback": ""
        })

    # Combine custom instructions from environment and request
    base_instructions = os.getenv('CUSTOM_INSTRUCTIONS', '')
    if request_data.custom_instructions:
        request_data.custom_instructions = f"{base_instructions}\n{request_data.custom_instructions}".strip()
    else:
        request_data.custom_instructions = base_instructions

    with timing_context("llm_time", timings):
        category, category_response, category_related_questions, sql_category_tokens = await ai_tools.sql_category(
            query=request_data.question,
            vector_search_tables=vector_search_tables,
            llm=llm,
            mode="data",
            custom_instructions=request_data.custom_instructions,
            session_id=session_id,
            column_description_char_limit=request_data.vector_search_column_description_char_limit,
            table_description_char_limit=request_data.vector_search_table_description_char_limit,
            check_ambiguity=request_data.check_ambiguity,
            markdown_response=request_data.markdown_response,
        )

    ambiguity_message = answer_question.build_ambiguity_message(category_response)

    if ambiguity_message:
        response = answer_question.process_ambiguity_category(
            ambiguity_message=ambiguity_message,
            vector_search_tables=vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens
        )
        response['llm_provider'] = request_data.llm_provider
        response['llm_model'] = request_data.llm_model
        return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

    response = await process_sql_category(
        request=request_data,
        vector_search_tables=vector_search_tables,
        category_response=category_response,
        auth=auth,
        custom_headers=custom_headers,
        timings=timings,
        session_id=session_id,
        sample_data=sample_data,
        chat_llm=llm,
        sql_gen_llm=llm,
        can_use_llm=check_llm_permission(permissions_data)
    )

    response['tokens'] = add_tokens(response['tokens'], sql_category_tokens)
    response['llm_provider'] = request_data.llm_provider
    response['llm_model'] = request_data.llm_model

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

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
from typing import Literal

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query

from api.utils import ai_tools
from api.utils import answer_question
from api.utils import state_manager
from api.utils.sdk_utils import timing_context, handle_endpoint_error, generate_session_id, authenticate, check_llm_permission
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

class streamAnswerQuestionRequest(BaseModel):
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
        description="The maximum OUTPUT tokens for the general LLM. Not recommended to decrease this value."
    )
    vdp_database_names: str = Field(
        default = '',
        description="A comma-separated list of databases to reduce the scope of the question to. If empty, all databases in the vector DB the user has permissions to will be considered."
    )
    vdp_tag_names: str = Field(
        default = '',
        description="A comma-separated list of tags to reduce the scope of the question to. If empty, all tags in the vector DB the user has permissions to will be considered."
    )
    allow_external_associations: bool = Field(
        default = False,
        description="If False, views from associations will NOT be considered if they don't belong to the VDBs/Tags specified in vdp_database_names and vdp_tag_names. If no VDBs/Tags specified, all views from associations will be considered."
    )
    use_views: str = Field(
            default = False,
            description="Please specify a view you want the LLM to take into consideration when answering the question. Expected format is views separated by commas: database.view_name, database.view_name2"
        )
    expand_set_views: bool = Field(
            default = True,
            description="If set to true, the LLM will search for relevant views in the vector store. If set to false, the LLM will not search in the vector store and will only access those specified in use_views"
        )
    custom_instructions: str = ''
    markdown_response: bool = True
    vector_search_k: int = Field(
        default = 5,
        description="Number of results to return from the similarity search in the vector store."
    )
    vector_search_sample_data_k: int = Field(
        default = 3,
        description="Number of similar sample data rows to return for the given question."
    )
    vector_search_total_limit: int = Field(
        default = 20,
        description="Maximum number of views to consider in total, including associations of the initial vector_search_k results."
    )
    vector_search_column_description_char_limit: int = Field(
        default=200,
        description="Maximum characters of column descriptions used when filtering how many views to keep. Not applied during vector search or VQL generation (those use full descriptions). Refer to the docs for when this trimming is applied."
    )
    vector_search_table_description_char_limit: int = Field(
        default=1000,
        description="Maximum characters of table descriptions used when filtering how many views to keep. Not applied during vector search or VQL generation (those use full descriptions). Refer to the docs for when this trimming is applied."
    )
    mode: Literal["default", "data", "metadata"] = Field(default = "default")
    disclaimer: bool = True
    verbose: bool = True
    check_ambiguity: bool = Field(
        default = bool(int(os.getenv('CHECK_AMBIGUITY', '1'))),
        description="If false, skip ambiguity detection."
    )
    vql_execute_rows_limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description="Maximum number of rows to return from the VQL execution result."
    )

@router.get(
        '/streamAnswerQuestion',
        response_class=StreamingResponse,
        tags = ['Ask a Question - Streaming']
)
@handle_endpoint_error("streamAnswerQuestion")
async def stream_answer_question_get(
    request: streamAnswerQuestionRequest = Query(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """This endpoint processes a natural language question and:

    - Searches for relevant tables using vector search
    - Determines whether the question should be answered using a SQL query or a metadata search
    - Generates a VQL query using an LLM if the question should be answered using a SQL query
    - Executes the VQL query and gets the data
    - Streams back an answer to the question using the data and the VQL query

    For now, this endpoint only streams back the answer and doesn't return the JSON response like answerQuestion does.

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - SQL_GENERATION_PROVIDER
    - SQL_GENERATION_MODEL
    - CHAT_PROVIDER
    - CHAT_MODEL
    - CUSTOM_INSTRUCTIONS
    - VQL_EXECUTE_ROWS_LIMIT
    As you can see, you can specify a different provider for SQL generation and chat generation. This is because generating a correct SQL query
    is a complex task that should be handled with a powerful LLM."""
    return await process_stream_question(request, auth, custom_headers)

@router.post(
        '/streamAnswerQuestion',
        response_class = StreamingResponse,
        tags = ['Ask a Question - Streaming'])
@handle_endpoint_error("streamAnswerQuestion")
async def stream_answer_question_post(
    endpoint_request: streamAnswerQuestionRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """This endpoint processes a natural language question and:

    - Searches for relevant tables using vector search
    - Determines whether the question should be answered using a SQL query or a metadata search
    - Generates a VQL query using an LLM if the question should be answered using a SQL query
    - Executes the VQL query and gets the data
    - Streams back an answer to the question using the data and the VQL query

    For now, this endpoint only streams back the answer and doesn't return the JSON response like answerQuestion does.

    This endpoint will also automatically look for the the following values in the environment variables for convenience:

    - EMBEDDINGS_PROVIDER
    - EMBEDDINGS_MODEL
    - VECTOR_STORE
    - SQL_GENERATION_PROVIDER
    - SQL_GENERATION_MODEL
    - CHAT_PROVIDER
    - CHAT_MODEL
    - CUSTOM_INSTRUCTIONS
    - VQL_EXECUTE_ROWS_LIMIT
    As you can see, you can specify a different provider for SQL generation and chat generation. This is because generating a correct SQL query
    is a complex task that should be handled with a powerful LLM."""
    return await process_stream_question(endpoint_request, auth, custom_headers)

async def process_stream_question(request_data: streamAnswerQuestionRequest, auth: str, custom_headers: dict = None):
    """Main function to process the question and stream the answer"""
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

    vector_search_tables, sample_data, timings, error_message, permissions_data = await ai_tools.get_relevant_tables(
        query=request_data.question,
        vector_store=vector_store,
        sample_data_vector_store=sample_data_vector_store,
        vdb_list=request_data.vdp_database_names,
        tag_list=request_data.vdp_tag_names,
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
            mode=request_data.mode,
            custom_instructions=request_data.custom_instructions,
            session_id=session_id,
            column_description_char_limit=request_data.vector_search_column_description_char_limit,
            table_description_char_limit=request_data.vector_search_table_description_char_limit,
            check_ambiguity=request_data.check_ambiguity,
            markdown_response=request_data.markdown_response,
        )

    ambiguity_message = answer_question.build_ambiguity_message(category_response)

    if ambiguity_message:
        def generator():
            yield from ambiguity_message
        return StreamingResponse(generator(), media_type = 'text/plain')

    if category == "SQL":
        response = await answer_question.process_sql_category(
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
    elif category == "METADATA":
        response = answer_question.process_metadata_category(
            category_response=category_response,
            category_related_questions=category_related_questions,
            vector_search_tables=vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens,
            disclaimer=request_data.disclaimer
        )
    else:
        response = answer_question.process_unknown_category(timings=timings)

    def generator():
        yield from response.get('answer', 'Error processing the question.')
    return StreamingResponse(generator(), media_type = 'text/plain')

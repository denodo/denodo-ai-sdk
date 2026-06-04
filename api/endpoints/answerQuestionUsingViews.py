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
from fastapi import APIRouter, Depends, HTTPException

from api.utils.sdk_utils import timing_context, add_tokens, handle_endpoint_error, generate_session_id, authenticate
from api.utils import ai_tools
from api.utils import answer_question
from api.utils import state_manager
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

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
    llm_max_tokens: int = Field(
        default = int(os.getenv('LLM_MAX_TOKENS', '4096')),
        description="The maximum OUTPUT tokens for the general LLM. Not recommended to decrease this value."
    )
    markdown_response: bool = True
    custom_instructions: str = ''
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
    verbose: bool = Field(
        default = True,
        description="If true, the LLM will return a natural language response in the answer key based on the selected mode. In data/default mode, it uses the execution result from the generated SQL. In metadata mode, it uses the vector search output of the schema of the relevant views. If set to false, data/default mode returns the execution result and generated SQL query, while metadata mode returns the vector search output of the schema of the relevant views. Setting to false is the recommended option when using the endpoint as a tool."
    )
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

class answerQuestionUsingViewsResponse(BaseModel):
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

@router.post(
        '/answerQuestionUsingViews',
        response_class = JSONResponse,
        response_model = answerQuestionUsingViewsResponse,
        tags = ['Ask a Question - Custom Vector Store'])
@handle_endpoint_error("answerQuestionUsingViews")
async def answerQuestionUsingViews(
    endpoint_request: answerQuestionUsingViewsRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
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
        category, category_response, category_related_questions, sql_category_tokens = await ai_tools.sql_category(
            query=endpoint_request.question,
            vector_search_tables=endpoint_request.vector_search_tables,
            llm=llm,
            mode=endpoint_request.mode,
            custom_instructions=endpoint_request.custom_instructions,
            session_id=session_id,
            column_description_char_limit=endpoint_request.vector_search_column_description_char_limit,
            table_description_char_limit=endpoint_request.vector_search_table_description_char_limit,
            check_ambiguity=endpoint_request.check_ambiguity,
            markdown_response=endpoint_request.markdown_response,
        )

    if endpoint_request.mode == "metadata" and not endpoint_request.verbose:
        response = answer_question.process_metadata_category(
            category_response='',
            category_related_questions=[],
            vector_search_tables=endpoint_request.vector_search_tables,
            timings=timings,
            tokens={'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
            disclaimer=endpoint_request.disclaimer,
        )
        response['llm_provider'] = endpoint_request.llm_provider
        response['llm_model'] = endpoint_request.llm_model
        return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

    ambiguity_message = answer_question.build_ambiguity_message(category_response)

    if ambiguity_message:
        response = answer_question.process_ambiguity_category(
            ambiguity_message=ambiguity_message,
            vector_search_tables=endpoint_request.vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens
        )
    elif category == "SQL":
        response = await answer_question.process_sql_category(
            request=endpoint_request,
            vector_search_tables=endpoint_request.vector_search_tables,
            category_response=category_response,
            auth=auth,
            custom_headers=custom_headers,
            timings=timings,
            session_id=session_id,
            chat_llm=llm,
            sql_gen_llm=llm
        )
        response['tokens'] = add_tokens(response['tokens'], sql_category_tokens)
    elif category == "METADATA":
        response = answer_question.process_metadata_category(
            category_response=category_response,
            category_related_questions=category_related_questions,
            vector_search_tables=endpoint_request.vector_search_tables,
            timings=timings,
            tokens=sql_category_tokens,
            disclaimer=endpoint_request.disclaimer
        )
    else:
        response = answer_question.process_unknown_category(timings=timings)

    response['llm_provider'] = endpoint_request.llm_provider
    response['llm_model'] = endpoint_request.llm_model

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

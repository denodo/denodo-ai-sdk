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
import logging
import traceback

from pydantic import BaseModel, Field
from typing import Dict, List, Literal

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException

from api.utils.sdk_utils import (
    add_tokens, generate_session_id, handle_endpoint_error,
    authenticate, check_llm_permission, get_custom_request_headers, timing_context
)
from api.utils import ai_tools
from api.utils import answer_question
from api.utils.data_category.pipeline import generate_and_resolve
from api.utils.data_category.answer import terminal_answer
from api.utils.data_category.resolve import Resolution, strip_conditions
from api.utils import param_descriptions as desc
from api.utils import state_manager

router = APIRouter()

class generateVQLRequest(BaseModel):
    request: str = Field(
        description="The natural language request to generate a single VQL query from."
    )
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    llm_provider: str = os.getenv('LLM_PROVIDER')
    llm_model: str = os.getenv('LLM_MODEL')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.0'))
    llm_max_tokens: int = Field(
        default=int(os.getenv('LLM_MAX_TOKENS', '4096')),
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
        default="OR",
        description=desc.FILTER_LOGIC
    )
    allow_external_associations: bool = Field(
        default=False,
        description=desc.ALLOW_EXTERNAL_ASSOCIATIONS
    )
    custom_instructions: str = ''
    vector_search_k: int = Field(
        default=5,
        description=desc.VECTOR_SEARCH_K
    )
    vector_search_sample_data_k: int = Field(
        default=3,
        description=desc.VECTOR_SEARCH_SAMPLE_DATA_K
    )
    vector_search_total_limit: int = Field(
        default=20,
        description=desc.VECTOR_SEARCH_TOTAL_LIMIT
    )
    vector_search_column_description_char_limit: int = Field(
        default=200,
        description=desc.VECTOR_SEARCH_COLUMN_DESCRIPTION_CHAR_LIMIT
    )
    vector_search_table_description_char_limit: int = Field(
        default=1000,
        description=desc.VECTOR_SEARCH_TABLE_DESCRIPTION_CHAR_LIMIT
    )
    check_ambiguity: bool = Field(
        default=bool(int(os.getenv('CHECK_AMBIGUITY', '1'))),
        description=desc.CHECK_AMBIGUITY
    )
    vql_execute_rows_limit: int = Field(
        default=100,
        ge=1,
        le=int(os.getenv('VQL_EXECUTE_ROWS_LIMIT', '10000')),
        description=desc.VQL_EXECUTE_ROWS_LIMIT
    )
    auto_fixing: bool = Field(
        default=bool(int(os.getenv('AUTO_FIXING', '1'))),
        description=desc.ENABLE_QUERY_FIXER
    )
    auto_fixing_attempts: int = Field(
        default=max(1, min(5, int(os.getenv('AUTO_FIXING_ATTEMPTS', '2')))),
        ge=1,
        le=5,
        description="Maximum number of automatic VQL fixing attempts when auto_fixing is enabled."
    )
    view_names: List[str] = Field(
        default_factory=list,
        description="A list of already selected views (database.view_name). When set, vector search and view selection are skipped."
    )

    @property
    def question(self):
        return self.request

    @property
    def enable_query_fixer(self):
        return self.auto_fixing

    @property
    def enable_query_reviewer(self):
        return False

class generateVQLResponse(BaseModel):
    vql: str
    query_explanation: str
    tokens: Dict
    execution_result: Dict
    tables_used: List[str]
    answer: str
    sql_execution_time: float
    vector_store_search_time: float
    llm_time: float
    total_execution_time: float
    llm_provider: str
    llm_model: str
    is_masked: bool = Field(default=False)

@router.post(
        '/generateVQL',
        response_class=JSONResponse,
        response_model=generateVQLResponse,
        tags=['Agent Tools'])
@handle_endpoint_error("generateVQL")
async def generate_vql_post(
    endpoint_request: generateVQLRequest,
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """Generate a VQL query from a natural language request, execute it, and optionally auto-fix failures.

    - Searches for relevant views (or uses view_names when provided)
    - Selects views and VQL parts (or only VQL parts when view_names is set)
    - Generates a VQL query
    - Executes it and, if auto_fixing is enabled, retries on execution errors

    This endpoint does not generate a natural-language answer, related questions, or a graph.
    """
    return await process_generate_vql(endpoint_request, auth, custom_headers)

async def process_generate_vql(request_data: generateVQLRequest, auth: str, custom_headers: dict = None):
    session_id = generate_session_id(request_data.request)
    request_data.vdp_database_names = [db.strip() for db in request_data.vdp_database_names if db.strip()]
    request_data.vdp_tag_names = [tag.strip() for tag in request_data.vdp_tag_names if tag.strip()]
    request_data.view_names = [view.strip() for view in request_data.view_names if view.strip()]

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

    if request_data.view_names:
        vector_search_tables, sample_data, timings, error_message, permissions_data = await ai_tools.get_tables_by_name(
            query=request_data.request,
            view_names=request_data.view_names,
            vector_store=vector_store,
            sample_data_vector_store=sample_data_vector_store,
            auth=auth,
            custom_headers=custom_headers,
            vector_search_sample_data_k=request_data.vector_search_sample_data_k,
            vdb_list=request_data.vdp_database_names,
            tag_list=request_data.vdp_tag_names,
            filter_logic=request_data.filter_logic,
        )
    else:
        vector_search_tables, sample_data, timings, error_message, permissions_data = await ai_tools.get_relevant_tables(
            query=request_data.request,
            vector_store=vector_store,
            sample_data_vector_store=sample_data_vector_store,
            vdb_list=request_data.vdp_database_names,
            tag_list=request_data.vdp_tag_names,
            auth=auth,
            custom_headers=custom_headers,
            vector_search_k=request_data.vector_search_k,
            use_views="",
            expand_set_views=True,
            vector_search_sample_data_k=request_data.vector_search_sample_data_k,
            allow_external_associations=request_data.allow_external_associations,
            vector_search_total_limit=request_data.vector_search_total_limit,
            filter_logic=request_data.filter_logic,
        )

    if not vector_search_tables:
        raise HTTPException(status_code=404, detail={
            "error": error_message,
            "traceback": ""
        })

    base_instructions = os.getenv('CUSTOM_INSTRUCTIONS', '')
    if request_data.custom_instructions:
        request_data.custom_instructions = f"{base_instructions}\n{request_data.custom_instructions}".strip()
    else:
        request_data.custom_instructions = base_instructions

    with timing_context("llm_time", timings):
        if request_data.view_names:
            _, category_response, _, sql_category_tokens = await ai_tools.direct_sql_parts(
                query=request_data.request,
                vector_search_tables=vector_search_tables,
                llm=llm,
                custom_instructions=request_data.custom_instructions,
                session_id=session_id,
                column_description_char_limit=request_data.vector_search_column_description_char_limit,
                table_description_char_limit=request_data.vector_search_table_description_char_limit,
                check_ambiguity=request_data.check_ambiguity,
            )
        else:
            _, category_response, _, sql_category_tokens = await ai_tools.sql_category(
                query=request_data.request,
                vector_search_tables=vector_search_tables,
                llm=llm,
                mode="data",
                custom_instructions=request_data.custom_instructions,
                session_id=session_id,
                column_description_char_limit=request_data.vector_search_column_description_char_limit,
                table_description_char_limit=request_data.vector_search_table_description_char_limit,
                check_ambiguity=request_data.check_ambiguity,
                markdown_response=False,
            )

    ambiguity_message = answer_question.build_ambiguity_message(category_response)
    if ambiguity_message:
        response = answer_question.prepare_generate_vql_response(
            vql_query='',
            query_explanation='',
            tokens=sql_category_tokens,
            execution_result={},
            vector_search_tables=vector_search_tables,
            timings=timings,
            answer=ambiguity_message,
            is_masked=False
        )
        response['llm_provider'] = request_data.llm_provider
        response['llm_model'] = request_data.llm_model
        return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

    if request_data.view_names:
        category_response = ai_tools.inject_selected_tables(category_response, request_data.view_names)

    result = await generate_and_resolve(
        request=request_data,
        vector_search_tables=vector_search_tables,
        sql_gen_llm=llm,
        category_response=category_response,
        auth=auth,
        timings=timings,
        session_id=session_id,
        sample_data=sample_data,
        custom_headers=custom_headers,
        can_use_llm=check_llm_permission(permissions_data),
        max_attempts=request_data.auto_fixing_attempts,
    )

    if result.resolved is None:
        response = answer_question.prepare_generate_vql_response(
            vql_query='',
            query_explanation=strip_conditions(result.generated.explanation),
            tokens=add_tokens(result.generated.tokens, sql_category_tokens),
            execution_result={},
            vector_search_tables=vector_search_tables,
            timings=timings,
            answer='No VQL query could be generated, please review the query explanation and the logs and try again.',
            is_masked=False
        )
        response['llm_provider'] = request_data.llm_provider
        response['llm_model'] = request_data.llm_model
        return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

    resolved = result.resolved
    kept_resolved_query = resolved.resolution in (Resolution.SUCCESS, Resolution.EMPTY)
    response_vql = resolved.vql if kept_resolved_query else resolved.original_vql
    execution_result = resolved.outcome.data if resolved.outcome.is_success else {}
    is_masked = resolved.outcome.is_masked if execution_result else False

    override = terminal_answer(resolved.resolution, resolved.attempts)
    if override is None and resolved.resolution is Resolution.EMPTY:
        override = "The VQL query executed correctly, but returned no rows."

    response = answer_question.prepare_generate_vql_response(
        vql_query=response_vql,
        query_explanation=resolved.explanation,
        tokens=add_tokens(resolved.tokens, sql_category_tokens),
        execution_result=execution_result,
        vector_search_tables=vector_search_tables,
        timings=timings,
        answer=override or "",
        is_masked=is_masked
    )
    response['llm_provider'] = request_data.llm_provider
    response['llm_model'] = request_data.llm_model

    return JSONResponse(content=jsonable_encoder(response), media_type='application/json')

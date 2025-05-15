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
from typing import Annotated, Literal

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils import sdk_ai_tools
from api.utils import sdk_answer_question
from api.utils.sdk_utils import timing_context, handle_endpoint_error, generate_session_id
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

class streamAnswerQuestionRequest(BaseModel):
    question: str
    plot: bool = False
    plot_details: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    sql_gen_provider: str = os.getenv('SQL_GENERATION_PROVIDER')
    sql_gen_model: str = os.getenv('SQL_GENERATION_MODEL')
    chat_provider: str = os.getenv('CHAT_PROVIDER')
    chat_model: str = os.getenv('CHAT_MODEL')
    vdp_database_names: str = os.getenv('VDB_NAMES', '')
    vdp_tag_names: str = os.getenv('VDB_TAGS', '')
    use_views: str = ''
    expand_set_views: bool = True
    custom_instructions: str = os.getenv('CUSTOM_INSTRUCTIONS', '')
    markdown_response: bool = True
    vector_search_k: int = 5
    vector_search_sample_data_k: int = 3
    mode: Literal["default", "data", "metadata"] = Field(default = "default")
    disclaimer: bool = True
    verbose: bool = True

@router.get(
        '/streamAnswerQuestion',
        response_class=StreamingResponse,
        tags = ['Ask a Question - Streaming']
)
@handle_endpoint_error("streamAnswerQuestion")
async def stream_answer_question_get(request: streamAnswerQuestionRequest = Depends(), auth: str = Depends(authenticate)):
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
    - VDB_NAMES

    As you can see, you can specify a different provider for SQL generation and chat generation. This is because generating a correct SQL query
    is a complex task that should be handled with a powerful LLM."""
    return await process_stream_question(request, auth)

@router.post(
        '/streamAnswerQuestion',
        response_class = StreamingResponse,
        tags = ['Ask a Question - Streaming'])
@handle_endpoint_error("streamAnswerQuestion")
async def stream_answer_question_post(endpoint_request: streamAnswerQuestionRequest, auth: str = Depends(authenticate)):
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
    - VDB_NAMES

    As you can see, you can specify a different provider for SQL generation and chat generation. This is because generating a correct SQL query
    is a complex task that should be handled with a powerful LLM."""
    return await process_stream_question(endpoint_request, auth)

async def process_stream_question(request_data: streamAnswerQuestionRequest, auth: str):
    """Main function to process the question and stream the answer"""
    # Generate session ID for Langfuse debugging purposes
    session_id = generate_session_id(request_data.question)
    chat_llm = UniformLLM(request_data.chat_provider, request_data.chat_model)
    sql_gen_llm = UniformLLM(request_data.sql_gen_provider, request_data.sql_gen_model)
    
    vector_search_tables, sample_data, timings = await sdk_ai_tools.get_relevant_tables(
        query=request_data.question,
        embeddings_provider=request_data.embeddings_provider,
        embeddings_model=request_data.embeddings_model,
        vector_store_provider=request_data.vector_store_provider,
        vdb_list=request_data.vdp_database_names,
        tag_list=request_data.vdp_tag_names,
        auth=auth,
        k=request_data.vector_search_k,
        use_views=request_data.use_views,
        expand_set_views=request_data.expand_set_views,
        vector_search_sample_data_k=request_data.vector_search_sample_data_k
    )

    with timing_context("llm_time", timings):
        category, category_response, category_related_questions, _ = await sdk_ai_tools.sql_category(
            query=request_data.question, 
            vector_search_tables=vector_search_tables, 
            llm=chat_llm,
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
            chat_llm=chat_llm,
            sql_gen_llm=sql_gen_llm
        )
    elif category == "METADATA":
        response = await sdk_answer_question.process_metadata_category(
            category_response=category_response, 
            category_related_questions=category_related_questions, 
            vector_search_tables=vector_search_tables, 
            timings=timings,
        )
    else:
        response = sdk_answer_question.process_unknown_category(timings=timings)

    def generator():
        yield from response.get('answer', 'Error processing the question.')
    return StreamingResponse(generator(), media_type = 'text/plain')
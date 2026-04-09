from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils.data_catalog import execute_vql
from utils.utils import custom_tag_parser
from api.utils.ai_tools.types import empty_tokens
from api.utils.ai_tools.vql_fixer import query_fixer, query_reviewer
from api.utils.answer_question.types import QueryExecutionResult
from api.utils.sdk_utils import add_tokens, timing_context


async def execute_query(vql_query, auth, limit, timings, custom_headers=None):
    with timing_context("vql_execution_time", timings):
        if vql_query:
            vql_status_code, execution_result = await execute_vql(
                vql=vql_query, auth=auth, limit=limit, custom_headers=custom_headers
            )
        else:
            vql_status_code = 499
            execution_result = "No VQL query was generated."
    return execution_result, vql_status_code, timings


async def attempt_query_execution(
    vql_query,
    request,
    auth, llm,
    timings,
    vector_search_tables,
    session_id,
    query_explanation,
    query_fixer_tokens=None,
    fixer_history=None,
    sample_data=None,
    custom_headers=None
):
    fixer_history = fixer_history or []
    if vql_query:
        execution_result, vql_status_code, timings = await execute_query(
            vql_query=vql_query,
            auth=auth,
            limit=request.vql_execute_rows_limit,
            timings=timings,
            custom_headers=custom_headers
        )
    else:
        vql_status_code = 500
        execution_result = "No VQL query was generated."

    if vql_status_code not in [499, 500]:
        return QueryExecutionResult(
            vql_query=vql_query,
            execution_result=execution_result,
            status_code=vql_status_code,
            timings=timings,
            fixer_history=fixer_history,
            tokens=query_fixer_tokens or empty_tokens()
        )

    if fixer_history:
        with timing_context("llm_time", timings):
            fixer_history.append(('human', f'Your response resulted in the following error {vql_status_code}: {execution_result}'))
            fixer_history = [(role, msg.replace("{", "{{").replace("}", "}}")) for role, msg in fixer_history]

            prompt = ChatPromptTemplate.from_messages(fixer_history)
            chain = prompt | llm.llm | StrOutputParser()

            with get_usage_metadata_callback() as cb:
                response = await chain.ainvoke(
                    {},
                    config=langfuse.build_config(
                        model_id=f"{llm.provider_name}.{llm.model_name}",
                        session_id=session_id,
                        run_name="fixer_dialogue"
                    )
                )

            vql_query = custom_tag_parser(response, 'vql', default='')[0].strip()
            fixer_history.append(('ai', response))
            query_fixer_tokens = add_tokens(
                query_fixer_tokens or empty_tokens(),
                next(iter(cb.usage_metadata.values())) if cb.usage_metadata else empty_tokens()
            )
    else:
        if vql_status_code == 500:
            with timing_context("llm_time", timings):
                vql_query, fixer_history, query_fixer_tokens = await query_fixer(
                    question=request.question,
                    query=vql_query,
                    query_explanation=query_explanation,
                    error_log=execution_result,
                    llm=llm,
                    session_id=session_id,
                    vector_search_sample_data_k=request.vector_search_sample_data_k,
                    vector_search_tables=vector_search_tables,
                    fixer_history=fixer_history,
                    sample_data=sample_data
                )
        elif vql_status_code == 499:
            with timing_context("llm_time", timings):
                vql_query, fixer_history, query_reviewer_tokens = await query_reviewer(
                    question=request.question,
                    vql_query=vql_query,
                    llm=llm,
                    vector_search_tables=vector_search_tables,
                    session_id=session_id,
                    vector_search_sample_data_k=request.vector_search_sample_data_k,
                    fixer_history=fixer_history,
                    sample_data=sample_data
                )

            query_fixer_tokens = add_tokens(query_fixer_tokens or empty_tokens(), query_reviewer_tokens)

    return QueryExecutionResult(
        vql_query=vql_query,
        execution_result=execution_result,
        status_code=vql_status_code,
        timings=timings,
        fixer_history=fixer_history,
        tokens=query_fixer_tokens or empty_tokens()
    )

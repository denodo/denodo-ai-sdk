from api.utils.ai_tools.vql_fixer import query_fixer
from api.utils.ai_tools.vql_generation import query_to_vql
from api.utils.answer_question.query_execution import attempt_query_execution, execute_query
from api.utils.answer_question.response_builders import prepare_response
from api.utils.answer_question.verbose_enrichment import enhance_verbose_response, handle_plotting
from api.utils.sdk_utils import add_tokens, timing_context


async def process_sql_category(
    request,
    vector_search_tables,
    sql_gen_llm,
    chat_llm,
    category_response,
    auth,
    timings,
    session_id=None,
    sample_data=None,
    custom_headers=None,
    can_use_llm=False
):
    with timing_context("llm_time", timings):
        vql_query, query_explanation, query_to_vql_tokens = await query_to_vql(
            query=request.question,
            vector_search_tables=vector_search_tables,
            llm=sql_gen_llm,
            filter_params=category_response,
            custom_instructions=request.custom_instructions,
            vector_search_sample_data_k=request.vector_search_sample_data_k,
            session_id=session_id,
            sample_data=sample_data,
            can_use_llm=can_use_llm
        )

        if not vql_query:
            response = prepare_response(
                vql_query='',
                query_explanation=query_explanation,
                tokens=query_to_vql_tokens,
                execution_result={},
                vector_search_tables=vector_search_tables,
                raw_graph='',
                timings=timings
            )
            response['answer'] = 'No VQL query could be generated with the provided schema.'
            return response

        vql_query, _, query_fixer_tokens = await query_fixer(
            question=request.question,
            query=vql_query,
            query_explanation=query_explanation,
            llm=sql_gen_llm,
            session_id=session_id,
            vector_search_sample_data_k=request.vector_search_sample_data_k,
            vector_search_tables=vector_search_tables,
            sample_data=sample_data,
            can_use_llm=can_use_llm
        )

    max_attempts = 2
    attempt = 0
    fixer_history = []
    original_vql_query = vql_query

    while attempt < max_attempts:
        execution_attempt = await attempt_query_execution(
            vql_query=vql_query,
            request=request,
            auth=auth,
            timings=timings,
            vector_search_tables=vector_search_tables,
            session_id=session_id,
            query_explanation=query_explanation,
            query_fixer_tokens=query_fixer_tokens,
            fixer_history=fixer_history,
            sample_data=sample_data,
            llm=sql_gen_llm,
            custom_headers=custom_headers,
            can_use_llm=can_use_llm
        )
        vql_query = execution_attempt.vql_query
        execution_result = execution_attempt.execution_result
        vql_status_code = execution_attempt.status_code
        timings = execution_attempt.timings
        fixer_history = execution_attempt.fixer_history
        query_fixer_tokens = execution_attempt.tokens

        if attempt == 0:
            original_execution_result = execution_result
            original_vql_status_code = vql_status_code

        if vql_query == 'OK':
            vql_query = original_vql_query
            break
        if vql_status_code not in [400, 499, 500]:
            break

        attempt += 1

    if vql_status_code in [400, 499, 500]:
        execution_result, vql_status_code, timings = await execute_query(
            vql_query=vql_query,
            auth=auth,
            limit=request.vql_execute_rows_limit,
            timings=timings,
            custom_headers=custom_headers
        )
        if vql_status_code in [400, 500] or (vql_status_code == 499 and original_vql_status_code == 499):
            vql_query = original_vql_query
            execution_result = original_execution_result
            vql_status_code = original_vql_status_code

    raw_graph, plot_data, request = handle_plotting(request=request, execution_result=execution_result)

    response = prepare_response(
        vql_query=vql_query,
        query_explanation=query_explanation,
        tokens=add_tokens(query_to_vql_tokens, query_fixer_tokens),
        execution_result=execution_result if vql_status_code == 200 else {},
        vector_search_tables=vector_search_tables,
        raw_graph=raw_graph,
        timings=timings
    )

    llm_execution_result = response.get('execution_result', {}).get('llm_csv', '')
    if request.verbose or request.plot:
        response = await enhance_verbose_response(
            request=request,
            response=response,
            vql_query=vql_query,
            llm_execution_result=llm_execution_result,
            vector_search_tables=vector_search_tables,
            plot_data=plot_data,
            timings=timings,
            session_id=session_id,
            sample_data=sample_data,
            chat_llm=chat_llm,
            sql_gen_llm=sql_gen_llm
        )

    if request.disclaimer:
        response['answer'] += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."

    return response

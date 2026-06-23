from api.utils.data_category.generate import query_to_vql, GenerationStatus
from api.utils.data_category.resolve import resolve_query
from api.utils.data_category.plot import prepare_plot_data
from api.utils.data_category.answer import build_answer, no_query_response
from api.utils.sdk_utils import timing_context

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
    """Once a question has been determined to be of "SQL" category, the flow runs in four phases:

    1. GENERATE - turn the question into a VQL query with the query_to_vql prompt.
    2. RESOLVE  - execute the generated VQL and fix/review until it works or the attempt limit is hit.
    3. ANSWER   - Generate plot, related questions, natural language response and build the final response payload.
    """
    # 1) GENERATE
    with timing_context("llm_time", timings):
        generated = await query_to_vql(
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

    if generated.status is GenerationStatus.NO_QUERY:
        return no_query_response(generated, vector_search_tables, timings)

    # 2) RESOLVE (execute / fix / review)
    resolved = await resolve_query(
        request=request,
        gen=generated,
        auth=auth,
        llm=sql_gen_llm,
        timings=timings,
        vector_search_tables=vector_search_tables,
        session_id=session_id,
        sample_data=sample_data,
        custom_headers=custom_headers,
        can_use_llm=can_use_llm
    )
    execution_result = resolved.outcome.data if resolved.outcome.is_success else {}

    # 3) ANSWER
    plot_data = prepare_plot_data(request, execution_result)

    return await build_answer(
        request=request,
        resolved=resolved,
        execution_result=execution_result,
        plot_data=plot_data,
        vector_search_tables=vector_search_tables,
        timings=timings,
        chat_llm=chat_llm,
        sql_gen_llm=sql_gen_llm,
        session_id=session_id,
        sample_data=sample_data
    )

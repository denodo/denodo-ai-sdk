import asyncio

from api.utils.ai_tools.graph_generation import graph_generator
from api.utils.ai_tools.response_generation import generate_view_answer, related_questions
from api.utils.sdk_utils import add_tokens, timing_context


def handle_plotting(request, execution_result):
    if not request.plot:
        return '', None, request

    if execution_result and isinstance(execution_result, dict) and len(execution_result.items()) > 0:
        plot_data = execution_result
    else:
        plot_data = None
        request.plot = False

    return '', plot_data, request


async def enhance_verbose_response(
    request, response, vql_query, llm_execution_result,
    vector_search_tables, plot_data, timings, chat_llm, sql_gen_llm,
    session_id=None, sample_data=None
):
    with timing_context("llm_time", timings):
        tasks = []

        if request.plot:
            tasks.append(
                graph_generator(
                    query=request.question,
                    plot_data=plot_data,
                    llm=sql_gen_llm,
                    details=request.plot_details,
                    session_id=session_id
                )
            )

        if request.verbose:
            tasks.append(
                generate_view_answer(
                    query=request.question,
                    vql_query=vql_query,
                    vql_execution_result=llm_execution_result,
                    llm=chat_llm,
                    vector_search_tables=vector_search_tables,
                    markdown_response=request.markdown_response,
                    custom_instructions=request.custom_instructions,
                    session_id=session_id
                )
            )
            tasks.append(
                related_questions(
                    question=request.question,
                    sql_query=vql_query,
                    execution_result=llm_execution_result,
                    vector_search_tables=vector_search_tables,
                    llm=chat_llm,
                    custom_instructions=request.custom_instructions,
                    session_id=session_id,
                    sample_data=sample_data
                )
            )

        results = await asyncio.gather(*tasks)

        result_index = 0
        if request.plot:
            response['raw_graph'], graph_tokens = results[result_index]
            response['tokens'] = add_tokens(response['tokens'], graph_tokens)
            result_index += 1

        if request.verbose:
            response['answer'], verbose_tokens = results[result_index]
            response['related_questions'], related_questions_tokens = results[result_index + 1]
            response['tokens'] = add_tokens(response['tokens'], verbose_tokens)
            response['tokens'] = add_tokens(response['tokens'], related_questions_tokens)

    response['llm_time'] = timings.get("llm_time", 0)
    response['total_execution_time'] = round(sum(timings.values()), 2)
    return response

import asyncio
import inspect

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from api.utils import sdk_utils
from api.utils.ai_tools.prompts import ANSWER_VIEW_PROMPT, RELATED_QUESTIONS_PROMPT
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.types import LLMCallResult, usage_tokens
from api.utils.sdk_utils import add_tokens, timing_context
from api.utils.data_category.plot import graph_generator
from api.utils.data_category.resolve import Resolution, strip_conditions
from api.utils.answer_question.response_builders import prepare_response

DISCLAIMER = (
    "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation "
    "of the data and may not be accurate."
)

@utils.log_params
@utils.timed
async def generate_view_answer(
    query, vql_query, vql_execution_result, llm,
    markdown_response=False,
    custom_instructions='',
    query_explanation='',
    session_id=None
):
    prompt = PromptTemplate.from_template(ANSWER_VIEW_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response_format, response_example = sdk_utils.get_response_format(markdown_response)
    chain_params = {
        "question": query,
        "sql_query": vql_query,
        "execution_result_csv": vql_execution_result,
        "response_format": response_format,
        "response_example": response_example,
        "custom_instructions": custom_instructions,
        "query_explanation": query_explanation
    }

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            chain_params,
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    result = LLMCallResult(
        text=utils.custom_tag_parser(
            response,
            'final_answer',
            default='There was an error while generating the answer. Please try again later.'
        )[0].strip(),
        tokens=usage_tokens(cb)
    )
    return result.text, result.tokens

@utils.log_params
@utils.timed
async def related_questions(
    question, sql_query, execution_result, vector_search_tables, llm,
    custom_instructions='',
    session_id=None,
    sample_data=None,
):
    prompt = PromptTemplate.from_template(RELATED_QUESTIONS_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    schema = [table for table in vector_search_tables if table['view_name'] in sql_query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data)

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            {
                "custom_instructions": f"Here are some things to remember:\n{custom_instructions}" if custom_instructions else '',
                "schema": relevant_tables,
                "question": question,
                "execution_result_csv": execution_result,
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    result = LLMCallResult(
        text=response,
        tokens=usage_tokens(cb)
    )
    return utils.custom_tag_parser(result.text, 'related_question', default=''), result.tokens

async def generate_answer_content(
    request, response, vql_query, llm_execution_result,
    vector_search_tables, plot_data, timings, chat_llm, sql_gen_llm,
    session_id=None, sample_data=None, query_explanation=''
):
    """The content of an answer can consist of:

    - Plot (if a plot is requested)
    - A natural language answer (if verbose=True)
    - Related questions"""
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
                    markdown_response=request.markdown_response,
                    custom_instructions=request.custom_instructions,
                    query_explanation=query_explanation,
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

def no_query_response(generated, vector_search_tables, timings):
    """Response payload when the generated VQL status is NO_QUERY."""
    response = prepare_response(
        vql_query='',
        query_explanation=strip_conditions(generated.explanation),
        tokens=generated.tokens,
        execution_result={},
        vector_search_tables=vector_search_tables,
        raw_graph='',
        timings=timings
    )
    response['answer'] = 'No VQL query could be generated, please review the query explanation and the logs and try again.'
    return response

def terminal_answer(resolution, attempts):
    """The answer string for a failed run, or None to keep prepare_response's default
    (used for SUCCESS / EMPTY)."""
    if resolution == Resolution.EXHAUSTED and attempts == 0:
        return "The generated VQL query failed and automatic query fixing is disabled."
    if resolution == Resolution.EXHAUSTED:
        return (
            f"The data agent tried to generate a query {attempts} times but failed to produce a VQL "
            f"query that worked. Returned is the VQL query and query explanations after "
            f"{attempts} attempts."
        )
    if resolution == Resolution.UNFIXABLE:
        return (
            "The query could not be answered because the data agent generated a VQL query that errored, and "
            "the error is not fixable at the query level. See the query explanation for details."
        )
    return None

async def build_answer(
    request, resolved, execution_result, plot_data,
    vector_search_tables, timings, chat_llm, sql_gen_llm,
    session_id=None, sample_data=None
):
    """Assemble the final response dict from a resolved execution. For verbose/plot
    requests, also generates the natural-language answer and the graph."""
    # SUCCESS/EMPTY report the query that actually ran; a failed run reverts to the
    # original generated query.
    kept_resolved_query = resolved.resolution in (Resolution.SUCCESS, Resolution.EMPTY)
    response_vql = resolved.vql if kept_resolved_query else resolved.original_vql

    response = prepare_response(
        vql_query=response_vql,
        query_explanation=resolved.explanation,
        tokens=resolved.tokens,
        execution_result=execution_result,
        vector_search_tables=vector_search_tables,
        raw_graph='',
        timings=timings
    )

    override = terminal_answer(resolved.resolution, resolved.attempts)
    if override is not None:
        response['answer'] = override

    if request.verbose or request.plot:
        response = await generate_answer_content(
            request=request,
            response=response,
            vql_query=response_vql,
            llm_execution_result=response.get('execution_result', {}).get('llm_csv', ''),
            vector_search_tables=vector_search_tables,
            plot_data=plot_data,
            timings=timings,
            session_id=session_id,
            sample_data=sample_data,
            chat_llm=chat_llm,
            sql_gen_llm=sql_gen_llm,
            query_explanation=resolved.explanation
        )

    if request.disclaimer:
        response['answer'] += DISCLAIMER

    return response

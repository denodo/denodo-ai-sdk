import asyncio

from api.utils import sdk_ai_tools
from utils.data_catalog import execute_vql
from utils.utils import custom_tag_parser, add_langfuse_callback
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback
from api.utils.sdk_utils import timing_context, add_tokens

async def process_sql_category(request, vector_search_tables, sql_gen_llm, chat_llm, category_response, auth, timings, session_id = None, sample_data = None):
    with timing_context("llm_time", timings):
        vql_query, query_explanation, query_to_vql_tokens = await sdk_ai_tools.query_to_vql(
            query=request.question,
            vector_search_tables=vector_search_tables,
            llm=sql_gen_llm,
            filter_params=category_response,
            custom_instructions=request.custom_instructions,
            vector_search_sample_data_k=request.vector_search_sample_data_k,
            session_id=session_id,
            sample_data=sample_data
        )

        # Early exit if no valid VQL could be generated
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
            response['answer'] = 'No VQL query was generated because no relevant schema was found.'
            return response

        vql_query, _, query_fixer_tokens = await sdk_ai_tools.query_fixer(
            question=request.question,
            query=vql_query,
            query_explanation=query_explanation,
            llm=sql_gen_llm,
            session_id=session_id,
            vector_search_sample_data_k=request.vector_search_sample_data_k,
            vector_search_tables=vector_search_tables,
            sample_data=sample_data
        )


    max_attempts = 2
    attempt = 0
    fixer_history = []
    original_vql_query = vql_query

    while attempt < max_attempts:
        vql_query, execution_result, vql_status_code, timings, fixer_history, query_fixer_tokens = await attempt_query_execution(
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
            llm=sql_gen_llm
        )

        if vql_query == 'OK':
            vql_query = original_vql_query
            break
        elif vql_status_code not in [499, 500]:
            break

        attempt += 1

    if vql_status_code in [499, 500]:
        if vql_query:
            execution_result, vql_status_code, timings = await execute_query(
                vql_query=vql_query,
                auth=auth,
                limit=request.vql_execute_rows_limit,
                timings=timings
            )
        else:
            vql_status_code = 500
            execution_result = "No VQL query was generated."

    llm_execution_result = prepare_execution_result(
        execution_result=execution_result,
        llm_response_rows_limit=request.llm_response_rows_limit,
        vql_status_code=vql_status_code
    )

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

def process_metadata_category(category_response, category_related_questions, disclaimer, vector_search_tables, timings, tokens):
    if disclaimer:
        category_response += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."

    # Normalize tokens to only include input_tokens, output_tokens, total_tokens
    normalized_tokens = {
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0
    }
    if isinstance(tokens, dict):
        normalized_tokens['input_tokens'] = tokens.get('input_tokens', 0)
        normalized_tokens['output_tokens'] = tokens.get('output_tokens', 0)
        normalized_tokens['total_tokens'] = tokens.get('total_tokens', 0)

    return {
        'answer': category_response,
        'sql_query': '',
        'query_explanation': '',
        'tokens': normalized_tokens,
        'related_questions': category_related_questions,
        'execution_result': {},
        'tables_used': [table['view_name'] for table in vector_search_tables],
        'raw_graph': '',
        'sql_execution_time': 0,
        'vector_store_search_time': timings.get('vector_store_search_time', 0),
        'llm_time': timings.get('llm_time', 0),
        'total_execution_time': round(sum(timings.values()), 2) if timings else 0
    }

def process_unknown_category(timings):
    ERROR_MESSAGE = "Sorry, that doesn't seem something I can help you with. Are you sure that question is related to your Denodo instance?"

    return {
        'answer': ERROR_MESSAGE,
        'sql_query': '',
        'query_explanation': '',
        'tokens': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
        'related_questions': [],
        'execution_result': {},
        'tables_used': '',
        'raw_graph': '',
        'sql_execution_time': 0,
        'vector_store_search_time': timings.get('vector_store_search_time', 0),
        'llm_time': timings.get('llm_time', 0),
        'total_execution_time': round(sum(timings.values()), 2) if timings else 0
    }

async def attempt_query_execution(
    vql_query,
    request,
    auth, llm,
    timings,
    vector_search_tables,
    session_id,
    query_explanation,
    query_fixer_tokens=None,
    fixer_history=[],
    sample_data=None
):
    if vql_query:
        execution_result, vql_status_code, timings = await execute_query(
            vql_query=vql_query,
            auth=auth,
            limit=request.vql_execute_rows_limit,
            timings=timings
        )
    else:
        vql_status_code = 500
        execution_result = "No VQL query was generated."

    if vql_status_code not in [499, 500]:
        return vql_query, execution_result, vql_status_code, timings, fixer_history, query_fixer_tokens

    if fixer_history:
        with timing_context("llm_time", timings):
            fixer_history.append(('human', f'Your response resulted in the following error {vql_status_code}: {execution_result}'))
            fixer_history = [(role, msg.replace("{", "{{").replace("}", "}}")) for role, msg in fixer_history]

            prompt = ChatPromptTemplate.from_messages(fixer_history)
            chain = prompt | llm.llm | StrOutputParser()

            with get_usage_metadata_callback() as cb:
                response = await chain.ainvoke({}, config = {
                "callbacks": add_langfuse_callback(f"{llm.provider_name}.{llm.model_name}", session_id),
                "run_name": "fixer_dialogue",
            }
)

            vql_query = custom_tag_parser(response, 'vql', default='')[0].strip()
            fixer_history.append(('ai', response))
            query_fixer_tokens = add_tokens(query_fixer_tokens or {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                                            next(iter(cb.usage_metadata.values())) if cb.usage_metadata else {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0})
    else:
        if vql_status_code == 500:
            with timing_context("llm_time", timings):
                vql_query, fixer_history, query_fixer_tokens = await sdk_ai_tools.query_fixer(
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
                vql_query, fixer_history, query_reviewer_tokens = await sdk_ai_tools.query_reviewer(
                    question=request.question,
                    vql_query=vql_query,
                    llm=llm,
                    vector_search_tables=vector_search_tables,
                    session_id=session_id,
                    vector_search_sample_data_k=request.vector_search_sample_data_k,
                    fixer_history=fixer_history,
                    sample_data=sample_data
                )

            query_fixer_tokens = add_tokens(query_fixer_tokens or {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
                                            query_reviewer_tokens)

    return vql_query, execution_result, vql_status_code, timings, fixer_history, query_fixer_tokens

async def execute_query(vql_query, auth, limit, timings):
    with timing_context("vql_execution_time", timings):
        if vql_query:
            vql_status_code, execution_result = await execute_vql(vql=vql_query, auth=auth, limit=limit)
        else:
            vql_status_code = 499
            execution_result = "No VQL query was generated."
    return execution_result, vql_status_code, timings

def prepare_execution_result(execution_result, llm_response_rows_limit, vql_status_code):
    if vql_status_code == 200 and isinstance(execution_result, dict) and len(execution_result) > llm_response_rows_limit:
        llm_execution_result = dict(list(execution_result.items())[:llm_response_rows_limit])
        llm_execution_result = str(llm_execution_result) + f"... Showing only the first {llm_response_rows_limit} rows of the execution result."
    else:
        llm_execution_result = str(execution_result)
    return llm_execution_result

def handle_plotting(request, execution_result):
    if not request.plot:
        return '', None, request

    if execution_result and isinstance(execution_result, dict) and len(execution_result.items()) > 0:
        plot_data = execution_result
    else:
        plot_data = None
        request.plot = False

    return '', plot_data, request

def prepare_response(vql_query, query_explanation, tokens, execution_result, vector_search_tables, raw_graph, timings):
    #Remove conditions from query explanation as it contains sample data the final user might not have access to
    if "Conditions:" in query_explanation:
        query_explanation = query_explanation.split("Conditions:")[0].strip()
    return {
        "answer": vql_query,
        "sql_query": vql_query if "FROM" in vql_query else "",
        "query_explanation": query_explanation,
        "tokens": tokens,
        "related_questions": [],
        "execution_result": execution_result,
        "tables_used": [table['view_name'] for table in vector_search_tables],
        "raw_graph": raw_graph,
        "sql_execution_time": timings.get("vql_execution_time", 0),
        "vector_store_search_time": timings.get("vector_store_search_time", 0),
        "llm_time": timings.get("llm_time", 0),
        "total_execution_time": round(sum(timings.values()), 2)
    }

async def enhance_verbose_response(
    request, response, vql_query, llm_execution_result,
    vector_search_tables, plot_data, timings, chat_llm, sql_gen_llm,
    session_id = None, sample_data = None
):
    with timing_context("llm_time", timings):
        tasks = []

        if request.plot:
            graph_task = sdk_ai_tools.graph_generator(
                query=request.question,
                plot_data=plot_data,
                llm=sql_gen_llm,
                details=request.plot_details,
                session_id=session_id
            )
            tasks.append(graph_task)

        if request.verbose:
            answer_task = sdk_ai_tools.generate_view_answer(
                query=request.question,
                vql_query=vql_query,
                vql_execution_result=llm_execution_result,
                llm=chat_llm,
                vector_search_tables=vector_search_tables,
                markdown_response=request.markdown_response,
                custom_instructions=request.custom_instructions,
                session_id=session_id
            )
            related_questions_task = sdk_ai_tools.related_questions(
                question=request.question,
                sql_query=vql_query,
                execution_result=llm_execution_result,
                vector_search_tables=vector_search_tables,
                llm=chat_llm,
                custom_instructions=request.custom_instructions,
                session_id=session_id,
                sample_data=sample_data
            )
            tasks.append(answer_task)
            tasks.append(related_questions_task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Process results
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

    # Update timings with the latest llm_time and total_execution_time
    response['llm_time'] = timings.get("llm_time", 0)
    response['total_execution_time'] = round(sum(timings.values()), 2)
    return response
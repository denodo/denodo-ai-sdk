import os
import json
import random
import string
import asyncio

from api.utils import sdk_ai_tools
from utils.data_catalog import execute_vql
from utils.utils import custom_tag_parser, add_langfuse_callback
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from api.utils.sdk_utils import timing_context, is_data_complex, add_tokens

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
                timings=timings
            )
        else:
            vql_status_code = 500
            execution_result = "No VQL query was generated."

    llm_execution_result = prepare_execution_result(
        execution_result=execution_result, 
        vql_status_code=vql_status_code
    )

    raw_graph, data_file, request = handle_plotting(request=request, execution_result=execution_result)

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
            data_file=data_file, 
            timings=timings,
            session_id=session_id,
            sample_data=sample_data,
            chat_llm=chat_llm,
            sql_gen_llm=sql_gen_llm
        )

    if request.disclaimer:
        response['answer'] += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."

    if os.path.exists(data_file):
        os.remove(data_file)

    return response

def process_metadata_category(category_response, category_related_questions, disclaimer, vector_search_tables, timings, tokens):
    if disclaimer:
        category_response += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."
    return {
        'answer': category_response,
        'sql_query': '',
        'query_explanation': '',
        'tokens': tokens,
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

async def attempt_query_execution(vql_query, request, auth, llm, timings, vector_search_tables, session_id, query_explanation, query_fixer_tokens=None, fixer_history=[], sample_data=None):
    if vql_query:
        execution_result, vql_status_code, timings = await execute_query(
            vql_query=vql_query, 
            auth=auth, 
            timings=timings
        )
    else:
        vql_status_code = 500
        execution_result = "No VQL query was generated."

    if vql_status_code not in [499, 500]:
        return vql_query, execution_result, vql_status_code, timings, fixer_history, query_fixer_tokens

    if fixer_history:
        with timing_context("llm_time", timings):
            escape_execution_result = execution_result.replace("{", "{{").replace("}", "}}")
            fixer_history.append(('human', f'Your response resulted in the following error {vql_status_code}: {escape_execution_result}'))
            llm.callback.reset_tokens()
            prompt = ChatPromptTemplate.from_messages(fixer_history)
            chain = prompt | llm.llm | StrOutputParser()
            response = await chain.ainvoke({}, config = {
            "callbacks": add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": "fixer_dialogue",
        }
)
        vql_query = custom_tag_parser(response, 'vql', default='')[0].strip()
        fixer_history.append(('ai', response))
        query_fixer_tokens = add_tokens(query_fixer_tokens or {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}, 
                                    llm.tokens)
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

async def execute_query(vql_query, auth, timings):
    with timing_context("vql_execution_time", timings):
        if vql_query:
            vql_status_code, execution_result = await execute_vql(vql=vql_query, auth=auth)
        else:
            vql_status_code = 499
            execution_result = "No VQL query was generated."
    return execution_result, vql_status_code, timings

def prepare_execution_result(execution_result, vql_status_code):
    if vql_status_code == 200 and isinstance(execution_result, dict) and len(execution_result) > 15:
        llm_execution_result = dict(list(execution_result.items())[:15])
        llm_execution_result = str(llm_execution_result) + "... Showing only the first 15 rows of the execution result."
    else:
        llm_execution_result = str(execution_result)
    return llm_execution_result

def handle_plotting(request, execution_result):
    if not request.plot:
        return '', '', request

    if is_data_complex(execution_result):
        random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
        data_file = f'data_{random_id}.json'
        with open(data_file, 'w') as f:
            json.dump(execution_result, f)
    else:
        data_file = ''
        request.plot = False

    return '', data_file, request

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

async def enhance_verbose_response(request, response, vql_query, llm_execution_result, vector_search_tables, data_file, timings, chat_llm, sql_gen_llm, session_id = None, sample_data = None):
    with timing_context("llm_time", timings):
        tasks = []
        
        if request.plot:
            graph_task = sdk_ai_tools.graph_generator(
                query=request.question,
                data_file=data_file,
                execution_result=response['execution_result'],
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

    return response
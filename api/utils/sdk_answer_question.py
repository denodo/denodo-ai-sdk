import os
import json
import random
import string
from concurrent.futures import ThreadPoolExecutor

from api.utils import sdk_ai_tools
from utils.data_catalog import execute_vql
from api.utils.sdk_utils import timing_context, is_data_complex

def process_sql_category(request, vector_search_tables, category_response, auth, timings):
    with timing_context("llm_time", timings):
        vql_query, to_execute, query_explanation, query_to_vql_tokens = sdk_ai_tools.query_to_vql(
            query=request.question, 
            vector_search_tables=vector_search_tables, 
            llm_provider=request.sql_gen_provider, 
            llm_model=request.sql_gen_model, 
            vector_store_provider=request.vector_store_provider, 
            embeddings_provider=request.embeddings_provider, 
            embeddings_model=request.embeddings_model, 
            filter_params=category_response,
            custom_instructions=request.custom_instructions
        )

        vql_query, query_fixer_tokens = sdk_ai_tools.query_fixer(
            query=vql_query, 
            llm_provider=request.sql_gen_provider, 
            llm_model=request.sql_gen_model
        ) if vql_query != "" else (vql_query, None)

    execution_result, vql_status_code, timings = execute_query(
        vql_query=vql_query, 
        to_execute=to_execute, 
        auth=auth, 
        timings=timings
    )

    if vql_status_code == 500:
        vql_query, execution_result, vql_status_code, timings = handle_query_error(
            vql_query=vql_query, 
            execution_result=execution_result, 
            request=request, 
            auth=auth, 
            timings=timings
        )

    llm_execution_result = prepare_execution_result(
        execution_result=execution_result, 
        vql_status_code=vql_status_code
    )

    raw_graph, data_file, request = handle_plotting(request=request, execution_result=execution_result)

    response = prepare_response(
        vql_query=vql_query, 
        query_explanation=query_explanation, 
        query_to_vql_tokens=query_to_vql_tokens, 
        execution_result=execution_result if vql_status_code == 200 else {}, 
        vector_search_tables=vector_search_tables, 
        raw_graph=raw_graph, 
        timings=timings
    )

    if request.verbose or request.plot:
        response = enhance_verbose_response(
            request=request, 
            response=response, 
            vql_query=vql_query, 
            llm_execution_result=llm_execution_result, 
            vector_search_tables=vector_search_tables, 
            data_file=data_file, 
            timings=timings
        )

    if request.disclaimer:
        response['answer'] += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."

    if os.path.exists(data_file):
        os.remove(data_file)

    return response

def process_metadata_category(category_response, category_related_questions, disclaimer, vector_search_tables, timings):
    if disclaimer:
        category_response += "\n\nDISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate."
    return {
        'answer': category_response,
        'sql_query': '',
        'query_explanation': '',
        'tokens': {},
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
        'tokens': {},
        'related_questions': [],
        'execution_result': {},
        'tables_used': '',
        'raw_graph': '',
        'sql_execution_time': 0,
        'vector_store_search_time': timings.get('vector_store_search_time', 0),
        'llm_time': timings.get('llm_time', 0),
        'total_execution_time': round(sum(timings.values()), 2) if timings else 0
    }

def execute_query(vql_query, to_execute, auth, timings):
    with timing_context("vql_execution_time", timings):
        if to_execute:
            vql_status_code, execution_result = execute_vql(vql=vql_query, auth=auth)
        else:
            vql_status_code, execution_result = 200, f'User asked not to execute the query, so return the SQL query instead:\n{vql_query}'
    return execution_result, vql_status_code, timings

def handle_query_error(vql_query, execution_result, request, auth, timings):
    with timing_context("llm_time", timings):
        vql_query, query_fixer_tokens = sdk_ai_tools.query_fixer(
            query=vql_query, 
            error_log=execution_result,
            llm_provider=request.sql_gen_provider,
            llm_model=request.sql_gen_model
        )

    if vql_query is not None:
        execution_result, vql_status_code, timings = execute_query(
            vql_query=vql_query, 
            to_execute=True, 
            auth=auth, 
            timings=timings
        )
    else:
        vql_status_code = 500
        execution_result = "There are errors in the query."

    if vql_status_code == 499:
        execution_result = "The query returned no rows."

    return vql_query, execution_result, vql_status_code, timings

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

def prepare_response(vql_query, query_explanation, query_to_vql_tokens, 
                     execution_result, vector_search_tables, raw_graph, timings):
    return {
        "answer": vql_query,
        "sql_query": vql_query,
        "query_explanation": query_explanation,
        "tokens": query_to_vql_tokens,
        "related_questions": [],
        "execution_result": execution_result,
        "tables_used": [table['view_name'] for table in vector_search_tables],
        "raw_graph": raw_graph,
        "sql_execution_time": timings.get("vql_execution_time", 0),
        "vector_store_search_time": timings.get("vector_store_search_time", 0),
        "llm_time": timings.get("llm_time", 0),
        "total_execution_time": round(sum(timings.values()), 2)
    }

def enhance_verbose_response(request, response, vql_query, llm_execution_result, 
                             vector_search_tables, data_file, timings):
    with timing_context("llm_time", timings):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            if request.plot:
                futures['graph'] = executor.submit(
                    sdk_ai_tools.graph_generator,
                    query=request.question,
                    data_file=data_file,
                    execution_result=response['execution_result'],
                    llm_provider=request.sql_gen_provider,
                    llm_model=request.sql_gen_model,
                    details=request.plot_details
                )
            
            if request.verbose:
                futures['answer'] = executor.submit(
                    sdk_ai_tools.generate_view_answer,
                    query=request.question,
                    vql_query=vql_query,
                    vql_execution_result=llm_execution_result,
                    llm_provider=request.chat_provider,
                    llm_model=request.chat_model,
                    vector_search_tables=vector_search_tables,
                    markdown_response=request.markdown_response,
                    custom_instructions=request.custom_instructions,
                    stream=False
                )

            if request.plot:
                response['raw_graph'], graph_tokens = futures['graph'].result()

            if request.verbose:
                response['answer'], response['related_questions'], response['tokens'] = futures['answer'].result()

    return response
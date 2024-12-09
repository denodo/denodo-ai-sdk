import os
import json
import logging
import inspect

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from langchain_core.prompts import PromptTemplate
from langchain_experimental.utilities import PythonREPL
from langchain_core.output_parsers import StrOutputParser

from utils import utils
from utils.uniformVectorStore import UniformVectorStore
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformLLM import UniformLLM
from utils.data_catalog import get_allowed_view_ids
from api.utils import sdk_utils

# LLM PROMPTS
QUERY_TO_VQL_PROMPT = os.getenv("QUERY_TO_VQL")
ANSWER_VIEW_PROMPT = os.getenv("ANSWER_VIEW")
SQL_CATEGORY_PROMPT = os.getenv("SQL_CATEGORY")
METADATA_CATEGORY_PROMPT = os.getenv("METADATA_CATEGORY")
GET_CONCEPTS_PROMPT = os.getenv("GET_CONCEPTS")
GENERATE_VISUALIZATION_PROMPT = os.getenv("GENERATE_VISUALIZATION")
DIRECT_SQL_CATEGORY_PROMPT = os.getenv("DIRECT_SQL_CATEGORY")
DIRECT_METADATA_CATEGORY_PROMPT = os.getenv("DIRECT_METADATA_CATEGORY")

# OTHER PROMPTS
VQL_RESTRICTIONS_PROMPT = os.getenv("VQL_RESTRICTIONS")
GROUPBY_VQL_PROMPT = os.getenv("GROUPBY_VQL")
HAVING_VQL_PROMPT = os.getenv("HAVING_VQL")
DATES_VQL_PROMPT = os.getenv("DATES_VQL")
ARITHMETIC_VQL_PROMPT = os.getenv("ARITHMETIC_VQL")
VQL_RULES_PROMPT = os.getenv("VQL_RULES")
FIX_LIMIT_PROMPT = os.getenv("FIX_LIMIT")
FIX_OFFSET_PROMPT = os.getenv("FIX_OFFSET")
QUERY_FIXER_PROMPT = os.getenv("QUERY_FIXER")

TODAYS_DATE = datetime.now().strftime("%Y-%m-%d")

@utils.log_params
@utils.timed
def generate_view_answer(query, vql_query, vql_execution_result, llm_provider, llm_model, vector_search_tables, markdown_response = False, custom_instructions = '', stream = False):
    llm = UniformLLM(llm_provider, llm_model)
    prompt = PromptTemplate.from_template(ANSWER_VIEW_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response_format, response_example = sdk_utils.get_response_format(markdown_response)
    chain_params = {
        "question": query,
        "sql_query": vql_query,
        "sql_response": vql_execution_result,
        "response_format": response_format,
        "response_example": response_example,
        "tables_needed": sdk_utils.readable_tables([table for table in vector_search_tables if table['view_name'] in vql_query.replace('"', '').replace("'", '')]),
        "custom_instructions": custom_instructions
    }
    chain_config = {
        "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
        "run_name": inspect.currentframe().f_code.co_name,
    }

    if stream:
        return chain.stream(chain_params, config=chain_config)
        
    response = chain.invoke(chain_params, config=chain_config)
    
    related_questions = utils.custom_tag_parser(response, 'related_question', default = [])

    for q in related_questions:
        response = response.replace(f"<related_question>{q}</related_question>", "")

    return response, related_questions, llm.tokens
    
@utils.log_params
@utils.timed
def query_to_vql(query, vector_search_tables, llm_provider, llm_model, vector_store_provider, embeddings_provider, embeddings_model, filter_params = '', custom_instructions = ''):
    llm = UniformLLM(llm_provider, llm_model)
    vector_store = UniformVectorStore(
        provider = vector_store_provider,
        embeddings_provider = embeddings_provider,
        embeddings_model = embeddings_model,
    )
    prompt = PromptTemplate.from_template(QUERY_TO_VQL_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    filtered_tables = utils.custom_tag_parser(filter_params, 'table', default = [])
    relevant_tables = get_relevant_tables_json(vector_search_tables, filtered_tables, vector_store)

    prompt_parts = {
        "having": int("<having>" in filter_params),
        "groupby": int("<orderby>" in filter_params or "<groupby>" in filter_params),
        "dates": int("<dates>" in filter_params),
        "arithmetic": int("<arithmetic>" in filter_params)
    }

    vql_restrictions = sdk_utils.generate_vql_restrictions(
        filter_params,
        prompt_parts,
        VQL_RULES_PROMPT,
        GROUPBY_VQL_PROMPT,
        HAVING_VQL_PROMPT,
        DATES_VQL_PROMPT,
        ARITHMETIC_VQL_PROMPT,
        VQL_RULES_PROMPT
    )

    response = chain.invoke(
        {
            "query": query,
            "schema": relevant_tables,
            "date": TODAYS_DATE,
            "vql_restrictions": vql_restrictions,
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    
    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()    
    execute = bool(int(utils.custom_tag_parser(response, 'execute', default = '1')[0].strip()))
    query_explanation = utils.custom_tag_parser(response, 'thoughts', default='')[0].strip()

    return vql_query, execute, query_explanation, llm.tokens

@utils.log_params
def get_relevant_tables_json(vector_search_tables, filtered_tables, vector_store):
    def quote_table_name(table):
        """
        This function is necessary to show LLM how to format table names in VQL, by adding quotes around the database and view names.	
        """
        database_name, view_name = table['view_json']['tableName'].split('.')
        table['view_json']['tableName'] = f'"{database_name}"."{view_name}"'
        return str(table['view_json'])

    if not filtered_tables:
        return '\n'.join([quote_table_name({'view_json': json.loads(table['view_json'])}) for table in vector_search_tables])
    else:
        vector_store_views = vector_store.get_views(filtered_tables)
        return '\n'.join([quote_table_name({'view_json': json.loads(view.metadata['view_json'])}) for view in vector_store_views])

@utils.log_params
@utils.timed
def metadata_category(query, vector_search_tables, llm_provider, llm_model, custom_instructions = ''):
    llm = UniformLLM(llm_provider, llm_model)

    prompt = PromptTemplate.from_template(METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = chain.invoke(
        {
            "instruction": query,
            "schema": [table['view_json'] for table in vector_search_tables],
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
    metadata_response = utils.custom_tag_parser(response, 'response', default='')[0].strip()
    related_questions = utils.custom_tag_parser(response, 'related_question', default=[])

    return category, metadata_response, related_questions, llm.tokens

@utils.log_params
@utils.timed
def direct_metadata_category(query, vector_search_tables, llm_provider, llm_model, custom_instructions = ''):
    llm = UniformLLM(llm_provider, llm_model)

    prompt = PromptTemplate.from_template(DIRECT_METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = chain.invoke(
        {
            "instruction": query,
            "schema": [table['view_json'] for table in vector_search_tables],
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    category = "METADATA"
    metadata_response = utils.custom_tag_parser(response, 'response', default='')[0].strip()
    related_questions = utils.custom_tag_parser(response, 'related_question', default=[])

    return category, metadata_response, related_questions, llm.tokens

@utils.log_params
@utils.timed
def direct_sql_category(query, vector_search_tables, llm_provider, llm_model, custom_instructions = ''):
    llm = UniformLLM(llm_provider, llm_model)
    prompt = PromptTemplate.from_template(DIRECT_SQL_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = chain.invoke({
        "instruction": query,
        "schema": sdk_utils.readable_tables(vector_search_tables),
        "custom_instructions": custom_instructions
    }, config={
        "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
        "run_name": inspect.currentframe().f_code.co_name,
    })

    category = "SQL"
    filter_params = utils.custom_tag_parser(response, 'query', default=[])
    sql_related_questions = []

    return category, filter_params[0] if len(filter_params) > 0 else '', sql_related_questions, llm.tokens

@utils.log_params
@utils.timed
def sql_category(query, vector_search_tables, llm_provider, llm_model, mode = 'default', custom_instructions = ''):
    llm = UniformLLM(llm_provider, llm_model)
    prompt = PromptTemplate.from_template(SQL_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    if mode == 'metadata':
        return direct_metadata_category(
            query=query, 
            vector_search_tables=vector_search_tables, 
            llm_provider=llm_provider, 
            llm_model=llm_model,
            custom_instructions=custom_instructions
        )

    if mode == 'data':
        return direct_sql_category(
            query=query, 
            vector_search_tables=vector_search_tables, 
            llm_provider=llm_provider, 
            llm_model=llm_model,
            custom_instructions=custom_instructions
        )
    else:
        with ThreadPoolExecutor(max_workers = 2) as executor:
            metadata_future = executor.submit(
                metadata_category, 
                query=query, 
                vector_search_tables=vector_search_tables, 
                llm_provider=llm_provider, 
                llm_model=llm_model,
                custom_instructions=custom_instructions
            )
            sql_future = executor.submit(chain.invoke, {
                "instruction": query,
                "schema": sdk_utils.readable_tables(vector_search_tables),
                "custom_instructions": custom_instructions
            }, config={
                "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
                "run_name": inspect.currentframe().f_code.co_name,
            })

            # Wait for metadata_category to complete first
            metadata_result = metadata_future.result()
            if metadata_result[0] == "METADATA":
                return metadata_result

            # If not METADATA, continue with sql_category
            response = sql_future.result()

    category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
    filter_params = utils.custom_tag_parser(response, 'query', default=[])
    sql_related_questions = []

    return category, filter_params[0] if len(filter_params) > 0 else None, sql_related_questions, llm.tokens

@utils.log_params
@utils.timed
def get_concepts(query, llm_provider, llm_model):
    llm = UniformLLM(llm_provider, llm_model)

    prompt = PromptTemplate.from_template(GET_CONCEPTS_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = chain.invoke(
        {"query": query},
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    concepts = utils.custom_tag_parser(response, 'search')
    return concepts, llm.tokens

@utils.log_params
@utils.timed
def graph_generator(query, data_file, execution_result, llm_provider, llm_model, details = 'No special requirements'):
    llm = UniformLLM(llm_provider, llm_model)

    final_prompt = PromptTemplate.from_template(GENERATE_VISUALIZATION_PROMPT)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    response = final_chain.invoke({
        "data": data_file, 
        "details": details,
        "instruction": query,
        "plot_details": details,
        "sample_data": json.dumps({'Row 1': execution_result['Row 1']})
    }, 
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    
    python_code = utils.custom_tag_parser(response, 'python', default = '')[0].strip()

    python_repl = PythonREPL()
    output = python_repl.run(python_code)

    # Check if data:image/svg+xml;base64, at the beginning of the output
    if output.startswith("data:image/svg+xml;base64,"):
        graph_image = output
    else:
        graph_image = "data:image/svg+xml;base64," + output

    # Check if the \n at the end of the string and remove it
    if graph_image.endswith("\n"):
        graph_image = graph_image[:-1]

    return graph_image, llm.tokens

@utils.log_params
@utils.timed
def query_fixer(query, llm_provider, llm_model, error_log=False):
    llm = UniformLLM(llm_provider, llm_model)
    
    vql_query, error_log, error_categories = sdk_utils.prepare_vql(query)

    prompt, parameters = _get_prompt_and_parameters(vql_query, error_log, error_categories)
    
    if not prompt:
        logging.info("VQL query is valid, continuing execution.")
        return vql_query, llm.tokens

    final_prompt = PromptTemplate.from_template(prompt)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    response = final_chain.invoke(
        parameters, 
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}"),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    
    fixed_vql_query = sdk_utils.prepare_vql(utils.custom_tag_parser(response, 'vql', default='')[0].strip())
    return fixed_vql_query, llm.tokens

def _get_prompt_and_parameters(vql_query, error_log, error_categories):
    error_handlers = {
        "LIMIT_SUBQUERY": (FIX_LIMIT_PROMPT, "LIMIT in subquery detected, fixing."),
        "LIMIT_OFFSET": (FIX_OFFSET_PROMPT, "LIMIT OFFSET detected, fixing."),
    }

    for category, (prompt, log_message) in error_handlers.items():
        if category in error_categories:
            logging.info(log_message)
            return prompt, {"query": vql_query}

    if error_log:
        logging.info("VQL generation failed, fixing query.")
        return QUERY_FIXER_PROMPT, {
            "query": vql_query,
            "query_error": error_log,
            "vql_restrictions": VQL_RESTRICTIONS_PROMPT
        }

    return None, None

@utils.log_params
@utils.timed
def get_relevant_tables(
    query,
    embeddings_provider,
    embeddings_model,
    vector_store_provider,
    vdb_list,
    auth,
    k = 5,
    user_permissions = False,
    use_views = '',
    expand_set_views = True
):    
    embeddings = UniformEmbeddings(embeddings_provider, embeddings_model)
    vdb_list = [db.strip() for db in vdb_list.split(',')]
    
    vector_store = UniformVectorStore(
        provider = vector_store_provider,
        embeddings_provider = embeddings_provider,
        embeddings_model = embeddings_model,
    )
    
    timings = {}

    embedded_query = embeddings.model.embed_query(query)

    search_params = {
        "vector": embedded_query,
        "k": k,
        "scores": False,
        "database_names": vdb_list
    }

    if user_permissions:
        valid_view_ids = get_allowed_view_ids(auth = auth, database_names = vdb_list)
        valid_view_ids = [str(view_id) for view_id in valid_view_ids]
        search_params["view_ids"] = valid_view_ids

    with sdk_utils.timing_context("vector_store_search_time", timings):
        vector_search = vector_store.search_by_vector(**search_params)

    relevant_tables = [
        {
            "view_text": table.page_content,
            "view_name": table.metadata['view_name'],
            "view_json": json.loads(table.metadata['view_json'])
        }
        for table in vector_search
    ]

    existing_view_names = set(table['view_name'] for table in relevant_tables)
    new_associations = []

    # Get associations for each table
    for table in relevant_tables:
        table_associations = utils.get_table_associations(table['view_name'], table['view_json'])
        new_associations.extend([
            assoc for assoc in table_associations
            if assoc not in existing_view_names
        ])

    if use_views != '':
        use_views = [view.strip() for view in use_views.split(',')]
        new_associations.extend([
            view for view in use_views
            if view not in existing_view_names
        ])

    # Remove duplicates from new_associations
    new_associations = list(set(new_associations))

    if new_associations:
        # Lookup new associations in vector_store
        with sdk_utils.timing_context("vector_store_search_time", timings):
            association_lookup = vector_store.get_views(new_associations, valid_view_ids if user_permissions else None)

        # Add new associations to relevant_tables
        for assoc in association_lookup:
            relevant_tables.append({
                "view_text": assoc.page_content,
                "view_name": assoc.metadata['view_name'],
                "view_json": json.loads(assoc.metadata['view_json']) if not user_permissions else sdk_utils.filter_non_allowed_associations(json.loads(assoc.metadata['view_json']), valid_view_ids)
            })

    if not expand_set_views:
        if use_views != '':
            relevant_tables = [table for table in relevant_tables if table['view_name'] in use_views]
        else:
            relevant_tables = []

    return relevant_tables, timings
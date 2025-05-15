import os
import re
import json
import logging
import inspect
import asyncio

from datetime import datetime

from langchain_core.prompts import PromptTemplate
from langchain_experimental.utilities import PythonREPL
from langchain_core.output_parsers import StrOutputParser

from utils import utils
from utils.uniformVectorStore import UniformVectorStore
from utils.data_catalog import get_allowed_view_ids
from api.utils import sdk_utils

# LLM PROMPTS
QUERY_TO_VQL_PROMPT = os.getenv("QUERY_TO_VQL")
ANSWER_VIEW_PROMPT = os.getenv("ANSWER_VIEW")
SQL_CATEGORY_PROMPT = os.getenv("SQL_CATEGORY")
METADATA_CATEGORY_PROMPT = os.getenv("METADATA_CATEGORY")
GENERATE_VISUALIZATION_PROMPT = os.getenv("GENERATE_VISUALIZATION")
GENERATE_VISUALIZATION_PYTHON_TEMPLATE = os.getenv("GENERATE_VISUALIZATION_PYTHON_TEMPLATE")
DIRECT_SQL_CATEGORY_PROMPT = os.getenv("DIRECT_SQL_CATEGORY")
DIRECT_METADATA_CATEGORY_PROMPT = os.getenv("DIRECT_METADATA_CATEGORY")
RELATED_QUESTIONS_PROMPT = os.getenv("RELATED_QUESTIONS")

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
QUERY_REVIEWER_PROMPT = os.getenv("QUERY_REVIEWER")

TODAYS_DATE = datetime.now().strftime("%Y-%m-%d")

@utils.log_params
@utils.timed
async def generate_view_answer(
    query, vql_query, vql_execution_result, llm, vector_search_tables,
    markdown_response = False,
    custom_instructions = '',
    session_id = None
):
    llm.callback.reset_tokens()
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
        "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
        "run_name": inspect.currentframe().f_code.co_name,
    }
        
    response = await chain.ainvoke(chain_params, config=chain_config)
    response = utils.custom_tag_parser(response, 'final_answer', default = 'There was an error while generating the answer. Please try again later.')[0].strip()

    return response, llm.tokens
    
@utils.log_params
@utils.timed
async def query_to_vql(
    query, vector_search_tables, llm,
    filter_params = '', 
    custom_instructions = '',
    session_id = None,
    sample_data = None,
    vector_search_sample_data_k = 3
):
    llm.callback.reset_tokens()

    prompt = PromptTemplate.from_template(QUERY_TO_VQL_PROMPT)
    query = re.sub(r'(?i)sql', 'VQL', query)
    chain = prompt | llm.llm | StrOutputParser()

    filtered_tables = utils.custom_tag_parser(filter_params, 'table', default = [])
    relevant_tables = format_schema_text(vector_search_tables, filtered_tables, sample_data, examples_per_table=vector_search_sample_data_k)

    prompt_parts = {
        "having": int("<having>" in filter_params),
        "groupby": int("<orderby>" in filter_params or "<groupby>" in filter_params),
        "dates": int("<dates>" in filter_params),
        "arithmetic": int("<arithmetic>" in filter_params)
    }

    vql_restrictions = sdk_utils.generate_vql_restrictions(
        prompt_parts,
        VQL_RULES_PROMPT,
        GROUPBY_VQL_PROMPT,
        HAVING_VQL_PROMPT,
        DATES_VQL_PROMPT,
        ARITHMETIC_VQL_PROMPT,
    )

    response = await chain.ainvoke(
        {
            "query": query,
            "schema": relevant_tables,
            "date": TODAYS_DATE,
            "vql_restrictions": vql_restrictions,
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    query_explanation = utils.custom_tag_parser(response, 'thoughts', default='')[0].strip()
    conditions = utils.custom_tag_parser(response, 'conditions', default='')[0].strip()

    if conditions != "None":
        query_explanation = f"{query_explanation}\n\nConditions: {conditions}"

    return vql_query, query_explanation, llm.tokens

@utils.log_params
@utils.timed
async def related_questions(
    question, sql_query, execution_result, vector_search_tables, llm,
    custom_instructions = '',
    session_id = None,
    sample_data = None,
):
    llm.callback.reset_tokens()
    prompt = PromptTemplate.from_template(RELATED_QUESTIONS_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    schema = [table for table in vector_search_tables if table['view_name'] in sql_query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data)

    response = await chain.ainvoke(
        {
            "custom_instructions": f"Here are some things to remember:\n{custom_instructions}" if custom_instructions else '',
            "schema": relevant_tables,
            "question": question,
            "sql_response": execution_result,
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    related_questions = utils.custom_tag_parser(response, 'related_question', default='')

    return related_questions, llm.tokens

def format_schema_text(vector_search_tables, filtered_tables, sample_data, examples_per_table = 3):
    """
    Formats and optimizes schema data into a readable text format with reduced token usage for LLMs.
    """
    def format_column(col):
        name = col.get('columnName', 'unnamed')
        col_type = col.get('type', 'unknown')
        desc = col.get('description')
        primary_key = col.get('primaryKey', False)
        nullable = col.get('nullable', True)
        examples = col.get('sample_data', [])

        flags = []
        if primary_key:
            flags.append("PK")
        if not nullable:
            flags.append("NOT NULL")

        parts = [f"→ {name} ({col_type})"]
        if flags:
            parts.append(f"[{' '.join(flags)}]")
        if desc:
            parts.append(f"- {desc if desc.endswith('.') else desc + '.'}")
        if examples:
            filtered_examples = [example for example in examples if example]
            if filtered_examples:
                parts.append(f"sample values: {', '.join(filtered_examples[:examples_per_table])}")

        return " ".join(parts)

    def format_table(table, sample_data, present_tables = []):
        lines = []
        table_name = table.get('tableName', 'unnamed_database.unnamed_table')
        table_description = table.get('description', '')
        table_id = str(table.get('id'))
        database_name, view_name = table_name.split('.')
        table_name = f'"{database_name}"."{view_name}"'
        lines.append(f"# Table: {table_name}")
        if table_description:
            lines.append(f"## Description:\n{table_description}")
        lines.append("## Columns:")
        # Format columns
        schema = table.get('schema', [])
        for col in schema:
            if sample_data and table_id in sample_data:
                col_sample_data = sample_data[table_id].get(col.get('columnName'), [])
                col['sample_data'] = col_sample_data
            lines.append(format_column(col))

        # Format associations
        associations = table.get('associations', [])
        association_lines = []
        if associations:
            for assoc in associations:
                where_clause = assoc.get('where')
                if where_clause and sum(table in where_clause for table in present_tables) == 2:
                    association_lines.append(f"→ {where_clause}")

        if association_lines:
            lines.append("## Joins:")
            lines.extend(association_lines)

        return "\n".join(lines)

    formatted_tables = []
    # Create a lookup dictionary for faster access
    table_lookup = {t['view_name']: t['view_json'] for t in vector_search_tables}
    present_tables = [table['view_name'] for table in vector_search_tables]
    if not filtered_tables:
        return "\n\n".join([format_table(table_lookup[table['view_name']], sample_data, present_tables) for table in vector_search_tables])

    for filtered_table in filtered_tables:
        if filtered_table not in table_lookup:
            continue

        table_json = table_lookup[filtered_table].copy()
        formatted_table = format_table(table_json, sample_data, filtered_tables)
        formatted_tables.append(formatted_table)

    if formatted_tables:
        return "\n\n".join(formatted_tables)
    else:
        return "\n\n".join([format_table(table_lookup[table['view_name']], sample_data, present_tables) for table in vector_search_tables])

@utils.log_params
def get_relevant_tables_json(vector_search_tables, filtered_tables):
    def quote_table_name(table):
        """
        This function is necessary to show LLM how to format table names in VQL, by adding quotes around the database and view names.	
        """
        database_name, view_name = table['view_json']['tableName'].split('.')
        table['view_json']['tableName'] = f'"{database_name}"."{view_name}"'
        return str(table['view_json'])

    if not filtered_tables:
        return '\n'.join([quote_table_name({'view_json': json.loads(json.dumps(table['view_json']))}) for table in vector_search_tables])
    else:
        to_return = []
        # Create a lookup dictionary for faster access
        table_lookup = {t['view_name']: t['view_json'] for t in vector_search_tables}
        
        for filtered_table in filtered_tables:
            table_name = utils.custom_tag_parser(filtered_table, 'name', default='')[0].strip()
            columns = utils.custom_tag_parser(filtered_table, 'column', default='')
            
            if table_name not in table_lookup:
                continue
                
            table_json = table_lookup[table_name].copy()  # Shallow copy is sufficient here
            
            if columns[0] != '':
                # Filter schema to include only specified columns
                table_json['schema'] = [
                    col for col in table_json['schema'] 
                    if col['columnName'] in columns
                ]
            
            to_return.append(quote_table_name({'view_json': table_json}))
        if to_return:
            return '\n'.join(to_return)
        else:
            return '\n'.join([quote_table_name({'view_json': json.loads(json.dumps(table['view_json']))}) for table in vector_search_tables])

@utils.log_params
@utils.timed
async def metadata_category(query, vector_search_tables, llm, custom_instructions = '', session_id = None):
    llm.callback.reset_tokens()

    prompt = PromptTemplate.from_template(METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = await chain.ainvoke(
        {
            "instruction": query,
            "schema": [table['view_json'] for table in vector_search_tables],
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
    metadata_response = utils.custom_tag_parser(response, 'response', default='')[0].strip()
    related_questions = utils.custom_tag_parser(response, 'related_question', default=[])

    return category, metadata_response, related_questions, llm.tokens

@utils.log_params
@utils.timed
async def direct_metadata_category(query, vector_search_tables, llm, custom_instructions = '', session_id = None):
    llm.callback.reset_tokens()

    prompt = PromptTemplate.from_template(DIRECT_METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = await chain.ainvoke(
        {
            "instruction": query,
            "schema": [table['view_json'] for table in vector_search_tables],
            "custom_instructions": custom_instructions
        },
        config={
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    category = "METADATA"
    metadata_response = utils.custom_tag_parser(response, 'response', default='')[0].strip()
    related_questions = utils.custom_tag_parser(response, 'related_question', default=[])

    return category, metadata_response, related_questions, llm.tokens

@utils.log_params
@utils.timed
async def direct_sql_category(query, vector_search_tables, llm, custom_instructions = '', session_id = None):
    llm.callback.reset_tokens()

    prompt = PromptTemplate.from_template(DIRECT_SQL_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    response = await chain.ainvoke({
        "instruction": query,
        "schema": sdk_utils.readable_tables(vector_search_tables),
        "custom_instructions": custom_instructions
    }, config={
        "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
        "run_name": inspect.currentframe().f_code.co_name,
    })

    category = "SQL"
    filter_params = utils.custom_tag_parser(response, 'query', default=[])
    sql_related_questions = []

    return category, filter_params[0] if len(filter_params) > 0 else '', sql_related_questions, llm.tokens

@utils.log_params
@utils.timed
async def sql_category(query, vector_search_tables, llm, mode = 'default', custom_instructions = '', session_id = None):
    llm.callback.reset_tokens()
    prompt = PromptTemplate.from_template(SQL_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    if mode == 'metadata':
        return await direct_metadata_category(
            query=query, 
            vector_search_tables=vector_search_tables, 
            llm=llm,
            custom_instructions=custom_instructions,
            session_id=session_id
        )
    elif mode == 'data':
        return await direct_sql_category(
            query=query, 
            vector_search_tables=vector_search_tables, 
            llm=llm,
            custom_instructions=custom_instructions,
            session_id=session_id
        )
    else:
        # Create tasks for both operations to run in parallel
        metadata_task = asyncio.create_task(
            metadata_category(
                query=query, 
                vector_search_tables=vector_search_tables, 
                llm=llm,
                custom_instructions=custom_instructions,
                session_id=session_id
            )
        )
        
        sql_task = asyncio.create_task(
            chain.ainvoke({
                "instruction": query,
                "schema": sdk_utils.readable_tables(vector_search_tables),
                "custom_instructions": custom_instructions
            }, config={
                "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
                "run_name": inspect.currentframe().f_code.co_name,
            })
        )
        
        # Wait for either task to complete
        done, _ = await asyncio.wait(
            {metadata_task, sql_task}, 
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Get the first completed task
        first_completed = list(done)[0]
        
        # If metadata_task completed first and returned METADATA
        if first_completed == metadata_task:
            metadata_result = first_completed.result()
            if metadata_result[0] == "METADATA":
                # Cancel the SQL task
                sql_task.cancel()
                return metadata_result
        elif first_completed == sql_task:
            response = first_completed.result()
            category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
            if category == "SQL":
                # Cancel the metadata task
                metadata_task.cancel()
            else:
                return await metadata_task
        
        # If sql_task is already done, get its result
        if sql_task in done:
            response = sql_task.result()
        else:
            # Otherwise wait for sql_task to complete
            response = await sql_task
        
        category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
        filter_params = utils.custom_tag_parser(response, 'query', default=[])
        sql_related_questions = []
        
        return category, filter_params[0] if len(filter_params) > 0 else '', sql_related_questions, llm.tokens

@utils.log_params
@utils.timed
async def graph_generator(
    query, data_file, execution_result, llm,
    details = 'No special requirements',
    session_id = None
):
    llm.callback.reset_tokens()
    final_prompt = PromptTemplate.from_template(GENERATE_VISUALIZATION_PROMPT)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    # Get the first 3 available rows in execution_result, if they exist
    sample_data = {f"Row {i+1}": execution_result[f"Row {i+1}"] for i in range(3) if f"Row {i+1}" in execution_result}

    response = await final_chain.ainvoke({
        "data": data_file, 
        "instruction": query,
        "plot_details": details,
        "sample_data": json.dumps(sample_data),
        "sample_data_stats": await sdk_utils.stats_about_data(data_file)
    }, 
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    
    python_code = utils.custom_tag_parser(response, 'python', default = '')[0].strip()
    python_code = GENERATE_VISUALIZATION_PYTHON_TEMPLATE.format(data=data_file, python_code=python_code)

    python_repl = PythonREPL()
    output = await asyncio.to_thread(python_repl.run, python_code)

    # Check if the \n at the end of the string and remove it
    if output.endswith("\n"):
        output = output[:-1]

    return output, llm.tokens

@utils.log_params
@utils.timed
async def query_fixer(
    question, query, llm, vector_search_tables,
    error_log = False,
    error_categories = None,
    fixer_history = None,
    session_id = None,
    query_explanation = '',
    sample_data = None,
    vector_search_sample_data_k = 3
):
    if error_categories is None:
        error_categories = []
    if fixer_history is None:
        fixer_history = []
        
    llm.callback.reset_tokens()
    
    if not error_log:
        query, error_log, error_categories = sdk_utils.prepare_vql(query)

    schema = [table for table in vector_search_tables if table['view_name'] in query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data, examples_per_table=vector_search_sample_data_k)
    prompt, parameters = _get_prompt_and_parameters(question, query, error_log, error_categories, relevant_tables, query_explanation)
    
    if not prompt:
        logging.info("VQL query is valid, continuing execution.")
        return query, fixer_history, llm.tokens

    final_prompt = PromptTemplate.from_template(prompt)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    response = await final_chain.ainvoke(
        parameters, 
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )
    
    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()

    fixed_vql_query, error_log, error_categories = sdk_utils.prepare_vql(vql_query)
    input_prompt = final_prompt.format(**parameters)
    fixer_history.extend([('human', input_prompt), ('ai', response)])
    return fixed_vql_query, fixer_history, llm.tokens

@utils.log_params
@utils.timed
async def query_reviewer(
    question, vql_query, llm, vector_search_tables,
    session_id = None,
    fixer_history = None,
    sample_data = None,
    vector_search_sample_data_k = 3
):

    if fixer_history is None:
        fixer_history = []

    llm.callback.reset_tokens()
    final_prompt = PromptTemplate.from_template(QUERY_REVIEWER_PROMPT)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    schema = [table for table in vector_search_tables if table['view_name'] in vql_query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data, examples_per_table=vector_search_sample_data_k)

    vql_restrictions = sdk_utils.generate_vql_restrictions(
        prompt_parts={"dates": 1, "arithmetic": 1, "groupby": 1, "having": 1},
        vql_rules_prompt=VQL_RULES_PROMPT,
        groupby_vql_prompt=GROUPBY_VQL_PROMPT,
        having_vql_prompt=HAVING_VQL_PROMPT,
        dates_vql_prompt=DATES_VQL_PROMPT,
        arithmetic_vql_prompt=ARITHMETIC_VQL_PROMPT,
    )

    vql_rules = f"Here are the VQL generation rules:\n<vql_rules>\n{vql_restrictions}\n</vql_rules>"

    response = await final_chain.ainvoke(
        {
            "question": question,
            "vql_restrictions": '',
            "query": vql_query,
            "schema": relevant_tables
        }, 
        config = {
            "callbacks": utils.add_langfuse_callback(llm.callback, f"{llm.provider_name}.{llm.model_name}", session_id),
            "run_name": inspect.currentframe().f_code.co_name,
        }
    )

    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    new_vql_query, _, _ = sdk_utils.prepare_vql(vql_query)
    input_prompt = final_prompt.format(**{
        "question": question,
        "vql_restrictions": vql_rules,
        "query": vql_query,
        "schema": relevant_tables
    })
    fixer_history.extend([('human', input_prompt), ('ai', response)])
    return new_vql_query, fixer_history, llm.tokens

def _get_prompt_and_parameters(question, vql_query, error_log, error_categories, schema, query_explanation):
    error_handlers = {
        "LIMIT_SUBQUERY": (FIX_LIMIT_PROMPT, "LIMIT in subquery detected, fixing."),
        "LIMIT_OFFSET": (FIX_OFFSET_PROMPT, "LIMIT OFFSET detected, fixing."),
    }

    for category, (prompt, log_message) in error_handlers.items():
        if category in error_categories:
            logging.info(log_message)
            return prompt, {"query": vql_query, "schema": schema, "question": question}

    if error_log:
        logging.info("VQL generation failed, fixing query.")
        vql_restrictions = sdk_utils.generate_vql_restrictions(
            prompt_parts={"dates": 1, "arithmetic": 1, "groupby": 1, "having": 1},
            vql_rules_prompt=VQL_RULES_PROMPT,
            groupby_vql_prompt=GROUPBY_VQL_PROMPT,
            having_vql_prompt=HAVING_VQL_PROMPT,
            dates_vql_prompt=DATES_VQL_PROMPT,
            arithmetic_vql_prompt=ARITHMETIC_VQL_PROMPT,
        )
        return QUERY_FIXER_PROMPT, {
            "query": vql_query,
            "query_error": error_log,
            "vql_restrictions": vql_restrictions,
            "schema": schema,
            "question": question,
            "query_explanation": query_explanation
        }

    return None, None

@utils.log_params
@utils.timed
async def get_relevant_tables(
    query, embeddings_provider, embeddings_model, vector_store_provider, vdb_list, tag_list, auth,
    k = 5, 
    use_views = '', 
    expand_set_views = True, 
    vector_search_sample_data_k = 3
):
    vdb_list = [db.strip() for db in vdb_list.split(',')] if vdb_list else []
    tag_list = [tag.strip() for tag in tag_list.split(',')] if tag_list else []
    
    timings = {}

    vector_store = UniformVectorStore(
        provider = vector_store_provider,
        embeddings_provider = embeddings_provider,
        embeddings_model = embeddings_model
    )

    sample_data_vector_store = UniformVectorStore(
        provider = vector_store_provider,
        embeddings_provider = embeddings_provider,
        embeddings_model = embeddings_model,
        index_name = "ai_sdk_sample_data"
    )
    
    # Create tasks for both async operations to run in parallel
    embedding_task = asyncio.create_task(vector_store.embeddings.aembed_query(query))
    view_ids_task = asyncio.create_task(get_allowed_view_ids(auth=auth))
    
    # Wait for both tasks to complete
    embedded_query, valid_view_ids = await asyncio.gather(embedding_task, view_ids_task)
    
    # Convert view_ids to strings
    valid_view_ids = [str(view_id) for view_id in valid_view_ids]

    search_params = {
        "vector": embedded_query,
        "k": k,
        "database_names": vdb_list,
        "tag_names": tag_list,
        "view_ids": valid_view_ids
    }

    with sdk_utils.timing_context("vector_store_search_time", timings):
        vector_search = vector_store.search_by_vector(**search_params)

    # Keep track of seen view_names to remove duplicates
    seen_view_ids = set()
    relevant_tables = []

    for table in vector_search:
        view_id = table.metadata['view_id']
        if view_id not in seen_view_ids:
            seen_view_ids.add(view_id)
            relevant_tables.append({
                "view_text": table.page_content,
                "view_name": table.metadata['view_name'],
                "view_json": json.loads(table.metadata['view_json']),
                "view_id": table.metadata['view_id']
            })

    MAX_ROUNDS = 2
    current_round = 0
    
    while len(relevant_tables) < k and len(valid_view_ids) > len(relevant_tables) and current_round < MAX_ROUNDS:
        remaining_view_ids = [view_id for view_id in valid_view_ids if view_id not in seen_view_ids]
        search_params["view_ids"] = remaining_view_ids        
        new_search = vector_store.search_by_vector(**search_params)
        if not new_search:  # Break if no new results found
            break
            
        for table in new_search:
            view_id = table.metadata['view_id']
            if view_id not in seen_view_ids and len(relevant_tables) < k:
                seen_view_ids.add(view_id)
                relevant_tables.append({
                    "view_text": table.page_content,
                    "view_name": table.metadata['view_name'],
                    "view_json": json.loads(table.metadata['view_json']),
                    "view_id": table.metadata['view_id']
                })
        
        current_round += 1

    new_associations = []

    # Get associations for each table
    for table in relevant_tables:
        table_associations = utils.get_table_associations(table['view_name'], table['view_json'])
        new_associations.extend([
            assoc_id for assoc_id in table_associations
            if assoc_id not in seen_view_ids
        ])

    if use_views != '':
        use_views = [view.strip() for view in use_views.split(',')]
        use_view_ids = vector_store.get_view_ids(use_views)
        new_associations.extend([
            view_id for view_id in use_view_ids
            if view_id not in seen_view_ids
        ])

    # Remove duplicates from new_associations
    new_associations = list(set(new_associations))
    new_associations = [assoc_id for assoc_id in new_associations if assoc_id in valid_view_ids]

    if new_associations:
        # Lookup new associations in vector_store
        with sdk_utils.timing_context("vector_store_search_time", timings):
            association_lookup = vector_store.get_views(new_associations)

        # Add new associations to relevant_tables
        for assoc in association_lookup:
            relevant_tables.append({
                "view_text": assoc.page_content,
                "view_name": assoc.metadata['view_name'],
                "view_json": sdk_utils.filter_non_allowed_associations(json.loads(assoc.metadata['view_json']), valid_view_ids),
                "view_id": assoc.metadata['view_id']
            })

    if not expand_set_views:
        if use_views != '':
            relevant_tables = [table for table in relevant_tables if table['view_name'] in use_views]
        else:
            relevant_tables = []

    sample_data = {}
    for table in relevant_tables:
        view_id = str(table['view_id'])
        result = sample_data_vector_store.search_by_vector(
            vector = embedded_query,
            k = vector_search_sample_data_k,
            view_ids = [view_id]
        )

        if result and len(result) > 0:
            # Parse column names from the metadata
            column_names = [col.strip() for col in result[0].metadata['columns'].split(',') if col.strip()]
            
            # Initialize the sample values for each column
            column_samples = {col: [] for col in column_names}
            
            # Process each row to extract sample values
            for row in result:
                # Parse the page_content into values
                values = [value.strip() for value in row.page_content.strip().split(',')]
                
                for col, val in zip(column_names, values):
                    column_samples[col].append(val)
            
            sample_data[view_id] = column_samples
    return relevant_tables, sample_data, timings
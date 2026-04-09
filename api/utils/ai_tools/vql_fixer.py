import inspect
import logging

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from api.utils import sdk_utils
from api.utils.ai_tools.prompts import (
    FIX_LIMIT_PROMPT,
    FIX_OFFSET_PROMPT,
    QUERY_FIXER_PROMPT,
    QUERY_REVIEWER_PROMPT,
)
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.types import empty_tokens
from api.utils.ai_tools.vql_rules_builder import build_full_vql_restrictions


def _usage_tokens(callback):
    return next(iter(callback.usage_metadata.values())) if callback.usage_metadata else empty_tokens()


@utils.log_params
@utils.timed
async def query_fixer(
    question, query, llm, vector_search_tables,
    error_log=False,
    error_categories=None,
    fixer_history=None,
    session_id=None,
    query_explanation='',
    sample_data=None,
    vector_search_sample_data_k=3
):
    if error_categories is None:
        error_categories = []
    if fixer_history is None:
        fixer_history = []

    if not error_log:
        query, error_log, error_categories = sdk_utils.prepare_vql(query)

    schema = [table for table in vector_search_tables if table['view_name'] in query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data, examples_per_table=vector_search_sample_data_k)
    prompt, parameters = _get_prompt_and_parameters(
        question,
        query,
        error_log,
        error_categories,
        relevant_tables,
        query_explanation
    )

    if not prompt:
        logging.info("VQL query is valid, continuing execution.")
        return query, fixer_history, empty_tokens()

    final_prompt = PromptTemplate.from_template(prompt)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    with get_usage_metadata_callback() as cb:
        response = await final_chain.ainvoke(
            parameters,
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    fixed_vql_query, _, _ = sdk_utils.prepare_vql(vql_query)
    input_prompt = final_prompt.format(**parameters)
    fixer_history.extend([('human', input_prompt), ('ai', response)])
    return fixed_vql_query, fixer_history, _usage_tokens(cb)


@utils.log_params
@utils.timed
async def query_reviewer(
    question, vql_query, llm, vector_search_tables,
    session_id=None,
    fixer_history=None,
    sample_data=None,
    vector_search_sample_data_k=3
):
    if fixer_history is None:
        fixer_history = []

    final_prompt = PromptTemplate.from_template(QUERY_REVIEWER_PROMPT)
    final_chain = final_prompt | llm.llm | StrOutputParser()

    schema = [table for table in vector_search_tables if table['view_name'] in vql_query.replace('"', '')]
    relevant_tables = format_schema_text(schema, [], sample_data, examples_per_table=vector_search_sample_data_k)
    vql_rules = f"Here are the VQL generation rules:\n<vql_rules>\n{build_full_vql_restrictions()}\n</vql_rules>"

    with get_usage_metadata_callback() as cb:
        response = await final_chain.ainvoke(
            {
                "question": question,
                "vql_restrictions": '',
                "query": vql_query,
                "schema": relevant_tables
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    reviewed_vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    new_vql_query, _, _ = sdk_utils.prepare_vql(reviewed_vql_query)
    input_prompt = final_prompt.format(
        **{
            "question": question,
            "vql_restrictions": vql_rules,
            "query": reviewed_vql_query,
            "schema": relevant_tables
        }
    )
    fixer_history.extend([('human', input_prompt), ('ai', response)])
    return new_vql_query, fixer_history, _usage_tokens(cb)


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
        return QUERY_FIXER_PROMPT, {
            "query": vql_query,
            "query_error": error_log,
            "vql_restrictions": build_full_vql_restrictions(),
            "schema": schema,
            "question": question,
            "query_explanation": query_explanation
        }

    return None, None

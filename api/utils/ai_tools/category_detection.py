import asyncio
import inspect

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from utils.schema_catalog import SchemaCatalog
from api.prompts.category_detection.direct_metadata_category import (
    DIRECT_METADATA_RESPONSE_MARKDOWN,
    DIRECT_METADATA_RESPONSE_PLAIN,
)
from api.prompts.category_detection.metadata_category import (
    METADATA_CATEGORY_RESPONSE_MARKDOWN,
    METADATA_CATEGORY_RESPONSE_PLAIN,
)
from api.utils.ai_tools.prompts import (
    DIRECT_METADATA_CATEGORY_PROMPT,
    DIRECT_SQL_CATEGORY_PROMPT,
    DIRECT_SQL_CATEGORY_NO_AMBIGUITY_PROMPT,
    METADATA_CATEGORY_PROMPT,
    SQL_CATEGORY_PROMPT,
    SQL_CATEGORY_NO_AMBIGUITY_PROMPT,
)
from api.utils.ai_tools.schema_text import selector_schema_for_prompt
from api.utils.ai_tools.types import CategoryDecision, usage_tokens

def _metadata_response_instructions(markdown_response, layout):
    if layout == "direct":
        return DIRECT_METADATA_RESPONSE_MARKDOWN if markdown_response else DIRECT_METADATA_RESPONSE_PLAIN
    return METADATA_CATEGORY_RESPONSE_MARKDOWN if markdown_response else METADATA_CATEGORY_RESPONSE_PLAIN

def _decision_tuple(decision):
    return decision.category, decision.category_response, decision.related_questions, decision.tokens

def _parse_sql_category_response(response, tokens, check_ambiguity):
    category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
    ambiguity_params = utils.custom_tag_parser(response, 'ambiguity', default=[]) if check_ambiguity else []
    if ambiguity_params:
        category_response = ambiguity_params[0]
    else:
        filter_params = utils.custom_tag_parser(response, 'query', default=[])
        category_response = filter_params[0] if filter_params else ''

    return CategoryDecision(
        category=category,
        category_response=category_response,
        related_questions=[],
        tokens=tokens
    )

@utils.log_params
@utils.timed
async def metadata_category(query, vector_search_tables, llm, custom_instructions='', session_id=None, markdown_response=True):
    prompt = PromptTemplate.from_template(METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            {
                "instruction": query,
                "schema": SchemaCatalog.from_vector_search_tables(vector_search_tables).render_vql_schema(),
                "custom_instructions": custom_instructions,
                "metadata_response_instructions": _metadata_response_instructions(
                    markdown_response, layout="category"
                ),
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    decision = CategoryDecision(
        category=utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip(),
        category_response=utils.custom_tag_parser(response, 'response', default='')[0].strip(),
        related_questions=utils.custom_tag_parser(response, 'related_question', default=[]),
        tokens=usage_tokens(cb)
    )
    return _decision_tuple(decision)

@utils.log_params
@utils.timed
async def direct_metadata_category(query, vector_search_tables, llm, custom_instructions='', session_id=None, markdown_response=True):
    prompt = PromptTemplate.from_template(DIRECT_METADATA_CATEGORY_PROMPT)
    chain = prompt | llm.llm | StrOutputParser()

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            {
                "instruction": query,
                "schema": SchemaCatalog.from_vector_search_tables(vector_search_tables).render_vql_schema(),
                "custom_instructions": custom_instructions,
                "metadata_response_instructions": _metadata_response_instructions(
                    markdown_response, layout="direct"
                ),
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    decision = CategoryDecision(
        category="METADATA",
        category_response=utils.custom_tag_parser(response, 'response', default='')[0].strip(),
        related_questions=utils.custom_tag_parser(response, 'related_question', default=[]),
        tokens=usage_tokens(cb)
    )
    return _decision_tuple(decision)

@utils.log_params
@utils.timed
async def direct_sql_category(
    query, vector_search_tables, llm,
    custom_instructions='',
    session_id=None,
    column_description_char_limit=None,
    table_description_char_limit=None,
    check_ambiguity=True
):
    prompt_text = DIRECT_SQL_CATEGORY_PROMPT if check_ambiguity else DIRECT_SQL_CATEGORY_NO_AMBIGUITY_PROMPT
    prompt = PromptTemplate.from_template(prompt_text)
    chain = prompt | llm.llm | StrOutputParser()

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            {
                "instruction": query,
                "schema": selector_schema_for_prompt(vector_search_tables, column_description_char_limit, table_description_char_limit),
                "custom_instructions": custom_instructions
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    decision = _parse_sql_category_response(response, usage_tokens(cb), check_ambiguity)
    decision.category = "SQL"
    return _decision_tuple(decision)

@utils.log_params
@utils.timed
async def sql_category(
    query, vector_search_tables, llm,
    mode='default',
    custom_instructions='',
    session_id=None,
    column_description_char_limit=None,
    table_description_char_limit=None,
    check_ambiguity=True,
    markdown_response=True,
):
    prompt_text = SQL_CATEGORY_PROMPT if check_ambiguity else SQL_CATEGORY_NO_AMBIGUITY_PROMPT
    prompt = PromptTemplate.from_template(prompt_text)
    chain = prompt | llm.llm | StrOutputParser()

    if mode == 'metadata':
        return await direct_metadata_category(
            query=query,
            vector_search_tables=vector_search_tables,
            llm=llm,
            custom_instructions=custom_instructions,
            session_id=session_id,
            markdown_response=markdown_response,
        )

    if mode == 'data':
        return await direct_sql_category(
            query=query,
            vector_search_tables=vector_search_tables,
            llm=llm,
            custom_instructions=custom_instructions,
            session_id=session_id,
            column_description_char_limit=column_description_char_limit,
            table_description_char_limit=table_description_char_limit,
            check_ambiguity=check_ambiguity
        )

    metadata_task = asyncio.create_task(
        metadata_category(
            query=query,
            vector_search_tables=vector_search_tables,
            llm=llm,
            custom_instructions=custom_instructions,
            session_id=session_id,
            markdown_response=markdown_response,
        )
    )

    with get_usage_metadata_callback() as cb:
        sql_task = asyncio.create_task(
            chain.ainvoke(
                {
                    "instruction": query,
                    "schema": selector_schema_for_prompt(vector_search_tables, column_description_char_limit, table_description_char_limit),
                    "custom_instructions": custom_instructions
                },
                config=langfuse.build_config(
                    model_id=f"{llm.provider_name}.{llm.model_name}",
                    session_id=session_id,
                    run_name=inspect.currentframe().f_code.co_name
                )
            )
        )

        done, _ = await asyncio.wait({metadata_task, sql_task}, return_when=asyncio.FIRST_COMPLETED)
        first_completed = list(done)[0]

        if first_completed == metadata_task:
            metadata_result = first_completed.result()
            if metadata_result[0] == "METADATA":
                sql_task.cancel()
                return metadata_result
        elif first_completed == sql_task:
            response = first_completed.result()
            category = utils.custom_tag_parser(response, 'cat', default="OTHER")[0].strip()
            if category == "SQL":
                metadata_task.cancel()
            else:
                return await metadata_task

        if sql_task in done:
            response = sql_task.result()
        else:
            response = await sql_task

    decision = _parse_sql_category_response(response, usage_tokens(cb), check_ambiguity)
    return _decision_tuple(decision)

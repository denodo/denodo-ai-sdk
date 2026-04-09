import inspect

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from api.utils import sdk_utils
from api.utils.ai_tools.prompts import ANSWER_VIEW_PROMPT, RELATED_QUESTIONS_PROMPT
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.types import LLMCallResult, empty_tokens

def _usage_tokens(callback):
    return next(iter(callback.usage_metadata.values())) if callback.usage_metadata else empty_tokens()

@utils.log_params
@utils.timed
async def generate_view_answer(
    query, vql_query, vql_execution_result, llm, vector_search_tables,
    markdown_response=False,
    custom_instructions='',
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
        "tables_needed": sdk_utils.readable_tables(
            [table for table in vector_search_tables if table['view_name'] in vql_query.replace('"', '').replace("'", '')]
        ),
        "custom_instructions": custom_instructions
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
        tokens=_usage_tokens(cb)
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
        tokens=_usage_tokens(cb)
    )
    return utils.custom_tag_parser(result.text, 'related_question', default=''), result.tokens

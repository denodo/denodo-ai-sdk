import inspect
import re

from datetime import datetime

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from api.utils.ai_tools.prompts import QUERY_TO_VQL_PROMPT
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.types import empty_tokens
from api.utils.ai_tools.vql_rules_builder import build_vql_restrictions


TODAYS_DATE = datetime.now().strftime("%Y-%m-%d")


def _usage_tokens(callback):
    return next(iter(callback.usage_metadata.values())) if callback.usage_metadata else empty_tokens()


@utils.log_params
@utils.timed
async def query_to_vql(
    query, vector_search_tables, llm,
    filter_params='',
    custom_instructions='',
    session_id=None,
    sample_data=None,
    vector_search_sample_data_k=3
):
    prompt = PromptTemplate.from_template(QUERY_TO_VQL_PROMPT)
    query = re.sub(r'(?i)sql', 'VQL', query)
    chain = prompt | llm.llm | StrOutputParser()

    filtered_tables = utils.custom_tag_parser(filter_params, 'table', default=[])
    relevant_tables = format_schema_text(
        vector_search_tables,
        filtered_tables,
        sample_data,
        examples_per_table=vector_search_sample_data_k
    )

    prompt_parts = {
        "dates": int("<dates>" in filter_params),
        "arithmetic": int("<arithmetic>" in filter_params),
        "spatial": int("<spatial>" in filter_params),
        "llm": int("<llm>" in filter_params),
        "vector": int("<vector>" in filter_params or "<ai>" in filter_params),
        "json": int("<json>" in filter_params),
        "xml": int("<xml>" in filter_params),
        "text": int("<text>" in filter_params),
        "aggregate": int("<aggregate>" in filter_params),
        "cast": int("<cast>" in filter_params),
        "window": int("<window>" in filter_params),
    }
    vql_restrictions = build_vql_restrictions(prompt_parts)

    with get_usage_metadata_callback() as cb:
        response = await chain.ainvoke(
            {
                "query": query,
                "schema": relevant_tables,
                "date": TODAYS_DATE,
                "vql_restrictions": vql_restrictions,
                "custom_instructions": custom_instructions
            },
            config=langfuse.build_config(
                model_id=f"{llm.provider_name}.{llm.model_name}",
                session_id=session_id,
                run_name=inspect.currentframe().f_code.co_name
            )
        )

    if '```' in response:
        response = response.replace('```vql', '<vql>').replace('```', '</vql>').strip()

    vql_query = utils.custom_tag_parser(response, 'vql', default='')[0].strip()
    if vql_query.lower() == 'none' or vql_query == '':
        vql_query = ''

    query_explanation = utils.custom_tag_parser(response, 'thoughts', default='')[0].strip()
    conditions = utils.custom_tag_parser(response, 'conditions', default='')[0].strip()
    if conditions != "None":
        query_explanation = f"{query_explanation}\n\nConditions: {conditions}"

    return vql_query, query_explanation, _usage_tokens(cb)

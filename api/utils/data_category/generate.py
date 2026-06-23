import inspect
import re

from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import get_usage_metadata_callback

from utils import langfuse
from utils import utils
from utils.schema_catalog import SchemaCatalog
from api.utils.ai_tools.prompts import QUERY_TO_VQL_PROMPT, PROCESS_STEP_NORMAL_PROMPT, PROCESS_STEP_OBLIGATORY_PROMPT
from api.utils.ai_tools.types import empty_tokens, usage_tokens
from api.utils.ai_tools.schema_text import format_schema_text
from api.utils.ai_tools.vql_rules_builder import build_vql_restrictions

TODAYS_DATE = datetime.now().strftime("%Y-%m-%d")

class GenerationStatus(str, Enum):
    """Status of the generated VQL query based on the output of the query_to_vql prompt.

    GENERATED when a VQL query is returned in <vql></vql> tags; NO_QUERY when the prompt
    returns nothing, <vql>NONE</vql>, or malformed tags.
    """
    GENERATED = "generated"
    NO_QUERY = "no_query"

@dataclass
class GeneratedQuery:
    """A generated VQL query: its status, the VQL itself, the generation reasoning,
    and the tokens used."""
    status: "GenerationStatus"
    vql: str
    explanation: str
    tokens: dict = field(default_factory=empty_tokens)

@utils.log_params
@utils.timed
async def query_to_vql(
    query, vector_search_tables, llm,
    filter_params='',
    custom_instructions='',
    session_id=None,
    sample_data=None,
    vector_search_sample_data_k=3,
    can_use_llm=False
):
    prompt = PromptTemplate.from_template(QUERY_TO_VQL_PROMPT)
    query = re.sub(r'(?i)sql', 'VQL', query)
    chain = prompt | llm.llm | StrOutputParser()

    filtered_tables = utils.custom_tag_parser(filter_params, 'table', default=[])
    schema_catalog = SchemaCatalog.from_vector_search_tables(vector_search_tables)
    include_vector = schema_catalog.selected_tables_have_vector_column(filtered_tables)
    include_metric = schema_catalog.selected_tables_include_metric_view(filtered_tables)
    relevant_tables = format_schema_text(
        vector_search_tables,
        filtered_tables,
        sample_data,
        examples_per_table=vector_search_sample_data_k
    )

    # Smaller LLMs struggle to respect [OBLIGATORY] field restrictions unless
    # they are forced into a strict, step-by-step mandatory validation process.
    # To save tokens we conditionally inject this strict validation step only
    # when an obligatory field is present.
    if "[OBLIGATORY]" in relevant_tables:
        query_generation_process = PROCESS_STEP_OBLIGATORY_PROMPT
    else:
        query_generation_process = PROCESS_STEP_NORMAL_PROMPT

    prompt_parts = {
        "dates": int("<dates>" in filter_params),
        "arithmetic": int("<arithmetic>" in filter_params),
        "spatial": int("<spatial>" in filter_params),
        "llm": int("<llm>" in filter_params and can_use_llm),
        "vector": int("<vector>" in filter_params or "<ai>" in filter_params or include_vector),
        "metric": int("<metric>" in filter_params or include_metric),
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
                "custom_instructions": custom_instructions,
                "query_generation_process": query_generation_process
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

    status = GenerationStatus.GENERATED if vql_query else GenerationStatus.NO_QUERY
    return GeneratedQuery(
        status=status,
        vql=vql_query,
        explanation=query_explanation,
        tokens=usage_tokens(cb),
    )

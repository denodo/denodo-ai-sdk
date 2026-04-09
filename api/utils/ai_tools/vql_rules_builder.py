from api.utils import sdk_utils

from . import prompts

def build_vql_restrictions(prompt_parts):
    return sdk_utils.generate_vql_restrictions(
        prompt_parts=prompt_parts,
        vql_rules_prompt=prompts.VQL_RULES_PROMPT,
        dates_vql_prompt=prompts.DATES_VQL_PROMPT,
        arithmetic_vql_prompt=prompts.ARITHMETIC_VQL_PROMPT,
        spatial_vql_prompt=prompts.SPATIAL_VQL_PROMPT,
        llm_vql_prompt=prompts.LLM_VQL_PROMPT,
        vector_vql_prompt=prompts.VECTOR_VQL_PROMPT,
        json_vql_prompt=prompts.JSON_VQL_PROMPT,
        xml_vql_prompt=prompts.XML_VQL_PROMPT,
        text_vql_prompt=prompts.TEXT_VQL_PROMPT,
        aggregate_vql_prompt=prompts.AGGREGATE_VQL_PROMPT,
        cast_vql_prompt=prompts.CAST_VQL_PROMPT,
        window_vql_prompt=prompts.WINDOW_VQL_PROMPT,
    )

def build_full_vql_restrictions():
    return build_vql_restrictions(
        {
            "dates": 1,
            "arithmetic": 1,
            "spatial": 1,
            "llm": 1,
            "vector": 1,
            "json": 1,
            "xml": 1,
            "text": 1,
            "aggregate": 1,
            "cast": 1,
            "window": 1,
        }
    )

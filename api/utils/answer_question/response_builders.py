import os

from utils.schema_catalog import SchemaCatalog
from utils.utils import custom_tag_parser

from api.utils.data_category.serialize import build_execution_result_bundle


AMBIGUITY_TYPE_LABELS = {
    "UNCL_SCHEMA": "Unclear schema reference",
    "TEMP": "Temporal ambiguity",
    "OUTPUT": "Output schema ambiguity",
    "QUAL": "Qualitative ambiguity",
    "MISSING_OBL": "Missing obligatory input",
}


def build_ambiguity_message(category_response):
    ambiguous_inputs = custom_tag_parser(category_response, 'ambiguous_input', default=[])
    if not ambiguous_inputs:
        return None

    lines = [
        "The LLM detected some ambiguity in your input. Please re-submit your question clarifying the following things:",
        "",
    ]

    for ambiguous in ambiguous_inputs:
        type_code = custom_tag_parser(ambiguous, 'type', default=[''])[0].strip()
        question = custom_tag_parser(ambiguous, 'cl_question', default=[''])[0].strip()
        if not question:
            continue
        pretty_type = AMBIGUITY_TYPE_LABELS.get(type_code, type_code or "Ambiguity")
        lines.append(f"- {pretty_type}: {question}")

    if len(lines) <= 2:
        return None

    return "\n".join(lines)


def _normalize_tokens(tokens):
    normalized_tokens = {
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0
    }
    if isinstance(tokens, dict):
        normalized_tokens['input_tokens'] = tokens.get('input_tokens', 0)
        normalized_tokens['output_tokens'] = tokens.get('output_tokens', 0)
        normalized_tokens['total_tokens'] = tokens.get('total_tokens', 0)
    return normalized_tokens


def process_metadata_category(category_response, category_related_questions, disclaimer, vector_search_tables, timings, tokens):
    if disclaimer:
        category_response += """
        DISCLAIMER: This response has been generated based on an LLM's interpretation of the data and may not be accurate.
        Also, since this is a metadata response, please note that the views used to generate the response are the result
        of a similarity search in the vector store. Therefore, it will not be an exhaustive search. For that purpose, please use the Denodo Data Marketplace.
        """

    related_tables = SchemaCatalog.from_vector_search_tables(vector_search_tables).render_related_tables_payload()

    return {
        'answer': category_response,
        'sql_query': '',
        'query_explanation': '',
        'tokens': _normalize_tokens(tokens),
        'related_questions': category_related_questions,
        'execution_result': {},
        'related_tables': related_tables,
        'tables_used': [table['view_name'] for table in vector_search_tables],
        'raw_graph': '',
        'sql_execution_time': 0,
        'vector_store_search_time': timings.get('vector_store_search_time', 0),
        'llm_time': timings.get('llm_time', 0),
        'total_execution_time': round(sum(timings.values()), 2) if timings else 0
    }


def process_ambiguity_category(ambiguity_message, vector_search_tables, timings, tokens):
    related_tables = SchemaCatalog.from_vector_search_tables(vector_search_tables).render_related_tables_payload()

    return {
        'answer': ambiguity_message,
        'sql_query': '',
        'query_explanation': '',
        'tokens': _normalize_tokens(tokens),
        'related_questions': [],
        'execution_result': {},
        'related_tables': related_tables,
        'tables_used': [table['view_name'] for table in vector_search_tables],
        'raw_graph': '',
        'sql_execution_time': 0,
        'vector_store_search_time': timings.get('vector_store_search_time', 0),
        'llm_time': timings.get('llm_time', 0),
        'total_execution_time': round(sum(timings.values()), 2) if timings else 0
    }


def process_unknown_category(timings):
    return {
        'answer': "Sorry, that doesn't seem something I can help you with. Are you sure that question is related to your Denodo instance?",
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


def prepare_response(vql_query, query_explanation, tokens, execution_result, vector_search_tables, raw_graph, timings):
    llm_response_rows_limit = int(os.getenv('LLM_RESPONSE_ROWS_LIMIT', '100'))
    execution_result_bundle = {}
    if execution_result:
        execution_result_bundle = build_execution_result_bundle(execution_result, llm_response_rows_limit)

    answer = "The SQL query executed correctly, but returned no results."
    if execution_result:
        answer = vql_query

    return {
        "answer": answer,
        "sql_query": vql_query if "FROM" in vql_query else "",
        "query_explanation": query_explanation,
        "tokens": tokens,
        "related_questions": [],
        "execution_result": execution_result_bundle,
        "tables_used": [table['view_name'] for table in vector_search_tables],
        "raw_graph": raw_graph,
        "sql_execution_time": timings.get("vql_execution_time", 0),
        "vector_store_search_time": timings.get("vector_store_search_time", 0),
        "llm_time": timings.get("llm_time", 0),
        "total_execution_time": round(sum(timings.values()), 2)
    }

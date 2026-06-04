from utils.schema_catalog import SchemaCatalog
from api.utils import sdk_utils

def format_schema_text(vector_search_tables, filtered_tables, sample_data, examples_per_table=3):
    return SchemaCatalog.from_vector_search_tables(vector_search_tables).render_vql_schema(
        filtered_tables=filtered_tables,
        sample_data=sample_data,
        examples_per_table=examples_per_table
    )

def selector_schema_for_prompt(vector_search_tables, column_description_char_limit=None, table_description_char_limit=None):
    selector_schema = sdk_utils.readable_tables(vector_search_tables, column_description_char_limit, table_description_char_limit)
    table_blocks = [block.strip() for block in selector_schema.strip().split("\n\n") if block.strip()]
    return "\n".join([f"<table>\n{block}\n</table>" for block in table_blocks])

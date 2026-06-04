"""
High-level schema catalog entry point.

`SchemaCatalog` is the canonical in-memory representation of the working data model schema
metadata AFTER it has been normalized from the Data Marketplace JSON payload.

Three different schema representations are supported:

- `embedding`
  - Purpose: semantic retrieval text stored in the vector DB
  - Used by: similarity search / relevant view retrieval
  - Characteristics: compact plain text focused on view meaning and column
    semantics; does not include association lines

- `selector`
  - Purpose: compact schema text for table selection
  - Used by: selector/category detection before query generation
  - Characteristics: plain text with the same table/column grammar as
    `embedding`, but can include association lines for views present in context;

- `vql`
  - Purpose: rich schema context for query generation, query review, and query
    fixing prompts
  - Used by: VQL generation, reviewer, and fixer flows
  - Characteristics: markdown-oriented output with PK / NOT NULL flags, sample
    values, and join lines
"""

from .helpers import build_table_name
from .view import SchemaTable

class SchemaCatalog:
    def __init__(self, views=None):
        self.views = views or []

    @classmethod
    def from_marketplace_json(
        cls,
        json_response,
        use_associations=True,
        use_table_descriptions=True,
        use_column_descriptions=True,
        filter_tables=None,
        view_prefix_filter='',
        view_suffix_filter=''
    ):
        filter_tables = filter_tables or []
        if 'viewsDetails' in json_response:
            json_response = json_response['viewsDetails']

        if not json_response:
            return cls([])

        views = []
        for table in json_response:
            table_database = table.get('databaseName', '')
            raw_table_name = table.get('name', '')
            table_name = build_table_name(table_database, raw_table_name)

            if table_name in filter_tables:
                continue
            if view_prefix_filter and not raw_table_name.startswith(view_prefix_filter):
                continue
            if view_suffix_filter and not raw_table_name.endswith(view_suffix_filter):
                continue

            views.append(
                SchemaTable.from_marketplace_table(
                    table=table,
                    use_associations=use_associations,
                    use_table_descriptions=use_table_descriptions,
                    use_column_descriptions=use_column_descriptions
                )
            )

        return cls(views)

    @classmethod
    def from_storage_json(cls, schema_json):
        if not schema_json or 'views' not in schema_json:
            return cls([])

        return cls([SchemaTable.from_dict(view) for view in schema_json.get('views', [])])

    @classmethod
    def from_vector_search_tables(cls, vector_search_tables):
        views = []
        for table in vector_search_tables:
            if 'view_json' in table:
                views.append(SchemaTable.from_dict(table['view_json']))
            else:
                views.append(SchemaTable.from_dict(table))
        return cls(views)

    def to_storage_json(self):
        if not self.views:
            return None

        return {'views': [view.to_dict() for view in self.views]}

    def to_view_jsons(self):
        return [view.to_dict() for view in self.views]

    def render_selector_schema(self, column_description_char_limit=None, table_description_char_limit=None):
        present_tables = [view.get_name() for view in self.views]
        return "".join(
            view.render_selector_text(column_description_char_limit, table_description_char_limit, present_tables)
            for view in self.views
        )

    def render_vql_schema(self, filtered_tables=None, sample_data=None, examples_per_table=3):
        filtered_tables = filtered_tables or []
        table_lookup = {view.get_name(): view for view in self.views}
        present_tables = [view.get_name() for view in self.views]

        if not filtered_tables:
            return "\n\n".join(
                view.render_vql_text(sample_data, present_tables, examples_per_table)
                for view in self.views
            )

        formatted_tables = []
        for filtered_table in filtered_tables:
            if filtered_table not in table_lookup:
                continue
            formatted_tables.append(
                table_lookup[filtered_table].render_vql_text(sample_data, filtered_tables, examples_per_table)
            )

        if formatted_tables:
            return "\n\n".join(formatted_tables)

        return "\n\n".join(
            view.render_vql_text(sample_data, present_tables, examples_per_table)
            for view in self.views
        )

    def render_metadata_prompt_payload(self):
        return self.to_view_jsons()

    def render_related_tables_payload(self, sample_data=None, examples_per_table=3):
        present_tables = [view.get_name() for view in self.views]
        return [
            {
                "view_name": view.get_name(),
                "view_json": view.to_dict(),
                "vql_representation": view.render_vql_text(
                    sample_data=sample_data,
                    present_tables=present_tables,
                    examples_per_table=examples_per_table
                )
            }
            for view in self.views
        ]

    def selected_tables_have_vector_column(self, selected_table_names):
        if not selected_table_names:
            views = self.views
        else:
            table_lookup = {view.get_name(): view for view in self.views}
            views = [table_lookup[name] for name in selected_table_names if name in table_lookup]
        return any(view.has_vector_column() for view in views)

    def selected_tables_include_metric_view(self, selected_table_names):
        if not selected_table_names:
            views = self.views
        else:
            table_lookup = {view.get_name(): view for view in self.views}
            views = [table_lookup[name] for name in selected_table_names if name in table_lookup]
        return any(view.is_metric_view() for view in views)

    def to_embedding_documents(self, embeddings_token_limit=0):
        documents = []
        for view in self.views:
            documents.append(view.to_embedding_documents(embeddings_token_limit))
        return documents

import json
from time import time

from langchain_core.documents.base import Document

from .helpers import (
    attach_sample_data,
    build_table_name,
    calculate_tokens,
    normalize_associations,
    normalize_schema_columns,
    remove_none_values,
    split_table_name,
)

class SchemaColumn:
    def __init__(self, column_data):
        self._column_data = dict(column_data)

    def to_dict(self):
        return dict(self._column_data)

    def _normalized_logical_name(self):
        logical_name = self._column_data.get('logicalName')
        if logical_name == '':
            return None
        return logical_name

    def _normalized_description(self):
        description = self._column_data.get('description')
        if description:
            description = description.replace("\n", " ").strip()
        else:
            description = None

        if not description:
            return None

        return description

    def render_plain_line(self, include_descriptions=True, description_limit=None):
        column_name = self._column_data.get('columnName', '').replace('"', '').replace("'", "")
        column_type = self._column_data.get('type', 'unknown')
        logical_name = self._normalized_logical_name()
        description = self._normalized_description()

        if not include_descriptions:
            description = None

        if description_limit and description and len(description) > description_limit:
            description = f"{description[:description_limit]}... (truncated)"

        if logical_name is not None and description is not None:
            return f"- {column_name} ({column_type}) → {logical_name}: {description}"
        if logical_name is None and description is not None:
            return f"- {column_name} ({column_type}) → {description}"
        if logical_name is not None and description is None:
            return f"- {column_name} ({column_type}) → {logical_name}"
        return f"- {column_name} ({column_type})"

    def render_vql_line(self, sample_values=None, examples_per_table=3):
        name = self._column_data.get('columnName', 'unnamed')
        column_type = self._column_data.get('type', 'unknown')
        logical_name = self._normalized_logical_name()
        description = self._normalized_description()
        primary_key = self._column_data.get('primaryKey', False)
        nullable = self._column_data.get('nullable', True)
        examples = sample_values if sample_values is not None else self._column_data.get('sample_data', [])

        flags = []
        if primary_key:
            flags.append("PK")
        if not nullable:
            flags.append("NOT NULL")

        parts = [f"- {name} ({column_type})"]
        if flags:
            parts.append(f"[{' '.join(flags)}]")
        if logical_name is not None and description is not None:
            parts.append(f"→ {logical_name}: {description if description.endswith('.') else description + '.'}")
        elif logical_name is None and description is not None:
            parts.append(f"→ {description if description.endswith('.') else description + '.'}")
        elif logical_name is not None and description is None:
            parts.append(f"→ {logical_name}.")
        if examples:
            filtered_examples = [example for example in examples if example]
            if filtered_examples:
                parts.append(f"sample values: {', '.join(filtered_examples[:examples_per_table])}")

        return " ".join(parts)

class SchemaAssociation:
    def __init__(self, association_data):
        self._association_data = dict(association_data)

    def to_dict(self):
        return dict(self._association_data)

    def render_line(self):
        association_line = f"→ {self._association_data.get('where')}"
        if self._association_data.get('description'):
            association_line += f". Description: {self._association_data.get('description')}"
        return association_line

class SchemaTable:
    def __init__(self, view_data):
        self._view_data = dict(view_data)

    @classmethod
    def from_dict(cls, view_data):
        return cls(view_data)

    @classmethod
    def from_marketplace_table(
        cls,
        table,
        use_associations=True,
        use_table_descriptions=True,
        use_column_descriptions=True
    ):
        json_table = remove_none_values(table)
        table_database = json_table.get('databaseName', '')
        table_name = build_table_name(table_database, json_table.get('name', ''))

        output_table = {
            'tableName': table_name,
            'description': json_table.get('description', ""),
        }

        attach_sample_data(json_table)

        keys_to_remove = ['name', 'description', 'databaseName', 'viewFieldDataList']
        for key in keys_to_remove:
            json_table.pop(key, None)

        json_table = output_table | json_table
        json_table['schema'] = normalize_schema_columns(
            json_table.get('schema', []),
            use_column_descriptions
        )

        associations = normalize_associations(
            json_table.pop('associationData', None),
            table_database,
            use_associations
        )
        if associations is not None and use_associations is not False:
            json_table['associations'] = associations

        if "description" in json_table and use_table_descriptions is False:
            json_table.pop('description')

        return cls(json_table)

    def to_dict(self):
        return dict(self._view_data)

    def get_id(self):
        return str(self._view_data['id'])

    def get_name(self):
        return self._view_data['tableName']

    def get_database_name(self):
        database_name, _ = split_table_name(self.get_name())
        return database_name

    def get_association_ids(self):
        association_ids = []
        for association in self._view_data.get('associations', []):
            association_ids.append(str(association['table_id']))
        return association_ids

    def _render_plain_text(self, include_associations=False, include_descriptions=True, description_limit=None, present_tables=None):
        present_tables = present_tables or []
        lines = [f"Table: {self.get_name()}"]

        table_description = self._view_data.get('description', '')
        if include_descriptions and table_description and table_description.strip():
            table_description = table_description.replace("\n", " ").strip()
            if description_limit and len(table_description) > description_limit:
                table_description = f"{table_description[:description_limit]}... (truncated)"
            lines.append(f"Description: {table_description}")

        lines.append("Columns:")
        for column in self._view_data.get('schema', []):
            lines.append(
                SchemaColumn(column).render_plain_line(
                    include_descriptions=include_descriptions,
                    description_limit=description_limit
                )
            )

        if include_associations:
            association_lines = []
            for association in self._view_data.get('associations', []):
                where_clause = association.get('where')
                if where_clause and sum(table in where_clause for table in present_tables) == 2:
                    association_lines.append(SchemaAssociation(association).render_line())

            if association_lines:
                lines.append("Associations:")
                lines.extend(association_lines)

        return "\n".join(lines) + "\n\n"

    def render_embedding_text(self):
        # Embedding grammar:
        # Table: <database>.<view>
        # Description: <description>
        # Columns:
        # - <column_name> (<type>)
        # - <column_name> (<type>) → <description>
        # - <column_name> (<type>) → <logical_name>
        # - <column_name> (<type>) → <logical_name>: <description>
        return self._render_plain_text(include_associations=False, include_descriptions=True)

    def render_selector_text(self, column_description_char_limit=None, present_tables=None):
        # Selector grammar:
        # Table: <database>.<view>
        # Description: <description>
        # Columns:
        # - <column_name> (<type>)
        # - <column_name> (<type>) → <description> ... (truncated)
        # - <column_name> (<type>) → <logical_name>
        # - <column_name> (<type>) → <logical_name>: <description> ... (truncated)
        # Associations:
        # → <join_clause>. Description: <association_description>
        # → <join_clause>
        return self._render_plain_text(
            include_associations=True,
            include_descriptions=column_description_char_limit is not None and column_description_char_limit > 0,
            description_limit=column_description_char_limit,
            present_tables=present_tables
        )

    def render_vql_text(self, sample_data=None, present_tables=None, examples_per_table=3):
        # VQL grammar:
        # # Table: "<database>"."<view>"
        # ## Description: <description>
        # ## Columns:
        # - <column_name> (<type>) [PK] [NOT NULL]
        # - <column_name> (<type>) → <logical_name>
        # - <column_name> (<type>) → <logical_name>: <description>.
        # - <column_name> (<type>) → <logical_name>. sample values: a, b, c
        # - <column_name> (<type>) sample values: a, b, c
        # ## JOINs:
        # → <join_clause>. Description: <association_description>
        # → <join_clause>
        present_tables = present_tables or []
        lines = []
        table_name = self.get_name()
        table_description = self._view_data.get('description', '')
        database_name, view_name = split_table_name(table_name)
        quoted_table_name = f'"{database_name}"."{view_name}"' if database_name else f'"{view_name}"'

        lines.append(f"# Table: {quoted_table_name}")
        if table_description:
            lines.append(f"## Description: {table_description}")
        lines.append("## Columns:")

        table_id = self.get_id()
        table_sample_data = sample_data.get(table_id, {}) if sample_data and table_id in sample_data else {}
        for column in self._view_data.get('schema', []):
            column_name = column.get('columnName')
            column_sample_data = table_sample_data.get(column_name, [])
            lines.append(
                SchemaColumn(column).render_vql_line(
                    sample_values=column_sample_data,
                    examples_per_table=examples_per_table
                )
            )

        association_lines = []
        for association in self._view_data.get('associations', []):
            where_clause = association.get('where')
            if where_clause and sum(table in where_clause for table in present_tables) == 2:
                association_lines.append(SchemaAssociation(association).render_line())

        if association_lines:
            lines.append("## JOINs:")
            lines.extend(association_lines)

        return "\n".join(lines)

    def to_embedding_documents(self, embeddings_token_limit=0):
        table_summary = self.render_embedding_text()
        table_summary_tokens = calculate_tokens(table_summary)
        if embeddings_token_limit and table_summary_tokens > embeddings_token_limit:
            return self._create_chunk_documents(embeddings_token_limit)

        metadata = {
            "view_name": self.get_name(),
            "view_json": json.dumps(self.to_dict()),
            "view_id": self.get_id(),
            "document_id": self.get_id(),
            "database_name": self.get_database_name(),
            "last_update": int(time() * 1000)
        }

        for tag in self._view_data.get('tagDetails', []):
            metadata[f"tag_{tag['name']}"] = "1"

        return Document(
            id=self.get_id(),
            page_content=table_summary,
            metadata=metadata
        )

    def _create_chunk_documents(self, embeddings_token_limit):
        summary = self.render_embedding_text()
        parts = summary.split("Columns:\n", 1)
        header = parts[0] + "Columns:\n"
        content = parts[1] if len(parts) > 1 else ""

        lines = content.split("\n")
        column_lines = []
        association_lines = []
        for line in lines:
            if line.startswith("This table is also associated"):
                association_lines.append(line)
            elif line.strip():
                column_lines.append(line)

        association_footer = "\n" + "\n".join(association_lines) if association_lines else ""
        base_tokens = calculate_tokens(header + association_footer)
        available_tokens = (embeddings_token_limit - 500) - base_tokens

        column_content = "\n".join(column_lines)
        total_tokens = calculate_tokens(column_content)
        target_chunks = (total_tokens // available_tokens) + 1
        chunk_size = max(1, len(column_lines) // target_chunks)

        chunks = []
        for index in range(0, len(column_lines), chunk_size):
            current_lines = column_lines[index:index + chunk_size]
            chunk_content = header + "\n".join(current_lines) + association_footer + "\n"
            document_id = f"{self.get_id()}_{len(chunks)}"
            metadata = {
                "view_name": self.get_name(),
                "view_json": json.dumps(self.to_dict()),
                "view_id": self.get_id(),
                "document_id": document_id,
                "database_name": self.get_database_name()
            }

            for tag in self._view_data.get('tagDetails', []):
                metadata[f"tag_{tag['name']}"] = "1"

            chunks.append(Document(
                id=document_id,
                page_content=chunk_content,
                metadata=metadata
            ))

        return chunks

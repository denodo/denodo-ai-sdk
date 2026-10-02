import re
import tiktoken

def remove_none_values(data):
    if not isinstance(data, dict):
        return data

    cleaned = {}
    for key, value in data.items():
        if value is None:
            continue
        cleaned[key] = value
    return cleaned

def calculate_tokens(string, encoding='cl100k_base'):
    return len(tiktoken.get_encoding(encoding).encode(string))

def split_table_name(table_name):
    if '.' not in table_name:
        return '', table_name

    return table_name.split('.', 1)

def normalize_table_name(table_name):
    """Strip whitespace and double quotes so '"db"."view"' matches 'db.view'."""
    if table_name is None:
        return ''
    return str(table_name).strip().replace('"', '')

def quote_table_name(table_name):
    """Render a table name in VQL form: '"db"."view"' (or '"view"' if no database)."""
    database_name, view_name = split_table_name(normalize_table_name(table_name))
    if database_name:
        return f'"{database_name}"."{view_name}"'
    if view_name:
        return f'"{view_name}"'
    return ''

def quote_table_name_from_parts(database_name, view_name):
    """Render a table name in VQL form from separate db and view names."""
    db = str(database_name).strip().replace('"', '') if database_name else ''
    view = str(view_name).strip().replace('"', '') if view_name else ''

    if db and view:
        return f'"{db}"."{view}"'
    if view:
        return f'"{view}"'
    return ''

def build_table_name(table_database, table_name):
    return f"{table_database}.{table_name}".replace('"', '')

def attach_sample_data(json_table):
    if 'viewFieldDataList' not in json_table:
        return

    sample_data_dict = {}
    for example in json_table['viewFieldDataList']:
        sample_data_dict[example['fieldName'].strip('"')] = example['fieldValues']

    for field in json_table.get('schema', []):
        field_name = field['name'].strip('"')
        field['sample_data'] = sample_data_dict.get(field_name, [])

def flatten_text(text):
    """Collapse a value to a single stripped line of text ('' when empty)."""
    if not text:
        return ''
    return str(text).replace('\n', ' ').strip()

def normalize_tag_details(raw_tags):
    """Normalize Data Marketplace tag payloads into [{'name': ..., 'description': ...}].

    Accepts both view-level `tagDetails` and column-level `tags` entries, which
    arrive as dicts with `name`/`description` keys. Non-dict entries and entries
    without a name are dropped; descriptions are flattened to a single line.
    """
    if not isinstance(raw_tags, list):
        return []

    normalized_tags = []
    for tag in raw_tags:
        if not isinstance(tag, dict):
            continue

        name = str(tag.get('name') or '').strip()
        if not name:
            continue

        normalized_tags.append({'name': name, 'description': flatten_text(tag.get('description'))})

    return normalized_tags

def encode_tag(tag_name):
    """
    Escapes any character that is not a letter or a number (INCLUDING underscores)
    using its hexadecimal value. This makes hash collisions mathematically impossible
    and bypasses Langchain's strict isidentifier() rules for SQL Server.
    """
    return re.sub(r'[^a-zA-Z0-9]', lambda m: f"_{ord(m.group(0)):x}_", str(tag_name))

def format_tag_names(tag_details):
    """Join tag names with ', ', quoting any name that contains the delimiter itself."""
    names = []
    for tag in tag_details:
        name = tag['name']
        names.append(f'"{name}"' if ',' in name else name)
    return ', '.join(names)

def normalize_schema_columns(schema, use_column_descriptions):
    normalized_schema = []
    for item in schema:
        normalized_item = {'columnName': item['name']} | {
            key: value for key, value in item.items() if key != 'name'
        }
        if not use_column_descriptions:
            normalized_item.pop('logicalName', None)
            normalized_item.pop('description', None)
        extra = normalized_item.get('extraProperties')
        if extra is not None and not isinstance(extra, dict):
            normalized_item.pop('extraProperties', None)
        normalized_schema.append(normalized_item)

    return normalized_schema

def normalize_associations(association_data, table_database, use_associations):
    if association_data is None:
        return None
    if use_associations is False:
        return []

    associations = []
    for association in association_data:
        other_table = association['viewDetailsOfTheOtherView']['name']
        other_table_db = association['viewDetailsOfTheOtherView']['databaseName']
        mapping = association['mapping'].replace('"', '').split("=")

        for index in range(len(mapping)):
            mapping_table_name = mapping[index].split(".")[0]
            if mapping_table_name != other_table:
                mapping[index] = f"{table_database}.{mapping[index]}"
            else:
                mapping[index] = f"{other_table_db}.{mapping[index]}"

        associations.append({
            'table_name': build_table_name(other_table_db, other_table),
            'table_id': association['viewDetailsOfTheOtherView']['id'],
            'where': " = ".join(mapping),
            'description': association.get('description', "")
        })

    return associations

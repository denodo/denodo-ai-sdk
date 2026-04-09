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

def normalize_schema_columns(schema, use_column_descriptions):
    normalized_schema = []
    for item in schema:
        normalized_item = {'columnName': item['name']} | {
            key: value for key, value in item.items() if key != 'name'
        }
        if not use_column_descriptions:
            normalized_item.pop('logicalName', None)
            normalized_item.pop('description', None)
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

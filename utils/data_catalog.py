"""
 Copyright (c) 2024. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import os
import json
import base64
import logging
import requests
import concurrent.futures
from utils.utils import timed, log_params

DATA_CATALOG_URL = os.getenv('DATA_CATALOG_URL', 'http://localhost:9090/denodo-data-catalog').rstrip('/') + '/'    
DATA_CATALOG_VERIFY_SSL = os.getenv('DATA_CATALOG_VERIFY_SSL', '0') == '1'
DATA_CATALOG_SERVER_ID = int(os.getenv('DATA_CATALOG_SERVER_ID', 1))
DATA_CATALOG_METADATA_URL = f"{DATA_CATALOG_URL}public/api/askaquestion/data"
DATA_CATALOG_EXECUTION_URL = f"{DATA_CATALOG_URL}public/api/askaquestion/execute"
DATA_CATALOG_PERMISSIONS_URL = f"{DATA_CATALOG_URL}public/api/views/allowed-identifiers"

EXECUTE_VQL_LIMIT = 100

@timed
def get_views_metadata_documents(
    database_name,
    auth,
    examples_per_table=3,
    table_associations=True,
    table_descriptions=True,
    table_column_descriptions=True,
    filter_tables=None,
    data_mode='DATABASE',
    server_id=DATA_CATALOG_SERVER_ID,
    verify_ssl=DATA_CATALOG_VERIFY_SSL,
    metadata_url=DATA_CATALOG_METADATA_URL
):
    """
    Retrieve JSON documents from views metadata with support for OAuth token or Basic auth.
    
    Args:
        database_name: Name of the database to query
        auth: Either (username, password) tuple for basic auth or OAuth token string
        examples_per_table: Number of example rows to fetch per table (0 to disable)
        table_associations: Whether to include table associations
        table_descriptions: Whether to include descriptions
        filter_tables: List of tables to exclude (default: None)
        data_mode: Mode of data retrieval (default: 'DATABASE')
        server_id: Server identifier
        verify_ssl: Whether to verify SSL certificates (default: DATA_CATALOG_VERIFY_SSL)
        metadata_url: Data Catalog metadata URL (default: DATA_CATALOG_METADATA_URL)
        
    Returns:
        Parsed metadata JSON response
    """
    logging.info(f"Starting to retrieve views metadata with {examples_per_table} examples per view on {database_name}")
    
    # Prepare request data
    data = {
        "dataMode": data_mode,
        "databaseName": database_name,
        "dataUsage": examples_per_table > 0
    }
    
    if examples_per_table > 0:
        data["dataUsageConfiguration"] = {
            "tuplesToUse": examples_per_table,
            "samplingMethod": "random"
        }

    # Prepare headers based on auth type
    headers = {'Content-Type': 'application/json'}
    if isinstance(auth, tuple):
        headers['Authorization'] = calculate_basic_auth_authorization_header(*auth)
    else:
        headers['Authorization'] = f'Bearer {auth}'

    try:
        response = requests.post(
            f"{metadata_url}?serverId={server_id}",
            json=data,
            headers=headers,
            verify=verify_ssl
        )
        response.raise_for_status()
        json_response = response.json()

        logging.info("Data from database %s returned successfully", database_name)

        return parse_metadata_json(
            json_response=json_response,
            use_associations=table_associations,
            use_descriptions=table_descriptions,
            use_column_descriptions=table_column_descriptions,
            filter_tables=filter_tables or []
        )

    except requests.HTTPError as e:
        error_response = json.loads(e.response.text)
        error_message = parse_execution_error(
            error_response.get('message', 'Data Catalog did not return further details')
        )
        logging.error("Data Catalog views metadata request failed: %s", error_message)
        raise

    except requests.RequestException as e:
        logging.error("Failed to connect to the server: %s", str(e))
        raise

@timed
def execute_vql(vql, auth, limit=EXECUTE_VQL_LIMIT, execution_url=DATA_CATALOG_EXECUTION_URL, 
                server_id=DATA_CATALOG_SERVER_ID, verify_ssl=DATA_CATALOG_VERIFY_SSL):
    """
    Execute VQL against Data Catalog with support for OAuth token or Basic auth.
    
    Args:
        vql: VQL query to execute
        auth: Either (username, password) tuple for basic auth or OAuth token string
        limit: Maximum number of rows to return
        execution_url: Data Catalog execution endpoint
        server_id: Server identifier
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        Status code and parsed response or error message
    """
    logging.info("Preparing execution request")
    
    # Prepare headers based on auth type
    headers = {'Content-Type': 'application/json'}
    if isinstance(auth, tuple):
        headers['Authorization'] = calculate_basic_auth_authorization_header(*auth)
    else:
        headers['Authorization'] = f'Bearer {auth}'

    data = {
        "vql": vql,
        "limit": limit
    }

    try:
        response = requests.post(
            f"{execution_url}?serverId={server_id}",
            json=data,
            headers=headers,
            verify=verify_ssl
        )
        response.raise_for_status()

        json_response = response.json()
        if not json_response.get('rows'):
            logging.info("Query returned no rows")
            return 499, None

        logging.info("Query executed successfully")
        return response.status_code, parse_execution_json(json_response)

    except requests.HTTPError as e:
        error_response = json.loads(e.response.text)
        error_message = parse_execution_error(error_response.get('message', 'Data Catalog did not return further details'))
        logging.error(f"Data Catalog execute VQL failed: {error_message}")
        return e.response.status_code, error_message

    except requests.RequestException as e:
        error_message = f"Failed to connect to the server: {str(e)}"
        logging.error(f"{error_message}. VQL: {vql}")
        return 500, error_message
    
@log_params
@timed
def get_allowed_view_ids(
    database_names,
    auth,
    server_id=DATA_CATALOG_SERVER_ID,
    permissions_url=DATA_CATALOG_PERMISSIONS_URL,
    verify_ssl=DATA_CATALOG_VERIFY_SSL
):
    """
    Retrieve allowed view IDs for given databases.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        database_names: List of database names to query
        server_id: The server ID (default is DATA_CATALOG_SERVER_ID)
        permissions_url: The Data Catalog permissions URL
        verify_ssl: Whether to verify SSL certificates

    Returns:
       List of allowed view IDs across all databases
    """

    # Prepare headers based on auth type
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': (
            calculate_basic_auth_authorization_header(*auth) 
            if isinstance(auth, tuple) 
            else f'Bearer {auth}'
        )
    }

    def fetch_view_ids(db_name):
        data = {
            "dataMode": "DATABASE",
            "databaseNames": [db_name]
        }
        try:
            response = requests.post(
                f"{permissions_url}?serverId={server_id}",
                json=data,
                headers=headers,
                verify=verify_ssl
            )
            response.raise_for_status()
            view_ids = response.json()
            
            if not isinstance(view_ids, list) or not all(isinstance(id, int) for id in view_ids):
                raise ValueError(f"Unexpected response format for {db_name}: not a list of integers")
            
            return view_ids
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Failed to retrieve allowed view IDs for {db_name}: {str(e)}")
            return None

    # Use ThreadPoolExecutor for concurrent requests
    allowed_view_ids = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(fetch_view_ids, db) for db in database_names]
        for future in concurrent.futures.as_completed(futures):
            if view_ids := future.result():
                allowed_view_ids.extend(view_ids)

    return allowed_view_ids

# This method calculates the authorization header for the Data Catalog REST API
def calculate_basic_auth_authorization_header(user, password):
    user_pass = user + ':' + password
    ascii_bytes = user_pass.encode('ascii')
    return 'Basic' + ' ' + base64.b64encode(ascii_bytes).decode('utf-8')

# Remove None Values from Metadata Views
def remove_none_values(json_dict):
    if isinstance(json_dict, dict):
        return {k: remove_none_values(v) for k, v in json_dict.items() if v is not None and v != ''}
    elif isinstance(json_dict, list):
        return [remove_none_values(item) for item in json_dict if item is not None and item != '']
    else:
        return json_dict

# Parse the Metadata JSON with more readable format
def parse_metadata_json(json_response, use_associations = True, use_descriptions = True, use_column_descriptions = True, filter_tables = []):
    # Denodo 9.1.0 onwards, the response is wrapped in viewsDetails
    if 'viewsDetails' in json_response:
        json_response = json_response['viewsDetails']

    if len(json_response) == 0:
        return None

    json_metadata = {'databaseName': json_response[0]['databaseName'], 'databaseTables': []}

    for table in json_response:
        json_table = remove_none_values(table)
        table_name = f"{json_response[0]['databaseName']}.{json_table['name']}"   
        table_name = table_name.replace('"', '')      

        if json_table['name'] in filter_tables:
            continue

        if 'viewFieldDataList' in json_table:
            output_table = {
                'tableName': table_name,
                'description': json_table.get('description', ""),
            }

            example_data_dict = {}
            for example in json_table['viewFieldDataList']:
                    example_data_dict[example['fieldName']] = example['fieldValues']

            # Combine the example data with the schema
            for field in json_table['schema']:
                field_name = field['name']
                if field_name in example_data_dict:
                    field['example_data'] = example_data_dict[field_name]
                else:
                    field['example_data'] = []
        else:
            output_table = {
                'tableName': table_name,
                'description': json_table.get('description', ""),
            }

        keys_to_remove = ['name', 'description', 'databaseName', 'viewFieldDataList']

        for key in keys_to_remove:
            json_table.pop(key, None)

        json_table = output_table | json_table

        for i, item in enumerate(json_table['schema']):
            column_name = {'columnName': item['name']}
            item.pop('name')
            if use_column_descriptions == False:
                if 'logicalName' in item:
                    item.pop('logicalName')
                if 'description' in item:
                    item.pop('description')
            json_table['schema'][i] = column_name | item
        
        if "associationData" in json_table:
            if use_associations is False:
                json_table.pop('associationData')
            else:
                json_table['associations'] = []
                for association in json_table['associationData']:
                    other_table = association['viewDetailsOfTheOtherView']['name']
                    other_table_db = association['viewDetailsOfTheOtherView']['databaseName']
                    mapping = association['mapping']
                    mapping = mapping.split("=")
                    mapping = [f"{other_table_db}.{table}" for table in mapping]
                    mapping = " = ".join(mapping)
                    association_data = {
                        'table_name': f"{other_table_db}.{other_table}",
                        'table_id': association['viewDetailsOfTheOtherView']['id'],
                        'where': mapping
                    }
                    json_table['associations'].append(association_data)
                json_table.pop("associationData")

        if "description" in json_table and use_descriptions is False:
            json_table.pop('description')
            
        json_metadata['databaseTables'].append(json_table)
    return json_metadata

# Parse the result of the Execution to a more readable format
def parse_execution_json(json_response):
    parsed_data = {}

    for i, row in enumerate(json_response['rows']):
        parsed_data[f'Row {i + 1}'] = []
        for value in row['values']:
            parsed_data[f'Row {i + 1}'].append({
                'columnName': value['column'],
                'value': value['value']
            })

    return parsed_data

# Parse Execution Error
def parse_execution_error(execution_error):
    return execution_error.split('\n')[0]
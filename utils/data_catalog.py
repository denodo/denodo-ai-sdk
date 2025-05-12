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
import aiohttp
import asyncio
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
    auth,
    tag_name=None,
    database_name=None,
    examples_per_table=3,
    table_associations=True,
    table_descriptions=True,
    table_column_descriptions=True,
    filter_tables=None,
    server_id=DATA_CATALOG_SERVER_ID,
    verify_ssl=DATA_CATALOG_VERIFY_SSL,
    metadata_url=DATA_CATALOG_METADATA_URL,
    last_update_timestamp_ms=None,
    view_prefix_filter='',
    view_suffix_filter=''
):
    """
    Retrieve JSON documents from views metadata with support for OAuth token or Basic auth.
    Handles both legacy and paginated API versions automatically.
    
    Args:
        database_name: Name of the database to query (mutually exclusive with tag_name)
        auth: Either (username, password) tuple for basic auth or OAuth token string
        examples_per_table: Number of example rows to fetch per table (0 to disable)
        table_associations: Whether to include table associations
        table_descriptions: Whether to include descriptions
        table_column_descriptions: Whether to include column descriptions
        filter_tables: List of tables to exclude (default: None)
        tag_name: Name of the tag to query (mutually exclusive with database_name)
        server_id: Server identifier
        verify_ssl: Whether to verify SSL certificates (default: DATA_CATALOG_VERIFY_SSL)
        metadata_url: Data Catalog metadata URL (default: DATA_CATALOG_METADATA_URL)
        
    Returns:
        Parsed metadata JSON response
    """
    # Validate that only one of database_name or tag_name is provided
    if (database_name is None and tag_name is None) or (database_name is not None and tag_name is not None):
        raise ValueError("Exactly one of database_name or tag_name must be provided")
    
    # Set data_mode based on which parameter is provided
    data_mode = 'DATABASE' if database_name is not None else 'TAG'
    
    # Set the appropriate logging message based on which parameter is provided
    entity_name = database_name if database_name is not None else tag_name
    entity_type = "database" if database_name is not None else "tag"
    logging.info(f"Starting to retrieve views metadata with {examples_per_table} examples per view on {entity_type} '{entity_name}'")
    
    def prepare_request_data(offset=None, limit=None):
        data = {
            "dataMode": data_mode,
            "dataUsage": examples_per_table > 0,
        }

        if last_update_timestamp_ms:
            data["updatedSince"] = last_update_timestamp_ms
        
        # Add the appropriate parameter based on data_mode
        if data_mode == 'DATABASE':
            data["databaseName"] = database_name
        else:  # data_mode == 'TAG'
            data["tagName"] = tag_name
        
        if examples_per_table > 0:
            data["dataUsageConfiguration"] = {
                "tuplesToUse": examples_per_table,
                "samplingMethod": "random"
            }
        
        # Add pagination parameters only if specified
        if offset is not None:
            data["offset"] = offset
        if limit is not None:
            data["limit"] = limit
            
        return data

    def make_request(data):
        headers = {'Content-Type': 'application/json'}
        if isinstance(auth, tuple):
            headers['Authorization'] = calculate_basic_auth_authorization_header(*auth)
        else:
            headers['Authorization'] = f'Bearer {auth}'

        # 1. Make request and raise any connection/HTTP errors
        response = requests.post(
            f"{metadata_url}?serverId={server_id}",
            json=data,
            headers=headers,
            verify=verify_ssl
        )
        response.raise_for_status()

        # 2. Try to parse JSON response
        try:
            json_response = response.json()
        except ValueError as e:
            logging.error(f"Failed to parse JSON response: {str(e)}")
            raise ValueError(f"Invalid JSON response from server: {response.text}")

        # 3. Validate response structure
        if not isinstance(json_response, list) and 'viewsDetails' not in json_response:
            error_msg = f"Unexpected response format from server: {response.text}"
            logging.error(error_msg)
            raise ValueError(error_msg)

        return json_response

    try:
        # Initial request without pagination to detect DC API version
        initial_response = make_request(prepare_request_data())
        
        # If it's not a list, it's the old DC API (<9.1.0)
        if not isinstance(initial_response, list):
            views = initial_response.get('viewsDetails', initial_response)
            total_views = len(views)
            logging.info(f"Total views retrieved: {total_views}")
        
            # If we got less than 1000 views we can exit
            if total_views < 1000:
                logging.info(f"Retrieved {total_views} views in single request. No pagination needed")
                all_views = views
            else:
                # We're dealing with the new API version - need to paginate
                logging.info("Dealing with the pagination API. Making requests with pagination.")
                all_views = views
                offset = 1000
                
                while True:
                    data = prepare_request_data(offset=offset, limit=1000)
                    page_response = make_request(data)
                    logging.info(f"Made request with offset {offset} and limit 1000: {page_response}")
                    page_views = page_response.get('viewsDetails', page_response)
                    if not page_views:
                        break
                        
                    all_views.extend(page_views)
                    offset += 1000
                    logging.info(f"Retrieved {len(all_views)} views so far")
                    
                    if len(page_views) < 1000:
                        break
        else:
            all_views = initial_response

        logging.info(f"Total views retrieved: {len(all_views)}")
        
        return parse_metadata_json(
            json_response=all_views,
            use_associations=table_associations,
            use_descriptions=table_descriptions,
            use_column_descriptions=table_column_descriptions,
            filter_tables=filter_tables or [],
            view_prefix_filter=view_prefix_filter,
            view_suffix_filter=view_suffix_filter
        )

    except requests.HTTPError as e:
        error_response = json.loads(e.response.text)
        error_message = str(error_response.get('message', 'Data Catalog did not return further details'))
        logging.error("Data Catalog views metadata request failed: %s", error_message)
        raise

    except requests.RequestException as e:
        logging.error("Failed to connect to the server: %s", str(e))
        raise

@timed
async def execute_vql(vql, auth, limit=EXECUTE_VQL_LIMIT, execution_url=DATA_CATALOG_EXECUTION_URL, 
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
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{execution_url}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                response.raise_for_status()
                json_response = await response.json()
                
                # Check for empty results in multiple scenarios
                if not json_response.get('rows'):
                    logging.info("Query returned no results.")
                    return 499, "Query executed succesfully but returned an empty result (no rows)."
                elif (len(json_response['rows']) == 1 and  # Single row
                    len(json_response['rows'][0]['values']) == 1 and  # Single column
                    (str(json_response['rows'][0]['values'][0]['value']) == '0' or  # Value is 0
                     json_response['rows'][0]['values'][0]['value'] is None)):  # Value is null/None
                    logging.info("Query returned only one row, one column with a value of 0 or null")
                    return 499, f"Query executed succesfully but returned a single row with a value of 0 or null: {parse_execution_json(json_response)}"
                logging.info("Query executed successfully")
                return response.status, parse_execution_json(json_response)
    except aiohttp.ClientResponseError as e:
        try:
            error_text = await e.response.text()
            error_response = json.loads(error_text)
            error_message = str(error_response.get('message', 'Data Catalog did not return further details'))
        except (json.JSONDecodeError, AttributeError):
            error_message = f"HTTP Error: {e.status} - {e.message}"
        logging.error(f"Data Catalog execute VQL failed: {error_message}")
        return e.status, error_message
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        error_message = f"Failed to connect to the server: {str(e)}"
        logging.error(f"{error_message}. VQL: {vql}")
        return 500, error_message

@log_params
@timed
async def get_allowed_view_ids(
    auth,
    server_id=DATA_CATALOG_SERVER_ID,
    permissions_url=DATA_CATALOG_PERMISSIONS_URL,
    verify_ssl=DATA_CATALOG_VERIFY_SSL
):
    """
    Retrieve allowed view IDs for all views accessible to the user.

    Args:
        auth: Either (username, password) tuple for basic auth or OAuth token string
        server_id: The server ID (default is DATA_CATALOG_SERVER_ID)
        permissions_url: The Data Catalog permissions URL
        verify_ssl: Whether to verify SSL certificates

    Returns:
       List of unique allowed view IDs across all accessible views
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

    # Use "ALL" data mode to fetch all accessible view IDs in a single request
    data = {"dataMode": "ALL"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{permissions_url}?serverId={server_id}",
                json=data,
                headers=headers,
                ssl=verify_ssl
            ) as response:
                response.raise_for_status()
                view_ids = await response.json()
                
                if not isinstance(view_ids, list) or not all(isinstance(id, int) for id in view_ids):
                    raise ValueError("Unexpected response format: not a list of integers")
                
                # Ensure unique values
                unique_view_ids = list(set(view_ids))
                return unique_view_ids
                
    except aiohttp.ClientResponseError as e:
        try:
            error_text = await e.response.text()
            error_response = json.loads(error_text)
            error_message = f"Failed to retrieve allowed view IDs: {error_response.get('message', 'Data Catalog did not return further details')}"
        except (json.JSONDecodeError, AttributeError):
            error_message = f"HTTP Error: {e.status} - {e.message}"
        logging.error(error_message)
        return []
    except (aiohttp.ClientError, ValueError) as e:
        logging.error(f"Failed to retrieve allowed view IDs: {str(e)}")
        return []

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
def parse_metadata_json(
    json_response,
    use_associations = True,
    use_descriptions = True,
    use_column_descriptions = True,
    filter_tables = [],
    view_prefix_filter='',
    view_suffix_filter=''
):
    # Denodo 9.1.0 onwards, the response is wrapped in viewsDetails
    if 'viewsDetails' in json_response:
        json_response = json_response['viewsDetails']

    if len(json_response) == 0:
        return None

    json_metadata = {'views': []}

    for table in json_response:
        json_table = remove_none_values(table)
        table_database = json_table['databaseName']
        table_name = json_table['name']
        table_name = f"{table_database}.{table_name}"   
        table_name = table_name.replace('"', '')      

        if table_name in filter_tables:
            continue

        if view_prefix_filter and not table_name.startswith(view_prefix_filter):
            continue

        if view_suffix_filter and not table_name.endswith(view_suffix_filter):
            continue

        if 'viewFieldDataList' in json_table:
            output_table = {
                'tableName': table_name,
                'description': json_table.get('description', ""),
            }

            sample_data_dict = {}
            for example in json_table['viewFieldDataList']:
                    sample_data_dict[example['fieldName'].strip('"')] = example['fieldValues']
            # Combine the example data with the schema
            for field in json_table['schema']:
                field_name = field['name'].strip('"')
                if field_name in sample_data_dict:
                    field['sample_data'] = sample_data_dict[field_name]
                else:
                    field['sample_data'] = []
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
            if not use_column_descriptions:
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
                    mapping = association['mapping'].replace('"', '')
                    mapping = mapping.split("=")

                    for i in range(len(mapping)):
                        table_name = mapping[i].split(".")[0]
                        if table_name != other_table:
                            mapping[i] = f"{table_database}.{mapping[i]}"
                        else:
                            mapping[i] = f"{other_table_db}.{mapping[i]}"

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
            
        json_metadata['views'].append(json_table)
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
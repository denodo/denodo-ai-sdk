"""
 Copyright (c) 2024. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import re
import os
import pytz
import json
import logging
import tiktoken
import functools

from time import time
from uuid import uuid4
from boto3 import Session
from functools import wraps, lru_cache
from datetime import datetime
from botocore.session import get_session
from langchain_core.documents.base import Document
from botocore.credentials import RefreshableCredentials
from langchain.callbacks.base import BaseCallbackHandler

def log_params(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        
        # Log entry
        def format_param(key, value):
            if key == "auth":
                return f"{key}=<redacted>"
            str_value = str(value)
            return f"{key}={str_value[:500] + '...' if len(str_value) > 500 else str_value}"
        
        params = ", ".join([format_param(f"arg{i}", arg) for i, arg in enumerate(args)] +
                           [format_param(k, v) for k, v in kwargs.items()])
        logging.info(f"{func_name} - Entry: Parameters({params})")
        
        # Call the original function
        result = func(*args, **kwargs)
        
        # Log exit
        str_result = str(result)
        truncated_result = str_result[:500] + '...' if len(str_result) > 500 else str_result
        logging.info(f"{func_name} - Exit: Returned({truncated_result})")
        
        return result
    return wrapper

@lru_cache(maxsize=None)
def get_langfuse_callback(model_id, session_id = None):
    if os.getenv('LANGFUSE_PUBLIC_KEY') and os.getenv('LANGFUSE_USER'):
        from langfuse.callback import CallbackHandler
        params = {
            "user_id": os.getenv('LANGFUSE_USER'),
            "release": os.getenv('AI_SDK_VER', 'Not set'),
            "metadata": {
                "model_id": model_id
            }
        }
        if session_id is not None:
            params["session_id"] = session_id
        return CallbackHandler(**params)
    return None

def generate_langfuse_session_id():
    """Generate a session ID in format: timestamp_user_shortUUID"""
    user = os.getenv('LANGFUSE_USER')
    if user:
        current_time = datetime.now().strftime("%Y_%m_%d_%H_%M")
        session_uuid = uuid4().hex[:4]
        return f"{current_time}_{user}_{session_uuid}"
    else:
        return None

def add_langfuse_callback(base_callback, model_id, session_id = None):
    callbacks = [base_callback]
    langfuse_callback = get_langfuse_callback(model_id, session_id)
    if langfuse_callback:
        callbacks.append(langfuse_callback)
    return callbacks

# Timer Decorator
def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        end = time()
        elapsed_time = round(end - start, 2)
        logging.info("{} ran in {}s".format(func.__name__, elapsed_time))

        wrapper.elapsed_time = elapsed_time
        return result

    return wrapper

# Get the associations for a given table
def get_table_associations(table_name, table_json):
    table_associations = []
    schema_table_name = table_json['tableName']
    if table_name == schema_table_name:
        if 'associations' in table_json:
            for association in table_json['associations']:
                table_associations.append(association['table_name'])
    return table_associations

# Summarize a schema
def schema_summary(schema):
    summary = "====="
    table_name = schema['tableName']
    if "description" in schema and schema['description'] and schema['description'].strip():
        summary += f"Table {table_name}=====\nDescription: {schema['description']}\nColumns:\n"
    else:
        summary += f"Table {table_name}=====\n"
    for column_info in schema['schema']:
        column_name = column_info['columnName']
        column_type = column_info['type']
        if "logicalName" in column_info:
            column_logical_name = column_info['logicalName']
        else:
            column_logical_name = None
        if "description" in column_info:
            column_description = column_info['description']
        else:
            column_description = None

        examples = schema.get('exampleRow')

        example_values = []

        if examples is not None:
            for example_dict in examples:
                if example_dict['fieldName'] == column_name:
                    example_values.extend(example_dict['fieldValues'])
                    break

        if len(example_values) != 0:
            example_values = list(set(example_values))
            example_values_str = ', '.join(example_values)
            example_value = f" Example value: {example_values_str}"
        else:
            example_value = ""

        if column_logical_name is not None and column_description is not None: 
            summary += f"- {column_name} ({column_type}) -> {column_logical_name}: {column_description}.{example_value}\n"
        elif column_logical_name is None and column_description is not None: 
            summary += f"- {column_name} ({column_type}) -> {column_description}.{example_value}\n"
        elif column_logical_name is not None and column_description is None:
            summary += f"- {column_name} ({column_type}) -> {column_logical_name}.{example_value}\n"
        else:
            summary += f"- {column_name} ({column_type}).{example_value}\n"
    
    if "associations" in schema and len(schema['associations']) != 0:
        summary += "\n"
        for association in schema['associations']:
            summary += f"This table is also associated with table {association['table_name']} on {association['where']}\n"
    summary += "\n"
    return summary
            
# Calculate the tokens of a given string
def calculate_tokens(string, encoding = 'cl100k_base'):
    encoding = tiktoken.get_encoding(encoding)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# Parse the XML tags in the LLM's response
def custom_tag_parser(text, tag, default=[]):
    if text is None:
        return [default] if not isinstance(default, list) else []
    
    pattern = re.compile(fr'<{tag}>(.*?)</{tag}>', re.DOTALL)
    matches = re.findall(pattern, text)
    
    if not matches:
        return [default] if not isinstance(default, list) else []
    
    return matches

@timed
def prepare_schema(schema, user_permissions=False, start_index = 0):
    if not schema:
        raise ValueError("No schema was received in prepare_schema for VectorDB insertion.")

    def create_document(table, index):
        base_metadata = {
            "view_name": table['tableName'],
            "view_json": json.dumps(table),
            "view_id": str(table['id']) if user_permissions else str(index),
            "database_name": table['tableName'].split('.')[0]
        }

        return Document(
            id=str(table['id']) if user_permissions else str(index),
            page_content=schema_summary(table),
            metadata=base_metadata
        )
        
    return [create_document(table, i + start_index) for i, table in enumerate(schema['databaseTables'])]

class RefreshableBotoSession:
    def __init__(
        self,
        region_name: str = None,
        access_key: str = None,
        secret_key: str = None,
        profile_name: str = None,
        sts_arn: str = None,
        session_name: str = None,
        session_ttl: int = 3000
    ):
        self.region_name = region_name
        self.access_key = access_key
        self.secret_key = secret_key
        self.profile_name = profile_name
        self.sts_arn = sts_arn
        self.session_name = session_name or uuid4().hex
        self.session_ttl = session_ttl

    def __get_session_credentials(self):
        if self.access_key and self.secret_key:
            session = Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region_name
            )
        else:
            session = Session(
                region_name = self.region_name,
                profile_name = self.profile_name
            )

        if self.sts_arn:
            sts_client = session.client(service_name = "sts", region_name = self.region_name)
            response = sts_client.assume_role(
                RoleArn = self.sts_arn,
                RoleSessionName = self.session_name,
                DurationSeconds = self.session_ttl,
            ).get("Credentials")

            credentials = {
                "access_key": response.get("AccessKeyId"),
                "secret_key": response.get("SecretAccessKey"),
                "token": response.get("SessionToken"),
                "expiry_time": response.get("Expiration").isoformat(),
            }
        else:
            session_credentials = session.get_credentials().get_frozen_credentials()
            credentials = {
                "access_key": session_credentials.access_key,
                "secret_key": session_credentials.secret_key,
                "token": session_credentials.token,
                "expiry_time": datetime.fromtimestamp(time() + self.session_ttl).replace(tzinfo = pytz.utc).isoformat(),
            }

        return credentials

    def refreshable_session(self) -> Session:
        refreshable_credentials = RefreshableCredentials.create_from_metadata(
            metadata = self.__get_session_credentials(),
            refresh_using = self.__get_session_credentials,
            method = "sts-assume-role",
        )

        session = get_session()
        session._credentials = refreshable_credentials
        session.set_config_variable("region", self.region_name)
        autorefresh_session = Session(botocore_session = session)

        return autorefresh_session
    
# Token Counter for LLMs
class TokenCounter(BaseCallbackHandler):
    def __init__(self, llm):
        self.llm = llm
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def on_llm_start(self, serialized, prompts, **kwargs):
        for p in prompts:
            self.prompt_tokens += self.llm.get_num_tokens(p)

    def on_llm_end(self, response, **kwargs):
        results = response.flatten()
        for r in results:
            self.completion_tokens = self.llm.get_num_tokens(r.generations[0][0].text)

    def reset_tokens(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
    
    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

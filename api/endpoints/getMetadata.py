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
import requests
import logging
import traceback

from pydantic import BaseModel
from typing import Dict, List, Annotated

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBearer, HTTPBasicCredentials, HTTPAuthorizationCredentials

from utils.uniformVectorStore import UniformVectorStore
from utils.data_catalog import get_views_metadata_documents
from utils.utils import calculate_tokens, schema_summary, prepare_schema

router = APIRouter()
security_basic = HTTPBasic()
security_bearer = HTTPBearer()

# Get the authentication type from environment
AUTH_TYPE = os.getenv("DATA_CATALOG_AUTH_TYPE", "http_basic")

if AUTH_TYPE.lower() == "http_basic":
    def authenticate(credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)]):
        return (credentials.username, credentials.password)
else:
    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]):
        return credentials.credentials

def process_database(db_name, request, auth, vector_store, user_permissions, start_index = 0):
    result = get_views_metadata_documents(
        database_name=db_name, 
        auth=auth,
        examples_per_table=request.examples_per_table, 
        table_descriptions=request.view_descriptions, 
        table_associations=request.associations,
        table_column_descriptions=request.column_descriptions
    )
    
    if not result:
        raise ValueError(f"Empty response from the Denodo Data Catalog for database {db_name}")
    
    if isinstance(result, dict):
        db_schema = result
        logging.info(f"Database schema for {db_name} has {calculate_tokens(str(db_schema))} tokens.")
        
        db_schema_text = [schema_summary(table) for table in db_schema['databaseTables']]
        
        if vector_store:
            views = prepare_schema(db_schema, user_permissions, start_index)
            vector_store.add_views(
                views=views,
                database_name=db_name,
                overwrite=request.overwrite
            )
        
        return db_schema, db_schema_text

class getMetadataRequest(BaseModel):
    vdp_database_names: str = os.getenv('VDB_NAMES')
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    examples_per_table: int = 3
    view_descriptions: bool = True
    column_descriptions: bool = True
    associations: bool = True
    insert: bool = False
    overwrite: bool = False

class TableSummary(BaseModel):
    summary: str

class getMetadataResponse(BaseModel):
    db_schema_json: Dict
    db_schema_text: List[TableSummary]

@router.get("/getMetadata", response_class = JSONResponse, response_model = getMetadataResponse)
def getMetadata(endpoint_request: getMetadataRequest = Depends(), auth: str = Depends(authenticate)):
    """
    This endpoint retrieves the metadata from a list of VDP databases (separated by commas) and returns it in JSON and natural language format. 
    Optionally, if given access to a Denodo-supported vector store, it can also insert the metadata using the embeddings provider of your choice.
    """
    try:
        vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',')]
        USER_PERMISSIONS = int(os.getenv("USER_PERMISSIONS", 0))

        all_db_schemas = []
        all_db_schema_texts = []

        if endpoint_request.insert:
            vector_store = UniformVectorStore(
                provider=endpoint_request.vector_store_provider,
                embeddings_provider=endpoint_request.embeddings_provider,
                embeddings_model=endpoint_request.embeddings_model,
            )
        else:
            vector_store = None

        for db_name in vdp_database_names:
            try:
                db_schema, db_schema_text = process_database(
                    db_name=db_name, 
                    request=endpoint_request, 
                    auth=auth,
                    vector_store=vector_store, 
                    user_permissions=USER_PERMISSIONS,
                    start_index=len(all_db_schema_texts)
                )
                
                all_db_schemas.append(db_schema)
                all_db_schema_texts.extend(db_schema_text)
            except ValueError as ve:
                logging.error(f"Error processing database: {ve}")
                continue

        if len(all_db_schemas) == 0:
            raise HTTPException(status_code=204, detail=f"Data Catalog returned empty response for: {vdp_database_names}")

        response = {
            'db_schema_json': all_db_schemas,
            'db_schema_text': all_db_schema_texts,
            'vdb_list': vdp_database_names
        }

        return JSONResponse(content = jsonable_encoder(response), media_type = "application/json")
    except requests.exceptions.HTTPError as he:
        if he.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except HTTPException as he:
        raise he
    except Exception as e:
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        raise HTTPException(status_code=500, detail=error_details)
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
import logging

from pydantic import BaseModel
from typing import Dict, List, Annotated

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBearer, HTTPBasicCredentials, HTTPAuthorizationCredentials

from utils.uniformVectorStore import UniformVectorStore
from utils.data_catalog import get_views_metadata_documents
from utils.utils import calculate_tokens, schema_summary, prepare_schema, flatten_list, prepare_sample_data_schema
from api.utils.sdk_utils import handle_endpoint_error

router = APIRouter()
security_basic = HTTPBasic(auto_error = False)
security_bearer = HTTPBearer(auto_error = False)
    
def authenticate(
        basic_credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]
        ):
    if bearer_credentials is not None:
        return bearer_credentials.credentials
    elif basic_credentials is not None:
        return (basic_credentials.username, basic_credentials.password)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

def process_tag(tag_name, request, auth, vector_store, sample_data_vector_store):
    if vector_store:
        last_update = vector_store.get_last_update()
    else:
        last_update = None

    result = get_views_metadata_documents(
        tag_name=tag_name,
        auth=auth,
        examples_per_table=request.examples_per_table,
        table_descriptions=request.view_descriptions,
        table_associations=request.associations,
        table_column_descriptions=request.column_descriptions,
        last_update_timestamp_ms=last_update,
        view_prefix_filter=request.view_prefix_filter,
        view_suffix_filter=request.view_suffix_filter
    )
    
    if not result:
        raise ValueError(f"Empty response from the Denodo Data Catalog for tag {tag_name}")
    
    if isinstance(result, dict):
        db_schema = result
        logging.info(f"Tag schema for {tag_name} has {calculate_tokens(str(db_schema))} tokens.")
        db_schema_text = [schema_summary(table) for table in db_schema['views']]
        
        if vector_store:
            views = flatten_list(prepare_schema(db_schema, request.embeddings_token_limit))
            vector_store.add_views(
                views=views,
                parallel=request.parallel
            )

        if sample_data_vector_store:
            views = flatten_list(prepare_sample_data_schema(db_schema))
            sample_data_vector_store.add_views(
                views=views,
                parallel=request.parallel
            )
        return db_schema, db_schema_text

def process_database(db_name, request, auth, vector_store, sample_data_vector_store):
    if vector_store:
        last_update = vector_store.get_last_update()
    else:
        last_update = None

    result = get_views_metadata_documents(
        database_name=db_name, 
        auth=auth,
        examples_per_table=request.examples_per_table, 
        table_descriptions=request.view_descriptions, 
        table_associations=request.associations,
        table_column_descriptions=request.column_descriptions,
        last_update_timestamp_ms=last_update,
        view_prefix_filter=request.view_prefix_filter,
        view_suffix_filter=request.view_suffix_filter
    )
    
    if not result:
        raise ValueError(f"Empty response from the Denodo Data Catalog for database {db_name}")
    
    if isinstance(result, dict):
        db_schema = result
        logging.info(f"Database schema for {db_name} has {calculate_tokens(str(db_schema))} tokens.")
        db_schema_text = [schema_summary(table) for table in db_schema['views']]
        
        if vector_store:
            views = flatten_list(prepare_schema(db_schema, request.embeddings_token_limit))
            vector_store.add_views(
                views=views,
                parallel=request.parallel
            )
        
        if sample_data_vector_store:
            views = flatten_list(prepare_sample_data_schema(db_schema))
            sample_data_vector_store.add_views(
                views=views,
                parallel=request.parallel
            )        
        return db_schema, db_schema_text

class getMetadataRequest(BaseModel):
    vdp_database_names: str = os.getenv('VDB_NAMES', '')
    vdp_tag_names: str = os.getenv('VDB_TAGS', '')
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    embeddings_token_limit: int = os.getenv('EMBEDDINGS_TOKEN_LIMIT', 0)
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    rate_limit_rpm: int = os.getenv('RATE_LIMIT_RPM', 0)
    examples_per_table: int = Query(100, ge=0, le=500)
    view_descriptions: bool = True
    column_descriptions: bool = True
    associations: bool = True
    view_prefix_filter: str = ''
    view_suffix_filter: str = ''
    insert: bool = True
    parallel: bool = True

class getMetadataResponse(BaseModel):
    db_schema_json: Dict
    db_schema_text: List[str]
    vdb_list: List[str]
    tag_list: List[str]
    
@router.get(
        '/getMetadata',
        response_class = JSONResponse,
        response_model = getMetadataResponse,
        tags = ['Vector Store'])
@handle_endpoint_error("getMetadata")
def getMetadata(endpoint_request: getMetadataRequest = Depends(), auth: str = Depends(authenticate)):
    """
    This endpoint retrieves the metadata from a list of VDP databases (separated by commas) and returns it in JSON and natural language format. 
    Optionally, if given access to a Denodo-supported vector store, it can also insert the metadata using the embeddings provider of your choice.

    You can use the view_prefix_filter and view_suffix_filter parameters to filter the views that are inserted into the vector store.
    For example, if you set view_prefix_filter to "vdp_", only views that start with "vdp_" will be inserted into the vector store.
    """
    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',') if db]
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names.split(',') if tag]

    if not vdp_database_names and not vdp_tag_names:
        raise HTTPException(status_code=400, detail="At least one database or tag must be provided")

    all_db_schemas = []
    all_db_schema_texts = []

    vector_store = None
    sample_data_vector_store = None

    if endpoint_request.insert:
        vector_store = UniformVectorStore(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model,
            rate_limit_rpm=endpoint_request.rate_limit_rpm,
        )

        if endpoint_request.examples_per_table > 0:
            sample_data_vector_store = UniformVectorStore(
                provider=endpoint_request.vector_store_provider,
                embeddings_provider=endpoint_request.embeddings_provider,
                embeddings_model=endpoint_request.embeddings_model,
                rate_limit_rpm=endpoint_request.rate_limit_rpm,
                index_name="ai_sdk_sample_data"
            )
    
    for tag_name in vdp_tag_names:
        try:
            db_schema, db_schema_text = process_tag(
                tag_name=tag_name,
                request=endpoint_request,
                auth=auth,
                vector_store=vector_store,
                sample_data_vector_store=sample_data_vector_store,
            )
            
            all_db_schemas.append(db_schema)
            all_db_schema_texts.extend(db_schema_text)
        except ValueError as ve:
            logging.error(f"Error processing tag: {ve}")
            continue

    for db_name in vdp_database_names:
        try:
            db_schema, db_schema_text = process_database(
                db_name=db_name, 
                request=endpoint_request, 
                auth=auth,
                vector_store=vector_store,
                sample_data_vector_store=sample_data_vector_store
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
        'vdb_list': vdp_database_names,
        'tag_list': vdp_tag_names
    }

    return JSONResponse(content = jsonable_encoder(response), media_type = "application/json")
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
from typing import Dict, List

from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query

from utils.data_catalog import activate_incremental
from api.utils import state_manager
from api.utils.sdk_utils import (
    handle_endpoint_error, authenticate, process_metadata_source, 
    format_metadata_response, delete_by_db_or_tag
)

router = APIRouter()

class getMetadataRequest(BaseModel):
    vdp_database_names: str = ''
    vdp_tag_names: str = ''
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
    incremental: bool = True
    parallel: bool = True

class TableSummary(BaseModel):
    summary: str

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

    For first-time vectorization, please set incremental to False. This will vectorize all views associated with the indicated databases/tags.
    After that, you can call getMetadata with incremental set to True to only vectorize views that have been modified since the last sync.
    """
    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',') if db]
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names.split(',') if tag]

    if not vdp_database_names and not vdp_tag_names:
        raise HTTPException(status_code=400, detail="At least one database or tag must be provided")
    
    if endpoint_request.incremental:
        status_code, response_message = activate_incremental(auth)
        logging.info(f"Received status code {status_code} and response message {response_message}")

    all_db_schemas = []
    all_db_schema_texts = []

    vector_store = None
    sample_data_vector_store = None

    # Initialize vector stores if needed
    if endpoint_request.insert:
        try:
            vector_store = state_manager.get_vector_store(
                provider=endpoint_request.vector_store_provider,
                embeddings_provider=endpoint_request.embeddings_provider,
                embeddings_model=endpoint_request.embeddings_model,
                rate_limit_rpm=endpoint_request.rate_limit_rpm
            )
            
            if endpoint_request.examples_per_table > 0:
                sample_data_vector_store = state_manager.get_vector_store(
                    provider=endpoint_request.vector_store_provider,
                    embeddings_provider=endpoint_request.embeddings_provider,
                    embeddings_model=endpoint_request.embeddings_model,
                    rate_limit_rpm=endpoint_request.rate_limit_rpm,
                    index_name="ai_sdk_sample_data"
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}")

    if not endpoint_request.incremental:
        try:
            delete_by_db_or_tag(
                vector_store=vector_store,
                sample_data_vector_store=sample_data_vector_store,
                vdp_database_names=vdp_database_names,
                vdp_tag_names=vdp_tag_names,
                delete_conflicting=False
            )

        except Exception as e:
            logging.error(f"Error during metadata deletion: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete metadata: {e}")

    # Process tags
    for tag_name in vdp_tag_names:
        try:
            db_schema, db_schema_text = process_metadata_source(
                source_type="TAG",
                source_name=tag_name,
                request=endpoint_request,
                auth=auth,
                vector_store=vector_store,
                sample_data_vector_store=sample_data_vector_store
            )
            
            all_db_schemas.append(db_schema)
            all_db_schema_texts.extend(db_schema_text)
        except ValueError as ve:
            logging.error(f"Error processing tag: {ve}")
            continue

    # Process databases
    for db_name in vdp_database_names:
        try:
            db_schema, db_schema_text = process_metadata_source(
                source_type="DATABASE",
                source_name=db_name,
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

    if not any(all_db_schemas):
        return Response(status_code=204, content=None)

    # Format and return response
    response = format_metadata_response(
        all_db_schemas=all_db_schemas,
        all_db_schema_texts=all_db_schema_texts,
        vdb_database_names=vdp_database_names,
        vdb_tag_names=vdp_tag_names
    )

    return JSONResponse(content=jsonable_encoder(response), media_type="application/json")
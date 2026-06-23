"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import os
import logging
import traceback
import asyncio

from pydantic import BaseModel, Field
from typing import Dict, List

from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query

from utils.data_marketplace.connection import activate_incremental, get_user_permissions, DataCatalogAuthError
from api.utils import state_manager
from api.utils.sdk_utils import (
    handle_endpoint_error, authenticate, process_metadata_source,
    format_metadata_response, delete_by_db_or_tag, get_by_db_or_tag,
    check_metadata_user_permission
)
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

class getMetadataRequest(BaseModel):
    vdp_database_names: str = ''
    vdp_tag_names: str = Field(
            default = '',
            description="NOTE: When both databases and tags are specified, views from both sources are included (union), not their intersection. For example, if you have a database 'db1' and a tag with name 'tag1', the views of 'db1' and the views of 'tag1' will be included, minus duplicates."
        )
    tags_to_ignore: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    embeddings_token_limit: int = os.getenv('EMBEDDINGS_TOKEN_LIMIT', 0)
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    rate_limit_rpm: int = os.getenv('RATE_LIMIT_RPM', 0)
    examples_per_table: int = Query(
        default=100,
        ge=0,
        le=500
    )
    view_descriptions: bool = True
    column_descriptions: bool = True
    associations: bool = True
    view_prefix_filter: str = ''
    view_suffix_filter: str = ''
    insert: bool = True
    views_per_request: int = Field(
            default = 50,
            description="Number of views to ask for per request to the Denodo Platform. This is implemented to avoid handling too many views in a single request that might overload the server."
        )
    incremental: bool = Field(
            default = False,
            description="If set to True, only views that have changed since the last execution are updated in the vector store based on a saved timestamp."
        )
    parallel: bool = Field(
            default = True,
            description="If set to true, vectorization through the embeddings provider and insertion into the vector store will be done in parallel. Denodo Platform requests will remain sequential."
        )

class getMetadataResponse(BaseModel):
    db_schema_json: Dict
    db_schema_text: List[str]
    vdb_list: List[str]
    tag_list: List[str]
    data_usage_errors: List[Dict]
    timings: List[Dict[str, float]]

@router.get(
        '/getMetadata',
        response_class = JSONResponse,
        response_model = getMetadataResponse,
        tags = ['Vector Store'])
@handle_endpoint_error("getMetadata")
async def getMetadata(
    endpoint_request: getMetadataRequest = Query(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    This endpoint retrieves the metadata from a list of VDP databases (separated by commas) and returns it in JSON and natural language format.
    Optionally, if given access to a Denodo-supported vector store, it can also insert the metadata using the embeddings provider of your choice.

    You can use the view_prefix_filter and view_suffix_filter parameters to filter the views that are inserted into the vector store
    from the specified databases/tags.
    For example, if you set view_prefix_filter to "vdp_", only views that start with "vdp_" will be inserted into the vector store.

    To use incremental, please set incremental to True. On first call, it will return all views associated with the specified databases/tags
    and activate tracking of changes. After that, you calling getMetadata with incremental set to True on the same set of databases/tags will only vectorize views
    that have been modified since the last sync.
    """
    try:
        permissions_data = await get_user_permissions(auth=auth, custom_headers=custom_headers)
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during getMetadata: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve permissions: {str(e)}") from e

    if not check_metadata_user_permission(auth, permissions_data):
        logging.warning("[Security] User unauthorized attempt to use getMetadata.")
        raise HTTPException(status_code=403, detail="You do not have authorization to use the vectorization endpoints.")

    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',') if db]
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names.split(',') if tag]
    tags_to_ignore = [tag.strip() for tag in endpoint_request.tags_to_ignore.split(',') if tag]
    vdp_tag_names = [tag for tag in vdp_tag_names if tag not in tags_to_ignore]

    if not vdp_database_names and not vdp_tag_names:
        raise HTTPException(status_code=400, detail="At least one database or tag must be provided")

    if endpoint_request.incremental:
        status_code, response_message = await activate_incremental(auth, custom_headers=custom_headers)
        logging.info(f"Received status code {status_code} and response message {response_message}")

    all_db_schemas = []
    all_db_schema_texts = []
    all_data_usage_errors = []
    all_timings = []

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
            logging.error(f"Resource initialization error: {str(e)}")
            logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    views_by_tag = {}

    if endpoint_request.insert:
        for tag in vdp_tag_names:
            view_ids = await get_by_db_or_tag(
                vector_store=vector_store,
                vdp_database_names=None,
                vdp_tag_names=[tag]
            )

            views_by_tag[tag] = view_ids

    if not endpoint_request.incremental and endpoint_request.insert:
        try:
            await delete_by_db_or_tag(
                vector_store=vector_store,
                sample_data_vector_store=sample_data_vector_store,
                vdp_database_names=vdp_database_names,
                vdp_tag_names=vdp_tag_names,
                delete_conflicting=False
            )

        except Exception as e:
            logging.error(f"Error during metadata deletion: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete metadata: {e}") from e

    try:
        for tag_name in vdp_tag_names:
            try:
                db_schema, db_schema_text, tag_errors, timings = await process_metadata_source(
                    source_type="TAG",
                    source_name=tag_name,
                    request=endpoint_request,
                    auth=auth,
                    custom_headers=custom_headers,
                    vector_store=vector_store,
                    sample_data_vector_store=sample_data_vector_store,
                    tagged_views=views_by_tag.get(tag_name, []),
                    incremental=endpoint_request.incremental,
                    tags_to_ignore=tags_to_ignore
                )

                all_db_schemas.append(db_schema)
                all_db_schema_texts.extend(db_schema_text)
                all_timings.append(timings)

                if tag_errors:
                    all_data_usage_errors.extend(tag_errors)

            except ValueError as ve:
                logging.error(f"Error processing tag: {ve}")
                continue

        for db_name in vdp_database_names:
            try:
                db_schema, db_schema_text, db_errors, timings = await process_metadata_source(
                    source_type="DATABASE",
                    source_name=db_name,
                    request=endpoint_request,
                    auth=auth,
                    custom_headers=custom_headers,
                    vector_store=vector_store,
                    sample_data_vector_store=sample_data_vector_store,
                    incremental=endpoint_request.incremental,
                    tags_to_ignore=tags_to_ignore
                )

                all_db_schemas.append(db_schema)
                all_db_schema_texts.extend(db_schema_text)
                all_timings.append(timings)

                if db_errors:
                    all_data_usage_errors.extend(db_errors)

            except ValueError as ve:
                logging.error(f"Error processing database: {ve}")
                continue

    except asyncio.CancelledError:
        log_message = "The client has disconnected. The request was cancelled before completion."

        if endpoint_request.insert:
            log_message += " It is recommended to synchronize again to ensure no metadata is missing."

        logging.warning(log_message)
        raise

    if not any(all_db_schemas):
        return Response(status_code=204, content=None)

    # Format and return response
    response = format_metadata_response(
        all_db_schemas=all_db_schemas,
        all_db_schema_texts=all_db_schema_texts,
        vdb_database_names=vdp_database_names,
        vdb_tag_names=vdp_tag_names,
        all_data_usage_errors=all_data_usage_errors,
        all_timings=all_timings
    )

    if all_data_usage_errors:
        logging.warning(f"Found {len(all_data_usage_errors)} data usage errors during metadata extraction: {all_data_usage_errors}")

    return JSONResponse(content=jsonable_encoder(response), media_type="application/json")
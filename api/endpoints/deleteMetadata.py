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

from pydantic import BaseModel

from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException

from utils.data_catalog import get_allowed_view_ids, DataCatalogAuthError
from api.utils import state_manager
from api.utils.sdk_utils import (
    handle_endpoint_error, authenticate, delete_by_db_or_tag
)

router = APIRouter()

class deleteMetadataRequest(BaseModel):
    vdp_database_names: str = ''
    vdp_tag_names: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    delete_conflicting: bool = False

class deleteMetadataResponse(BaseModel):
    message: str

@router.delete(
    '/deleteMetadata',
    response_class=JSONResponse,
    response_model=deleteMetadataResponse,
    tags=['Vector Store']
)
@handle_endpoint_error("deleteMetadata")
async def deleteMetadata(endpoint_request: deleteMetadataRequest = Depends(), auth: str = Depends(authenticate)):
    """
    Deletes views from the vector store based on database names or tag names.

    If `delete_conflicting` is set to `False`, only views that satisfy all of the following conditions will be deleted:
    - The associated database is included in the list of databases to delete, or it has not been previously synchronized (view was synchronized through a tag).
    - All active tags are included in the list of tags to delete, or those tags have not been previously synchronized.

    This behavior ensures that only views that unambiguously match the deletion criteria are removed, while preserving any entries that may be linked to other synchronized sources.
    """
    try:
        allowed_view_ids = await get_allowed_view_ids(auth=auth)
        allowed_view_ids = [str(view_id) for view_id in allowed_view_ids]
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during deleteMetadata: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieving allowed view IDs from Denodo Data Catalog failed: {str(e)}") from e

    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',') if db]
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names.split(',') if tag]

    if not vdp_database_names and not vdp_tag_names:
        raise HTTPException(status_code=400, detail="At least one database or tag must be provided for deletion.")

    try:
        vector_store = state_manager.get_vector_store(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model
        )
        sample_data_vector_store = state_manager.get_vector_store(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model,
            index_name="ai_sdk_sample_data"
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error initializing resources: {str(e)}") from e

    try:
        total_deleted_ids = delete_by_db_or_tag(
            vector_store=vector_store,
            sample_data_vector_store=sample_data_vector_store,
            vdp_database_names=vdp_database_names,
            vdp_tag_names=vdp_tag_names,
            delete_conflicting=endpoint_request.delete_conflicting,
            allowed_view_ids=allowed_view_ids
        )

    except Exception as e:
        logging.error(f"Error during metadata deletion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete metadata: {e}")

    if total_deleted_ids == 0:
        return Response(status_code=204, content=None)

    message_suffix_parts = []
    if vdp_database_names:
        db_label = "database" if len(vdp_database_names) == 1 else "databases"
        message_suffix_parts.append(f"{db_label} {', '.join(vdp_database_names)}")

    if vdp_tag_names:
        tag_label = "tag" if len(vdp_tag_names) == 1 else "tags"
        message_suffix_parts.append(f"{tag_label} {', '.join(vdp_tag_names)}")

    message_suffix = " and ".join(message_suffix_parts)
    final_message = f"Metadata associated with {message_suffix} successfully deleted."

    return JSONResponse(
        content=jsonable_encoder(deleteMetadataResponse(message=final_message)),
        media_type="application/json"
    )

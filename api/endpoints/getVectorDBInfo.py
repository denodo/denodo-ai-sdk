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

from pydantic import BaseModel, Field
from typing import Dict

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException

from api.utils import state_manager
from api.utils.sdk_utils import get_user_synced_resources, handle_endpoint_error, check_metadata_user_permission, authenticate
from utils.data_marketplace.connection import get_user_permissions, DataCatalogAuthError
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()

class VectorDBInfoRequest(BaseModel):
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')

class VectorDBInfoResponse(BaseModel):
    synced_resources: Dict = Field(
        default_factory=dict,
        alias="syncedResources",
        description="Dictionary of fully synced resources (databases/tags) with their last sync dates and view counts."
    )
    partial_resources: Dict = Field(
        default_factory=dict,
        alias="partialResources",
        description="Dictionary of partially synced resources (databases/tags) that have some but not all views synced."
    )

    # Allow both the snake_case field name and the camelCase alias to be used,
    # so the response schema documents snake_case while the JSON output uses camelCase
    # to match the existing API contract consumed by the frontend.
    # NOTE: Will be deprecated in Pydantic v3.
    model_config = {"populate_by_name": True}

@router.get(
    '/getVectorDBInfo',
    response_class=JSONResponse,
    response_model=VectorDBInfoResponse,
    tags=['Vector Store']
)
@handle_endpoint_error("getVectorDBInfo")
async def getVectorDBInfo(
    endpoint_request: VectorDBInfoRequest = Depends(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    Gets the synchronized VDBs and tags with their last synchronization date.
    This list is filtered to show only the resources that contain at least one view
    the current user has permissions for.
    """
    try:
        permissions_data = await get_user_permissions(auth=auth, custom_headers=custom_headers)
        views_details = permissions_data.get("viewsPermissions", [])
        allowed_view_ids_str = [str(view["viewId"]) for view in views_details]
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during getVectorDBInfo: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user permissions from Data Marketplace: {str(e)}") from e

    user_sync_permissions = check_metadata_user_permission(auth, permissions_data)

    if not allowed_view_ids_str:
        logging.info("getVectorDBInfo: User has no allowed view IDs.")
        return JSONResponse(content={
            "syncedResources": {},
            "partialResources": {},
            "userSyncPermissions": user_sync_permissions
        }, status_code=200)

    try:
        vector_store = state_manager.get_vector_store(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get vector store from state manager: {e}") from e

    try:
        filtered_synced_resources, filtered_partial_resources = get_user_synced_resources(
            vector_store=vector_store,
            allowed_view_ids_str=allowed_view_ids_str
        )
        return JSONResponse(content={
            "syncedResources": filtered_synced_resources,
            "partialResources": filtered_partial_resources,
            "userSyncPermissions": user_sync_permissions
        }, status_code=200)

    except Exception as e:
        logging.error(f"Error in getVectorDBInfo endpoint: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) from e

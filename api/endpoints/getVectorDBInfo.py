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
from typing import Annotated

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils import state_manager
from api.utils.sdk_utils import get_user_synced_resources, handle_endpoint_error
from utils.data_catalog import get_allowed_view_ids, DataCatalogAuthError

router = APIRouter()
security_basic = HTTPBasic(auto_error=False)
security_bearer = HTTPBearer(auto_error=False)


def authenticate(
        basic_credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)],
        bearer_credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]
):
    """Handles Basic and Bearer authentication."""
    if bearer_credentials is not None:
        return bearer_credentials.credentials
    elif basic_credentials is not None:
        return (basic_credentials.username, basic_credentials.password)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")


@router.get(
    '/getVectorDBInfo',
    response_class=JSONResponse,
    tags=['Vector Store']
)
@handle_endpoint_error("getVectorDBInfo")
async def getVectorDBInfo(auth: str = Depends(authenticate)):
    """
    Gets the synchronized VDBs and tags with their last synchronization date.
    This list is filtered to show only the resources that contain at least one view
    the current user has permissions for.
    """
    try:
        allowed_view_ids = await get_allowed_view_ids(auth=auth)
        allowed_view_ids_str = [str(vid) for vid in allowed_view_ids]
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during getVectorDBInfo: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user permissions from Data Catalog: {str(e)}") from e

    if not allowed_view_ids_str:
        logging.info("getVectorDBInfo: User has no allowed view IDs.")
        return JSONResponse(content={"syncedResources": {}}, status_code=200)

    try:
        vector_store = state_manager.get_vector_store(
            provider=os.getenv('VECTOR_STORE'),
            embeddings_provider=os.getenv('EMBEDDINGS_PROVIDER'),
            embeddings_model=os.getenv('EMBEDDINGS_MODEL')
        )
    except Exception as e:
        logging.error(f"Resource initialization error: {str(e)}")
        logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get vector store from state manager: {e}") from e

    try:
        filtered_resources = get_user_synced_resources(
            vector_store=vector_store,
            allowed_view_ids_str=allowed_view_ids_str
        )
        return JSONResponse(content={"syncedResources": filtered_resources}, status_code=200)

    except Exception as e:
        logging.error(f"Error in getVectorDBInfo endpoint: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) from e
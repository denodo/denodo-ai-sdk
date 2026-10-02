"""
Copyright (c) 2026. DENODO Technologies.
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
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.utils import state_manager
from api.utils.sdk_utils import authenticate, handle_endpoint_error, get_custom_request_headers
from utils.data_marketplace.connection import (
    get_user_permissions_for_vector_store,
    DataCatalogAuthError,
)

router = APIRouter()

class UserPermissionsRequest(BaseModel):
    embeddings_provider: str = os.getenv("EMBEDDINGS_PROVIDER")
    embeddings_model: str = os.getenv("EMBEDDINGS_MODEL")
    vector_store_provider: str = os.getenv("VECTOR_STORE")

class UserPermissionsResponse(BaseModel):
    username: str
    is_admin: bool
    roles: List[str]
    legacy_permissions_endpoint: bool

@router.get(
    "/getUserPermissions", response_class=JSONResponse, response_model=UserPermissionsResponse, tags=["Authentication"]
)
@handle_endpoint_error("getUserPermissions")
async def getUserPermissions(
    endpoint_request: UserPermissionsRequest = Query(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers),
):
    """
    Retrieves the authenticated user's profile, including their roles, global admin status,
    and whether the underlying Data Marketplace API is a legacy version.
    """
    try:
        try:
            vector_store = state_manager.get_vector_store(
                provider=endpoint_request.vector_store_provider,
                embeddings_provider=endpoint_request.embeddings_provider,
                embeddings_model=endpoint_request.embeddings_model,
            )
        except Exception as e:
            logging.error(f"Resource initialization error: {str(e)}")
            logging.error(f"Resource initialization traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to get vector store from state manager: {e}") from e

        permissions_data = await get_user_permissions_for_vector_store(
            auth=auth, vector_store=vector_store, custom_headers=custom_headers
        )

        response_data = {
            "username": permissions_data.get("username", ""),
            "is_admin": permissions_data.get("isAdmin", False),
            "roles": permissions_data.get("roles", []),
            "legacy_permissions_endpoint": permissions_data.get("legacyEndpoint", False),
        }

        return JSONResponse(content=response_data, status_code=200)

    except DataCatalogAuthError as e:
        logging.error(f"Authentication failed during getUserPermissions: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid credentials for Data Marketplace") from e
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get user permissions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get user permissions from Data Marketplace: {str(e)}"
        ) from e

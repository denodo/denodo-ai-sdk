"""
Copyright (c) 2026. DENODO Technologies.
http://www.denodo.com
All rights reserved.

This software is the confidential and proprietary information of DENODO
Technologies ("Confidential Information"). You shall not disclose such
Confidential Information and shall use it only in accordance with the terms
of the license agreement you entered into with DENODO.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.utils.sdk_utils import authenticate, handle_endpoint_error
from utils.data_marketplace.connection import get_user_permissions, DataCatalogAuthError
from api.utils.sdk_utils import get_custom_request_headers

router = APIRouter()


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
    auth: str = Depends(authenticate), custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    Retrieves the authenticated user's profile, including their roles, global admin status,
    and whether the underlying Data Marketplace API is a legacy version.
    """
    try:
        permissions_data = await get_user_permissions(auth=auth, custom_headers=custom_headers)

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

    except Exception as e:
        logging.error(f"Failed to get user permissions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get user permissions from Data Marketplace: {str(e)}"
        ) from e

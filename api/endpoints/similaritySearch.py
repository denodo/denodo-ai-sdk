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
import json
import logging
import traceback

from pydantic import BaseModel
from typing import List, Annotated

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from api.utils import state_manager
from utils.data_catalog import get_allowed_view_ids, DataCatalogAuthError
from api.utils.sdk_utils import filter_non_allowed_associations, handle_endpoint_error

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

class similaritySearchRequest(BaseModel):
    query: str
    vdp_database_names: str = ''
    vdp_tag_names: str = ''
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    n_results: int = Query(
        default = 5,
        ge=1,
    )
    scores: bool = False

class similaritySearchResponse(BaseModel):
    views: List[str]

@router.get(
        '/similaritySearch',
        response_class = JSONResponse,
        response_model = similaritySearchResponse,
        tags = ['Vector Store'])
@handle_endpoint_error("similaritySearch")
async def similaritySearch(endpoint_request: similaritySearchRequest = Depends(), auth: str = Depends(authenticate)):
    """
    This endpoint performs a similarity search on the vector database specified in the request.
    The vector store MUST have been previously populated with the metadata of the views in the vector database
    using getMetadata endpoint.
    """
    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',')] if endpoint_request.vdp_database_names else []
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names.split(',')] if endpoint_request.vdp_tag_names else []

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
        valid_view_ids = await get_allowed_view_ids(auth=auth)
        valid_view_ids = [str(view_id) for view_id in valid_view_ids]
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during similaritySearch: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieving allowed view IDs from Denodo Data Catalog failed: {str(e)}") from e

    search_params = {
        "query": endpoint_request.query,
        "k": endpoint_request.n_results,
        "scores": endpoint_request.scores,
        "database_names": vdp_database_names,
        "tag_names": vdp_tag_names,
        "view_ids": valid_view_ids
    }

    search_results = vector_store.search(**search_params)

    output = {
        "views": [
            {
                "view_name": (result[0] if endpoint_request.scores else result).metadata["view_name"],
                "view_json": (
                    filter_non_allowed_associations(
                        json.loads((result[0] if endpoint_request.scores else result).metadata["view_json"]),
                        valid_view_ids
                    )
                ),
                "view_text": (result[0] if endpoint_request.scores else result).page_content,
                "database_name": (result[0] if endpoint_request.scores else result).metadata["database_name"],
                **{key: (result[0] if endpoint_request.scores else result).metadata[key]
                    for key in (result[0] if endpoint_request.scores else result).metadata
                    if key.startswith('tag_')},
                **({"scores": result[1]} if endpoint_request.scores else {})
            } for result in search_results
        ]
    }

    return JSONResponse(content = jsonable_encoder(output), media_type = "application/json")
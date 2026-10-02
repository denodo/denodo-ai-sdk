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

from pydantic import BaseModel, Field, Field
from typing import List, Dict, Any, Literal

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException, Query

from api.utils import state_manager
from utils.data_marketplace.connection import get_user_permissions_for_vector_store, DataCatalogAuthError
from api.utils.sdk_utils import parse_view_document, handle_endpoint_error, authenticate
from api.utils.sdk_utils import get_custom_request_headers
from api.utils import param_descriptions as desc

router = APIRouter()

class similaritySearchRequest(BaseModel):
    query: str
    vdp_database_names: List[str] = Field(default_factory=list)
    vdp_tag_names: List[str] = Field(default_factory=list)
    filter_logic: Literal["AND", "OR"] = Field(
        default = 'OR',
        description=desc.FILTER_LOGIC
    )
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    n_results: int = Query(
        default = 5,
        ge=1,
    )
    scores: bool = False

class similaritySearchResponse(BaseModel):
    views: List[Dict[str, Any]]

@router.get(
        '/similaritySearch',
        response_class = JSONResponse,
        response_model = similaritySearchResponse,
        tags = ['Vector Store'])
@handle_endpoint_error("similaritySearch")
async def similaritySearch(
    endpoint_request: similaritySearchRequest = Query(),
    auth: str = Depends(authenticate),
    custom_headers: dict = Depends(get_custom_request_headers)
):
    """
    This endpoint performs a similarity search on the vector database specified in the request.
    The vector store MUST have been previously populated with the metadata of the views in the vector database
    using getMetadata endpoint.
    """
    vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names if db.strip()]
    vdp_tag_names = [tag.strip() for tag in endpoint_request.vdp_tag_names if tag.strip()]

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
        permissions_data = await get_user_permissions_for_vector_store(
            auth=auth, vector_store=vector_store, custom_headers=custom_headers
        )
        views_details = permissions_data.get("viewsPermissions", [])

        valid_view_ids = [str(view["viewId"]) for view in views_details]

        security_policies_by_view = {
            str(view["viewId"]): view
            for view in views_details
        }
    except DataCatalogAuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed during similaritySearch: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieving allowed view IDs from Denodo Data Marketplace failed: {str(e)}") from e

    search_params = {
        "query": endpoint_request.query,
        "k": endpoint_request.n_results,
        "scores": endpoint_request.scores,
        "database_names": vdp_database_names,
        "tag_names": vdp_tag_names,
        "view_ids": valid_view_ids,
        "filter_logic": endpoint_request.filter_logic
    }

    search_results = vector_store.search_batched(**search_params)

    output_views = []
    for result in search_results:
        doc = result[0] if endpoint_request.scores else result
        score = result[1] if endpoint_request.scores else None

        view_id = str(doc.metadata.get("view_id", ""))
        security_info = security_policies_by_view.get(view_id, {})

        view_dict = parse_view_document(
            doc=doc,
            filter_associations=True, 
            valid_view_ids=valid_view_ids,
            security_info=security_info
        )

        view_dict["database_name"] = doc.metadata.get("database_name", "")

        view_dict.update({key: val for key, val in doc.metadata.items() if key.startswith('tag_')})

        if endpoint_request.scores:
            view_dict["scores"] = score

        output_views.append(view_dict)

    output = {
        "views": output_views
    }

    return JSONResponse(content = jsonable_encoder(output), media_type = "application/json")

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
import json
import traceback

from pydantic import BaseModel
from typing import List, Annotated

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPAuthorizationCredentials, HTTPBearer

from utils.data_catalog import get_allowed_view_ids
from utils.uniformVectorStore import UniformVectorStore
from api.utils.sdk_utils import filter_non_allowed_associations

router = APIRouter()
security_basic = HTTPBasic()
security_bearer = HTTPBearer()

# Get the authentication type from environment
AUTH_TYPE = os.getenv("DATA_CATALOG_AUTH_TYPE", "http_basic")

if AUTH_TYPE.lower() == "http_basic":
    def authenticate(credentials: Annotated[HTTPBasicCredentials, Depends(security_basic)]):
        return (credentials.username, credentials.password)
else:
    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_bearer)]):
        return credentials.credentials

class similaritySearchRequest(BaseModel):
    query: str
    vdp_database_names: str = os.getenv('VDB_NAMES')
    embeddings_provider: str = os.getenv('EMBEDDINGS_PROVIDER')
    embeddings_model: str = os.getenv('EMBEDDINGS_MODEL')
    vector_store_provider: str = os.getenv('VECTOR_STORE')
    n_results: int = 5
    scores: bool = False

class similaritySearchResponse(BaseModel):
    views: List[str]

@router.get("/similaritySearch", response_class = JSONResponse, response_model = similaritySearchResponse)
def similaritySearch(endpoint_request: similaritySearchRequest = Depends(), auth: str = Depends(authenticate)):
    """
    This endpoint performs a similarity search on the vector database specified in the request.
    The vector store MUST have been previously populated with the metadata of the views in the vector database
    using getMetadata endpoint.
    """
    try:
        # Right now, not all Denodo instances have permissions implemented. This should be deleted in the future.
        USER_PERMISSIONS = int(os.getenv("USER_PERMISSIONS", 0))

        vdp_database_names = [db.strip() for db in endpoint_request.vdp_database_names.split(',')]
        vector_store = UniformVectorStore(
            provider=endpoint_request.vector_store_provider,
            embeddings_provider=endpoint_request.embeddings_provider,
            embeddings_model=endpoint_request.embeddings_model,
        )

        search_params = {
            "query": endpoint_request.query,
            "k": endpoint_request.n_results,
            "scores": endpoint_request.scores,
            "database_names": vdp_database_names
        }

        if USER_PERMISSIONS:
            valid_view_ids = get_allowed_view_ids(auth = auth, database_names = vdp_database_names)
            valid_view_ids = [str(view_id) for view_id in valid_view_ids]
            search_params["view_ids"] = valid_view_ids

        search_results = vector_store.search(**search_params)

        output = {
            "views": [
                {
                    "view_name": (result[0] if endpoint_request.scores else result).metadata["view_name"],
                    "view_json": (
                        filter_non_allowed_associations(
                            json.loads((result[0] if endpoint_request.scores else result).metadata["view_json"]),
                            valid_view_ids
                        ) if USER_PERMISSIONS else 
                        json.loads((result[0] if endpoint_request.scores else result).metadata["view_json"])
                    ),
                    "view_text": (result[0] if endpoint_request.scores else result).page_content,
                    "database_name": (result[0] if endpoint_request.scores else result).metadata["database_name"],
                    **({"scores": result[1]} if endpoint_request.scores else {})
                } for result in search_results
            ]
        }

        return JSONResponse(content = jsonable_encoder(output), media_type = "application/json")
    except Exception as e:

        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }

        raise HTTPException(status_code=500, detail=error_details)

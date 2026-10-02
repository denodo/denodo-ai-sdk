"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

DELETE_CONFLICTING = (
    "If checked, entries linked to other synchronized sources will also be deleted. "
    "For example, if you synced both 'example_tag' and 'example_database', and you delete only 'example_tag', any views present in both will also be deleted."
)

EMBEDDINGS_TOKEN_LIMIT = (
    "Maximum input tokens for the embedding model. Use 0 to disable chunking. "  # noqa: S105
    "If enabled, the value must be 1000 or greater."
)

INCREMENTAL = (
    "If set to True, only views that have changed since the last execution are updated in the vector store "
    "based on a saved timestamp."
)

PARALLEL = (
    "If set to true, vectorization through the embeddings provider and insertion into the vector store will "
    "be done in parallel. Denodo Platform requests will remain sequential."
)

TAGS_TO_IGNORE = (
    "A list of tags to explicitly ignore. "
    "Views associated with these tags will be excluded from the final results."
)

VIEWS_PER_REQUEST = (
    "Number of views to ask for per request to the Denodo Platform. This is implemented to avoid handling "
    "too many views in a single request that might overload the server."
)

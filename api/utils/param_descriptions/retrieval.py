"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

ALLOW_EXTERNAL_ASSOCIATIONS = (
    "If False, views from associations will NOT be considered if they don't belong to the "
    "VDBs/Tags specified in vdp_database_names and vdp_tag_names. If no VDBs/Tags specified, "
    "all views from associations will be considered."
)

USE_VIEWS = (
    "Please specify a list of views you want the LLM to take into consideration when answering the question. "
    "Expected format is a list of strings: ['database.view_name', 'database.view_name2']"
)

EXPAND_SET_VIEWS = (
    "If set to true, the LLM will search for relevant views in the vector store. "
    "If set to false, the LLM will not search in the vector store and will only access those specified in use_views"
)

VECTOR_SEARCH_K = "Number of results to return from the similarity search in the vector store."

VECTOR_SEARCH_SAMPLE_DATA_K = "Number of similar sample data rows to return for the given question."

VECTOR_SEARCH_TOTAL_LIMIT = (
    "Maximum number of views to consider in total, including associations of the initial vector_search_k results."
)

VECTOR_SEARCH_COLUMN_DESCRIPTION_CHAR_LIMIT = (
    "Maximum characters of column descriptions used when filtering how many views to keep. "
    "Not applied during vector search or VQL generation (those use full descriptions). "
    "Refer to the docs for when this trimming is applied."
)

VECTOR_SEARCH_TABLE_DESCRIPTION_CHAR_LIMIT = (
    "Maximum characters of table descriptions used when filtering how many views to keep. "
    "Not applied during vector search or VQL generation (those use full descriptions). "
    "Refer to the docs for when this trimming is applied."
)

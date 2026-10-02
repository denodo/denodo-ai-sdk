"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

FILTER_LOGIC = (
    "How to combine vdp_database_names and vdp_tag_names when both are provided. "
    "OR (default) includes views matching any listed database or tag. "
    "AND includes only views that belong to one of the listed databases and one of the listed tags. "
    "Multiple databases or multiple tags are still combined with OR within that category."
)

VDP_DATABASE_NAMES = (
    "A list of databases to reduce the scope of the question to. "
    "If empty, all databases in the vector DB the user has permissions to will be considered."
)

VDP_TAG_NAMES = (
    "A list of tags to reduce the scope of the question to. "
    "If empty, all tags in the vector DB the user has permissions to will be considered."
)

VDP_DATABASE_NAMES_METADATA = (
    "A list of databases to retrieve metadata from."
)

VDP_TAG_NAMES_METADATA = (
    "A list of tags to retrieve metadata from."
)

VDP_DATABASE_NAMES_DELETE = (
    "A list of databases to delete from the vector store."
)

VDP_TAG_NAMES_DELETE = (
    "A list of tags to delete from the vector store."
)


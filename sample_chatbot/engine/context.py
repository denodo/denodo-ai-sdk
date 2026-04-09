"""
Contains the UserContext dataclass for passing runtime context to tools,
and TOOL_DEFINITIONS for frontend tool configuration.
"""

from typing import Optional
from dataclasses import dataclass
@dataclass
class UserContext:
    api_host: str
    username: str
    password: str
    custom_instructions: str
    verify_ssl: bool
    ai_sdk_params: dict
    vdp_database_names: str = ""
    vdp_tag_names: str = ""
    vector_store: object = None
    active_csv_sources: list = Optional[list]  # List of active CSV source names to filter knowledge queries

# Tool definitions for frontend configuration
TOOL_DEFINITIONS = {
    "data_query": {
        "pretty_name": "Data Query",
        "aliases": ["@data_query", "@sql", "@data"],
        "optional": False,
    },
    "deep_query": {
        "pretty_name": "Deep Query",
        "aliases": ["@deep_query", "@deepquery"],
        "optional": True,
    },
    "metadata_query": {
        "pretty_name": "Metadata Query",
        "aliases": ["@metadata_query", "@metadata", "@schema"],
        "optional": False,
    },
    "knowledge_query": {
        "pretty_name": "Knowledge Base Query",
        "aliases": ["@knowledge_query", "@kb", "@knowledge"],
        "optional": True,
    },
}
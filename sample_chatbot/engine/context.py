"""
Contains the UserContext dataclass for passing runtime context to tools,
and TOOL_DEFINITIONS for frontend tool configuration (aliases, tool_public_text_key for tool args, etc.).
"""

from dataclasses import dataclass, field
@dataclass
class UserContext:
    api_host: str
    username: str
    password: str
    ai_sdk_custom_instructions: str
    verify_ssl: bool
    ai_sdk_params: dict
    timeout: int = 1200
    vdp_database_names: str = ""
    vdp_tag_names: str = ""
    vector_store: object = None
    active_csv_sources: list | None = None  # List of active CSV source names to filter knowledge queries
    kb_collections: dict = field(default_factory=dict)  # name -> description for the user's active collections
    can_manage_skills: bool = False  # Whether the user may create/edit skills
    agent_id: str = "global"  # Agent this engine serves
    allowed_system_skills: list | None = None  # Agent-declared skills (None = all system skills apply)
    disabled_skills: object = None  # Skills force-deactivated by feature flags (e.g. 'deepquery')
    cancel_event: object = None  # threading.Event set when the user cancels the query; aborts in-flight AI SDK requests

# Tool definitions for frontend configuration
TOOL_DEFINITIONS = {
    "data_agent": {
        "pretty_name": "Data Agent",
        "aliases": ["@data_agent", "@sql", "@data"],
        "optional": False,
        "tool_public_text_key": "request",
    },
    "deep_query": {
        "pretty_name": "Deep Query",
        "aliases": ["@deep_query", "@deepquery"],
        "optional": True,
        "tool_public_text_key": "analysis_request",
    },
    "metadata_search": {
        "pretty_name": "Metadata Search",
        "aliases": ["@metadata_search", "@metadata", "@schema"],
        "optional": False,
        "tool_public_text_key": "search_query",
    },
    "knowledge_query": {
        "pretty_name": "Knowledge Base Query",
        "aliases": ["@knowledge_query", "@kb", "@knowledge"],
        "optional": True,
        "tool_public_text_key": "search_query",
    },
    "read_skill": {
        "pretty_name": "Read Skill",
        "aliases": ["@read_skill"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
    "read_skill_reference": {
        "pretty_name": "Read Skill Reference",
        "aliases": ["@read_skill_reference"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
    "edit_skill": {
        "pretty_name": "Edit Skill",
        "aliases": ["@edit_skill"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
    "edit_skill_reference": {
        "pretty_name": "Edit Skill Reference",
        "aliases": ["@edit_skill_reference"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
    "create_skill": {
        "pretty_name": "Create Skill",
        "aliases": ["@create_skill"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
    "create_skill_reference": {
        "pretty_name": "Create Skill Reference",
        "aliases": ["@create_skill_reference"],
        "optional": True,
        "tool_public_text_key": "skill_name",
    },
}
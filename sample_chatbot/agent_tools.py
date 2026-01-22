"""
Chatbot agent tools module.

This module exposes the tools configured in chatbot_tools.py to the chatbot agent.
This separations allows control over what arguments the agent can see and use.
"""

import logging

from utils import denodo_tools
from dataclasses import dataclass
from sample_chatbot import chatbot_tools
from langchain.tools import ToolRuntime, tool
from utils.denodo_tools import create_basic_auth_header, format_data_query_output, format_metadata_query_output

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

TOOL_DEFINITIONS = {
    "data_query": {
        "pretty_name": "Data Query",
        "aliases": ["@data_query", "@sql", "@data"],
        "optional": False,
    },
    "deep_query": {
        "pretty_name": "DeepQuery",
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

@tool(response_format="content_and_artifact")
def data_query(
    runtime: ToolRuntime[UserContext],
    natural_language_query: str,
    plot: int = 0,
    plot_details: str = "",
):
    """Query the Denodo Platform (which contains the user's data) in natural language.

    Args:
        natural_language_query: Natural language query to search for the data in the user's Denodo instance. For example, 'number of total customers'.
        plot: Whether to plot the data. 1 for yes, 0 for no.
        plot_details: Any extra details of the graph to generate. For example, 'bar chart of the number of customers by country'.
    """

    # UI-level filters coming from the question form (set in ai_sdk_params)
    if runtime.context.vdp_database_names:
        logging.info(f"Received UI filters: vdp_database_names={runtime.context.vdp_database_names}")
    if runtime.context.vdp_tag_names:
        logging.info(f"Received UI filters: vdp_tag_names={runtime.context.vdp_tag_names}")

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)

    response = denodo_tools.data_query(
        natural_language_query=natural_language_query,
        api_host=runtime.context.api_host,
        auth=auth,
        vdp_database_names=runtime.context.vdp_database_names,
        vdp_tag_names=runtime.context.vdp_tag_names,
        plot=plot,
        plot_details=plot_details,
        custom_instructions=runtime.context.custom_instructions,
        verify_ssl=runtime.context.verify_ssl,
        **(runtime.context.ai_sdk_params or {}),
    )

    return format_data_query_output(response)


@tool(response_format="content_and_artifact")
def deep_query(
    runtime: ToolRuntime[UserContext],
    analysis_request: str,
):
    """Request an advanced analysis request over the user's data to the DeepQuery agent.

    Args:
        analysis_request: Detailed analysis request to perform.
    """

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)

    response = denodo_tools.deep_query(
        analysis_request=analysis_request,
        api_host=runtime.context.api_host,
        auth=auth,
        verify_ssl=runtime.context.verify_ssl,
        **(runtime.context.ai_sdk_params or {}),
    )

    content = response.get("answer", "DeepQuery analysis failed, please check the additional information modal.")
    return (content, response)

@tool(response_format="content_and_artifact")
def metadata_query(
    runtime: ToolRuntime[UserContext],
    search_query: str,
    n_results: int = 5,
):
    """This tool can perform a similarity search in the database and return the schema of the n_results (stick to the default of 5 if not specified) most similar views.
        For example, it can be helpful to answer questions like:
        - What views do we have related to X topic.
        - What is the primary key of this table.
        - What associations does this view have.

    Args:
        search_query: Natural language query to search for the metadata of the views in the user's Denodo instance. For example, 'views related to loans'.
        n_results: Maximum number of results to return.
    """

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)

    response = denodo_tools.metadata_query(
        search_query=search_query,
        api_host=runtime.context.api_host,
        auth=auth,
        vdp_database_names=runtime.context.vdp_database_names,
        vdp_tag_names=runtime.context.vdp_tag_names,
        n_results=n_results,
        verify_ssl=runtime.context.verify_ssl,
    )

    return format_metadata_query_output(response)


@tool(response_format="content_and_artifact")
def knowledge_query(runtime: ToolRuntime[UserContext], search_query: str, k: int = 5):
    """Search the user's documents in theknowledge base, stored in a vectorDB, with similarity search. By default, search the top 5 similar results.

    Args:
        search_query: Natural language query to search for the knowledge base.
        k: Maximum number of results to return.
    """
    if not runtime.context.vector_store:
        return "Knowledge base is not configured."

    response = chatbot_tools.knowledge_query(
        search_query=search_query,
        vector_store=runtime.context.vector_store,
        k=k,
    )

    if 'error' in response:
        return (f"Knowledge query failed: {response.get('error', 'Unknown error')}", response)

    content = response.get("answer", "Knowledge query failed, please check the additional information modal.")
    return (content, response)
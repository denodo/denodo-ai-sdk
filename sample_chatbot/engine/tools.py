"""
Contains LangChain tool definitions that the chatbot agent can use
to query data, metadata, and knowledge bases.
"""

import logging
import traceback

from utils import denodo_tools
from langchain.tools import ToolRuntime, tool
from sample_chatbot.engine.context import UserContext
from utils.denodo_tools import create_basic_auth_header, format_data_agent_output, format_metadata_search_output

# =============================================================================
# Knowledge Query Implementation
# =============================================================================

def _knowledge_query_impl(search_query, vector_store, collection, k=5, document_size_limit_chars=10000):
    """
    Search a single collection inside the knowledge base.

    Returns a dict carrying the rendered answer plus collection metadata so the
    UI can show provenance.
    """
    try:
        result = vector_store.search(
            query=search_query,
            k=k,
            scores=False,
            database_names=[collection],
        )

        blocks = [
            f"<result_{i + 1}>\n{doc.page_content[:document_size_limit_chars]}\n</result_{i + 1}>"
            for i, doc in enumerate(result)
        ]
        return {"answer": "\n\n".join(blocks)}
    except Exception as e:
        return {
            "error": f"Knowledge query failed: {e}",
            "traceback": traceback.format_exc(),
        }

# =============================================================================
# LangChain Tool Definitions
# Response format must always be content_and_artifact
# =============================================================================

@tool(response_format="content_and_artifact")
def data_agent(
    runtime: ToolRuntime[UserContext],
    request: str,
    limit: int = 0,
    plot: int = 0,
    plot_details: str = "",
):
    """Communicates with the data agent to generate and execute a single VQL query.
    The data agent does not have memory of previous requests or conversations. Every individual request to the data_agent must be self-contained, meaning it must not rely on the agent having recollection of previous requests.

    Args:
        request: Request to generate a single VQL query from and return the VQL query, its explanation and the execution result. For example, 'count the number of unique customers in the organization.customers view'.
        limit: Maximum number of rows to return. If omitted, it defaults to the data_agent's limit configured for this session.
        plot: Whether to generate and also return a plot of the data. 1 for yes, 0 for no.
        plot_details: Any extra details of the graph to generate. For example, 'bar chart of the number of customers by country in organization.customers view'.
    """

    # UI-level filters coming from the QuestionForm (set in ai_sdk_params)
    if runtime.context.vdp_database_names:
        logging.info(f"Received UI filters: vdp_database_names={runtime.context.vdp_database_names}")
    if runtime.context.vdp_tag_names:
        logging.info(f"Received UI filters: vdp_tag_names={runtime.context.vdp_tag_names}")

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)
    default_limit = (runtime.context.ai_sdk_params or {}).get("vql_execute_rows_limit")
    effective_limit = default_limit if limit in (None, 0) else limit

    response = denodo_tools.data_agent(
        natural_language_query=request,
        api_host=runtime.context.api_host,
        auth=auth,
        vdp_database_names=runtime.context.vdp_database_names,
        vdp_tag_names=runtime.context.vdp_tag_names,
        plot=plot,
        plot_details=plot_details,
        limit=effective_limit,
        custom_instructions=runtime.context.ai_sdk_custom_instructions,
        verify_ssl=runtime.context.verify_ssl,
        timeout=runtime.context.timeout,
        **(runtime.context.ai_sdk_params or {}),
    )

    return format_data_agent_output(response)

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
        timeout=runtime.context.timeout,
        **(runtime.context.ai_sdk_params or {}),
    )

    if "answer" in response:
        content = response["answer"]
    else:
        error_detail = response.get("detail") or response.get("error")
        content = str(error_detail) if error_detail else "DeepQuery analysis failed, please check the additional information modal."

    return (content, response)

@tool(response_format="content_and_artifact")
def metadata_search(
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

    response = denodo_tools.metadata_search(
        search_query=search_query,
        api_host=runtime.context.api_host,
        auth=auth,
        vdp_database_names=runtime.context.vdp_database_names,
        vdp_tag_names=runtime.context.vdp_tag_names,
        n_results=n_results,
        verify_ssl=runtime.context.verify_ssl,
        timeout=runtime.context.timeout,
    )

    return format_metadata_search_output(response)

@tool(response_format="content_and_artifact")
def knowledge_query(runtime: ToolRuntime[UserContext], search_query: str, collection: str, k: int = 5):
    """Search a single collection in the user's knowledge base with similarity search.

    Args:
        search_query: Natural language query to search for in the collection.
        collection: REQUIRED. The exact name of the collection to search, taken from the
            list shown in extra_tools_guidance. To cover several collections, call this
            tool once per collection.
        k: Maximum number of results to return (default 5).
    """
    if not runtime.context.vector_store:
        return (
            "Knowledge base is not configured.",
            {"error": "knowledge_base_not_configured"},
        )

    active = runtime.context.active_csv_sources or []
    requested = (collection or "").strip()

    if not requested:
        return (
            "The `collection` argument is required. Pick one of the active collections: "
            f"{', '.join(active) if active else '(none active)'}.",
            {"error": "collection_required", "active_collections": active},
        )

    if not active:
        # No subscribed collections means the user has nothing to search. We
        # MUST refuse — otherwise the LLM could be coaxed into naming someone
        # else's private collection and reading it through the shared store.
        return (
            "You have no collections active for this chatbot. Open the Knowledge "
            "Base Manager to activate one before asking a knowledge-base question.",
            {"error": "no_collections_active", "active_collections": []},
        )

    if requested not in active:
        return (
            f"Collection '{requested}' is not in your active set. "
            f"Active collections: {', '.join(active)}.",
            {"error": "collection_not_active", "active_collections": active},
        )

    collection_description = (runtime.context.kb_collections or {}).get(requested, "")

    response = _knowledge_query_impl(
        search_query=search_query,
        vector_store=runtime.context.vector_store,
        collection=requested,
        k=k,
    )
    response["collection_name"] = requested
    response["collection_description"] = collection_description

    if 'error' in response:
        return (f"Knowledge query failed: {response.get('error', 'Unknown error')}", response)

    content = response.get("answer", "Knowledge query failed, please check the additional information modal.")
    return (content, response)

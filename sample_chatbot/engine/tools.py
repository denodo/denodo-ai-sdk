"""
Contains LangChain tool definitions that the chatbot agent can use
to query data, metadata, and knowledge bases.
"""

import logging
import traceback

from utils import denodo_tools
from langchain.tools import ToolRuntime, tool
from sample_chatbot.engine import skills
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
        cancel_event=runtime.context.cancel_event,
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
        cancel_event=runtime.context.cancel_event,
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
        cancel_event=runtime.context.cancel_event,
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

# =============================================================================
# Skill Tools
# Skills are reusable guidance the agent reads on demand. System skills live
# on disk and are shared by everyone; personal skills live in the database and
# belong to a single user. Reading and personal skill management are open to
# all users; managing SYSTEM skills requires can_manage_skills.
# =============================================================================

_SKILL_MANAGEMENT_DENIED = (
    "You are not authorized to edit system skills. Only administrators "
    "(or explicitly allowed users/roles) can manage system skills."
)

def _available_skill_or_error(context, skill_name):
    """Return an error message unless skill_name is active in the user's current context.

    Skills that do not apply here — inactive for this user/agent, not declared
    by the agent, or force-disabled by feature flags (e.g. 'deepquery' when
    DeepQuery is off) — must not be readable from the chat, so the agent never
    follows guidance for features it cannot use. Resolved live so skills
    created or activated during the conversation are picked up.
    """
    available = skills.active_skills_for_user(
        context.username,
        context.agent_id,
        context.allowed_system_skills,
        context.disabled_skills,
    )
    if skill_name not in available:
        return (
            f"Skill '{skill_name}' is not available in this context. "
            f"You can only read the skills listed in your system prompt."
        )
    return None

@tool(response_format="content_and_artifact")
def read_skill(runtime: ToolRuntime[UserContext], skill_name: str):
    """Read the full instructions (SKILL.md) of a skill, so you can follow its guidance.

    Read the relevant skill BEFORE acting on a task it covers. The system prompt lists
    the available skill names and descriptions.

    Args:
        skill_name: The name of the skill to read. For example, 'deepquery'.
    """
    try:
        error = _available_skill_or_error(runtime.context, skill_name)
        if error:
            return (error, {"error": error, "skill": skill_name})
        content = skills.read_skill_for_user(runtime.context.username, skill_name)
        return (content, {"skill": skill_name})
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name})

@tool(response_format="content_and_artifact")
def read_skill_reference(runtime: ToolRuntime[UserContext], skill_name: str, reference_name: str):
    """Read one of a skill's reference documents for deeper detail on a sub-topic.

    The available reference names for each skill are listed next to the skill in the
    system prompt.

    Args:
        skill_name: The name of the skill. For example, 'deepquery'.
        reference_name: The name of the reference document (without extension). For example, 'interpret_results'.
    """
    try:
        error = _available_skill_or_error(runtime.context, skill_name)
        if error:
            return (error, {"error": error, "skill": skill_name, "reference": reference_name})
        content = skills.read_skill_reference(skill_name, reference_name)
        return (content, {"skill": skill_name, "reference": reference_name})
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name, "reference": reference_name})

@tool(response_format="content_and_artifact")
def edit_skill(runtime: ToolRuntime[UserContext], skill_name: str, text_to_search: str, text_to_replace: str):
    """Edit a skill by replacing text. Personal skills are always editable by their
    owner; editing shared SYSTEM skills requires skill-management permission.

    IMPORTANT: This replaces ALL occurrences of text_to_search with text_to_replace.
    Make text_to_search specific enough to match exactly what you intend to change
    (including whitespace).

    Args:
        skill_name: The name of the skill to edit. For example, 'deepquery'.
        text_to_search: The exact text to find. All occurrences are replaced.
        text_to_replace: The text to replace it with.
    """
    username = runtime.context.username
    try:
        try:
            count = skills.edit_personal_skill(username, skill_name, text_to_search, text_to_replace)
            scope = "personal"
        except skills.PersonalSkillNotFoundError:
            # Not one of the user's personal skills: fall back to system skills.
            if not runtime.context.can_manage_skills:
                return (_SKILL_MANAGEMENT_DENIED, {"error": "unauthorized", "skill": skill_name})
            count = skills.edit_skill(skill_name, text_to_search, text_to_replace)
            scope = "system"
        return (
            f"Replaced {count} occurrence(s) in {scope} skill '{skill_name}'.",
            {"skill": skill_name, "scope": scope, "replacements": count},
        )
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name})

@tool(response_format="content_and_artifact")
def edit_skill_reference(runtime: ToolRuntime[UserContext], skill_name: str, reference_name: str, text_to_search: str, text_to_replace: str):
    """Edit a skill reference document by replacing text. Requires skill-management permission.

    IMPORTANT: This replaces ALL occurrences of text_to_search with text_to_replace.
    Make text_to_search specific enough to match exactly what you intend to change
    (including whitespace).

    Args:
        skill_name: The name of the skill. For example, 'deepquery'.
        reference_name: The name of the reference document (without extension). For example, 'interpret_results'.
        text_to_search: The exact text to find. All occurrences are replaced.
        text_to_replace: The text to replace it with.
    """
    if not runtime.context.can_manage_skills:
        return (_SKILL_MANAGEMENT_DENIED, {"error": "unauthorized", "skill": skill_name})
    try:
        count = skills.edit_skill_reference(skill_name, reference_name, text_to_search, text_to_replace)
        return (
            f"Replaced {count} occurrence(s) in reference '{reference_name}' of skill '{skill_name}'.",
            {"skill": skill_name, "reference": reference_name, "replacements": count},
        )
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name, "reference": reference_name})

@tool(response_format="content_and_artifact")
def create_skill(runtime: ToolRuntime[UserContext], skill_name: str, content: str):
    """Create a brand new PERSONAL skill for this user, only visible to them.

    The content must be the full markdown body of the skill, starting with a
    YAML frontmatter block containing a 'name' and a 'description'.
    Name: max 64 characters, lowercase letters/numbers/hyphens only, must not
    start or end with a hyphen. Description: non-empty, max 1024 characters.

    Args:
        skill_name: The name of the new skill (must match the frontmatter name). For example, 'deepquery-usage-2'.
        content: The full SKILL.md content for the new skill.
    """
    try:
        skills.create_personal_skill(runtime.context.username, skill_name, content)
        return (
            f"Created personal skill '{skill_name}'.",
            {"skill": skill_name, "scope": "personal", "created": True},
        )
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name})

@tool(response_format="content_and_artifact")
def create_skill_reference(runtime: ToolRuntime[UserContext], skill_name: str, reference_name: str, content: str):
    """Create a new reference document inside an existing skill. Requires skill-management permission.

    Args:
        skill_name: The name of the existing skill the reference belongs to. For example, 'deepquery'.
        reference_name: The name of the new reference document (without extension; same naming rules as skills). For example, 'interpret-results'.
        content: The full markdown content for the new reference document.
    """
    if not runtime.context.can_manage_skills:
        return (_SKILL_MANAGEMENT_DENIED, {"error": "unauthorized", "skill": skill_name})
    try:
        skills.create_skill_reference(skill_name, reference_name, content)
        return (
            f"Created reference '{reference_name}' in skill '{skill_name}'.",
            {"skill": skill_name, "reference": reference_name, "created": True},
        )
    except skills.SkillError as e:
        return (str(e), {"error": str(e), "skill": skill_name, "reference": reference_name})

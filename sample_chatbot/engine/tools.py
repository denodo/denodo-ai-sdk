"""
Contains LangChain tool definitions that the chatbot agent can use
to query data, metadata, and knowledge bases.
"""

import logging
import traceback

from utils import denodo_tools
from langchain.tools import ToolRuntime, tool
from sample_chatbot.engine import memory
from sample_chatbot.engine import skills
from sample_chatbot.engine.context import UserContext
from sample_chatbot.services.report_jobs import ReportJobContext, report_job_manager
from utils.denodo_tools import create_basic_auth_header, format_generate_vql_output, format_execute_vql_output, format_generate_graph_output, format_metadata_search_output

def _inline_graph_reference(tool_call_id):
    if not tool_call_id:
        return ""
    return f"\n\nTo show this graph in your answer, paste this markdown code block exactly where the chart should appear:\n```graph\n{tool_call_id}\n```"

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
def generate_vql(
    runtime: ToolRuntime[UserContext],
    request: str,
    limit: int = 0,
    view_names: list[str] | None = None,
):
    """Takes a precise natural language request, generates a single valid VQL query from it and executes it, returning the query execution result.

    Limitations:
    - This tool cannot handle multi-step workflows. (i.e. do this first, then do that. if this fails, then do that, etc)
    - This tool does not have memory of previous requests or conversations. Every individual request to this tool must be self-contained, meaning it must not rely on recollection of previous requests.

    Args:
        request: The natural language request to generate a single VQL query from. For example, "Generate a VQL query to count the number of loan_id in the view org.loan_status where loan_status is 'active' and date_created is after or equal to 2026-01-01".
        limit: Maximum number of rows to return. If omitted, it defaults to the generate_vql limit configured for this session.
        view_names: Optional list of views (format: database.view_name) to be used in the VQL query, for example ['organization.loans', 'database.loan1']. If you're certain about the views you want the VQL to use, setting this value will speed up the VQL generation process because it won't have to look for relevant views in the database.
    """

    if runtime.context.vdp_database_names:
        logging.info(f"Received UI filters: vdp_database_names={runtime.context.vdp_database_names}")
    if runtime.context.vdp_tag_names:
        logging.info(f"Received UI filters: vdp_tag_names={runtime.context.vdp_tag_names}")

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)
    default_limit = (runtime.context.ai_sdk_params or {}).get("vql_execute_rows_limit")
    effective_limit = default_limit if limit in (None, 0) else limit

    extra_params = dict(runtime.context.ai_sdk_params or {})
    extra_params.pop("request", None)
    extra_params.pop("view_names", None)
    extra_params.pop("filter_logic", None)

    response = denodo_tools.generate_vql(
        natural_language_query=request,
        api_host=runtime.context.api_host,
        auth=auth,
        vdp_database_names=runtime.context.vdp_database_names,
        vdp_tag_names=runtime.context.vdp_tag_names,
        limit=effective_limit,
        custom_instructions=runtime.context.ai_sdk_custom_instructions,
        view_names=view_names or [],
        verify_ssl=runtime.context.verify_ssl,
        timeout=runtime.context.timeout,
        cancel_event=runtime.context.cancel_event,
        **extra_params,
    )

    return format_generate_vql_output(response)

@tool(response_format="content_and_artifact")
def execute_vql(
    runtime: ToolRuntime[UserContext],
    vql: str,
    limit: int = 0,
):
    """Tool to execute a VQL query. Execute only:
    - A previously generated VQL query by the generate_vql tool
    - A small edit to a previously generated VQL by the generate_vql tool (for example changing a filter, ORDER BY or LIMIT)
    - A exploratory query to explore the data model and understand the views available in Denodo and their schema. For example, 'SELECT DISTINCT example_field FROM "database"."view_name"'.

    Args:
        vql: The VQL query to execute.
        limit: Maximum number of rows to return. If omitted, it defaults to the session limit.
    """

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)
    default_limit = (runtime.context.ai_sdk_params or {}).get("vql_execute_rows_limit")
    effective_limit = default_limit if limit in (None, 0) else limit

    response = denodo_tools.execute_vql(
        vql=vql,
        api_host=runtime.context.api_host,
        auth=auth,
        limit=effective_limit,
        verify_ssl=runtime.context.verify_ssl,
        timeout=runtime.context.timeout,
        cancel_event=runtime.context.cancel_event,
    )

    return format_execute_vql_output(response)

@tool(response_format="content_and_artifact")
def generate_graph(
    runtime: ToolRuntime[UserContext],
    vql: str,
    plot_details: str,
    limit: int = 0,
):
    """Tool to generate a graph from a VQL query. The VQL query used as input must have been previously validated to work. Do not submit unverified VQL queries to this tool.
    Use plot_details to own the graph generation process. Be detailed in your requirements, for example:

    Chart requirements:
        Graph type: Bar chart
        X-axis: Loan
        Y-axis: Loan Amount
        Bars colored green (#2ca02c)
        Include horizontal gridlines on the y-axis
        Remove top and right spines
        Title: 'Top 5 Loans by Loan Amount (2024)'

    Args:
        vql: The VQL query whose result should be plotted. Must have been previously validated to work.
        plot_details: Very detailed description of the graph to generate. For example, 'bar chart of the number of customers by country, with x-axis as country and y-axis as number of customers, and title as "Number of customers by country"'.
        limit: Maximum number of rows to execute and plot. If omitted, it defaults to the session limit.
    """

    auth = create_basic_auth_header(runtime.context.username, runtime.context.password)
    default_limit = (runtime.context.ai_sdk_params or {}).get("vql_execute_rows_limit")
    effective_limit = default_limit if limit in (None, 0) else limit

    extra_params = dict(runtime.context.ai_sdk_params or {})
    extra_params.pop("vql", None)
    extra_params.pop("plot_details", None)
    extra_params.pop("limit", None)

    response = denodo_tools.generate_graph(
        vql=vql,
        api_host=runtime.context.api_host,
        auth=auth,
        plot_details=plot_details,
        limit=effective_limit,
        verify_ssl=runtime.context.verify_ssl,
        timeout=runtime.context.timeout,
        cancel_event=runtime.context.cancel_event,
        **extra_params,
    )

    content, artifact = format_generate_graph_output(response)
    raw_graph = artifact.get("raw_graph", "")
    if raw_graph.startswith("data:image/svg+xml;base64,"):
        content += _inline_graph_reference(runtime.tool_call_id)
    return content, artifact

@tool(response_format="content_and_artifact")
def deep_query(
    runtime: ToolRuntime[UserContext],
    analysis_request: str,
    languages: list[str] | None = None,
):
    """Launch an advanced DeepQuery analysis on the user's data in Denodo as a BACKGROUND job and return immediately.

    The analysis and the HTML report take minutes and run asynchronously: this tool never returns the analysis
    results, only a confirmation that the job started. The user follows the progress and opens the finished
    reports from the DeepQuery Reports Manager. Never claim the analysis or report is finished, and do not invent findings.

    Args:
        analysis_request: Detailed analysis request to perform.
        languages: Languages to generate the report in, one report per language, for example ['English', 'French']. If the user did not ask for specific languages, pass a single-item list with the language the user is writing in during the conversation (for example ['Spanish']).
    """

    try:
        job_context = ReportJobContext.from_user_context(runtime.context)
        analysis_id, reports = report_job_manager.submit(job_context, analysis_request, languages)
    except ValueError as e:
        return (str(e), {"error": str(e), "status": "rejected"})
    except Exception as e:
        logging.error("Could not start the DeepQuery background job", exc_info=True)
        return (
            f"The DeepQuery background job could not be started: {e}",
            {"error": str(e), "status": "rejected"},
        )

    report_languages = [report["language"] for report in reports]
    report_word = "report" if len(reports) == 1 else "reports"
    content = (
        f"Background job started: {len(reports)} {report_word} queued ({', '.join(report_languages)}). "
        "The analysis is running in the background and is NOT finished. Tell the user they can follow "
        "the progress and open the report from the DeepQuery Reports Manager in the header."
    )
    artifact = {
        "analysis_id": analysis_id,
        "report_ids": [report["report_id"] for report in reports],
        "languages": report_languages,
        "status": "queued",
    }
    return (content, artifact)

@tool(response_format="content_and_artifact")
def metadata_search(
    runtime: ToolRuntime[UserContext],
    search_query: str,
    n_results: int = 5,
):
    """This tool runs a similarity search in the database and returns the schema of the n_results (stick to the default of 5 if not specified) most similar views.
        For example, it can be helpful to answer questions like what views do we have related to X topic.
        If a view's schema was already returned earlier in the conversation, it will not be repeated in this tool's response.

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

    content, artifact = format_metadata_search_output(response)
    if runtime.context.memory_enabled:
        try:
            content += memory.render_metadata_memories_section(
                runtime.context.username,
                runtime.context.agent_id,
                response,
                runtime.context.share_general_memory,
            )
        except Exception:
            logging.exception("Failed to attach metadata memories to metadata_search")
    return content, artifact

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

# =============================================================================
# Memory Tools
# =============================================================================

def _memory_scope(runtime):
    context = runtime.context
    return (
        context.agent_id or "global",
        context.share_general_memory,
    )

def _memory_call(action):
    try:
        return action()
    except memory.MemoryError as exc:
        return (str(exc), {"error": str(exc)})

def _stored_index_text(records):
    rendered = memory.format_index(records)
    if not rendered:
        return ""
    return f"{rendered}\n"

@tool(response_format="content_and_artifact")
def read_memory(runtime: ToolRuntime[UserContext], name: str):
    """Read a specific memory's contents.

    The name is unique for this user, so the type is not needed.

    Args:
        name: Memory name, without the .md extension. For example, 'prefers-eur'.
    """
    def _read():
        agent_id, share_general = _memory_scope(runtime)
        record = memory.find_memory(runtime.context.username, name, agent_id, share_general)
        return (record.get("content") or record.get("body") or "", record)
    return _memory_call(_read)

@tool(response_format="content_and_artifact")
def list_memories(
    runtime: ToolRuntime[UserContext],
    memory_type: str = "",
    link_kind: str = "",
    link_name: str = "",
):
    """List memory index lines for this user on this agent.

    Use this to see 'user-metadata' or 'metadata' memories, or 'user'
    memories that fell past the portion of the index loaded into the
    system prompt. Leave a filter empty when you do not want to apply it.

    Args:
        memory_type: 'user', 'user-metadata', 'metadata', or empty for all.
        link_kind: Optional filter: 'view', 'database', 'tag', or 'none'.
            A memory matches when any of its links has this kind.
        link_name: Optional link name. For a view, use database.view_name.
            A memory matches when any of its links has this name.
    """
    def _list():
        agent_id, share_general = _memory_scope(runtime)
        records = memory.list_memories(
            runtime.context.username,
            memory_type=memory_type or None,
            link_kind=link_kind,
            link_name=link_name,
            agent_id=agent_id,
            include_shared_general=share_general,
        )
        content = memory.format_index(records) or "No memories match."
        if not memory_type or memory_type == "user":
            user_records = memory.list_memories(
                runtime.context.username, memory_type="user",
                agent_id=agent_id, include_shared_general=share_general,
            )
            notice = memory.index_limit_notice("user", _stored_index_text(user_records))
            if notice:
                content = f"{content}\n\n{notice}"
        return (content, {"memories": records})
    return _memory_call(_list)

@tool(response_format="content_and_artifact")
def write_memory(
    runtime: ToolRuntime[UserContext],
    memory_type: str,
    name: str,
    description: str,
    body: str,
    links: str = "",
):
    """Save or replace a memory for this user.

    Pick the memory type by what it represents:
    - 'user': a fact or preference about the person, with no link to any specific metadata. For
      example, a personal preference: that they like to be called Jamie instead of James or
      a workflow preference that applies always: James likes to show all currency fields converted to EUR.
    - 'user-metadata': a personal preference about specific metadata. It
      must be linked to at least one view, database, or tag. For example,
      that Jamie likes salary in samples_bank.loan to show the currency
      sign. The same preference with no link belongs in 'user'.
    - 'metadata': an objective fact about the metadata that the metadata
      itself does not say, linked to at least one view, database, or tag.
      For example, that the currency of salary in samples_bank.loan is USD.
      The logic is that a 'metadata' memory is a fact that is applicable to any user, not just the one you are talking to.

    One linked memory can be linked to several views, databases, and tags.
    Pass every link the memory should keep.

    Name: max 64 characters, lowercase letters, numbers, and hyphens, and it
    must not start or end with a hyphen.

    Args:
        memory_type: 'user', 'user-metadata', or 'metadata'.
        name: Filename stem. For example, 'revenue-means-net'.
        description: One-line title shown in the memory index.
        body: The note to reuse later. State the fact plainly.
        links: One link per line, as kind:name. kind is view, database, or tag.
            A view name is database.view_name. Example:
            view:sales.orders
            view:finance.invoices
            database:sales
            tag:revenue
            Leave empty for a 'user' memory; required otherwise.
    """
    def _write():
        agent_id, share_general = _memory_scope(runtime)
        result = memory.write_memory(
            runtime.context.username,
            memory_type,
            name,
            description,
            body,
            links=links,
            agent_id=agent_id,
            include_shared_general=share_general,
        )
        return (result["message"], result)
    return _memory_call(_write)

@tool(response_format="content_and_artifact")
def delete_memory(runtime: ToolRuntime[UserContext], name: str):
    """Delete one memory this user owns.

    The name is unique for this user, so the type is not needed.

    Args:
        name: Memory name, without the .md extension. For example, 'prefers-eur'.
    """
    def _delete():
        agent_id, share_general = _memory_scope(runtime)
        record = memory.find_memory(runtime.context.username, name, agent_id, share_general)
        result = memory.delete_memory(
            runtime.context.username, record["type"], name, agent_id, share_general,
        )
        return (result["message"], result)
    return _memory_call(_delete)

import os
import re
import json
import time
import base64
import logging
import asyncio
from collections import defaultdict
from urllib.parse import unquote

from fastmcp import FastMCP
from pydantic import AnyHttpUrl
from starlette.routing import Route
from starlette.responses import JSONResponse
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.dependencies import get_http_headers, get_http_request
from fastmcp.server.auth.providers.jwt import JWTVerifier
from api.endpoints.answerQuestion import answerQuestionRequest, process_question
from api.endpoints.generateVQL import generateVQLRequest, process_generate_vql
from api.endpoints.executeVQL import executeVQLRequest, process_execute_vql
from api.mcp.spaces import load_spaces
from api.utils import state_manager
from utils.denodo_tools import (
    format_generate_vql_output_mcp,
    format_execute_vql_output_mcp,
    format_metadata_search_output_mcp,
)
from utils.utils import filter_allowed_headers

logger = logging.getLogger(__name__)

SCOPE_REGEX = re.compile(r"/(database|tag|space)/([^/]+)/mcp/?$")
SCOPED_MCP_PATHS = (
    ("database", "/database/{database_name}/mcp"),
    ("tag", "/tag/{tag_name}/mcp"),
    ("space", "/space/{space_name}/mcp"),
)
SCOPE_PARAM = {
    "database": "database_name",
    "tag": "tag_name",
    "space": "space_name",
}

def _scope_from_path(path):
    match = SCOPE_REGEX.search(path or "")
    if not match:
        return None, None
    return match.group(1), unquote(match.group(2))

def _scope_name(scope, kind):
    name = (scope.get("path_params") or {}).get(SCOPE_PARAM[kind])
    if name:
        return name
    parsed_kind, parsed_name = _scope_from_path(scope.get("path", ""))
    if parsed_kind == kind:
        return parsed_name
    return None

VECTORIZED_CACHE_TTL_SECONDS = 60 * 60
_vectorized_cache = {}
_vectorized_locks = defaultdict(asyncio.Lock)

def _cached_vectorized(kind, name, now):
    stored_at, exists = _vectorized_cache.get((kind, name), (None, None))
    if stored_at is None or now - stored_at >= VECTORIZED_CACHE_TTL_SECONDS:
        return None
    return exists

async def _lookup_vectorized(kind, name):
    vector_store = state_manager.get_vector_store(
        provider=os.getenv("VECTOR_STORE"),
        embeddings_provider=os.getenv("EMBEDDINGS_PROVIDER"),
        embeddings_model=os.getenv("EMBEDDINGS_MODEL"),
    )
    kwargs = {"database_names": [name]} if kind == "database" else {"tag_names": [name]}
    return await asyncio.to_thread(vector_store.check_existence, None, **kwargs)

async def _resource_is_vectorized(kind, name):
    cached = _cached_vectorized(kind, name, time.monotonic())
    if cached is not None:
        return cached

    async with _vectorized_locks[(kind, name)]:
        cached = _cached_vectorized(kind, name, time.monotonic())
        if cached is not None:
            return cached
        exists = bool(await _lookup_vectorized(kind, name))
        _vectorized_cache[(kind, name)] = (time.monotonic(), exists)
        return exists

class ScopedMCP:
    """404 unknown spaces and databases/tags that have no vectorized views."""

    def __init__(self, endpoint, kind, spaces):
        self.endpoint = endpoint
        self.kind = kind
        self.spaces = spaces

    async def __call__(self, scope, receive, send):
        name = _scope_name(scope, self.kind)
        try:
            if self.kind == "space":
                allowed = name in self.spaces
                error = f"Unknown AI Space '{name}'."
            else:
                allowed = bool(name) and await _resource_is_vectorized(self.kind, name)
                error = f"No vectorized views found for {self.kind} '{name}'."
        except Exception:
            logger.exception(f"Failed to check vectorized {self.kind} '{name}'")
            await JSONResponse({"error": "Vector store is not available."}, status_code=503)(scope, receive, send)
            return
        if not allowed:
            await JSONResponse({"error": error}, status_code=404)(scope, receive, send)
            return
        await self.endpoint(scope, receive, send)

def get_mcp_app(host, port, root_path):
    """
    Factory function to create and configure the FastMCP app.
    """

    MCP_AI_SDK_BASIC_AUTH_ENABLED = os.getenv("MCP_AI_SDK_BASIC_AUTH", "1") == "1"
    MCP_AI_SDK_SCOPES_SUPPORTED = os.getenv("MCP_AI_SDK_SCOPES_SUPPORTED")
    MCP_AI_SDK_OIDC_ISSUER_URL = os.getenv("MCP_AI_SDK_OIDC_ISSUER_URL")
    MCP_AI_SDK_OIDC_JWKS_URI = os.getenv("MCP_AI_SDK_OIDC_JWKS_URI")
    MCP_AI_SDK_OIDC_AUDIENCE = os.getenv("MCP_AI_SDK_OIDC_AUDIENCE")
    MCP_AI_SDK_DCR_URL = os.getenv("MCP_AI_SDK_DCR_URL")
    LLM_RESPONSE_ROWS_LIMIT = int(os.getenv("LLM_RESPONSE_ROWS_LIMIT", "100"))
    GENERATE_VQL_TOOL_DESCRIPTION = f"""Takes a precise natural language request, generates a single valid VQL query from it and executes it, returning the query execution result.

    Limitations:
    - This tool cannot handle multi-step workflows. (i.e. do this first, then do that. if this fails, then do that, etc)
    - This tool does not have memory of previous requests or conversations. Every individual request to this tool must be self-contained, meaning it must not rely on recollection of previous requests.

    Args:
        request: The natural language request to generate a single VQL query from. For example, "Generate a VQL query to count the number of loan_id in the view org.loan_status where loan_status is 'active' and date_created is after or equal to 2026-01-01".
        limit: Maximum number of rows to return from the VQL execution result. Any integer between 1 and {LLM_RESPONSE_ROWS_LIMIT} can be set.
        This limit is set to avoid LLM context saturation. However, you must be transparent with the user regarding this limit to avoid confusion.
        view_names: Optional list of views (format: database.view_name) to be used in the VQL query, for example ['organization.loans', 'database.loan1']. If you're certain about the views you want the VQL to use, setting this value will speed up the VQL generation process because it won't have to look for relevant views in the database.
    """
    EXECUTE_VQL_TOOL_DESCRIPTION = f"""Tool to execute a VQL query. Execute only:
    - A previously generated VQL query by the generate_vql tool
    - A small edit to a previously generated VQL by the generate_vql tool (for example changing a filter, ORDER BY or LIMIT)
    - A exploratory query to explore the data model and understand the views available in Denodo and their schema. For example, 'SELECT DISTINCT example_field FROM "database"."view_name"'.

    Args:
        vql: The VQL query to execute.
        limit: Maximum number of rows to return. If omitted, it defaults to the session limit. Any integer between 1 and {LLM_RESPONSE_ROWS_LIMIT} can be set.
    """
    METADATA_SEARCH_TOOL_DESCRIPTION = """This tool can perform a similarity search in the database and return the schema of the n_results (stick to the default of 5 if not specified) most similar views.
        For example, it can be helpful to answer questions like:
        - What views do we have related to X topic.
        - What is the primary key of this table.
        - What associations does this view have.

    Args:
        search_query: Natural language query to search for the metadata of the views in the user's Denodo instance. For example, 'views related to loans'.
        n_results: Maximum number of results to return.
    """

    auth_provider = None

    if not MCP_AI_SDK_BASIC_AUTH_ENABLED:
        logger.info("Configuring security with JWT (OIDC/DCR)")

        issuer_url = MCP_AI_SDK_OIDC_ISSUER_URL.rstrip("/") if MCP_AI_SDK_OIDC_ISSUER_URL else None
        jwks_uri = MCP_AI_SDK_OIDC_JWKS_URI.rstrip("/") if MCP_AI_SDK_OIDC_JWKS_URI else None

        if not all([issuer_url, jwks_uri, MCP_AI_SDK_OIDC_AUDIENCE, MCP_AI_SDK_SCOPES_SUPPORTED]):
            raise ValueError(
                "For secure mode (MCP_AI_SDK_BASIC_AUTH=0), all MCP_AI_SDK_OIDC_* and MCP_AI_SDK_SCOPES_SUPPORTED variables must be defined."
            )

        if MCP_AI_SDK_DCR_URL:
            base_url = MCP_AI_SDK_DCR_URL.rstrip("/")
        else:
            base_url = f"http://{host}:{port}{root_path}"

        scopes_supported = [scope.strip() for scope in MCP_AI_SDK_SCOPES_SUPPORTED.split(",") if scope.strip()]

        token_verifier = JWTVerifier(
            jwks_uri=jwks_uri,
            issuer=issuer_url,
            audience=MCP_AI_SDK_OIDC_AUDIENCE,
            required_scopes=scopes_supported,
        )

        auth_provider = RemoteAuthProvider(
            base_url=base_url,
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(issuer_url)],
        )
    else:
        logger.warning("MCP server has started without an authentication provider.")
        logger.warning("The AI SDK will send the 'Authorization' header as is to the Denodo Platform.")

    mcp = FastMCP(
        "Denodo_AI_SDK_MCP",
        auth=auth_provider,
    )
    spaces = load_spaces()

    logger.info("MCP Server initialized")

    def _scope_filters():
        kind, name = _scope_from_path(get_http_request().url.path)
        if not kind:
            return [], []
        if kind == "database":
            return [name], []
        if kind == "tag":
            return [], [name]
        if name not in spaces:
            raise ValueError(f"Unknown AI Space '{name}'. Add api/agents/spaces/{name}.yaml")
        return spaces[name]

    def _extract_auth():
        raw_headers = get_http_headers(include={"authorization"})
        headers = {k.lower(): v for k, v in raw_headers.items()}
        auth = headers.get("authorization")

        if not auth:
            logger.error("Authorization header not found in MCP request")
            raise ValueError("Authorization header not found.")

        if not isinstance(auth, tuple) and auth.startswith("Basic "):
            try:
                encoded_credentials = auth.split(" ", 1)[1]
                decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
                user, pwd = decoded_credentials.split(":", 1)
                auth = (user, pwd)
                logger.debug("Successfully decoded Basic authentication")
            except Exception as e:
                logger.error(f"Failed to decode Basic auth: {str(e)}")
                raise ValueError("Invalid Basic authentication format") from e
        elif not isinstance(auth, tuple) and auth.startswith("Bearer "):
            try:
                auth = auth.split(" ", 1)[1]
                logger.debug("Successfully extracted Bearer token")
            except Exception as e:
                logger.error(f"Failed to extract Bearer token: {str(e)}")
                raise ValueError("Invalid Bearer authentication format") from e

        custom_headers = filter_allowed_headers(raw_headers)

        return auth, custom_headers

    # Keep the MCP tool docs in the decorator description instead of the docstring
    # so we can inject dynamic limits from environment variables when needed.
    @mcp.tool(
        description=GENERATE_VQL_TOOL_DESCRIPTION
    )
    async def generate_vql(
        request: str,
        limit: int = LLM_RESPONSE_ROWS_LIMIT,
        view_names: list[str] | None = None,
    ):
        logger.info(f"MCP request received - generate_vql, Request: {request}")

        auth, custom_headers = _extract_auth()

        try:
            vdp_database_names, vdp_tag_names = _scope_filters()
            logger.info(f"MCP scope filters databases={vdp_database_names!r} tags={vdp_tag_names!r}")
            endpoint_request = generateVQLRequest(
                request=request,
                vql_execute_rows_limit=limit,
                view_names=view_names or [],
                vdp_database_names=vdp_database_names,
                vdp_tag_names=vdp_tag_names,
            )

            response = await process_generate_vql(endpoint_request, auth, custom_headers=custom_headers)
            response_body = json.loads(response.body.decode())

            logger.info("MCP request completed successfully for generate_vql")
            return format_generate_vql_output_mcp(response_body)
        except Exception as e:
            logger.exception(f"Error processing MCP request - generate_vql, Request: {request}")
            return f"Error fetching response: {str(e)}"

    @mcp.tool(
        description=EXECUTE_VQL_TOOL_DESCRIPTION
    )
    async def execute_vql(
        vql: str,
        limit: int = LLM_RESPONSE_ROWS_LIMIT,
    ):
        logger.info(f"MCP request received - execute_vql")

        auth, custom_headers = _extract_auth()

        try:
            endpoint_request = executeVQLRequest(vql=vql, limit=limit)
            response = await process_execute_vql(endpoint_request, auth, custom_headers=custom_headers)
            response_body = json.loads(response.body.decode())

            logger.info("MCP request completed successfully for execute_vql")
            return format_execute_vql_output_mcp(response_body)
        except Exception as e:
            logger.exception("Error processing MCP request - execute_vql")
            return f"Error fetching response: {str(e)}"

    @mcp.tool(
        description=METADATA_SEARCH_TOOL_DESCRIPTION
    )
    async def metadata_search(
        search_query: str,
        n_results: int = 5,
    ):
        logger.info(f"MCP request received - Mode: metadata, Question: {search_query}")

        auth, custom_headers = _extract_auth()

        try:
            logger.debug("Processing request directly via process_question function")

            vdp_database_names, vdp_tag_names = _scope_filters()
            logger.info(f"MCP scope filters databases={vdp_database_names!r} tags={vdp_tag_names!r}")
            request = answerQuestionRequest(
                question=search_query,
                mode="metadata",
                verbose=False,
                vector_search_k=n_results,
                vdp_database_names=vdp_database_names,
                vdp_tag_names=vdp_tag_names,
            )

            response = await process_question(request, auth, custom_headers=custom_headers)
            response_body = json.loads(response.body.decode())

            logger.info("MCP request completed successfully for mode: metadata")
            return format_metadata_search_output_mcp(response_body)
        except Exception as e:
            logger.exception(f"Error processing MCP request - Mode: metadata, Question: {search_query}")
            return f"Error fetching response: {str(e)}"

    mcp_app = mcp.http_app(transport="http", path="/mcp", stateless_http=True, json_response=True)
    mcp_route = next(route for route in mcp_app.routes if getattr(route, "path", None) == "/mcp")
    methods = list(mcp_route.methods) if mcp_route.methods else None

    for kind, extra_path in SCOPED_MCP_PATHS:
        mcp_app.routes.insert(
            0,
            Route(extra_path, endpoint=ScopedMCP(mcp_route.endpoint, kind, spaces), methods=methods),
        )

    return mcp_app

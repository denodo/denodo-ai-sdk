import os
import json
import base64
import logging

from fastmcp import FastMCP
from pydantic import AnyHttpUrl
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.auth.providers.jwt import JWTVerifier
from api.endpoints.answerQuestion import answerQuestionRequest, process_question
from utils.denodo_tools import format_data_agent_output_mcp, format_metadata_search_output_mcp
from utils.utils import filter_allowed_headers

logger = logging.getLogger(__name__)


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
    DATA_AGENT_TOOL_DESCRIPTION = f"""Communicates with the data agent to generate and execute a single VQL query.
    The data agent does not have memory of previous requests or conversations. Every individual request to the data_agent must be self-contained, meaning it must not rely on the data agent having recollection of previous requests.

    Args:
        request: Request to generate a single VQL query from and return the VQL query, its explanation and the execution result. For example, 'count the number of unique customers in the organization.customers view'.
        limit: Maximum number of rows to return from the VQL execution result. Any integer between 1 and {LLM_RESPONSE_ROWS_LIMIT} can be set.
        This limit is set to avoid LLM context saturation. However, you must be transparent with the user regarding this limit to avoid confusion.
        For example, if 100 rows are returned for new customers, is it because limit is set to 100 (and then there may be more new customers) or because there are actually 100 new customers?
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

    logger.info("MCP Server initialized")

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
        description=DATA_AGENT_TOOL_DESCRIPTION
    )
    async def data_agent(
        request: str,
        limit: int = LLM_RESPONSE_ROWS_LIMIT,
    ):
        logger.info(f"MCP request received - Mode: data, Question: {request}")

        auth, custom_headers = _extract_auth()

        try:
            logger.debug("Processing request directly via process_question function")

            request = answerQuestionRequest(
                question=request,
                mode="data",
                verbose=False,
                disclaimer=False,
                vql_execute_rows_limit=limit
            )

            response = await process_question(request, auth, custom_headers=custom_headers)
            response_body = json.loads(response.body.decode())

            logger.info("MCP request completed successfully for mode: data")
            return format_data_agent_output_mcp(response_body)
        except Exception as e:
            logger.exception(f"Error processing MCP request - Mode: data, Question: {request}")
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

            request = answerQuestionRequest(
                question=search_query,
                mode="metadata",
                verbose=False,
                vector_search_k=n_results,
            )

            response = await process_question(request, auth, custom_headers=custom_headers)
            response_body = json.loads(response.body.decode())

            logger.info("MCP request completed successfully for mode: metadata")
            return format_metadata_search_output_mcp(response_body)
        except Exception as e:
            logger.exception(f"Error processing MCP request - Mode: metadata, Question: {search_query}")
            return f"Error fetching response: {str(e)}"

    return mcp.http_app(transport="http", path="/mcp", stateless_http=True, json_response=True)

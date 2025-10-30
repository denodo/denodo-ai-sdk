import os
import json
import base64
import logging

from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_http_headers
from pydantic import AnyHttpUrl
from api.endpoints.answerQuestion import answerQuestionRequest, process_question

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

    @mcp.tool()
    async def ask_database(question: str, mode: str = "data"):
        """Query the user's database in natural language.

        Accepts a mode parameter to specify the mode to use for the query:
        - data: Query the data in the database. For example, 'how many new customers did we get last month?'
        - metadata: Query the metadata in the database. For example, 'what is the type of the column 'customer_id' in the customers table?'

        Args:
            question: Natural language question (e.g. "how many new customers did we get last month?")
            mode: The mode to use for the query. Can be "data" or "metadata".
        """
        logger.info(f"MCP request received - Mode: {mode}, Question: {question}")

        raw_headers = get_http_headers()
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

        try:
            logger.debug("Processing request directly via process_question function")

            request = answerQuestionRequest(
                question=question,
                mode=mode,
                verbose=False,
            )

            response = await process_question(request, auth)

            response_body = json.loads(response.body.decode())

            if mode == "data":
                result = response_body.get("execution_result", "The AI SDK did not return a result.")
            else:
                result = response_body.get("answer", "The AI SDK did not return a result.")

            logger.info(f"MCP request completed successfully for mode: {mode}")
            return result
        except Exception as e:
            logger.exception(f"Error processing MCP request - Mode: {mode}, Question: {question}")
            return f"Error fetching response: {str(e)}"

    return mcp.http_app(transport="http", path="/mcp", stateless_http=True)

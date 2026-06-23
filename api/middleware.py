"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import time
import json
import base64
import logging
import asyncio
from fastapi import Response
from utils.utils import generate_transaction_id
from utils.data_marketplace.connection import get_username_from_denodo
from utils.logging_utils import transaction_id_var, username_var

logger = logging.getLogger(__name__)

# Cache configuration
TOKEN_CACHE = {}
CACHE_TTL_SECONDS = 300
MAX_CACHE_SIZE = 1000

async def logging_context_middleware(request, call_next):
    """
    Middleware to generate a transaction ID and extract the username
    from the Authorization header (Basic Auth, JWT, or opaque tokens
    via Denodo fallback), storing them in context variables. Includes
    an in-memory TTL cache to prevent redundant decoding/network calls.
    """
    transaction_id = generate_transaction_id()
    transaction_id_var.set(transaction_id)

    username = "anonymous"
    auth_header = request.headers.get("Authorization")

    if auth_header:
        try:
            scheme, credentials = auth_header.split(" ", 1)
            current_time = time.time()

            cached_data = TOKEN_CACHE.get(credentials)
            if cached_data and current_time < cached_data['expires']:
                username = cached_data['username']
            else:
                if scheme.lower() == "basic":
                    decoded = base64.b64decode(credentials).decode("utf-8")
                    username = decoded.split(":", 1)[0]

                elif scheme.lower() == "bearer":
                    try: # Extract from JWT Token
                        payload_b64 = credentials.split(".")[1]
                        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
                        username = payload.get("preferred_username") or payload.get("sub") or "jwt-user"

                    except Exception as e: # Opaque tokens fallback
                        logging.debug(f"Token is not a readable JWT. Fallback to Denodo... ({e})")
                        fallback_user = await get_username_from_denodo(auth=credentials)

                        if fallback_user:
                            username = fallback_user
                        else:
                            logging.warning("Fallback failed: Could not retrieve username from Denodo using the provided token.")

                if username != "anonymous":
                    if len(TOKEN_CACHE) >= MAX_CACHE_SIZE:
                        TOKEN_CACHE.clear()

                    TOKEN_CACHE[credentials] = {
                        'username': username,
                        'expires': current_time + CACHE_TTL_SECONDS
                    }

        except Exception as e:
            logging.debug(f"Failed to extract username from Authorization header: {e}")

    username_var.set(username)

    try:
        response = await call_next(request)
        response.headers["X-Transaction-ID"] = transaction_id
        return response
    except RuntimeError as exc:
        if str(exc) == "No response returned.":
            # Client Closed Request
            return Response(status_code=499)
        raise


class RequestCancelledMiddleware:
    """
    ASGI middleware: cancel the request task when the client disconnects.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        queue = asyncio.Queue()

        async def message_poller(sentinel, handler_task):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    handler_task.cancel()
                    return sentinel
                await queue.put(message)

        sentinel = object()
        handler_task = asyncio.create_task(self.app(scope, queue.get, send))
        poller_task = asyncio.create_task(message_poller(sentinel, handler_task))

        try:
            await handler_task
        except asyncio.CancelledError:
            logger.warning("Request cancelled (client disconnected)")
        finally:
            poller_task.cancel()
            try:
                await poller_task
            except asyncio.CancelledError:
                pass

"""
Handles chat/query processing logic and streaming responses.
"""

import json
import logging

from sample_chatbot.reporting import write_to_report
from sample_chatbot.extensions import report_lock

class ChatService:
    """Service for handling chat queries and streaming responses."""

    def __init__(self, config):
        """
        Initialize the chat service.

        Args:
            config: ChatbotConfig instance
        """
        self._config = config

    def process_query_stream(self, user, llm, query, tool_name, vdp_databases, vdp_tags, allow_external_associations):
        """
        Process a query and yield streaming response chunks.

        Args:
            user: User instance
            llm: Default UniformLLM instance
            query: User's query string
            tool_name: Optional tool name to use
            vdp_databases: Database filter string
            vdp_tags: Tag filter string
            allow_external_associations: Whether to allow external associations

        Yields:
            SSE formatted response chunks
        """
        try:
            chatbot = user.get_or_create_chatbot(llm)
        except Exception as e:
            logging.error(f"Error creating chatbot: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'There was an error configuring the chatbot: {str(e)}'})}\n\n"
            return

        for chunk in chatbot.process_query(
            query=query,
            tool=tool_name,
            vdp_database_names=vdp_databases,
            vdp_tag_names=vdp_tags,
            allow_external_associations=allow_external_associations
        ):
            if isinstance(chunk, dict):
                yield "data: <STREAMOFF>\n\n"
                chunk_json = json.dumps(chunk)
                yield f"data: {chunk_json}\n\n"

                # Write to report if enabled
                if self._config.reporting_enabled:
                    write_to_report(
                        report_lock,
                        self._config.report_max_size,
                        self._config.report_max_files,
                        query,
                        chunk,
                        user.id
                    )
            elif isinstance(chunk, str):
                chunk = chunk.replace('\n', '<NEWLINE>')
                yield f"data: {chunk}\n\n"
            else:
                yield f"data: {chunk}\n\n"

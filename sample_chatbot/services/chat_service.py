"""
Handles chat/query processing logic and streaming responses.
"""

import json
import logging

from langchain_core.messages import RemoveMessage, ToolMessage

from sample_chatbot.reporting import write_to_report
from sample_chatbot.extensions import report_lock
from utils.database_utils import HistoryMetadata

# Synthetic result recorded for tool calls that never completed, so interrupted
# turns render as an errored tool instead of a permanently loading one.
INTERRUPTED_TOOL_CALL_CONTENT = (
    "This tool call was interrupted before it could complete (the query was "
    "cancelled or the server stopped), so no output is available."
)
# The frontend styles a tool call as errored when its result artifact carries an error.
INTERRUPTED_TOOL_CALL_ARTIFACT = {
    "error": "interrupted",
    "error_message": INTERRUPTED_TOOL_CALL_CONTENT,
}

class ChatService:
    """Service for handling chat queries and streaming responses."""

    def __init__(self, config):
        """
        Initialize the chat service.

        Args:
            config: ChatbotConfig instance
        """
        self._config = config

    def _rollback_failed_turn(self, chatbot, thread_id, query):
        """
        Rolls back the conversation state by removing the failed query 
        and any partial/tool responses appended after it.
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state_snapshot = chatbot.agent.get_state(config)

            if not state_snapshot or not hasattr(state_snapshot, 'values'):
                return

            messages = state_snapshot.values.get("messages", [])
            if not messages:
                return

            # Find the index of the last human message
            last_human_idx = -1
            for i in range(len(messages) - 1, -1, -1):
                if getattr(messages[i], 'type', '') in ['human', 'user']:
                    last_human_idx = i
                    break

            if last_human_idx != -1:
                human_msg_content = str(messages[last_human_idx].content)

                # Verify the human message matches the failed query to avoid deleting old valid turns
                if query.strip() in human_msg_content:
                    # Target the human message and anything after it (like failed tool calls or partial AIs).
                    # Remove messages one by one: the snapshot can include transient in-flight messages
                    # (e.g. partial AI chunks from an interrupted stream) whose IDs were never persisted,
                    # and a single batched removal would fail entirely on the first missing ID.
                    removed_count = 0
                    for m in messages[last_human_idx:]:
                        if not (hasattr(m, 'id') and m.id):
                            continue
                        try:
                            # as_node='__start__': an interrupted thread can leave the graph in a
                            # state where LangGraph cannot infer the node to attribute the update
                            # to and raises a KeyError, so attribute it explicitly.
                            chatbot.agent.update_state(config, {"messages": [RemoveMessage(id=m.id)]}, as_node="__start__")
                            removed_count += 1
                        except Exception as remove_error:
                            logging.debug(f"Skipping rollback of message {m.id} in thread {thread_id}: {remove_error}")

                    if removed_count:
                        logging.warning(f"Rolled back {removed_count} messages in thread {thread_id} due to failure.")

        except Exception as e:
            logging.error(f"Failed to rollback turn for thread {thread_id}: {e}", exc_info=True)
        finally:
            self._delete_chat_if_empty(chatbot, thread_id)

    def _delete_chat_if_empty(self, chatbot, thread_id):
        """
        Deletes the chat metadata row when its thread has no messages left,
        so a rolled-back or cancelled first turn does not leave an empty
        conversation behind in the sidebar.
        """
        try:
            state_snapshot = chatbot.agent.get_state({"configurable": {"thread_id": thread_id}})
            messages = state_snapshot.values.get("messages", []) if state_snapshot and hasattr(state_snapshot, 'values') else []
            if not messages:
                HistoryMetadata.delete_chat(thread_id)
                logging.info(f"Deleted empty chat {thread_id} after rollback.")
        except Exception as e:
            logging.error(f"Failed to check for empty chat {thread_id}: {e}")

    @staticmethod
    def _msg_field(message, field, default=None):
        """Reads a field from a message that may be a BaseMessage or a plain dict
        (state snapshots occasionally return raw dicts for not-yet-finalized writes)."""
        if isinstance(message, dict):
            return message.get(field, default)
        return getattr(message, field, default)

    def _sanitize_dangling_tool_calls(self, chatbot, thread_id):
        """
        Repairs AI messages whose tool calls never received a ToolMessage.

        Such messages get persisted when the turn dies between the model step
        and the tool result (process killed/restarted mid-tool-call...). They render as a
        permanently loading tool call in the UI and block the conversation thread.

        When the dangling calls sit at the tail of the history, a synthetic
        errored tool result is recorded for each so the turn renders as an
        interrupted tool instead of a loading one.
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state_snapshot = chatbot.agent.get_state(config)

            if not state_snapshot or not hasattr(state_snapshot, 'values'):
                return

            messages = state_snapshot.values.get("messages", [])
            if not messages:
                return

            answered_call_ids = {
                self._msg_field(m, 'tool_call_id') for m in messages
                if isinstance(m, ToolMessage) or self._msg_field(m, 'type') == 'tool'
            }

            def unanswered_calls(message):
                return [
                    call for call in (self._msg_field(message, 'tool_calls') or [])
                    if call.get('id') and call.get('id') not in answered_call_ids
                ]

            dangling = [m for m in messages if unanswered_calls(m)]
            if not dangling:
                return

            repaired_count = 0
            removed_count = 0

            # as_node='__start__' on every update: a thread killed mid-superstep leaves
            # the graph in a state where LangGraph cannot infer the node to attribute
            # the update to and raises a KeyError, so attribute it explicitly.
            if dangling == [messages[-1]]:
                # Trailing interrupted turn: record synthetic errored results so the
                # tool renders as interrupted and the history stays visible.
                synthetic_results = [
                    ToolMessage(
                        content=INTERRUPTED_TOOL_CALL_CONTENT,
                        tool_call_id=call.get('id'),
                        name=call.get('name', 'tool'),
                        status='error',
                        artifact=INTERRUPTED_TOOL_CALL_ARTIFACT,
                    )
                    for call in unanswered_calls(messages[-1])
                ]
                chatbot.agent.update_state(config, {"messages": synthetic_results}, as_node="__start__")
                repaired_count = len(synthetic_results)
            else:
                # Dangling calls buried in the history: remove them (and any tool
                # results they would orphan) since appended results would not be
                # adjacent to their calls.
                dropped_call_ids = {call.get('id') for m in dangling for call in (self._msg_field(m, 'tool_calls') or [])}
                to_remove = dangling + [
                    m for m in messages
                    if (isinstance(m, ToolMessage) or self._msg_field(m, 'type') == 'tool')
                    and self._msg_field(m, 'tool_call_id') in dropped_call_ids
                ]
                for m in to_remove:
                    message_id = self._msg_field(m, 'id')
                    if not message_id:
                        continue
                    try:
                        chatbot.agent.update_state(config, {"messages": [RemoveMessage(id=message_id)]}, as_node="__start__")
                        removed_count += 1
                    except Exception as remove_error:
                        logging.warning(f"Skipping dangling message {message_id} in thread {thread_id}: {remove_error}")

            if repaired_count or removed_count:
                logging.warning(
                    f"Sanitized dangling tool calls in thread {thread_id} "
                    f"(synthetic error results: {repaired_count}, removed messages: {removed_count})."
                )

        except Exception as e:
            logging.error(f"Failed to sanitize dangling tool calls for thread {thread_id}: {e}", exc_info=True)

    def process_query_stream(self, user, query, tool_name, vdp_databases, vdp_tags, allow_external_associations, thread_id=None, is_new_thread=False, cancel_event=None):
        """
        Process a query and yield streaming response chunks.

        Args:
            user: User instance
            query: User's query string
            tool_name: Optional tool name to use
            vdp_databases: Database filter string
            vdp_tags: Tag filter string
            allow_external_associations: Whether to allow external associations
            thread_id: ID of the conversation thread for persistent memory
            is_new_thread: Boolean indicating if this is the first message of the chat

        Yields:
            SSE formatted response chunks
        """
        try:
            chatbot = user.get_or_create_chatbot()

        except Exception as e:
            logging.error(f"Error creating chatbot: {str(e)}", exc_info=True)

            if is_new_thread and thread_id:
                logging.warning(f"Deleting ghost chat {thread_id} due to initialization error.")
                HistoryMetadata.delete_chat(thread_id)

            yield f"data: {json.dumps({'type': 'error', 'message': f'There was an error configuring the chatbot: {str(e)}'})}\n\n"
            return

        # Self-heal threads poisoned by a turn that died mid-tool-call
        if thread_id and not is_new_thread:
            self._sanitize_dangling_tool_calls(chatbot, thread_id)

        vdp_databases = vdp_databases or ",".join(self._config.databases)
        vdp_tags = vdp_tags or ",".join(self._config.tags)

        stream = chatbot.process_query(
            query=query,
            tool=tool_name,
            vdp_database_names=vdp_databases,
            vdp_tag_names=vdp_tags,
            allow_external_associations=allow_external_associations,
            thread_id=thread_id,
            cancel_event=cancel_event
        )

        try:
            for chunk in stream:
                if cancel_event is not None and cancel_event.is_set():
                    logging.warning(f"User cancelled the query for thread {thread_id}. Rolling back the interrupted turn.")
                    stream.close()
                    if thread_id:
                        self._rollback_failed_turn(chatbot, thread_id, query)
                    return

                if isinstance(chunk, dict):
                    is_error = chunk.get('type') == 'error' or 'error' in chunk

                    if is_error:
                        if is_new_thread and thread_id:
                            logging.warning(f"Error returned on first message for thread {thread_id}. Deleting chat.")
                            HistoryMetadata.delete_chat(thread_id)
                        elif thread_id:
                            # Rollback the specific turn for existing chats
                            self._rollback_failed_turn(chatbot, thread_id, query)

                    yield "data: <STREAMOFF>\n\n"
                    chunk_json = json.dumps(chunk)
                    yield f"data: {chunk_json}\n\n"

                    if self._config.reporting_enabled and not is_error:
                        write_to_report(
                            report_lock,
                            self._config.report_max_size,
                            self._config.report_max_files,
                            query,
                            chunk,
                            user.id,
                            self._config.reports_folder
                        )
                elif isinstance(chunk, str):
                    chunk = chunk.replace('\n', '<NEWLINE>')
                    yield f"data: {chunk}\n\n"
                else:
                    yield f"data: {chunk}\n\n"

        except GeneratorExit:
            # The client cancelled the query (disconnected mid-stream). Stop the
            # underlying agent stream and roll back the interrupted turn so the
            # stored history matches what the client shows after cancelling.
            logging.warning(f"Client cancelled the query for thread {thread_id}. Rolling back the interrupted turn.")
            stream.close()

            if thread_id:
                self._rollback_failed_turn(chatbot, thread_id, query)
            raise

        except Exception as e:
            logging.error(f"Streaming error during query processing: {str(e)}", exc_info=True)

            if is_new_thread and thread_id:
                logging.warning(f"Exception on first message for thread {thread_id}. Deleting ghost chat.")
                HistoryMetadata.delete_chat(thread_id)
            elif thread_id:
                # Rollback the specific turn if the stream crashes mid-way
                self._rollback_failed_turn(chatbot, thread_id, query)

            yield "data: <STREAMOFF>\n\n"
            yield f"data: {json.dumps({'type': 'error', 'message': f'An unexpected error occurred: {str(e)}'})}\n\n"

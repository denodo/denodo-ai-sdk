"""
Handles question processing and chat history endpoints.
"""

import os
import re
import uuid
import json
import logging
import threading
from flask import Blueprint, request, jsonify, Response, copy_current_request_context
from flask_login import login_required, current_user
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage, ToolMessage
from sample_chatbot.config import get_config
from sample_chatbot.services.chat_service import ChatService, INTERRUPTED_TOOL_CALL_CONTENT, INTERRUPTED_TOOL_CALL_ARTIFACT
from utils.database_utils import UniformCheckpointer, HistoryMetadata
from sample_chatbot.utils.helpers import generate_chat_title, format_chat_log
from utils.logging_utils import username_var, transaction_id_var

chat_bp = Blueprint('chat', __name__)

try:
    MAX_CHATS_PER_USER = int(os.getenv("CHATBOT_MAX_CHATS_PER_USER", 50))
except ValueError:
    MAX_CHATS_PER_USER = 50

try:
    MAX_MESSAGES_PER_CHAT = int(os.getenv("CHATBOT_MAX_MESSAGES_PER_CHAT", 100))
except ValueError:
    MAX_MESSAGES_PER_CHAT = 100

try:
    max_import_size_mb = int(os.getenv("CHATBOT_MAX_IMPORT_FILE_SIZE_MB", 5))
except ValueError:
    max_import_size_mb = 5

MAX_IMPORT_FILE_SIZE_BYTES = max_import_size_mb * 1024 * 1024

# Cancellation events for in-flight questions, keyed by
# (user_id, client-generated cancellation_id). Setting an event
# aborts the in-flight AI SDK request too.
CANCEL_EVENTS = {}

def update_title_in_background(thread_id, user_query, uniform_llm, temp_title, user_id, agent_id="global", transaction_id=None):
    """Calls the helper and updates the DB in the background, respecting manual renames."""
    username_var.set(user_id)
    if transaction_id:
        transaction_id_var.set(transaction_id)
    try:
        new_title = generate_chat_title(uniform_llm, user_query, session_id=thread_id)

        chats = HistoryMetadata.get_user_chats(user_id, limit=50)
        current_chat = next((c for c in chats if c['thread_id'] == thread_id), None)

        if current_chat and current_chat['title'] == temp_title:
            HistoryMetadata.rename_chat(thread_id, new_title)
            logging.info(
                f"{format_chat_log(agent_id, thread_id, 'chat_title_update')} {new_title}"
            )
        else:
            logging.info(
                f"{format_chat_log(agent_id, thread_id, 'chat_title_update')} "
                f"skipped (manually modified or deleted)"
            )
    except Exception as e:
        logging.error(f"Error in background title generation: {e}")

@chat_bp.route('/api/question', methods=['POST'])
@login_required
def question():
    """Process a user question and stream the response."""
    data = request.get_json()
    query = data.get('query')
    tool_name = data.get('tool')
    databases_str = data.get('databases', '')
    tags_str = data.get('tags', '')
    allow_external_associations = data.get('allow_external_associations', True)
    force_overwrite = data.get('force_overwrite', False)

    # Capture the actual user object, not the proxy
    user_obj = current_user._get_current_object()

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400

    thread_id = data.get('thread_id')
    is_new_thread = not bool(thread_id)
    agent_id = user_obj.agent_id if user_obj.agent_id else 'global'

    # The chat row may have been deleted while the client kept its thread id
    # (e.g. an empty conversation cleaned up after a cancelled first turn).
    # Treat it as a brand-new conversation instead of denying access.
    if thread_id and not HistoryMetadata.chat_exists(thread_id):
        thread_id = None
        is_new_thread = True

    if is_new_thread:
        chats = HistoryMetadata.get_user_chats(user_obj.id, limit=5000)
        current_chats = len(chats)

        if current_chats >= MAX_CHATS_PER_USER:
            excess = current_chats - MAX_CHATS_PER_USER + 1
            unpinned_chats = sorted([c for c in chats if not c['is_pinned']], key=lambda x: x['updated_at'])
            pinned_chats = sorted([c for c in chats if c['is_pinned']], key=lambda x: x['updated_at'])
            ordered_chats = unpinned_chats + pinned_chats

            chats_to_delete = ordered_chats[:excess]

            if not force_overwrite:
                targets = [c['title'] for c in chats_to_delete]
                return jsonify({
                    "error": "limit_reached",
                    "type": "chats",
                    "limit": MAX_CHATS_PER_USER,
                    "current": current_chats,
                    "targets_to_delete": targets
                }), 409
            else:
                for c in chats_to_delete:
                    HistoryMetadata.delete_chat(c['thread_id'])

        thread_id = str(uuid.uuid4())

        temp_title = (query[:30] + '...') if len(query) > 30 else query
        HistoryMetadata.save_new_chat(thread_id, user_obj.id, agent_id, temp_title)

        uniform_llm = user_obj.get_chatbot_llm()
        parent_transaction_id = transaction_id_var.get()

        @copy_current_request_context
        def background_task():
            update_title_in_background(
                thread_id, query, uniform_llm, temp_title, user_obj.id, agent_id,
                transaction_id=parent_transaction_id,
            )

        threading.Thread(target=background_task).start()

    else:
        if not HistoryMetadata.verify_ownership(thread_id, user_obj.id):
            return jsonify({"error": "Access denied to this chat"}), 403

        checkpointer = UniformCheckpointer.get_saver()
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = checkpointer.get_tuple(config)

        if checkpoint_tuple:
            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            messages = state.get("messages", [])
            human_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
            current_messages = len(human_indices)

            if current_messages >= MAX_MESSAGES_PER_CHAT:
                excess = current_messages - MAX_MESSAGES_PER_CHAT + 1

                if not force_overwrite:
                    targets = []
                    for i in range(excess):
                        raw_content = str(messages[human_indices[i]].content)

                        match = re.search(r'<user_query>([\s\S]*?)</user_query>', raw_content)
                        if match:
                            clean_content = match.group(1).strip()
                        else:
                            clean_content = raw_content

                        targets.append((clean_content[:80] + '...') if len(clean_content) > 80 else clean_content)

                    return jsonify({
                        "error": "limit_reached",
                        "type": "messages",
                        "limit": MAX_MESSAGES_PER_CHAT,
                        "current": current_messages,
                        "targets_to_delete": targets
                    }), 409
                else:
                    if len(human_indices) >= excess + 1:
                        block_to_delete = messages[0:human_indices[excess]]
                        delete_commands = [RemoveMessage(id=m.id) for m in block_to_delete]
                        chatbot = user_obj.get_or_create_chatbot()
                        chatbot.agent.update_state(config, {"messages": delete_commands})

        HistoryMetadata.save_new_chat(thread_id, user_obj.id, agent_id, query)

    config_obj = get_config(agent_id)
    chat_service = ChatService(config_obj)

    cancellation_id = data.get('cancellation_id')
    cancel_key = (user_obj.id, cancellation_id)
    cancel_event = None
    if cancellation_id:
        cancel_event = threading.Event()
        CANCEL_EVENTS[cancel_key] = {
            'event': cancel_event,
            'thread_id': thread_id,
            'done': threading.Event(),
        }

    def generate():
        try:
            yield from chat_service.process_query_stream(
                user=user_obj,
                query=query,
                tool_name=tool_name,
                vdp_databases=databases_str,
                vdp_tags=tags_str,
                allow_external_associations=allow_external_associations,
                thread_id=thread_id,
                is_new_thread=is_new_thread,
                cancel_event=cancel_event
            )
        finally:
            if cancellation_id:
                entry = CANCEL_EVENTS.pop(cancel_key, None)
                if entry:
                    entry['done'].set()

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'X-Thread-ID': thread_id}
    )

@chat_bp.route('/api/question/cancel', methods=['POST'])
@login_required
def cancel_question():
    """Cancel an in-flight question, aborting any AI SDK request it is running.

    Responds only after the streaming request has finished its rollback and
    empty-chat cleanup, so the client can refresh the chat list exactly once
    the state is final. `chat_deleted` tells the client whether the cancelled
    conversation was removed entirely (first message of a new chat).
    """
    data = request.get_json()
    # Keyed by user too, so a user can only ever cancel their own questions.
    entry = CANCEL_EVENTS.get((current_user.id, data.get('cancellation_id') or ''))

    if entry:
        entry['event'].set()
        # Bounded wait as a safety net in case the streaming thread never
        # finishes (e.g. it is blocked on a non-cancellable call).
        cleanup_finished = entry['done'].wait(timeout=30)

        thread_id = entry.get('thread_id')
        chat_deleted = bool(thread_id) and not HistoryMetadata.chat_exists(thread_id)

        return jsonify({
            "success": True,
            "cleanup_finished": cleanup_finished,
            "chat_deleted": chat_deleted,
        })
    return jsonify({"success": False, "error": "No matching in-flight question"}), 404

@chat_bp.route('/api/history', methods=['GET'])
@login_required
def list_history():
    user_obj = current_user._get_current_object()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    search_query = request.args.get('q', '', type=str)

    chats = HistoryMetadata.get_user_chats(user_obj.id, limit=limit, offset=offset, search_query=search_query)
    return jsonify({"chats": chats})

@chat_bp.route('/api/history/<thread_id>', methods=['PUT'])
@login_required
def rename_history(thread_id):
    if not HistoryMetadata.verify_ownership(thread_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    new_title = data.get('title')
    if new_title:
        HistoryMetadata.rename_chat(thread_id, new_title)
    return jsonify({"success": True})

@chat_bp.route('/api/history/<thread_id>/pin', methods=['PUT'])
@login_required
def pin_history(thread_id):
    if not HistoryMetadata.verify_ownership(thread_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    is_pinned = data.get('is_pinned', False)
    HistoryMetadata.pin_chat(thread_id, is_pinned)
    return jsonify({"success": True})

@chat_bp.route('/api/history/<thread_id>', methods=['DELETE'])
@login_required
def delete_history(thread_id):
    if not HistoryMetadata.verify_ownership(thread_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    HistoryMetadata.delete_chat(thread_id)
    return jsonify({"success": True})

@chat_bp.route('/api/history/<thread_id>/export', methods=['GET'])
@login_required
def export_history(thread_id):
    if not HistoryMetadata.verify_ownership(thread_id, current_user.id):
        return jsonify({"error": "Access denied"}), 403

    checkpointer = UniformCheckpointer.get_saver()
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = checkpointer.get_tuple(config)

    if not checkpoint_tuple:
        return jsonify({"error": "History not found for this thread"}), 404

    state = checkpoint_tuple.checkpoint.get("channel_values", {})
    messages = state.get("messages", [])

    export_data = []
    current_turn_uuid = None

    for msg in messages:
        if msg.type in ['human', 'user']:
            current_turn_uuid = getattr(msg, 'id', None)

        content = msg.content
        if isinstance(content, list):
            # LangChain content blocks are list[str | dict]: bare strings are
            # text, dicts carry a "type" (Gemini thinking models emit both).
            text_parts = []
            for c in content:
                if isinstance(c, str):
                    text_parts.append(c)
                elif isinstance(c, dict) and c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
            content_str = "".join(text_parts)
        else:
            content_str = str(content)

        if msg.type == 'ai' and (content_str.strip().startswith('[{') or 'tool_calls' in content_str):
            content_str = ""

        tool_calls = getattr(msg, 'tool_calls', [])
        tool_call_id = getattr(msg, 'tool_call_id', None)
        tool_name = getattr(msg, 'name', None)
        artifact = getattr(msg, 'artifact', None)

        chatbot_llm = None
        is_imported = False

        if msg.type == 'ai' and hasattr(msg, 'response_metadata'):
            metadata = msg.response_metadata
            chatbot_llm = metadata.get('model_name') or metadata.get('model') or metadata.get('model_id')
            is_imported = metadata.get('imported', False)

        export_data.append({
            "uuid": current_turn_uuid,
            "role": msg.type,
            "content": content_str,
            "tool_calls": tool_calls,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "artifact": artifact,
            "chatbot_llm": chatbot_llm,
            "is_imported": is_imported
        })

    # Represent tool calls that never completed (e.g. the turn was interrupted
    # mid-tool-call) as errored tool results, so loading or re-importing this
    # history renders an interrupted tool instead of a permanently loading one.
    answered_call_ids = {e['tool_call_id'] for e in export_data if e['role'] == 'tool'}
    repaired_data = []
    for entry in export_data:
        repaired_data.append(entry)
        for call in (entry.get('tool_calls') or []):
            call_id = call.get('id')
            if call_id and call_id not in answered_call_ids:
                repaired_data.append({
                    "uuid": entry.get("uuid"),
                    "role": "tool",
                    "content": INTERRUPTED_TOOL_CALL_CONTENT,
                    "tool_calls": [],
                    "tool_call_id": call_id,
                    "tool_name": call.get('name', 'tool'),
                    "artifact": INTERRUPTED_TOOL_CALL_ARTIFACT,
                    "chatbot_llm": None,
                    "is_imported": False
                })
    export_data = repaired_data

    chats = HistoryMetadata.get_user_chats(current_user.id, limit=100)
    current_title = next((c['title'] for c in chats if c['thread_id'] == thread_id), "Chat Export")

    return jsonify({
        "title": current_title,
        "thread_id": thread_id,
        "total_messages": len(export_data),
        "messages": export_data
    })

@chat_bp.route('/api/history/import', methods=['POST'])
@login_required
def import_history():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    force_overwrite = request.form.get('force_overwrite') == 'true'

    content = file.read()
    if len(content) > MAX_IMPORT_FILE_SIZE_BYTES:
        return jsonify({"error": f"Import file is too large. Maximum size is {MAX_IMPORT_FILE_SIZE_BYTES // (1024 * 1024)}MB."}), 413

    try:
        data = json.loads(content)

        if not isinstance(data, dict):
            return jsonify({"error": "Invalid file format: Expected a JSON object."}), 400

        if 'messages' not in data or not isinstance(data['messages'], list):
            return jsonify({"error": "Invalid export file: Missing 'messages' array."}), 400
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format in the uploaded file."}), 400
    except Exception as e:
        return jsonify({"error": "Could not read the uploaded file."}), 400

    raw_messages = data.get('messages', [])
    human_indices = [i for i, msg in enumerate(raw_messages) if msg.get('role') in ['human', 'user']]

    is_truncated = False

    if len(human_indices) > MAX_MESSAGES_PER_CHAT:
        cutoff_index = human_indices[-MAX_MESSAGES_PER_CHAT]
        raw_messages = raw_messages[cutoff_index:]
        is_truncated = True
        logging.info(f"Imported chat was too large. Truncated to the last {MAX_MESSAGES_PER_CHAT} human messages.")

    try:
        user_obj = current_user._get_current_object()
        agent_id = user_obj.agent_id if user_obj.agent_id else 'global'
        chats = HistoryMetadata.get_user_chats(user_obj.id, limit=5000)
        current_chats = len(chats)

        if current_chats >= MAX_CHATS_PER_USER:
            excess = current_chats - MAX_CHATS_PER_USER + 1
            unpinned_chats = sorted([c for c in chats if not c['is_pinned']], key=lambda x: x['updated_at'])
            pinned_chats = sorted([c for c in chats if c['is_pinned']], key=lambda x: x['updated_at'])
            ordered_chats = unpinned_chats + pinned_chats

            chats_to_delete = ordered_chats[:excess]

            if not force_overwrite:
                targets = [c['title'] for c in chats_to_delete]
                return jsonify({
                    "error": "limit_reached",
                    "type": "chats",
                    "limit": MAX_CHATS_PER_USER,
                    "current": current_chats,
                    "targets_to_delete": targets
                }), 409
            else:
                for c in chats_to_delete:
                    HistoryMetadata.delete_chat(c['thread_id'])

        thread_id = str(uuid.uuid4())

        chatbot = user_obj.get_or_create_chatbot()
        messages = []

        for msg in raw_messages:
            role = msg.get('role')
            content = msg.get('content', '')
            if role in ['human', 'user']:
                messages.append(HumanMessage(content=content))
            elif role in ['ai', 'assistant']:
                kwargs = {'content': content}
                kwargs['response_metadata'] = {'imported': True}
                chatbot_llm = msg.get('chatbot_llm')
                if chatbot_llm:
                    kwargs['response_metadata']['model_name'] = chatbot_llm

                tool_calls = msg.get('tool_calls')
                if tool_calls:
                    kwargs['tool_calls'] = tool_calls

                messages.append(AIMessage(**kwargs))

            elif role == 'tool':
                kwargs = {
                    'content': content,
                    'tool_call_id': msg.get('tool_call_id', ''),
                    'name': msg.get('tool_name', 'tool')
                }
                artifact = msg.get('artifact')
                if artifact:
                    kwargs['artifact'] = artifact

                messages.append(ToolMessage(**kwargs))

        # Repair mid-stream interruped tools calls and record a synthetic errored result
        answered_call_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
        repaired_messages = []
        for m in messages:
            repaired_messages.append(m)
            for call in (getattr(m, 'tool_calls', None) or []):
                call_id = call.get('id')
                if call_id and call_id not in answered_call_ids:
                    repaired_messages.append(ToolMessage(
                        content=INTERRUPTED_TOOL_CALL_CONTENT,
                        tool_call_id=call_id,
                        name=call.get('name', 'tool'),
                        status='error',
                        artifact=INTERRUPTED_TOOL_CALL_ARTIFACT,
                    ))
        messages = repaired_messages

        if messages:
            chatbot.agent.update_state({"configurable": {"thread_id": thread_id}}, {"messages": messages})

        title = data.get('title')
        if not title:
            first_q = next((m.get('content', '') for m in raw_messages if m.get('role') in ['human', 'user']), "Imported Chat")
            title = (first_q[:30] + '...') if len(first_q) > 30 else first_q
        HistoryMetadata.save_new_chat(thread_id, user_obj.id, agent_id, title)

        return jsonify({
            "success": True,
            "thread_id": thread_id,
            "agent_id": agent_id,
            "title": title,
            "was_truncated": is_truncated,
            "max_messages": MAX_MESSAGES_PER_CHAT
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/api/clear_history', methods=['POST'])
@login_required
def clear_history():
    """Clear the chat history for the current user."""
    current_user.chatbot = None
    return jsonify({"message": f"Chat history cleared for user {current_user.id}"})

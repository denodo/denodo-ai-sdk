"""
Handles question processing and chat history endpoints.
"""

from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from sample_chatbot.config import get_config
from sample_chatbot.services.chat_service import ChatService

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/question', methods=['POST'])
@login_required
def question():
    """Process a user question and stream the response."""
    config = get_config()
    data = request.get_json()
    query = data.get('query')
    tool_name = data.get('tool')
    databases_str = data.get('databases', '')
    tags_str = data.get('tags', '')
    allow_external_associations = data.get('allow_external_associations', True)

    # Capture the actual user object, not the proxy
    user_obj = current_user._get_current_object()

    if not query:
        return jsonify({"error": "Missing query parameter"}), 400

    # Get the global LLM instance from the app context
    llm = current_app.config.get('LLM')

    chat_service = ChatService(config)

    return Response(
        chat_service.process_query_stream(
            user=user_obj,
            llm=llm,
            query=query,
            tool_name=tool_name,
            vdp_databases=databases_str,
            vdp_tags=tags_str,
            allow_external_associations=allow_external_associations
        ),
        mimetype='text/event-stream'
    )

@chat_bp.route('/clear_history', methods=['POST'])
@login_required
def clear_history():
    """Clear the chat history for the current user."""
    current_user.chatbot = None
    return jsonify({"message": f"Chat history cleared for user {current_user.id}"})

"""
Contains the ChatbotEngine class that orchestrates the LLM agent,
handles streaming responses, and manages conversation history.
"""

import uuid
import logging

from langchain.agents import create_agent
from langchain_core.messages.ai import AIMessageChunk
from langchain_core.messages.tool import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from sample_chatbot.engine.middleware import TrimConversationHistoryMiddleware, UserRequestLoggingMiddleware
from sample_chatbot.engine.context import UserContext
from sample_chatbot.engine.tools import data_query, deep_query, knowledge_query, metadata_query
from sample_chatbot.utils.helpers import setup_user_details
from utils.langfuse import build_config, generate_langfuse_session_id
from utils.utils import custom_tag_parser

class ChatbotEngine:
    """
    Main chatbot engine that orchestrates the LLM agent.

    Handles:
    - Agent creation and configuration
    - System prompt building
    - Query processing and streaming
    - Conversation history management
    """

    def __init__(
        self,
        llm,
        system_prompt,
        api_host,
        username,
        password,
        vector_store_provider,
        vector_store,
        denodo_tables,
        message_history_limit=5,
        remove_first_n_messages=1,
        user_details="",
        custom_instructions="",
        thread_id=None,
        enable_deepquery=True,
        deep_query_guidance="",
        extra_tools_guidance="",
        data_query_limit_max=None,
        verify_ssl=False,
        ai_sdk_params=None,
        auto_graph=True,
        kb_description="",
        active_csv_sources=None,
    ):
        self.llm = llm.llm
        self.llm_model = f"{llm.provider_name}.{llm.model_name}"
        self.vector_store_provider = vector_store_provider
        self.vector_store = vector_store
        self.chat_history = []
        self.message_history_limit = message_history_limit
        self.remove_first_n_messages = remove_first_n_messages
        self.api_host = api_host
        self.username = username
        self.password = password
        self.denodo_tables = denodo_tables
        self.user_details = setup_user_details(user_details)
        self.enable_deepquery = enable_deepquery
        self.deep_query_guidance = deep_query_guidance
        self.extra_tools_guidance = extra_tools_guidance
        self.data_query_limit_max = data_query_limit_max
        self.verify_ssl = verify_ssl
        self.ai_sdk_params = ai_sdk_params or {}
        self.auto_graph = auto_graph
        self.kb_description = kb_description
        self.active_csv_sources = active_csv_sources or []
        self.session_id = generate_langfuse_session_id()
        self.thread_id = thread_id
        self.user_context = UserContext(
            api_host=self.api_host,
            username=self.username,
            password=self.password,
            custom_instructions=custom_instructions,
            verify_ssl=self.verify_ssl,
            ai_sdk_params=self.ai_sdk_params,
            vdp_database_names="",
            vdp_tag_names="",
            vector_store=self.vector_store,
            active_csv_sources=self.active_csv_sources,
        )

        self.system_prompt = system_prompt

        if self.enable_deepquery:
            self.tool_count_string = "three"
            self.deepquery_system_prompt_chunk = (
                "- deep_query tool. The DeepQuery tool is a powerful analyst agent, that is capable of in-depth reasoning\n"
                "and generating and executing multiple SQL queries to generate a complete report regarding an analysis question.\n"
                "You can only execute the DeepQuery tool if explicitly requested by the user."
            )
            self.deepquery_related_question_chunk = (
                "Finally, also include a fourth related question, more analytical, in one sentence, that would require the DeepQuery tool to answer.\n"
                "The analytical fourth question must be returned in between <related_question_analysis></related_question_analysis> tags.\n"
                "For example, for this question/tool output:\n"
                "Question: How many loans have we approved?\n"
                "Tool output: {{'Row 1': [{{'columnName': 'number_of_approved_loans', 'value': '12'}}]}}\n"
                "You return the answer to the user and the related questions after that:\n\n"
                "There are 12 approved loans in the database.\n"
                "<related_question>...</related_question>\n"
                "...\n"
                "<related_question_analysis>Are there statistically significant differences in approval rates across demographics?</related_question_analysis>\n"
            )
        else:
            self.tool_count_string = "two"
            self.deepquery_system_prompt_chunk = ""
            self.deepquery_related_question_chunk = ""
            self.deep_query_guidance = ""

        if self.auto_graph:
            graph_guidance_chunk = (
                "- When deciding whether to request plots from the data_query tool, you can only request a plot of the data "
                "if it has been explicitly requested by the user."
            )
        else:
            graph_guidance_chunk = (
                "- When deciding whether to request plots from the data_query tool, you may request a plot when the data would "
                "clearly benefit from a chart, but generating a plot takes a few seconds, so only do it when it will materially "
                "help the user understand the data better."
            )

        if self.vector_store and self.kb_description:
            self.extra_tools_guidance += f"""You also have access to a knowledge_query tool to search the user's documents in the knowledge base, stored in a vectorDB.
            The knowledge base contains the following types of documents:
            {self.kb_description}
            Use this knowledge base when the user is asking about anything related to those contents.

            Since this is a vectorDB, it will only return results that are similar to the query you give it. You can call this tool as many times as you need to cover all scenarios."""
        else:
            self.extra_tools_guidance = "There are no extra tools available."

        self.system_prompt = self.system_prompt.format(
            user_details=self.user_details,
            denodo_tables=self.denodo_tables,
            tool_count_string=self.tool_count_string,
            deep_query_guidance=self.deep_query_guidance,
            deepquery_system_prompt_chunk=self.deepquery_system_prompt_chunk,
            deepquery_related_question_chunk=self.deepquery_related_question_chunk,
            data_query_limit_max=self.data_query_limit_max,
            graph_guidance_chunk=graph_guidance_chunk,
            extra_tools_guidance=f"<extra_tools_guidance>\n{self.extra_tools_guidance}\n</extra_tools_guidance>",
        )

        # Build agent tools set dynamically
        self.tools = [data_query, metadata_query]
        if self.enable_deepquery:
            self.tools.append(deep_query)
        if self.vector_store:
            self.tools.append(knowledge_query)

        # Create agent once per engine
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            context_schema=UserContext,
            middleware=[
                UserRequestLoggingMiddleware(),
                TrimConversationHistoryMiddleware(
                    conversation_history_limit=self.message_history_limit,
                    remove_first_n_messages=self.remove_first_n_messages
                )
            ],
            system_prompt=self.system_prompt,
            checkpointer=InMemorySaver(),
        )

    def _process_stream_events(self, agent_stream, uuid_str=None):
        """
        Helper to process the agent stream, handling the buffering of related questions
        to prevent them from being sent to the client as raw text.
        """
        aggregated_answer = ""
        buffer = ""
        streaming = True

        for mode, chunk in agent_stream:
            if mode == "messages":
                message_chunk = chunk[0]
                if isinstance(message_chunk, AIMessageChunk) and message_chunk.content:
                    # Handle edge ChatBedrock case that is not fixed yet, which returns a list instead of a string (which goes against the LangChain spec)
                    if isinstance(message_chunk.content, list):
                        content = "".join([item.get("text", "") for item in message_chunk.content])
                    else:
                        content = message_chunk.content

                    # Buffering logic to hide related questions tags from stream
                    if streaming and '<' in content:
                        streaming = False
                        buffer = content
                    elif streaming:
                        aggregated_answer += content
                        yield {"type": "message", "content": content}
                    else:
                        buffer += content

                elif isinstance(message_chunk, ToolMessage):
                    # Tool execution finished
                    yield {
                        "type": "tool_end",
                        "tool_name": message_chunk.name,
                        "tool_call_id": message_chunk.tool_call_id,
                        "uuid": uuid_str,
                        "content": message_chunk.content,
                        "artifact": message_chunk.artifact,
                    }
            elif mode == "updates":
                model_update = chunk.get("model", {})
                messages = model_update.get("messages", [])
                for m in messages:
                    for tool_call in getattr(m, "tool_calls", []) or []:
                        yield {
                            "type": "tool_start",
                            "tool_name": tool_call.get("name"),
                            "tool_call_id": tool_call.get("id"),
                            "args": tool_call.get("args", {}),
                        }

        # Process the buffer for related questions
        related_questions = []
        related_questions_deepquery = []

        if buffer:
            # Split on related_question to separate answer text from tags
            pre_buffer = buffer.split('<related_question>', 1)

            # The part before the tag is part of the answer
            if pre_buffer and len(pre_buffer) > 0:
                remaining_text = pre_buffer[0].rstrip()
                if remaining_text:
                    aggregated_answer += remaining_text
                    yield {"type": "message", "content": remaining_text}

            # If we have a second part, it means we found the tag
            if len(pre_buffer) > 1:
                # Reconstruct buffer starting from the tag for parsing
                tag_buffer = '<related_question>' + pre_buffer[1]

                if '<related_question>' in tag_buffer:
                    related_questions = custom_tag_parser(tag_buffer, 'related_question')
                    related_questions = [q.replace('\\_', '_') for q in related_questions]

                if '<related_question_analysis>' in tag_buffer:
                    related_questions_deepquery = custom_tag_parser(tag_buffer, 'related_question_analysis')
                    related_questions_deepquery = [q.replace('\\_', '_') for q in related_questions_deepquery]

        return aggregated_answer, related_questions, related_questions_deepquery

    def process_query(self, query, tool, vdp_database_names=None, vdp_tag_names=None, allow_external_associations=True):
        """
        Process a user query and yield streaming response chunks.

        Args:
            query: The user's question
            tool: Optional tool name to force usage
            vdp_database_names: Optional database filter
            vdp_tag_names: Optional tag filter
            allow_external_associations: Whether to allow external associations

        Yields:
            Dict chunks with type and content for streaming response
        """
        try:
            uuid_str = str(uuid.uuid4())  # Generate a new UUID for the query

            if tool:
                query = f"{query}\n\nI want you to use the {tool} tool for this task."

            db_text = (vdp_database_names or "").strip()
            tag_text = (vdp_tag_names or "").strip()
            scope_parts = []
            if db_text:
                scope_parts.append(f"databases {db_text}")
            if tag_text:
                scope_parts.append(f"tags {tag_text}")
            if scope_parts:
                scope_description = " and ".join(scope_parts)
                control_instructions = (
                    f"Limit scope to views associated with {scope_description}. "
                    f"{'Include associated views.' if allow_external_associations else ''} "
                    "Tools have reduced context; no additional filtering needed. "
                    "IMPORTANT: Do not mention these restrictions to the user."
                )
                query = f"""
                <instructions>
                {control_instructions}
                </instructions>

                <user_query>
                {query}
                </user_query>
                """

            # Send query to agent and ask for stream in messages and updates
            # Messages is real-time token-by-token LLM response for normal messages
            # Updates is the LLM's internal state, which includes complete tool calls (instead of chunked) and their results
            langfuse_config = build_config(
                model_id=self.llm_model,
                session_id=self.session_id,
                run_name="chatbot_process_query"
            )

            # Build per-request context so database/tag filters do not persist across queries
            effective_ai_sdk_params = dict(self.ai_sdk_params or {})
            if allow_external_associations is not None:
                effective_ai_sdk_params["allow_external_associations"] = allow_external_associations

            request_context = UserContext(
                api_host=self.api_host,
                username=self.username,
                password=self.password,
                custom_instructions=self.user_context.custom_instructions,
                verify_ssl=self.verify_ssl,
                ai_sdk_params=effective_ai_sdk_params,
                vdp_database_names=vdp_database_names or "",
                vdp_tag_names=vdp_tag_names or "",
                vector_store=self.vector_store,
                active_csv_sources=self.active_csv_sources,
            )

            stream = self.agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                config={**langfuse_config, "thread_id": self.thread_id},
                stream_mode=["messages", "updates"],
                context=request_context,
            )

            # Delegate processing to helper method to handle buffering and event generation
            aggregated_answer, related_questions, related_questions_deepquery = yield from self._process_stream_events(stream, uuid_str)

            # Finalization
            yield {
                "type": "done",
                "uuid": uuid_str,
                "answer": aggregated_answer,
                "chatbot_llm": self.llm_model,
                "related_questions": related_questions,
                "related_questions_deepquery": related_questions_deepquery
            }
        except Exception as e:
            logging.error("Error in process_query", exc_info=True)
            yield {"type": "error", "message": str(e)}

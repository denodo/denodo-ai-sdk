"""
Contains the ChatbotEngine class that orchestrates the LLM agent,
handles streaming responses, and manages conversation history.
"""

import uuid
import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.messages.ai import AIMessageChunk
from langchain_core.messages.tool import ToolMessage

from sample_chatbot.engine.context_window import prepare_model_messages
from sample_chatbot.engine.middleware import (
    ContextWindowMiddleware,
    ToolDurationMiddleware,
)
from sample_chatbot.engine.context import UserContext
from sample_chatbot.engine.memory import render_user_memories_content, strip_memory_prompt
from sample_chatbot.engine.skills import build_skills_prompt_section
from sample_chatbot.engine.tools import (
    generate_vql,
    execute_vql,
    generate_graph,
    deep_query,
    knowledge_query,
    metadata_search,
    read_skill,
    read_skill_reference,
    edit_skill,
    edit_skill_reference,
    create_skill,
    create_skill_reference,
    read_memory,
    list_memories,
    write_memory,
    delete_memory,
)
from sample_chatbot.utils.helpers import setup_user_details, format_user_instructions_for_prompt, format_chat_log
from utils.langfuse import build_config
from utils.utils import custom_tag_parser, calculate_tokens, safe_str
from utils.database_utils import UniformCheckpointer
from utils.denodo_tools import AISDKRequestCancelled

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
        context_window=128000,
        user_details="",
        ai_sdk_custom_instructions="",
        chatbot_custom_instructions="",
        enable_deepquery=True,
        extra_tools_guidance="",
        skills=None,
        can_manage_skills=False,
        agent_id="global",
        allowed_system_skills=None,
        disabled_skills=None,
        verify_ssl=False,
        ai_sdk_params=None,
        auto_graph=True,
        kb_description="",
        active_csv_sources=None,
        kb_collections=None,
        timeout=1200,
        memory_enabled=True,
        share_general_memory=True,
    ):
        self.llm = llm.llm
        self.max_output_tokens = llm.max_tokens
        self.llm_model = f"{llm.provider_name}.{llm.model_name}"
        self.vector_store_provider = vector_store_provider
        self.vector_store = vector_store
        self.chat_history = []
        self.context_window = context_window
        self.api_host = api_host
        self.username = username
        self.password = password
        self.user_details = setup_user_details(user_details)
        self.enable_deepquery = enable_deepquery
        self.extra_tools_guidance = extra_tools_guidance
        self.skills = skills or {}
        self.can_manage_skills = can_manage_skills
        self.agent_id = agent_id
        self.allowed_system_skills = allowed_system_skills
        self.disabled_skills = disabled_skills
        self.verify_ssl = verify_ssl
        self.ai_sdk_params = ai_sdk_params or {}
        self.auto_graph = auto_graph
        self.kb_description = kb_description
        self.active_csv_sources = active_csv_sources or []
        self.kb_collections = kb_collections or {}
        self.memory_enabled = bool(memory_enabled)
        self.share_general_memory = bool(share_general_memory)
        self.ai_sdk_custom_instructions = (ai_sdk_custom_instructions or "").strip()
        self.timeout = timeout
        self.user_context = UserContext(
            api_host=self.api_host,
            username=self.username,
            password=self.password,
            ai_sdk_custom_instructions=self.ai_sdk_custom_instructions,
            verify_ssl=self.verify_ssl,
            ai_sdk_params=self.ai_sdk_params,
            timeout=self.timeout,
            vdp_database_names=[],
            vdp_tag_names=[],
            vector_store=self.vector_store,
            active_csv_sources=self.active_csv_sources,
            kb_collections=self.kb_collections,
            can_manage_skills=self.can_manage_skills,
            agent_id=self.agent_id,
            memory_enabled=self.memory_enabled,
            share_general_memory=self.share_general_memory,
            allowed_system_skills=self.allowed_system_skills,
            disabled_skills=self.disabled_skills,
        )

        self.system_prompt = system_prompt

        if self.enable_deepquery:
            self.tool_count_string = "five"
            self.deepquery_system_prompt_chunk = (
                "- You also have access to the deep_query tool, which gives you access to the DeepQuery agent. DeepQuery is a powerful, autonomous analyst agent, that is capable of in-depth reasoning\n"
                "and generating complete HTML reports regarding an analysis question.\n"
                "The deep_query tool is ASYNCHRONOUS: it starts a background job and returns immediately with a confirmation, never with the analysis results. Its `languages` argument accepts several languages (for example ['English', 'French']) and queues one report per language. If the user does not specify any language, use the language of the conversation.\n"
                "After calling it, tell the user the job was started and that they can follow its progress and open the report from the DeepQuery Reports Manager in the header. Never say the analysis or the report is finished, and never invent findings.\n"
                "You can only execute the DeepQuery tool if explicitly requested by the user.\n"
                "Before proposing or running any DeepQuery analysis, you MUST read the 'deepquery' skill with read_skill(\"deepquery\") and follow its process. If the skill is not available, you cannot use the DeepQuery tool."
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
            self.tool_count_string = "four"
            self.deepquery_system_prompt_chunk = ""
            self.deepquery_related_question_chunk = ""

        if not self.auto_graph:
            graph_guidance_chunk = "- You can only request a plot of the data using the generate_graph tool if it has been explicitly requested by the user."
        else:
            graph_guidance_chunk = ""

        if self.vector_store and self.kb_description:
            self.extra_tools_guidance += f"""You also have access to a knowledge_query tool to search the user's knowledge base, stored in a vectorDB.
            The knowledge base is organised into the following collections:
            {self.kb_description}
            When the user's request is related to one or more of the collections above, you must use the knowledge_query tool to search the knowledge base to ground your answer.
            You must pass the exact name of one collection from the list above as the 'collection' argument on every call to knowledge_query to filter results per collection. If the user's request spans more than one collection, call the tool once per collection.
            Since this is a vectorDB, it will only return results that are similar to the query you give it. You can call this tool as many times as you need to cover all scenarios.
            Whenever the results include URLs as sources, you must cite along your response the specific URLs you used for your answer by formatting them as markdown links (i.e, [1](url1), [2](url2)...)"""
        else:
            self.extra_tools_guidance = "There are no extra tools available."

        skills_guidance = build_skills_prompt_section(self.skills, can_manage_skills=self.can_manage_skills)
        self.skills_prompt_section = skills_guidance

        # The memory index is fixed here, when the engine is built. A memory
        # written during a conversation only appears once the engine is
        # rebuilt (new chat, agent switch, or settings change).
        memories_content = ""
        if self.memory_enabled:
            memories_content = render_user_memories_content(
                self.username, self.agent_id, self.share_general_memory
            )

        self.system_prompt = self.system_prompt.format(
            user_details=self.user_details,
            memories=memories_content,
            custom_instructions=format_user_instructions_for_prompt(chatbot_custom_instructions),
            tool_count_string=self.tool_count_string,
            skills_guidance=skills_guidance,
            deepquery_system_prompt_chunk=self.deepquery_system_prompt_chunk,
            deepquery_related_question_chunk=self.deepquery_related_question_chunk,
            graph_guidance_chunk=graph_guidance_chunk,
            extra_tools_guidance=f"<extra_tools_guidance>\n{self.extra_tools_guidance}\n</extra_tools_guidance>",
        )
        if not self.memory_enabled:
            self.system_prompt = strip_memory_prompt(self.system_prompt)

        # Build agent tools set dynamically
        self.tools = [generate_vql, execute_vql, generate_graph, metadata_search]
        if self.enable_deepquery:
            self.tools.append(deep_query)
        # Only when the user actually has active collections: with none, the
        # tool could only ever refuse, so it is not exposed to the LLM at all
        # (activating a collection rebuilds the engine, which re-adds it).
        if self.vector_store and self.kb_collections:
            self.tools.append(knowledge_query)

        # Skill tools: reading and personal skill management are available to
        # everyone; system skill reference management only for authorized users
        # so unauthorized users never even see those tools.
        self.tools.extend([read_skill, read_skill_reference, create_skill, edit_skill])
        if self.can_manage_skills:
            self.tools.extend([edit_skill_reference, create_skill_reference])

        # Memory is per Denodo user. This agent forms and uses it only when
        # memory is turned on for the agent.
        if self.memory_enabled:
            self.tools.extend([read_memory, list_memories, write_memory, delete_memory])

        # Initialize the persistent database-backed checkpointer
        self.checkpointer = UniformCheckpointer.get_saver()

        middleware = [
            ContextWindowMiddleware(
                context_window=self.context_window,
                max_output_tokens=self.max_output_tokens,
                skills_text=self.skills_prompt_section,
            ),
        ]
        middleware.append(ToolDurationMiddleware())

        # Create agent once per engine
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            context_schema=UserContext,
            middleware=middleware,
            system_prompt=self.system_prompt,
            checkpointer=self.checkpointer,
        )

    def _process_stream_events(self, agent_stream, uuid_str=None, thread_id=None):
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
                    # Log tool calls (response tokens and truncated content)
                    tool_tokens = calculate_tokens(str(message_chunk.content)) if message_chunk.content else 0
                    logging.info(
                        f"{format_chat_log(self.agent_id, thread_id, 'tool_response', tool_tokens)} "
                        f"'{message_chunk.name}' -> {safe_str(message_chunk.content, 200)}"
                    )

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
                        # Log tool calls (args)
                        logging.info(
                            f"{format_chat_log(self.agent_id, thread_id, 'tool_call')} "
                            f"'{tool_call.get('name')}' Args: {tool_call.get('args')}"
                        )

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

    def context_usage(self, thread_id=None):
        """Token breakdown of the next model call for this thread, after compaction and view deduplication."""
        messages = []
        if thread_id:
            try:
                snapshot = self.agent.get_state({"configurable": {"thread_id": thread_id}})
                if snapshot and getattr(snapshot, "values", None):
                    messages = snapshot.values.get("messages") or []
            except Exception:
                logging.debug("Could not read conversation state for context usage", exc_info=True)

        _, usage = prepare_model_messages(
            messages=messages,
            system_text=self.system_prompt,
            tools=self.tools,
            skills_text=self.skills_prompt_section,
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
        )
        return usage

    def process_query(self, query, tool, vdp_database_names=None, vdp_tag_names=None, allow_external_associations=False, thread_id=None, cancel_event=None):
        """
        Process a user query and yield streaming response chunks.

        Args:
            query: The user's question
            tool: Optional tool name to force usage
            vdp_database_names: Optional database filter
            vdp_tag_names: Optional tag filter
            allow_external_associations: Whether to allow external associations
            thread_id: Request-scoped thread ID to prevent concurrency mutations

        Yields:
            Dict chunks with type and content for streaming response
        """
        try:
            uuid_str = str(uuid.uuid4())  # Generate a new UUID for the query

            # Log user question and tokens
            question_tokens = calculate_tokens(str(query)) if query else 0
            logging.info(
                f"{format_chat_log(self.agent_id, thread_id, 'user_question', question_tokens)} "
                f"{safe_str(query)}"
            )

            if tool:
                query = f"{query}\n\nI want you to use the {tool} tool for this task."

            vdp_database_names = vdp_database_names or []
            vdp_tag_names = vdp_tag_names or []

            scope_parts = []
            if vdp_database_names:
                scope_parts.append(f"databases {', '.join(vdp_database_names)}")
            if vdp_tag_names:
                scope_parts.append(f"tags {', '.join(vdp_tag_names)}")

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
                session_id=thread_id,
                user_id=self.username,
                run_name=f"chatbot_ui:{self.agent_id or 'global'}",
                extra_metadata={
                    "agent_id": self.agent_id or "global",
                    "langfuse_tags": [f"agent:{self.agent_id or 'global'}", "sample_chatbot"],
                },
            )

            # Build per-request context so database/tag filters do not persist across queries
            effective_ai_sdk_params = dict(self.ai_sdk_params or {})
            if allow_external_associations is not None:
                effective_ai_sdk_params["allow_external_associations"] = allow_external_associations

            request_context = UserContext(
                api_host=self.api_host,
                username=self.username,
                password=self.password,
                ai_sdk_custom_instructions=self.user_context.ai_sdk_custom_instructions,
                verify_ssl=self.verify_ssl,
                ai_sdk_params=effective_ai_sdk_params,
                timeout=self.timeout,
                vdp_database_names=vdp_database_names,
                vdp_tag_names=vdp_tag_names,
                vector_store=self.vector_store,
                active_csv_sources=self.active_csv_sources,
                kb_collections=self.kb_collections,
                can_manage_skills=self.can_manage_skills,
                agent_id=self.agent_id,
                memory_enabled=self.memory_enabled,
                share_general_memory=self.share_general_memory,
                allowed_system_skills=self.allowed_system_skills,
                disabled_skills=self.disabled_skills,
                cancel_event=cancel_event,
                thread_id=thread_id,
            )

            human_msg = HumanMessage(content=query, id=uuid_str)

            stream = self.agent.stream(
                {"messages": [human_msg]},
                config={**langfuse_config, "configurable": {"thread_id": thread_id}},
                stream_mode=["messages", "updates"],
                context=request_context,
            )

            # Delegate processing to helper method to handle buffering and event generation
            aggregated_answer, related_questions, related_questions_deepquery = yield from self._process_stream_events(
                stream, uuid_str, thread_id=thread_id
            )

            # Log response (truncated to 200 chars) and tokens
            response_tokens = calculate_tokens(aggregated_answer) if aggregated_answer else 0
            logging.info(
                f"{format_chat_log(self.agent_id, thread_id, 'agent_response', response_tokens)} "
                f"{safe_str(aggregated_answer, 200)}"
            )

            # Finalization
            yield {
                "type": "done",
                "uuid": uuid_str,
                "answer": aggregated_answer,
                "chatbot_llm": self.llm_model,
                "related_questions": related_questions,
                "related_questions_deepquery": related_questions_deepquery,
                "context_usage": self.context_usage(thread_id),
            }
        except AISDKRequestCancelled as e:
            logging.info(f"Query cancelled by the user: {e}")
            yield {"type": "error", "message": str(e)}
        except Exception as e:
            logging.error("Error in process_query", exc_info=True)
            yield {"type": "error", "message": str(e)}

import uuid
import inspect
import traceback
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.utils import add_langfuse_callback, generate_langfuse_session_id, custom_tag_parser
from sample_chatbot.chatbot_utils import process_tool_query, add_to_chat_history, readable_tool_result, parse_xml_tags, trim_conversation, setup_user_details

class ChatbotEngine:
    def __init__(self, llm, llm_response_rows_limit, system_prompt, tool_selection_prompt, related_questions_prompt, tools, api_host, username, password, vector_store_provider, denodo_tables, message_history = 10, user_details = ""):
        self.llm = llm.llm
        self.llm_response_rows_limit = llm_response_rows_limit
        self.llm_model = f"{llm.provider_name}.{llm.model_name}"
        self.vector_store_provider = vector_store_provider
        self.chat_history = []
        self.tools = tools
        self.session_id = generate_langfuse_session_id()
        self.system_prompt = system_prompt
        self.tool_selection_prompt = tool_selection_prompt
        self.related_questions_prompt = related_questions_prompt
        self.message_history = message_history
        self.api_host = api_host
        self.username = username
        self.password = password
        self.wait_phrases = ["Give me a second", "Please wait", "Hold on", "Just a moment", "I'm working on it", "I'm looking into it", "I'm checking it out", "I'm on it"]
        self.denodo_tables = denodo_tables
        self.user_details = setup_user_details(user_details)
        self.tool_execution_history = []
        self.tools_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages=self.message_history),
            ("human", "{input}\n\n{force_tool}" + self.tool_selection_prompt + "\n\n{force_tool}"),
        ])

        self.answer_with_tool_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages = self.message_history),
            ("human", "{input}" + "\n{tool_query}\n" + self.related_questions_prompt),
        ])

        # Alternative prompt without related questions for odd deep_query calls
        self.answer_with_tool_prompt_no_related = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages = self.message_history),
            ("human", "{input}" + "\n{tool_query}"),
        ])

        self.tool_selection_chain = (
            self.tools_prompt
            | self.llm
            | StrOutputParser()
        )

        self.answer_with_tool_chain = (
            self.answer_with_tool_prompt
            | self.llm
            | StrOutputParser()
        )

        self.answer_with_tool_chain_no_related = (
            self.answer_with_tool_prompt_no_related
            | self.llm
            | StrOutputParser()
        )

    def process_query(self, query, tool = None):
        if tool == "data":
            tool = "database_query"
        elif tool == "metadata":
            tool = "metadata_query"
        elif tool == "deep_query":
            tool = "deep_query"
        else:
            tool = None

        try:
            force_tool = f"The user requested to use the tool {tool} for this query. If a user requests a tool, you must use it, without asking for any confirmation." if tool else ""

            first_input = self.tool_selection_chain.invoke(
                {"input": query,
                 "chat_history": self.chat_history,
                 "force_tool": force_tool,
                 "denodo_tables": self.denodo_tables,
                 "user_details": self.user_details},
                config={
                    "callbacks": add_langfuse_callback(self.llm_model, self.session_id),
                    "run_name": inspect.currentframe().f_code.co_name,
                }
            )

            if force_tool:
                query += "\n\n" + force_tool

            # Send selected tool to the frontend
            parsed_query = parse_xml_tags(first_input)

            for tool_name, _ in self.tools.items():
                if tool_name in parsed_query:
                    yield from self._yield_tool_status_message(parsed_query, tool_name)
                    break  # Only process the first matching tool

            tool_result = process_tool_query(first_input, self.tools, self.tool_execution_history)
            if tool_result:
                tool_name, tool_output, original_xml_call = tool_result
                readable_tool_output = readable_tool_result(tool_name, tool_output, self.llm_response_rows_limit)
                # Check if this is an odd deep_query call to exclude related questions
                use_related_questions = True
                if tool_name == "deep_query_schema_check":
                    use_related_questions = False

                # Choose the appropriate chain based on whether to include related questions
                if use_related_questions:
                    ai_stream = self.answer_with_tool_chain.stream({
                        "input": query,
                        "chat_history": self.chat_history,
                        "tool_query": readable_tool_output,
                        "denodo_tables": self.denodo_tables,
                        "user_details": self.user_details
                    },
                    config = {
                        "callbacks": add_langfuse_callback(self.llm_model, self.session_id),
                        "run_name": inspect.currentframe().f_code.co_name,
                    })
                else:
                    ai_stream = self.answer_with_tool_chain_no_related.stream({
                        "input": query,
                        "chat_history": self.chat_history,
                        "tool_query": readable_tool_output,
                        "denodo_tables": self.denodo_tables,
                        "user_details": self.user_details
                    },
                    config = {
                        "callbacks": add_langfuse_callback(self.llm_model, self.session_id),
                        "run_name": inspect.currentframe().f_code.co_name,
                    })
            else:
                ai_stream = first_input
                tool_name, tool_output, original_xml_call = "direct_response", "", ""

            ai_response = ""
            buffer = ""
            streaming = True

            for chunk in ai_stream:
                ai_response += chunk

                if streaming and '<' in chunk:
                    streaming = False
                    buffer = chunk
                elif streaming:
                    yield chunk
                else:
                    buffer += chunk

            pre_buffer = buffer.split('<related_question>', 1)

            if pre_buffer and len(pre_buffer) > 0:
                yield pre_buffer[0].rstrip()
            else:
                yield ""  # Yield empty string if pre_buffer is empty or None

            if len(pre_buffer) > 1:
                buffer = '<related_question>' + pre_buffer[1]
                # Parse related questions from the final buffer if it contains any
                if '<related_question>' in buffer:
                    related_questions = custom_tag_parser(buffer, 'related_question')
                    # Sometimes the LLM escapes the underscore character
                    related_questions = [question.replace('\\_', '_') for question in related_questions]

                # Parse DeepQuery questions from the final buffer if it contains any
                if '<related_question_analysis>' in buffer:
                    related_questions_deepquery = custom_tag_parser(buffer, 'related_question_analysis')
                    # Sometimes the LLM escapes the underscore character
                    related_questions_deepquery = [question.replace('\\_', '_') for question in related_questions_deepquery]
                else:
                    related_questions_deepquery = []
            else:
                related_questions = []
                related_questions_deepquery = []

            return_data = {
                "uuid": str(uuid.uuid4()),
                "chatbot_llm": self.llm_model,
                "related_questions": related_questions,
                "related_questions_deepquery": related_questions_deepquery,
                "answer": ai_response
            }

            if tool_name == "database_query" and isinstance(tool_output, dict):
                return_data["vql"] = tool_output.get("sql_query", "")
                return_data["execution_result"] = tool_output.get("execution_result", "")
                return_data["graph"] = tool_output.get("raw_graph", "")
                return_data["tables_used"] = tool_output.get("tables_used", [])
                return_data["query_explanation"] = tool_output.get("query_explanation", "")
                return_data["tokens"] = tool_output.get("tokens", {}).get("total_tokens", 0)
                return_data["ai_sdk_time"] = tool_output.get("total_execution_time", 0)
            elif tool_name == "deep_query" and isinstance(tool_output, dict):
                return_data["answer"] = tool_output.get("answer", ai_response)
                return_data["deepquery_metadata"] = tool_output.get("deepquery_metadata", {})
                return_data["total_execution_time"] = tool_output.get("total_execution_time", 0)
            elif tool_name == "kb_lookup":
                return_data["data_sources"] = self.vector_store_provider

            yield return_data

            # Log return data except key 'deepquery_metadata' because it is too large to inspect
            # deepquery_metadata is received from the deepQuery endpoint and should be sent as-is to the PDF generation endpoint
            return_data_to_log = {k: v for k, v in return_data.items() if k != "deepquery_metadata"}
            logging.info(f"Return data: {return_data_to_log}")

            add_to_chat_history(
                chat_history = self.chat_history,
                human_query = query,
                ai_response = ai_response,
                tool_name = tool_name,
                tool_output = tool_output,
                original_xml_call = original_xml_call,
                llm_response_rows_limit = self.llm_response_rows_limit
            )

            self.chat_history = trim_conversation(self.chat_history)
        except Exception as e:
            traceback_info = traceback.format_exc()
            error_message = f"An error occurred: {str(e)}\n\nTraceback:\n{traceback_info}"
            logging.error(error_message)
            yield error_message
            yield {'error': str(e), 'traceback': str(traceback_info)}

    def _clean_query(self, text):
        """Helper method to ensure the query sent to the frontend has no newlines and ends with a period."""
        text = text.replace("\n", " ")
        return text.rstrip('.') + '.'

    def _yield_tool_status_message(self, parsed_query, tool_name):
        """Helper method to yield appropriate tool status messages to the frontend"""
        if tool_name == "database_query":
            natural_language_query = parsed_query.get("database_query", {}).get("natural_language_query", "")
            yield "<TOOL:data>"
            if natural_language_query:
                clean_query = self._clean_query(natural_language_query)
                yield f"Querying the Denodo AI SDK for: **{clean_query}**"
        elif tool_name == "metadata_query":
            search_query = parsed_query.get("metadata_query", {}).get("search_query", "")
            yield "<TOOL:metadata>"
            if search_query:
                clean_query = self._clean_query(search_query)
                yield f"Querying the Denodo AI SDK for: **{clean_query}**"
        elif tool_name == "deep_query":
            yield "<TOOL:deep_query>"
            analysis_request = parsed_query.get("deep_query", {}).get("analysis_request", "")
            if analysis_request:
                clean_request = self._clean_query(analysis_request)
                yield f"Starting DeepQuery analysis for: **{clean_request}**"
        elif tool_name == "kb_lookup":
            yield "<TOOL:kb>"
        else:
            yield "<TOOL:direct>"
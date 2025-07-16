import uuid
import inspect
import traceback
import logging
import random

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.utils import add_langfuse_callback, generate_langfuse_session_id, custom_tag_parser
from sample_chatbot.chatbot_utils import process_tool_query, add_to_chat_history, readable_tool_result, parse_xml_tags, trim_conversation, setup_user_details

RELATED_QUESTIONS_PROMPT = """
After I have answered the user's query, I will also provide a list of 3 related questions in plain text format (no markdown) that the user might ask next.
The questions should be closely related to the current conversation and should not require external information.
- Return each related question in between <related_question></related_question> tags. I will now answer:"""

class ChatbotEngine:
    def __init__(self, llm, llm_response_rows_limit, system_prompt, tool_selection_prompt, tools, api_host, username, password, vector_store_provider, denodo_tables, message_history = 4, user_details = ""):
        self.llm = llm.llm
        self.llm_callback = llm.callback
        self.llm_model = f"{llm.provider_name}.{llm.model_name}"
        self.llm_response_rows_limit = llm_response_rows_limit
        self.vector_store_provider = vector_store_provider
        self.chat_history = []
        self.tools = tools
        self.session_id = generate_langfuse_session_id()
        self.system_prompt = system_prompt
        self.tool_selection_prompt = tool_selection_prompt
        self.message_history = message_history
        self.api_host = api_host
        self.username = username
        self.password = password
        self.wait_phrases = ["Give me a second", "Please wait", "Hold on", "Just a moment", "I'm working on it", "I'm looking into it", "I'm checking it out", "I'm on it"]
        self.denodo_tables = denodo_tables
        self.user_details = setup_user_details(user_details)
        self.tools_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages=self.message_history),
            ("human", "{input}\n\n{force_tool}" + self.tool_selection_prompt + "\n\n{force_tool}"),
        ])

        self.answer_with_tool_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages = self.message_history),
            ("human", "{input}" + "\n{tool_query}\n" + RELATED_QUESTIONS_PROMPT),
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
        
    def process_query(self, query, tool = None):
        if tool == "data":
            tool = "database_query"
        elif tool == "metadata":
            tool = "metadata_query"
        else:
            tool = None
        try:
            force_tool = f"I want you to use the tool {tool} for this query." if tool else ""
            first_input = self.tool_selection_chain.invoke(
                {"input": query,
                 "chat_history": self.chat_history,
                 "force_tool": force_tool,
                 "denodo_tables": self.denodo_tables,
                 "user_details": self.user_details},
                config={
                    "callbacks": add_langfuse_callback(self.llm_callback, self.llm_model, self.session_id),
                    "run_name": inspect.currentframe().f_code.co_name,
                }
            )

            # Send selected tool to the frontend
            try:
                parsed_query = parse_xml_tags(first_input)
                for tool_name, _ in self.tools.items():
                    if tool_name in parsed_query:
                        if tool_name == "database_query":
                            natural_language_query = parsed_query["database_query"]["natural_language_query"]
                            yield "<TOOL:data>"
                            yield f"Querying the Denodo AI SDK for: **{natural_language_query}**. {random.choice(self.wait_phrases)}.\n\n"
                        elif tool_name == "metadata_query":
                            search_query = parsed_query["metadata_query"]["search_query"]
                            yield "<TOOL:metadata>"
                            yield f"Querying the Denodo AI SDK for: **{search_query}**. {random.choice(self.wait_phrases)}. Please note that the Metadata Tool works with similarity search (n = 5) and not exact match. For exact search, please use the Denodo Data Catalog.\n\n"
                        elif tool_name == "kb_lookup":
                            yield "<TOOL:kb>"
                        else:
                            yield "<TOOL:direct>"
            except Exception as e:
                yield 

            tool_result = process_tool_query(first_input, self.tools)
            if tool_result:
                tool_name, tool_output, original_xml_call = tool_result
                readable_tool_output = readable_tool_result(tool_name, tool_output, self.llm_response_rows_limit)
                ai_stream = self.answer_with_tool_chain.stream({
                    "input": query,
                    "chat_history": self.chat_history,
                    "tool_query": readable_tool_output,
                    "denodo_tables": self.denodo_tables,
                    "user_details": self.user_details
                },
                config = {
                    "callbacks": add_langfuse_callback(self.llm_callback, self.llm_model, self.session_id),
                    "run_name": inspect.currentframe().f_code.co_name,
                })
            else:
                ai_stream = first_input
                tool_name, tool_output, original_xml_call = "Direct Response", "", ""
            
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
            else:
                related_questions = []
    
            return_data = {
                "uuid": str(uuid.uuid4()),
                "vql": '',
                "data_sources": self.llm_model,
                "embeddings": None,
                "related_questions": related_questions,
                "execution_result": None,
                "tokens": 0,
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
            elif tool_name == "kb_lookup":
                return_data["data_sources"] = self.vector_store_provider
                
            logging.info(f"Return data: {return_data}")

            yield return_data

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
            error_message = f"An error occurred: {str(e)}"
            traceback_info = traceback.format_exc()
            yield f"Error: {error_message}\n\nTraceback:\n{traceback_info}"

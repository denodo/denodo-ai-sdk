import inspect
import traceback
import logging

from utils.utils import add_langfuse_callback, generate_langfuse_session_id
from langchain_core.output_parsers import StrOutputParser
from sample_chatbot.chatbot_utils import process_tool_query, add_to_chat_history, get_relevant_tables, readable_tool_result, parse_xml_tags
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

class ChatbotEngine:
    def __init__(self, llm, system_prompt, tool_selection_prompt, tools, api_host, username, password, vdp_database_names, vector_store_provider, message_history = 4):
        self.llm = llm.llm
        self.llm_callback = llm.callback
        self.llm_model = f"{llm.provider_name}.{llm.model_name}"
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
        self.vdp_database_names = vdp_database_names
        self.tools_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder("chat_history", n_messages=self.message_history),
            ("human", "{input}" + self.tool_selection_prompt + "\n\n{force_tool}"),
        ])

        self.answer_with_tool_prompt = ChatPromptTemplate.from_messages([
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

    def process_query(self, query, tool = None):
        if tool == "data":
            tool = "database_query"
        elif tool == "metadata":
            tool = "metadata_query"
        else:
            tool = None
        try:
            result, relevant_tables = get_relevant_tables(
                self.api_host,
                self.username,
                self.password,
                query,
                self.vdp_database_names
            )
            if result and relevant_tables:
                denodo_tables = "Some of the tables in the user's Denodo instance: " + ", ".join(relevant_tables) + "... Use the Metadata tool to query all."
            else:
                denodo_tables = "No views where found in the user's Denodo instance. Either the user has no views, the connection is not working or he does not have enough permissions. Use the Metadata tool to check."

            force_tool = f"In this case, I will use tool {tool}..." if tool else ""
            first_input = self.tool_selection_chain.invoke(
                {"input": query,
                 "chat_history": self.chat_history,
                 "force_tool": force_tool,
                 "denodo_tables": denodo_tables},
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
                            yield f"Querying Denodo for: **{natural_language_query}**. Give me a second.\n\n"
                        elif tool_name == "metadata_query":
                            search_query = parsed_query["metadata_query"]["search_query"]
                            yield "<TOOL:metadata>"
                            yield f"Querying Denodo for: **{search_query}**. Give me a second.\n\n"
                        elif tool_name == "kb_lookup":
                            yield "<TOOL:kb>"
                        else:
                            yield "<TOOL:direct>"
            except Exception as e:
                yield 

            tool_result = process_tool_query(first_input, self.tools)
            if tool_result:
                tool_name, tool_output, original_xml_call = tool_result

                readable_tool_output = readable_tool_result(tool_name, tool_output)
                ai_stream = self.answer_with_tool_chain.stream({
                    "input": query,
                    "chat_history": self.chat_history,
                    "tool_query": readable_tool_output,
                    "denodo_tables": denodo_tables
                },
                config = {
                    "callbacks": add_langfuse_callback(self.llm_callback, self.llm_model, self.session_id),
                    "run_name": inspect.currentframe().f_code.co_name,
                })
            else:
                ai_stream = first_input
                tool_name, tool_output, original_xml_call = "Direct Response", "", ""
            
            ai_response = ""
            for chunk in ai_stream:
                ai_response += chunk
                yield chunk

            return_data = {
                "vql": None,
                "data_sources": self.llm_model,
                "embeddings": None,
                "related_questions": None,
                "execution_result": None,
                "total_tokens": 0,
                "answer": ai_response
            }

            if tool_name == "database_query" and isinstance(tool_output, dict):
                return_data["vql"] = tool_output["sql_query"]
                return_data["execution_result"] = tool_output["execution_result"]
                return_data["related_questions"] = tool_output["related_questions"]
                return_data["graph"] = tool_output["raw_graph"]
                return_data["tables_used"] = tool_output["tables_used"]
                return_data["query_explanation"] = tool_output["query_explanation"]
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
                original_xml_call = original_xml_call
            )
            
            if len(self.chat_history) > 10:
                self.chat_history = self.chat_history[-10:]
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            traceback_info = traceback.format_exc()
            yield f"Error: {error_message}\n\nTraceback:\n{traceback_info}"

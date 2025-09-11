from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from api.deepquery.agent.xml_utils import remove_think_tags
from api.deepquery.analysis_agent.prompts import SCHEMA_DIGEST_PROMPT
from api.deepquery.utils import trace_context, create_langfuse_handler, execute_base_database_query

class AnalysisToolsMixin:
    """
    Mixin class containing tools for the AnalysisAgent.

    This mixin provides database querying and cohort management functionality.
    """

    async def create_cohort(self, name, description):
        """
        Create a new cohort with a name and description.

        Args:
            name: The name of the cohort
            description: A description of what this cohort represents

        Returns:
            Dict containing the status of the cohort creation
        """
        # Check if cohort with this name already exists
        for cohort in self.cohorts:
            if cohort["name"] == name:
                return {
                    "status": "error",
                    "message": f"Cohort with name '{name}' already exists."
                }

        # Add new cohort
        self.cohorts.append({
            "name": name,
            "description": description
        })

        return {
            "status": "success",
            "message": f"Cohort '{name}' created successfully.",
            "cohort": {
                "name": name,
                "description": description
            }
        }

    async def database_agent(self, action, action_description, default_rows="10"):
        """
        Execute a database action through the database agent.

        This tool will query the database agent that can answer natural language questions
        about the database. If the action or action_description contains '{cohort}', the tool will
        be called multiple times, once for each cohort, replacing '{cohort}' with the cohort name.

        Args:
            action: The action to perform (aggregate_metric or generate_metadata_summary)
            action_description: The description of the action to perform
            default_rows: The default number of rows to return
        Returns:
            Dict containing execution results, SQL queries, and graph data if applicable
        """
        # Check if this is a multiple cohorts operation
        if "<cohorts>" in action_description:
            if not self.cohorts:
                return {
                    "status": "error",
                    "message": "No cohorts have been created yet. Create cohorts first before using the <cohorts> placeholder."
                }

            # Create individual tool calls for each cohort
            cohort_tool_ids = []
            for cohort in self.cohorts:
                cohort_action = action.replace("<cohorts>", f'{cohort["name"]}: ({cohort["description"]})')
                cohort_description = action_description.replace("<cohorts>", f'{cohort["name"]}: ({cohort["description"]})')

                # Create individual tool call by calling execute_tool
                # This creates a proper tool_id and stores it in self.tool_calls
                tool_id, cohort_result = await self.tool_executor.execute_tool(
                    self,
                    "database_agent",
                    f"<action>{cohort_action}</action><action_description>{cohort_description}</action_description><default_rows>{default_rows}</default_rows>"
                )

                cohort_tool_ids.append({
                    "cohort": cohort,
                    "tool_id": tool_id,
                    "result": cohort_result
                })

            # Return response with references to individual tool_ids
            response = {
                "status": "success",
                "message": f"Executed action across {len(cohort_tool_ids)} cohorts",
                "results": [ct for ct in cohort_tool_ids]
            }

            # Process based on tool_response_mode
            if self.tool_executor.tool_response_mode == "answer":
                response["answer"] = f"Successfully executed action across {len(cohort_tool_ids)} cohorts. Individual tool IDs: {', '.join(ct['tool_id'] for ct in cohort_tool_ids)}"
                answer_results = "\n\n".join([f"Cohort: {ct['cohort']['name']} (Tool ID: {ct['tool_id']})\n{ct['cohort']['description']}\n{ct['result'].get('answer', str(ct['result']))}" for ct in cohort_tool_ids])
                response["answer"] += "\n\n" + answer_results

            return response
        else:
            # Normal execution (single query)
            return await self._execute_database_query(action, action_description, int(default_rows))

    async def _execute_database_query(self, action, action_description, default_rows=10):
        """
        Internal method to execute the actual database query.

        Args:
            action: The action to perform
            action_description: The description of the action
            default_rows: Number of rows to return

        Returns:
            Dict containing query results
        """

        if action not in ["generate_metadata_summary", "aggregate_metric"]:
            return {
                "status": "error",
                "answer": "Invalid action. Only 'generate_metadata_summary', and 'aggregate_metric' are supported."
            }

        # Determine the mode based on the action
        if action == "generate_metadata_summary":
            mode = "metadata"
        else:
            mode = "data"

        # Use the common base function for database query execution
        json_response = await execute_base_database_query(
            action=action,
            action_description=action_description,
            cohorts=self.cohorts,
            auth=self.auth,
            mode=mode,
            verbose=False,
            disclaimer=False,
        )

        # Return early if there was an error (cohort not found, etc.)
        if json_response.get("status") == "error":
            return json_response

        # Keep only the first N rows where keys are 'Row 1', 'Row 2', ..., 'Row N'
        filtered = {}
        for i in range(1, default_rows + 1):
            key = f"Row {i}"
            if key in json_response.get("execution_result", {}):
                filtered[key] = json_response["execution_result"][key]
        json_response["execution_result"] = filtered

        # Handle metadata summary actions
        if not action.startswith("generate_metadata_summary"):
            json_response["answer"] = str(json_response.get("execution_result", {})) + "\n\n" + "SQL query: " + json_response.get("sql_query", "")

        return json_response

async def schema_digest(schema, analysis_question, llm):
    """
    Generate a schema explanation using the provided LLM with langfuse tracking.

    Args:
        schema: The database schema text
        analysis_question: The business question being analyzed
        llm: The language model to use for generating the explanation

    Returns:
        Formatted schema explanation text
    """
    prompt = ChatPromptTemplate.from_messages([
        ("human", SCHEMA_DIGEST_PROMPT)
    ])

    chain = prompt | llm | StrOutputParser()

    # Create langfuse handler for this operation
    langfuse_handler = create_langfuse_handler(trace_name="schema_digest")

    with trace_context(langfuse_handler) as config:
        result = await chain.ainvoke(
            {"schema": schema, "analysis_question": analysis_question},
            config=config
        )
    result = result.replace("{", "{{").replace("}", "}}")
    return remove_think_tags(result)
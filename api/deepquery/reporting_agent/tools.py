from api.deepquery.utils import execute_base_database_query

class ReportingToolsMixin:
    """
    Mixin class containing tools for the ReportingAgent.
    """
    async def database_agent(self, action: str, action_description: str):
        """
        Execute specific database actions through the database agent.

        This tool allows the reporting agent to generate additional visualizations
        or tables for the report. It supports two specific actions:
        - generate_graph: Creates custom visualizations for the report

        Args:
            action: The action to perform (generate_graph)
            action_description: The description of what to generate

        Returns:
            Dict containing execution results, SQL queries, and graph data if applicable
        """
        # Only allow specific actions for the reporting agent
        if action not in ["generate_graph"]:
            return {
                "status": "error",
                "message": f"Action '{action}' not allowed. Use 'generate_graph'"
            }

        # Use the common base function for database query execution
        json_response = await execute_base_database_query(
            action=action,
            action_description=action_description,
            cohorts=self.cohorts,
            auth=self.auth,
            mode="data",
            verbose=False,
            plot=True if action == "generate_graph" else False,
            plot_details=action_description if action == "generate_graph" else "",
            disclaimer=False,
        )

        # Return early if there was an error (cohort not found, etc.)
        if json_response.get("status") == "error":
            return json_response

        # Handle graph generation success/failure
        if json_response and action == "generate_graph" and json_response.get("raw_graph", "").startswith("data:image/svg+xml;base64,"):
            json_response["answer"] = "Graph generated successfully"
        else:
            json_response["answer"] = "Graph generation failed"

        return json_response
import logging

from api.deepquery.agent.agent import Agent
from api.deepquery.analysis_agent.tools import AnalysisToolsMixin
from api.deepquery.analysis_agent.prompts import ANALYSIS_SYSTEM_PROMPT, ANALYSIS_INITIAL_PROMPT, ANALYSIS_POST_TOOL_PROMPT

# Set up logging
logger = logging.getLogger(__name__)

class AnalysisAgent(Agent, AnalysisToolsMixin):
    """
    A specialized agent for performing data analysis tasks through natural language.

    This agent interacts with a database agent to perform analysis operations and
    track cohorts throughout the analysis process.
    """

    def __init__(
        self,
        llm,
        system_prompt=ANALYSIS_SYSTEM_PROMPT,
        initial_prompt=ANALYSIS_INITIAL_PROMPT,
        post_tool_prompt=ANALYSIS_POST_TOOL_PROMPT,
        max_loops=None,
        tool_response_mode="answer",  # "answer" or "complete"
        auth=None,
        start_llm=None,  # Optional LLM for first interaction only
        xml_callbacks=None,  # Dictionary of tag -> callback function
        max_concurrent_tool_calls=5
    ):
        """
        Initialize the AnalysisAgent with database connectivity.

        Args:
            llm: Language model for generating responses
            system_prompt: Custom system prompt for specialized agent behavior
            initial_prompt: Prompt to add before processing the first user input
            post_tool_prompt: Prompt to add after each tool call
            max_loops: Maximum number of interaction loops before timeout
            tool_response_mode: Response mode for tools, either "answer" or "complete"
            auth: Authentication token for database access
            start_llm: Optional LLM to use only for the first interaction
            xml_callbacks: Dictionary mapping XML tag names to callback functions
            max_concurrent_tool_calls: Maximum number of tools that can be called concurrently
        """
        # Store auth for tool calls
        self.auth = auth

        # Initialize with tools
        super().__init__(
            agent_name="AnalysisAgent",
            tools=[self.database_agent, self.create_cohort],
            llm=llm,
            system_prompt=system_prompt,
            initial_prompt=initial_prompt,
            post_tool_prompt=post_tool_prompt,
            tool_response_mode=tool_response_mode,
            max_loops=max_loops,
            start_llm=start_llm,
            xml_callbacks=xml_callbacks,  # NEW: Pass to parent
            max_concurrent_tool_calls=max_concurrent_tool_calls,
        )

        # Track created cohorts (name, description)
        self.cohorts = []
        logger.info("AnalysisAgent initialization completed")

    def set_initial_prompt(self, initial_prompt):
        self.initial_prompt = initial_prompt

    def get_cohorts(self):
        return self.cohorts
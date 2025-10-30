import time
import logging

from markdown_it import MarkdownIt
from api.deepquery.agent.agent import Agent
from api.deepquery.utils import prepare_sequential_report_trace
from api.deepquery.reporting_agent.tools import ReportingToolsMixin
from api.deepquery.reporting_agent.report_processor import ReportProcessor
from api.deepquery.analysis_agent.prompts import ANALYSIS_POST_TOOL_PROMPT
from api.deepquery.reporting_agent.utils import convert_html_to_pdf, COLOR_PALETTES
from api.deepquery.reporting_agent.prompts import REPORTING_SYSTEM_PROMPT, REPORTING_INITIAL_PROMPT

logger = logging.getLogger(__name__)

class ReportingAgent(Agent, ReportingToolsMixin):
    """
    A specialized agent for generating detailed reports from analysis results.

    This agent transforms raw analysis data and tool call history into professional
    formatted reports for business stakeholders, with support for tables, code
    blocks, and visualizations.
    """

    def __init__(
        self,
        llm,
        cohorts=None,
        system_prompt: str = REPORTING_SYSTEM_PROMPT,
        initial_prompt: str = REPORTING_INITIAL_PROMPT,
        post_tool_prompt: str = ANALYSIS_POST_TOOL_PROMPT,
        max_loops: int = None,
        auth: str = None,
    ):
        """
        Initialize the ReportingAgent.

        Args:
            llm: Language model for generating responses
            cohorts: List of cohort dictionaries from analysis phase (optional)
            system_prompt: System prompt for the reporting agent
            initial_prompt: First input prompt
            post_tool_prompt: Prompt to add after tool calls
            max_loops: Maximum number of execution loops
            auth: Authentication token for database access
        """
        # Store auth for tool calls
        self.auth = auth

        super().__init__(
            agent_name="ReportingAgent",
            tools=[self.database_agent],
            llm=llm,
            system_prompt=system_prompt,
            initial_prompt=initial_prompt,
            post_tool_prompt=post_tool_prompt,
            max_loops=max_loops,
        )

        self.analysis_question = ""
        self.cohorts = cohorts or []
        logger.info("ReportingAgent initialization completed")

    async def generate_visualizations(self, analysis_result, analysis_question: str):
        """
        Generate visualizations to complement the report from analysis results.
        """
        try:
            #self.tool_calls = analysis_result.get("tool_calls", [])
            self.cohorts = analysis_result.get("cohorts", [])
            self.analysis_question = analysis_question

            formatted_input = self.initial_prompt.format(
                question=analysis_question,
                cohorts=str([c["name"] for c in self.cohorts])
            )

            # Wrap the formatted string in a dictionary with 'text' key as expected by _execute_loop
            user_input_dict = {"text": formatted_input}

            result = await self._execute_loop(user_input_dict, loop_count=0)
            visualizations = result.get("tool_calls", [])
            return visualizations
        except Exception as e:
            logger.error(f"Visualization generation failed: {e}", exc_info=True)
            raise

    async def generate_report(self, visualization_tool_calls, deepquery_metadata=None, include_failed_tool_calls_appendix=False):
        """
        Generate a complete report from analysis results.
        """
        start_time = time.time()
        logger.info("Starting report generation")

        try:
            plan = deepquery_metadata.get("plan", "<PLAN_NOT_FOUND>")
            cohorts = deepquery_metadata.get("cohorts", [])
            analysis_tool_calls = deepquery_metadata.get("tool_calls", [])
            answer = deepquery_metadata.get("analysis_body", "")
            default_rows = deepquery_metadata.get("default_rows", 10)

            cohorts_message = f"These were the cohorts created:\n<cohorts>{cohorts}</cohorts>" if cohorts else ""
            formatted_trace = prepare_sequential_report_trace(
                plan=plan,
                cohorts=cohorts_message,
                analysis_tool_calls=analysis_tool_calls,
                visualization_tool_calls=visualization_tool_calls,
                answer=answer,
                default_rows=default_rows
            )

            processor = ReportProcessor(
                visualization_tool_calls=visualization_tool_calls,
                analysis_tool_calls=analysis_tool_calls,
                llm=self.llm,
                langfuse_handler=self.langfuse_handler,
                deepquery_metadata=deepquery_metadata,
                include_failed_tool_calls_appendix=include_failed_tool_calls_appendix)
            report = await processor.generate_report(formatted_trace)

            duration = time.time() - start_time
            return report
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Report generation failed after {duration:.2f}s: {e}", exc_info=True)
            raise

    def generate_html(self, markdown_text: str) -> str:
        """
        Generate HTML from markdown text.

        This method provides standalone HTML generation capability that was present
        in the original implementation.

        Args:
            markdown_text: The markdown content to convert

        Returns:
            The generated HTML as a string
        """
        start_time = time.time()
        logger.info("Starting standalone HTML generation")

        try:
            # Convert markdown to HTML using markdown-it
            md = MarkdownIt("commonmark").enable('table')
            html_body = md.render(markdown_text)

            duration = time.time() - start_time
            logger.info(f"HTML generation completed in {duration:.2f}s, output length: {len(html_body)} characters")

            return html_body

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"HTML generation failed after {duration:.2f}s: {e}", exc_info=True)
            raise

    async def generate_pdf(self, report_content: str, output_path: str = "report.pdf", css_path: str = None, color_palette: str = "red"):
        """
        Generate a PDF file from the report content.

        Args:
            report_content: The markdown report content
            output_path: The path where to save the PDF file
            css_path: Optional path to custom CSS file for styling (for future extensibility)
            color_palette: Color theme for the PDF ("red", "blue", "green", "black")
        """
        start_time = time.time()
        logger.info(f"Starting PDF generation: {output_path}")

        try:
            # Validate color palette
            if color_palette not in COLOR_PALETTES:
                logger.warning(f"Invalid color palette '{color_palette}', defaulting to 'red'")
                color_palette = "red"

            selected_palette = COLOR_PALETTES[color_palette]
            logger.info(f"Using {color_palette} color palette for PDF generation")

            # Convert to HTML using the standalone method
            logger.info("Converting markdown to HTML using generate_html method")
            html = self.generate_html(report_content)

            # Convert to PDF with selected color palette
            logger.info(f"Converting HTML content to PDF using {color_palette} color palette with Playwright")
            await convert_html_to_pdf(html, output_path, selected_palette, self.analysis_question)
            return output_path
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"PDF generation failed after {duration:.2f}s: {e}", exc_info=True)
            raise
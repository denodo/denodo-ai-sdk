import time
import logging
import aiofiles

from utils.utils import custom_tag_parser
from api.deepquery.utils import prepare_visualization_analysis_trace
from api.deepquery.analysis_agent import AnalysisAgent
from api.deepquery.reporting_agent import ReportingAgent
from api.deepquery.analysis_agent.tools import schema_digest
from api.deepquery.analysis_agent.prompts import ANALYSIS_SYSTEM_PROMPT
from api.deepquery.reporting_agent.prompts import REPORTING_SYSTEM_PROMPT

# Set up logging
logger = logging.getLogger(__name__)

async def process_analysis(
    question,
    executing_llm,
    planning_llm,
    planning_provider,
    planning_model,
    executing_provider,
    executing_model,
    default_rows,
    max_analysis_loops,
    max_concurrent_tool_calls,
    formatted_schema,
    auth=None,
    thinking_llm_temperature=0.0,
    thinking_llm_max_tokens=10240,
    llm_temperature=0.0,
    llm_max_tokens=4096,
    execution_model="thinking"
):
    """
    Perform analysis on the database and return answer with metadata for future PDF generation.

    Args:
        question: The business question to analyze
        executing_llm: LLM that will be performing the tool calls
        planning_llm: LLM that will be performing the reasoning and planning tasks
        planning_provider: Provider name for planning LLM
        planning_model: Model name for planning LLM
        executing_provider: Provider name for executing LLM
        executing_model: Model name for executing LLM
        default_rows: Number of rows to return in database queries
        max_analysis_loops: Maximum number of analysis loops allowed
        max_concurrent_tool_calls: Maximum number of tools that can be called concurrently
        formatted_schema: Pre-formatted schema text from get_relevant_tables
        auth: Authentication token for database access

    Returns:
        Dict with 'answer' and 'deepquery_metadata' keys
    """
    start_time = time.time()

    # Log the start of analysis
    logger.info(f"Starting analysis for question: {question[:100]}{'...' if len(question) > 100 else ''}")
    logger.info(f"Parameters: default_rows={default_rows}")
    logger.info(f"Parameters: execution_model={execution_model}")
    logger.info(f"Parameters: execution_model_provider={planning_provider if execution_model == 'thinking' else executing_provider}")
    logger.info(f"Parameters: execution_model_model={planning_model if execution_model == 'thinking' else executing_model}")

    # Storage for the first plan
    first_plan = {"content": None, "captured": False}

    def on_plan_parsed(tag, content, response_count, tool_call_count):
        """Callback function to capture the first plan"""
        if not first_plan["captured"]:
            logger.info(f"First plan captured at response #{response_count}")
            first_plan["content"] = content.strip()
            first_plan["captured"] = True

    # Set up XML callbacks for plan monitoring
    xml_callbacks = {
        "plan": on_plan_parsed
    }

    try:
        schema = formatted_schema
        logger.info(f"Schema length: {len(schema) if schema else 0} characters")

        # Check if schema is empty and exit early if so
        if not schema or not schema.strip():
            error_message = "Unable to retrieve database schema. This may indicate a data catalog connection issue or no relevant tables found for your query. Please check the system logs for more details."
            total_duration = time.time() - start_time
            logger.info(f"Analysis exited early due to empty schema in {total_duration:.2f}s")
            return {
                "answer": error_message,
                "deepquery_metadata": None
            }

        # Generate schema explanation using the planning LLM
        schema_explanation = await schema_digest(schema, question, planning_llm)

        # Create system prompt for analysis
        logger.info("Creating analysis agent system prompt")
        analysis_agent_system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
            database_schema=schema,
            database_explanation=schema_explanation,
            default_rows=default_rows
        )

        # Initialize the analysis agent
        analysis_agent = AnalysisAgent(
            llm=executing_llm,
            system_prompt=analysis_agent_system_prompt,
            auth=auth,
            start_llm=planning_llm,
            max_loops=max_analysis_loops,
            max_concurrent_tool_calls=max_concurrent_tool_calls,
            xml_callbacks=xml_callbacks
        )

        # Run the analysis
        logger.info("Starting analysis agent execution")
        analysis_start_time = time.time()
        analysis_agent.set_initial_prompt(analysis_agent.initial_prompt.format(user_input=question)) #Set the initial prompt with the user's question
        analysis_result = await analysis_agent.start({"text": "Follow the instructions given above to begin your analysis."}) #No need for input, we already set the initial prompt
        analysis_duration = time.time() - analysis_start_time
        answer = analysis_result.get("answer").get("answer")
        logger.info(f"Analysis result: {answer}")

        analysis_title = custom_tag_parser(answer, tag="report_title", default="Failed to parse analysis title. LLM did not output the correct format. Check logs for more details.")[0].strip()
        analysis_body = custom_tag_parser(answer, tag="report_body", default="Failed to parse analysis body. LLM did not output the correct format. Check logs for more details.")[0].strip()

        analysis_result["cohorts"] = analysis_agent.get_cohorts() #Add generated cohorts to the analysis result

        logger.info(f"Analysis completed in {analysis_duration:.2f}s")
        logger.info(f"Analysis result contains {len(analysis_result.get('tool_calls', []))} tool calls")
        logger.info(f"Analysis created {len(analysis_result.get('cohorts', []))} cohorts")

        # Calculate actual execution LLM based on execution_model
        if execution_model == "thinking":
            actual_executing_provider = planning_provider
            actual_executing_model = planning_model
            actual_executing_temperature = thinking_llm_temperature
            actual_executing_max_tokens = thinking_llm_max_tokens
        else:  # "base"
            actual_executing_provider = executing_provider
            actual_executing_model = executing_model
            actual_executing_temperature = llm_temperature
            actual_executing_max_tokens = llm_max_tokens

        # Prepare metadata for PDF generation
        deepquery_metadata = {
            "question": question,
            "analysis_title": analysis_title,
            "analysis_body": analysis_body,
            "conversation_history": analysis_result.get("conversation_history", []),
            "tool_calls": analysis_result.get("tool_calls", []),
            "cohorts": analysis_result.get("cohorts", []),
            "schema": schema,
            "schema_explanation": schema_explanation,
            "planning_provider": planning_provider,
            "planning_model": planning_model,
            "executing_provider": executing_provider,
            "executing_model": executing_model,
            "default_rows": default_rows,
            "plan": first_plan.get("content", "<PLAN_NOT_FOUND>"),
            "analysis_execution_time": analysis_duration,
            "analysis_iterations": analysis_result.get("loop_count", 0),
            "total_tool_calls": len(analysis_result.get("tool_calls", [])),
            "thinking_llm_temperature": thinking_llm_temperature,
            "thinking_llm_max_tokens": thinking_llm_max_tokens,
            "actual_executing_provider": actual_executing_provider,
            "actual_executing_model": actual_executing_model,
            "actual_executing_temperature": actual_executing_temperature,
            "actual_executing_max_tokens": actual_executing_max_tokens
        }

        total_duration = time.time() - start_time
        logger.info(f"Analysis completed in {total_duration:.2f}s")

        return {
            "answer": analysis_body,
            "deepquery_metadata": deepquery_metadata
        }
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Error in process_analysis after {total_duration:.2f}s: {e}", exc_info=True)
        raise

async def generate_pdf_from_deepquery_metadata(
    deepquery_metadata,
    executing_llm,
    output_pdf=None,
    color_palette="red",
    max_reporting_loops=None,
    include_failed_tool_calls_appendix=False,
    auth=None
):
    """
    Generate PDF from deepquery metadata.

    Args:
        deepquery_metadata: Metadata from analysis phase
        plan: The original analysis plan
        executing_llm: LLM for executing tasks
        output_pdf: Optional path to save PDF file (default: None)
        color_palette: Color theme for PDF ("red", "blue", "green", "black", default: "red")
        auth: Authentication token for database access

    Returns:
        Dict with 'pdf_blob' and 'pdf_path' keys
    """
    start_time = time.time()

    if not deepquery_metadata:
        logger.error("No deepquery_metadata provided")
        return {
            "pdf_blob": None,
            "pdf_path": None
        }

    logger.info("Starting PDF generation from deepquery metadata")
    logger.info(f"Parameters: color_palette={color_palette}")

    try:
        # Extract data from metadata
        question = deepquery_metadata.get("question", "")
        tool_calls = deepquery_metadata.get("tool_calls", [])
        cohorts = deepquery_metadata.get("cohorts", [])
        analysis_body = deepquery_metadata.get("analysis_body", "")
        plan = deepquery_metadata.get("plan", "<PLAN_NOT_FOUND>")

        # Not mention cohorts if none were created
        cohorts_message = f"These were the cohorts created:\n<cohorts>{cohorts}</cohorts>" if cohorts else ""

        reporting_agent_system_prompt = REPORTING_SYSTEM_PROMPT.format(
            analysis_trace = prepare_visualization_analysis_trace(plan, cohorts_message, tool_calls, analysis_body, deepquery_metadata.get("default_rows", 10))
        )
        reporting_agent = ReportingAgent(
            llm=executing_llm,
            cohorts=cohorts,
            system_prompt=reporting_agent_system_prompt,
            auth=auth,
            max_loops=max_reporting_loops
        )

        # Create analysis result structure for visualization generation
        analysis_result = {
            "tool_calls": tool_calls,
            "cohorts": cohorts
        }

        # Generate visualizations
        logger.info("Generating visualizations")
        viz_start_time = time.time()
        visualization_tool_calls = await reporting_agent.generate_visualizations(analysis_result, question)
        viz_duration = time.time() - viz_start_time
        logger.info(f"Visualization generation completed in {viz_duration:.2f}s, created {len(visualization_tool_calls)} visualizations")

        # Generate the report
        logger.info("Generating report content")
        report_start_time = time.time()
        report = await reporting_agent.generate_report(
            visualization_tool_calls=visualization_tool_calls,
            deepquery_metadata=deepquery_metadata,
            include_failed_tool_calls_appendix=include_failed_tool_calls_appendix
        )
        report_duration = time.time() - report_start_time
        logger.info(f"Report generation completed in {report_duration:.2f}s, report length: {len(report) if report else 0} characters")

        # Generate PDF
        pdf_output_path = output_pdf if output_pdf else "report.pdf"
        logger.info(f"Generating PDF: {pdf_output_path}")
        pdf_start_time = time.time()
        pdf_path = await reporting_agent.generate_pdf(report, pdf_output_path, color_palette=color_palette)
        pdf_duration = time.time() - pdf_start_time
        logger.info(f"PDF generation completed in {pdf_duration:.2f}s")

        # Read PDF as blob
        pdf_blob = None
        try:
            logger.info("Reading PDF as blob")
            async with aiofiles.open(pdf_path, 'rb') as f:
                pdf_blob = await f.read()
            logger.info(f"PDF blob created, size: {len(pdf_blob)} bytes")
        except Exception as e:
            logger.error(f"Could not read PDF file: {e}")
            pdf_blob = None

        total_duration = time.time() - start_time
        logger.info(f"PDF generation completed in {total_duration:.2f}s")

        return {
            "pdf_blob": pdf_blob,
            "pdf_path": pdf_path
        }
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Error in generate_pdf_from_deepquery_metadata after {total_duration:.2f}s: {e}", exc_info=True)
        raise
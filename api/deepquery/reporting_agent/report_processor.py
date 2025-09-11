import re
import json
import logging
from api.deepquery.utils import (
    trace_context,
    filter_tool_calls_appendix,
    prepare_tool_calls_only_trace
)
from api.deepquery.agent.xml_utils import parse_xml
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from api.deepquery.reporting_agent.prompts import SEQUENTIAL_REPORT_PROMPT

# Set up logging
logger = logging.getLogger(__name__)

class ReportProcessor:
    def __init__(self, visualization_tool_calls, analysis_tool_calls, llm, langfuse_handler, deepquery_metadata=None, include_failed_tool_calls_appendix=False):
        self.visualization_tool_calls = visualization_tool_calls
        self.analysis_tool_calls = analysis_tool_calls
        self.llm = llm
        self.langfuse_handler = langfuse_handler
        self.deepquery_metadata = deepquery_metadata
        self.include_failed_tool_calls_appendix = include_failed_tool_calls_appendix
        self.tool_id_map = {call['tool_id']: call for call in self.analysis_tool_calls + self.visualization_tool_calls}

    async def generate_report(self, trace):
        """
        Generate a complete report from analysis results.

        Args:
            trace: The full conversation trace from the analysis agent.

        Returns:
            The generated report in markdown format as a string
        """

        report_template = await self._generate_sequential_report(trace, self.llm, self.langfuse_handler)

        processed_report = self.process_template(report_template)

        appendix = self._generate_appendix()
        processed_appendix = self.process_template(appendix)

        return processed_report + "<div class='page-break'></div>" + processed_appendix

    async def _generate_sequential_report(self, trace, llm, langfuse_handler=None):
        """Generate a report by sequentially building it one section at a time."""
        sections = [
            ("introduction", "Introduction"),
            ("detailed_analysis", "Detailed Analysis"),
            ("methodology", "Methodology"),
            ("recommendations", "Recommendations"),
            ("conclusion", "Conclusion"),
            ("executive_summary", "Executive Summary")
        ]

        final_order = [
            "introduction",
            "executive_summary",
            "detailed_analysis",
            "methodology",
            "recommendations",
            "conclusion"
        ]

        # Define section categories for different trace data levels
        full_trace_sections = {"introduction", "detailed_analysis", "methodology"}
        tool_calls_only_sections = {"executive_summary", "recommendations", "conclusion"}

        current_report = ""
        section_contents = {}

        for section_tag, section_name in sections:
            logger.info(f"Generating section: {section_name}")
            prompt = ChatPromptTemplate.from_messages([
                ("human", SEQUENTIAL_REPORT_PROMPT)
            ])

            chain = prompt | llm | StrOutputParser()

            # Determine what type of trace data to provide based on section
            trace_data = ""
            if section_tag in full_trace_sections:
                trace_data = f"<trace>{trace}</trace>"
            elif section_tag in tool_calls_only_sections:
                # Extract tool calls from the deepquery metadata
                if self.deepquery_metadata:
                    analysis_tool_calls = self.deepquery_metadata.get("tool_calls", [])
                    tool_calls_only = prepare_tool_calls_only_trace(
                        analysis_tool_calls=analysis_tool_calls,
                        visualization_tool_calls=self.visualization_tool_calls
                    )
                    trace_data = f"<trace>{tool_calls_only}</trace>"

            with trace_context(langfuse_handler, f"generate_{section_tag}") as config:
                section_result = await chain.ainvoke(
                    {
                        "trace": trace_data,
                        "current_report": current_report,
                        "next_section": section_name,
                        "section_tag": section_tag
                    },
                    config=config
                )

            parsed = parse_xml(section_result)
            if section_tag in parsed:
                logger.info(f"Section {section_name} generated successfully")
                section_content = parsed[section_tag]
            else:
                logger.info(f"Section {section_name} generated failed, retrying...")
                section_content = await self._retry_section_generation(
                    section_result, section_tag, section_name, trace_data,
                    current_report, llm, langfuse_handler
                )

            current_report += f"\n\n{section_content}"
            section_contents[section_tag] = section_content

        report_parts = [f"\n\n{section_contents[tag]}" for tag in final_order if tag in section_contents]
        return "\n\n".join(report_parts)

    async def _retry_section_generation(self, failed_result, section_tag, section_name, trace_data, current_report, llm, langfuse_handler):
        """
        Retry section generation when XML parsing fails.
        Gives the LLM one more chance to properly format the response with required tags.
        """
        retry_prompt = ChatPromptTemplate.from_messages([
            ("human", SEQUENTIAL_REPORT_PROMPT),
            ("ai", failed_result),
            ("human", f"I did not detect the <{section_tag}> or </{section_tag}> tags. Did you finish the section? Please proceed now to return the complete section in between <{section_tag}> </{section_tag}> as shown in the initial instructions.")
        ])

        retry_chain = retry_prompt | llm | StrOutputParser()

        try:
            with trace_context(langfuse_handler, f"retry_generate_{section_tag}") as config:
                retry_result = await retry_chain.ainvoke(
                    {
                        "trace": trace_data,
                        "current_report": current_report,
                        "next_section": section_name,
                        "section_tag": section_tag
                    },
                    config=config
                )

            retry_parsed = parse_xml(retry_result)
            if section_tag in retry_parsed:
                return retry_parsed[section_tag]
            else:
                logger.info(f"Section {section_name} generated failed, no more retries.")
                return f"[Error generating {section_name} section]"
        except Exception:
            return f"[Error generating {section_name} section]"

    def process_template(self, template_text):
        """
        Process a template string by replacing tool reference tags with their stored values.

        The template can contain tags like:
        <image>
        <tool_id>tool_id_value</tool_id>
        <tool_value>graph</tool_value>
        </image>

        Args:
            template_text: The template string with tool reference tags

        Returns:
            Processed string with tool values substituted
        """
        # First, find all tool references in the template
        image_pattern = r"<image>\s*<tool_id>(.*?)</tool_id>\s*<tool_value>(.*?)</tool_value>\s*</image>"
        # Modified pattern to capture leading whitespace before the table tag
        table_pattern = r"([ \t]*)<table>\s*<tool_id>(.*?)</tool_id>\s*<tool_value>(.*?)</tool_value>(?:\s*<limit>(.*?)</limit>)?(?:\s*<order_by>(.*?)</order_by>)?(?:\s*<sort>(.*?)</sort>)?\s*</table>"
        # Modified pattern to capture leading whitespace before the code tag
        code_pattern = r"([ \t]*)<code>\s*<tool_id>(.*?)</tool_id>\s*<tool_value>(.*?)</tool_value>\s*<language>(.*?)</language>\s*</code>"
        # Process image references
        def replace_image(match):
            tool_id = match.group(1).strip()
            value_key = match.group(2).strip()

            # First check if we can find the tool in our map
            tool_call = self.tool_id_map.get(tool_id)

            # If not found in map, try to find it using the get_tool_call method
            if not tool_call:
                tool_call = self._get_tool_call(tool_id)

            # Check if we have a valid tool call and the requested value exists
            if not tool_call or value_key not in tool_call.get("output", {}):
                return f"[IMAGE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

            # Get the image data
            image_data = tool_call.get("output", {}).get(value_key)
            if isinstance(image_data, str) and image_data.startswith("data:image"):
                tool_name = tool_call.get('tool_name', 'Graph from analysis')
                return f"<p><a href='#{tool_id}'><img src='{image_data}' alt='Tool call {tool_name}' /></a></p>"
            else:
                return "Graph generation failed: " + str(image_data)

        def replace_table(match):
            # Get the leading whitespace (we capture it but won't use it for the table)
            indent = match.group(1)
            tool_id = match.group(2).strip()
            value_key = match.group(3).strip()
            # Check if a limit was specified
            row_limit = None
            if match.group(4):
                try:
                    row_limit = int(match.group(4).strip())
                except ValueError:
                    pass

            # Check if order_by was specified
            order_by = None
            if match.group(5):
                order_by = match.group(5).strip()

            # Check if sort direction was specified
            sort_direction = "ASC"
            if match.group(6):
                sort_dir = match.group(6).strip().upper()
                if sort_dir in ["ASC", "DESC"]:
                    sort_direction = sort_dir

            # Find the tool call using our method
            tool_call = self._get_tool_call(tool_id)
            if not tool_call or value_key not in tool_call.get("output", {}):
                return f"[TABLE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

            # Get the table data
            value = tool_call.get("output", {}).get(value_key)

            # If it's a JSON string, try to parse it
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return f"```\n{value}\n```"

            # Format as table based on the expected structure
            if isinstance(value, dict) and any(key.startswith("Row ") for key in value.keys()):
                # Get headers from the first row
                first_row_key = next((k for k in value.keys() if k.startswith("Row ")), None)
                if first_row_key and isinstance(value[first_row_key], list):
                    headers = [item.get("columnName", f"Column {i+1}") for i, item in enumerate(value[first_row_key])]

                    # Create the markdown table with zero indentation
                    md_table = "| " + " | ".join(headers) + " |\n"
                    md_table += "| " + " | ".join(["---" for _ in headers]) + " |\n"

                    # Get all row keys and sort them
                    row_keys = sorted([k for k in value.keys() if k.startswith("Row ")])

                    # Convert row data to a list of dictionaries for sorting
                    rows_data = []
                    for row_key in row_keys:
                        if isinstance(value[row_key], list):
                            row_values = []
                            for item in value[row_key]:
                                val = item.get("value", "")
                                # Try to convert to float and round if possible
                                try:
                                    val_float = float(val)
                                    val = round(val_float, 2)
                                    val = str(val)
                                except (ValueError, TypeError):
                                    pass
                                row_values.append(val)
                            rows_data.append(row_values)

                    # If order_by is specified, determine the column index
                    sort_idx = 0
                    if order_by:
                        try:
                            # First check if it's a column index (0-based)
                            sort_idx = int(order_by)
                        except ValueError:
                            # Then check if it's a column name
                            if order_by in headers:
                                sort_idx = headers.index(order_by)

                    # Sort rows based on the specified column
                    if rows_data:
                        # Define sort key function that handles different data types
                        def sort_key(row):
                            if len(row) <= sort_idx:
                                return (0, "")
                            val = row[sort_idx]
                            # Try to convert to numeric for proper sorting
                            try:
                                # Remove any currency symbols or commas
                                clean_val = str(val).replace(',', '').replace('$', '')
                                return (1, float(clean_val))
                            except (ValueError, TypeError):
                                return (0, str(val))

                        # Sort with the appropriate direction
                        reverse_sort = sort_direction == "DESC"
                        rows_data.sort(key=sort_key, reverse=reverse_sort)

                    # Apply row limit if specified
                    total_rows = len(rows_data)
                    if row_limit and row_limit < total_rows:
                        rows_data = rows_data[:row_limit]

                    # Add rows to the table
                    for row_values in rows_data:
                        md_table += "| " + " | ".join([str(val) for val in row_values]) + " |\n"

                    # Add note about limited rows if applicable
                    if row_limit and row_limit < total_rows:
                        md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

                    # Add note about sorting if applicable
                    if order_by:
                        col_name = headers[sort_idx] if sort_idx < len(headers) else order_by
                        md_table += f"\n_Sorted by {col_name} {sort_direction}_\n"

                    return md_table

            # Generic handling for other JSON structures
            elif isinstance(value, dict):
                # Try to convert dictionary to a table
                md_table = "| Key | Value |\n| --- | --- |\n"
                items = list(value.items())

                # Sort items by key or value
                if order_by == "key":
                    items.sort(key=lambda x: x[0], reverse=(sort_direction == "DESC"))
                elif order_by == "value":
                    # Try numeric sort for values if possible
                    def sort_key(item):
                        try:
                            # Remove any currency symbols or commas
                            clean_val = str(item[1]).replace(',', '').replace('$', '')
                            return (1, float(clean_val))
                        except (ValueError, TypeError):
                            return (0, str(item[1]))
                    items.sort(key=sort_key, reverse=(sort_direction == "DESC"))
                else:
                    # Default sort by key
                    items.sort(key=lambda x: x[0])

                # Apply row limit if specified
                total_rows = len(items)
                if row_limit and row_limit < total_rows:
                    items = items[:row_limit]

                for k, v in items:
                    # Try to convert to float and round if possible
                    try:
                        v_float = float(v)
                        v = round(v_float, 2)
                    except (ValueError, TypeError):
                        pass
                    md_table += f"| {k} | {v} |\n"

                # Add note about limited rows if applicable
                if row_limit and row_limit < total_rows:
                    md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

                # Add note about sorting if applicable
                if order_by:
                    md_table += f"\n_Sorted by {order_by} {sort_direction}_\n"

                return md_table
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Try to convert list of dictionaries to a table
                headers = list(value[0].keys())
                md_table = "| " + " | ".join(headers) + " |\n"
                md_table += "| " + " | ".join(["---" for _ in headers]) + " |\n"

                # Convert to list of lists for easier processing
                rows_data = []
                for item in value:
                    row = []
                    for h in headers:
                        val = item.get(h, "")
                        # Try to convert to float and round if possible
                        try:
                            val_float = float(val)
                            val = round(val_float, 2)
                        except (ValueError, TypeError):
                            pass
                        row.append(val)
                    rows_data.append((row, item))  # Store the original item for sorting

                # If order_by is specified, determine the column index
                sort_idx = 0
                if order_by:
                    if order_by in headers:
                        sort_idx = headers.index(order_by)

                # Sort rows based on the specified column
                if rows_data:
                    # Define sort key function that handles different data types
                    def sort_key(row_tuple):
                        row, original_item = row_tuple
                        if order_by and order_by in original_item:
                            val = original_item[order_by]
                        elif len(row) > sort_idx:
                            val = row[sort_idx]
                        else:
                            return (0, "")

                        # Try to convert to numeric for proper sorting
                        try:
                            # Remove any currency symbols or commas
                            clean_val = str(val).replace(',', '').replace('$', '')
                            return (1, float(clean_val))
                        except (ValueError, TypeError):
                            return (0, str(val))

                    # Sort with the appropriate direction
                    reverse_sort = sort_direction == "DESC"
                    rows_data.sort(key=sort_key, reverse=reverse_sort)

                # Apply row limit if specified
                total_rows = len(rows_data)
                if row_limit and row_limit < total_rows:
                    rows_data = rows_data[:row_limit]

                for row, _ in rows_data:
                    md_table += "| " + " | ".join([str(val) for val in row]) + " |\n"

                # Add note about limited rows if applicable
                if row_limit and row_limit < total_rows:
                    md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

                # Add note about sorting if applicable
                if order_by:
                    md_table += f"\n_Sorted by {order_by} {sort_direction}_\n"

                return md_table

            # Fallback to string representation
            return f"```json\n{json.dumps(value, indent=2)}\n```"

        # Process code references
        def replace_code(match):
            # Get the leading whitespace (we capture it but won't use it for the code block)
            indent = match.group(1)
            tool_id = match.group(2).strip()
            value_key = match.group(3).strip()
            language = match.group(4).strip()

            # Find the tool call using our method
            tool_call = self._get_tool_call(tool_id)
            if not tool_call or value_key not in tool_call.get("output", {}):
                return f"[CODE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

            # Get the code data
            value = tool_call.get("output", {}).get(value_key)
            return f"```{language}\n{value}\n```"

        # Apply all replacements
        result = re.sub(image_pattern, replace_image, template_text)
        result = re.sub(table_pattern, replace_table, result)
        result = re.sub(code_pattern, replace_code, result)

        # Replace standalone tool ID references with markdown links
        tool_id_pattern = r"(?<!\])\(#([a-f0-9]{8})\)"
        result = re.sub(tool_id_pattern, r"[\1](#\1)", result)
        return result

    def _get_tool_call(self, tool_id: str):
        return self.tool_id_map.get(tool_id)

    def _replace_image(self, match):
        tool_id = match.group(1).strip()
        value_key = match.group(2).strip()

        tool_call = self._get_tool_call(tool_id)

        if not tool_call or value_key not in tool_call.get("output", {}):
            return f"[IMAGE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

        image_data = tool_call.get("output", {}).get(value_key)
        if isinstance(image_data, str) and image_data.startswith("data:image"):
            tool_name = tool_call.get('tool_name', 'Graph from analysis')
            return f"<p><img src='{image_data}' alt='Tool call {tool_name}' /></p>"
        else:
            return "Graph generation failed: " + str(image_data)

    def _replace_table(self, match):
        indent, tool_id, value_key, limit, order_by, sort = match.groups()
        row_limit = int(limit.strip()) if limit else None
        order_by = order_by.strip() if order_by else None
        sort_direction = sort.strip().upper() if sort and sort.strip().upper() in ["ASC", "DESC"] else "ASC"

        tool_call = self._get_tool_call(tool_id)
        if not tool_call or value_key not in tool_call.get("output", {}):
            return f"[TABLE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

        value = tool_call.get("output", {}).get(value_key)

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return f"```\n{value}\n```"

        # This part is complex, will need careful implementation of table formatting
        # For now, returning a placeholder
        return self._format_as_markdown_table(value, row_limit, order_by, sort_direction)

    def _format_as_markdown_table(self, data, row_limit, order_by, sort_direction):
        """
        Format data as a sophisticated markdown table with sorting, limiting, and proper data handling.
        """
        # Handle different data structures
        if isinstance(data, dict) and any(key.startswith("Row ") for key in data.keys()):
            # Handle Row-based dictionary structure (execution_result format)
            # Get headers from the first row
            first_row_key = next((k for k in data.keys() if k.startswith("Row ")), None)
            if first_row_key and isinstance(data[first_row_key], list):
                headers = [item.get("columnName", f"Column {i+1}") for i, item in enumerate(data[first_row_key])]

                # Create the markdown table
                md_table = "| " + " | ".join(headers) + " |\n"
                md_table += "| " + " | ".join(["---" for _ in headers]) + " |\n"

                # Get all row keys and sort them
                row_keys = sorted([k for k in data.keys() if k.startswith("Row ")])

                # Convert row data to a list of dictionaries for sorting
                rows_data = []
                for row_key in row_keys:
                    if isinstance(data[row_key], list):
                        row_values = []
                        for item in data[row_key]:
                            val = item.get("value", "")
                            # Try to convert to float and round if possible
                            try:
                                val_float = float(val)
                                val = round(val_float, 2)
                                val = str(val)
                            except (ValueError, TypeError):
                                pass
                            row_values.append(val)
                        rows_data.append(row_values)

                # If order_by is specified, determine the column index
                sort_idx = 0
                if order_by:
                    try:
                        # First check if it's a column index (0-based)
                        sort_idx = int(order_by)
                    except ValueError:
                        # Then check if it's a column name
                        if order_by in headers:
                            sort_idx = headers.index(order_by)

                # Sort rows based on the specified column
                if rows_data:
                    # Define sort key function that handles different data types
                    def sort_key(row):
                        if len(row) <= sort_idx:
                            return (0, "")
                        val = row[sort_idx]
                        # Try to convert to numeric for proper sorting
                        try:
                            # Remove any currency symbols or commas
                            clean_val = str(val).replace(',', '').replace('$', '')
                            return (1, float(clean_val))
                        except (ValueError, TypeError):
                            return (0, str(val))

                    # Sort with the appropriate direction
                    reverse_sort = sort_direction == "DESC"
                    rows_data.sort(key=sort_key, reverse=reverse_sort)

                # Apply row limit if specified
                total_rows = len(rows_data)
                if row_limit and row_limit < total_rows:
                    rows_data = rows_data[:row_limit]

                # Add rows to the table
                for row_values in rows_data:
                    md_table += "| " + " | ".join([str(val) for val in row_values]) + " |\n"

                # Add note about limited rows if applicable
                if row_limit and row_limit < total_rows:
                    md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

                # Add note about sorting if applicable
                if order_by:
                    col_name = headers[sort_idx] if sort_idx < len(headers) else order_by
                    md_table += f"\n_Sorted by {col_name} {sort_direction}_\n"

                return md_table

        # Generic handling for other JSON structures
        elif isinstance(data, dict):
            # Try to convert dictionary to a table
            md_table = "| Key | Value |\n| --- | --- |\n"
            items = list(data.items())

            # Sort items by key or value
            if order_by == "key":
                items.sort(key=lambda x: x[0], reverse=(sort_direction == "DESC"))
            elif order_by == "value":
                # Try numeric sort for values if possible
                def sort_key(item):
                    try:
                        # Remove any currency symbols or commas
                        clean_val = str(item[1]).replace(',', '').replace('$', '')
                        return (1, float(clean_val))
                    except (ValueError, TypeError):
                        return (0, str(item[1]))
                items.sort(key=sort_key, reverse=(sort_direction == "DESC"))
            else:
                # Default sort by key
                items.sort(key=lambda x: x[0])

            # Apply row limit if specified
            total_rows = len(items)
            if row_limit and row_limit < total_rows:
                items = items[:row_limit]

            for k, v in items:
                # Try to convert to float and round if possible
                try:
                    v_float = float(v)
                    v = round(v_float, 2)
                except (ValueError, TypeError):
                    pass
                md_table += f"| {k} | {v} |\n"

            # Add note about limited rows if applicable
            if row_limit and row_limit < total_rows:
                md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

            # Add note about sorting if applicable
            if order_by:
                md_table += f"\n_Sorted by {order_by} {sort_direction}_\n"

            return md_table
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            # Try to convert list of dictionaries to a table
            headers = list(data[0].keys())
            md_table = "| " + " | ".join(headers) + " |\n"
            md_table += "| " + " | ".join(["---" for _ in headers]) + " |\n"

            # Convert to list of lists for easier processing
            rows_data = []
            for item in data:
                row = []
                for h in headers:
                    val = item.get(h, "")
                    # Try to convert to float and round if possible
                    try:
                        val_float = float(val)
                        val = round(val_float, 2)
                    except (ValueError, TypeError):
                        pass
                    row.append(val)
                rows_data.append((row, item))  # Store the original item for sorting

            # If order_by is specified, determine the column index
            sort_idx = 0
            if order_by:
                if order_by in headers:
                    sort_idx = headers.index(order_by)

            # Sort rows based on the specified column
            if rows_data:
                # Define sort key function that handles different data types
                def sort_key(row_tuple):
                    row, original_item = row_tuple
                    if order_by and order_by in original_item:
                        val = original_item[order_by]
                    elif len(row) > sort_idx:
                        val = row[sort_idx]
                    else:
                        return (0, "")

                    # Try to convert to numeric for proper sorting
                    try:
                        # Remove any currency symbols or commas
                        clean_val = str(val).replace(',', '').replace('$', '')
                        return (1, float(clean_val))
                    except (ValueError, TypeError):
                        return (0, str(val))

                # Sort with the appropriate direction
                reverse_sort = sort_direction == "DESC"
                rows_data.sort(key=sort_key, reverse=reverse_sort)

            # Apply row limit if specified
            total_rows = len(rows_data)
            if row_limit and row_limit < total_rows:
                rows_data = rows_data[:row_limit]

            for row, _ in rows_data:
                md_table += "| " + " | ".join([str(val) for val in row]) + " |\n"

            # Add note about limited rows if applicable
            if row_limit and row_limit < total_rows:
                md_table += f"\n_Showing {row_limit} of {total_rows} total rows_\n"

            # Add note about sorting if applicable
            if order_by:
                md_table += f"\n_Sorted by {order_by} {sort_direction}_\n"

            return md_table

        # Fallback to JSON representation
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    def _replace_code(self, match):
        indent, tool_id, value_key, language = match.groups()
        tool_call = self._get_tool_call(tool_id)
        if not tool_call or value_key not in tool_call.get("output", {}):
            return f"[CODE NOT FOUND FOR TOOL ID: {tool_id}, VALUE KEY: {value_key}]"

        value = tool_call.get("output", {}).get(value_key)
        return f"```{language.strip()}\n{value}\n```"

    def _generate_appendix(self) -> str:
        appendix = "\n\n## Appendix\n\n"

        # Add analysis performance summary if metadata is available
        if self.deepquery_metadata:
            appendix += self._generate_analysis_summary()

        appendix += "\n\n### Tool Calls\n\n"

        analysis_tool_calls = self.deepquery_metadata.get("tool_calls", [])

        filtered_tool_calls = filter_tool_calls_appendix(
            analysis_tool_calls,
            self.visualization_tool_calls,
            self.include_failed_tool_calls_appendix
        )

        for i, tool_call in enumerate(filtered_tool_calls, 1):
            tool_id = tool_call.get("tool_id", "unknown")
            tool_name = tool_call.get("tool_name", "unknown")
            tool_input = tool_call.get("input", {})
            tool_output = tool_call.get("output", {})

            appendix += f"<h3 id='{tool_id}'>Tool Call {i}: {tool_name}</h3>\n\n"
            appendix += f"**Tool ID**: `{tool_id}`\n\n"
            appendix += "**Input Parameters:**\n\n"
            appendix += "| Parameter | Value |\n"
            appendix += "|-----------|-------|\n"
            for key, value in tool_input.items():
                appendix += f"| {key} | {value} |\n"
            appendix += "\n"

            if "execution_result" in tool_output and tool_output.get("execution_result"):
                note = tool_output.get("execution_result_note", "")
                appendix += f"**Execution Result** {note}:\n\n"
                appendix += f"<table>\n<tool_id>{tool_id}</tool_id>\n<tool_value>execution_result</tool_value>\n<limit>10</limit>\n</table>\n\n"

            if "sql_query" in tool_output and tool_output.get("sql_query"):
                appendix += "**SQL Query**:\n\n"
                appendix += f"<code>\n<tool_id>{tool_id}</tool_id>\n<tool_value>sql_query</tool_value>\n<language>sql</language>\n</code>\n\n"

            if "query_explanation" in tool_output and tool_output.get("query_explanation"):
                appendix += "**Query Explanation**:\n\n"
                appendix += f"{tool_output['query_explanation']}\n\n"

            if "raw_graph" in tool_output and tool_output.get("raw_graph"):
                appendix += "**Graph**:\n\n"
                appendix += f"<image>\n<tool_id>{tool_id}</tool_id>\n<tool_value>raw_graph</tool_value>\n</image>\n\n"

            if "answer" in tool_output and tool_output.get("answer"):
                appendix += "**Answer**:\n\n"
                appendix += f"{tool_output['answer']}\n\n"

            # Handle any other output fields not specifically mentioned above
            handled_fields = {"execution_result", "sql_query", "query_explanation", "raw_graph", "answer", "execution_result_note"}
            other_fields = {k: v for k, v in tool_output.items() if k not in handled_fields and v}

            if other_fields:
                appendix += "**Output**:\n\n"
                appendix += "| Field | Value |\n"
                appendix += "|-------|-------|\n"
                for key, value in other_fields.items():
                    # Truncate very long values for readability
                    if isinstance(value, str) and len(value) > 200:
                        value = value[:200] + "..."
                    appendix += f"| {key} | {value} |\n"
                appendix += "\n"

            appendix += "---\n\n"

        return appendix

    def _generate_analysis_summary(self) -> str:
        """Generate analysis performance summary from DeepQuery metadata."""
        if not self.deepquery_metadata:
            return ""

        metadata = self.deepquery_metadata
        summary = "### DeepQuery Summary\n\n"

        # Analysis execution metrics
        analysis_time = metadata.get("analysis_execution_time", 0)
        if analysis_time > 60:
            minutes = int(analysis_time // 60)
            seconds = int(analysis_time % 60)
            summary += f"- **Total Analysis Time**: {int(analysis_time)} seconds ({minutes} minute{'s' if minutes != 1 else ''} and {seconds} second{'s' if seconds != 1 else ''})\n"
        else:
            summary += f"- **Total Analysis Time**: {int(analysis_time)} second{'s' if int(analysis_time) != 1 else ''}\n"

        iterations = metadata.get("analysis_iterations", 0)
        summary += f"- **Analysis Iterations**: {iterations} loops\n"

        tool_calls = metadata.get("total_tool_calls", 0)
        summary += f"- **Tool Calls Executed**: {tool_calls} calls\n\n"

        # LLM configuration
        planning_provider = metadata.get("planning_provider", "unknown")
        planning_model = metadata.get("planning_model", "unknown")
        thinking_temp = metadata.get("thinking_llm_temperature", 0.0)
        thinking_tokens = metadata.get("thinking_llm_max_tokens", 0)
        summary += f"- **Planning LLM**: {planning_provider}/{planning_model} (temp: {thinking_temp}, max_tokens: {thinking_tokens})\n"

        exec_provider = metadata.get("actual_executing_provider", "unknown")
        exec_model = metadata.get("actual_executing_model", "unknown")
        exec_temp = metadata.get("actual_executing_temperature", 0.0)
        exec_tokens = metadata.get("actual_executing_max_tokens", 0)
        summary += f"- **Execution LLM**: {exec_provider}/{exec_model} (temp: {exec_temp}, max_tokens: {exec_tokens})\n"

        return summary
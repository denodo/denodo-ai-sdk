import re
import logging

logger = logging.getLogger(__name__)

def parse_xml(text):
    """
    Parse content between XML-like tags, handling multiline content and duplicate tags.

    Args:
        text: The text containing XML-like tags

    Returns:
        Dictionary mapping tag names to their content
    """

    if isinstance(text, list):
        # Means the LLM generated multiple <tools> tags, we need to join the elements of all of them
        text = "\n\n".join(text)
    elif not isinstance(text, str):
        logger.error(f"Invalid XML input: {text}")
        return {}

    pattern = r"<(\w+)>([\s\S]*?)</\1>"
    matches = re.finditer(pattern, text)
    result = {}

    for match in matches:
        tag, content = match.group(1), match.group(2).strip()
        if tag in result:
            if isinstance(result[tag], list):
                result[tag].append(content)
            else:
                result[tag] = [result[tag], content]
        else:
            result[tag] = content

    return result

def format_tool_as_xml(tool):
    """
    Format a tool's documentation in XML format.

    Args:
        tool: The tool function to format

    Returns:
        XML-formatted tool documentation
    """
    doc = tool.__doc__ or ""
    tool_name = tool.__name__

    # Extract parameter information from docstring
    param_pattern = r"Args:(.*?)(?:Returns:|$)"
    param_match = re.search(param_pattern, doc, re.DOTALL)

    # Create the XML format
    xml = f"<{tool_name}>\n"

    if param_match:
        params_text = param_match.group(1).strip()
        param_lines = params_text.split('\n')

        for line in param_lines:
            line = line.strip()
            if line:
                # Extract parameter name and description
                param_match = re.match(r'\s*(\w+)(?:\s*\(\w+\))?:\s*(.*)', line)
                if param_match:
                    param_name, param_desc = param_match.groups()
                    xml += f"<{param_name}>{param_desc}</{param_name}>\n"

    xml += f"</{tool_name}>"
    return xml

def remove_think_tags(text):
    """
    Remove <think> and </think> tags and their content from the text.
    """
    pattern = r'<think>.*?</think>'
    return re.sub(pattern, '', text, flags=re.DOTALL).strip()
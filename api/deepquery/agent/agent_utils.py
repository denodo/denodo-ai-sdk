import uuid
from datetime import datetime

def get_formatted_date():
    """
    Get the current date formatted with timezone.

    Returns:
        Formatted date string with timezone
    """
    now = datetime.now()
    local_now = now.astimezone()
    local_tz = local_now.tzinfo
    local_tzname = local_tz.tzname(local_now)
    return now.strftime("%Y-%m-%d %H:%M") + " " + local_tzname

def generate_session_id():
    """
    Generate a unique session ID.

    Returns:
        UUID string for the session
    """
    return str(uuid.uuid4())

def add_final_answer_tool(tools, final_answer_func):
    """
    Adds the final_answer tool to the list of tools if it's not already there.
    """
    if not any(t.__name__ == 'final_answer' for t in tools):
        tools.append(final_answer_func)
    return tools
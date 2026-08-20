"""
General helper utilities.
"""
import base64
import os
import sys
import logging
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from utils import langfuse
from utils.utils import custom_tag_parser
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sample_chatbot.engine.prompts import CONV_HISTORY_TITLE_GENERATION_PROMPT

def setup_user_details(user_details):
    """
    Format user details for inclusion in prompts.

    Args:
        user_details: User-provided details string

    Returns:
        Formatted string with user details, or empty string if none
    """
    user_detail_strings = (user_details or "").strip()
    if not user_detail_strings:
        return ""

    return f"""<user_details>
{user_detail_strings}
</user_details>"""

def format_user_instructions_for_prompt(chatbot_custom_instructions):
    text = (chatbot_custom_instructions or "").strip()
    if not text:
        return ""
    return f"<user_instructions>\n{text}\n</user_instructions>"

def format_chat_log(agent_id, conversation_id, event, tokens=None):
    """Build a structured chat event log prefix for admin triage."""
    agent = agent_id or "global"
    conversation = conversation_id or "unknown"
    base = f"[agent_id: {agent}] [conversation_id: {conversation}] [{event}]"
    if tokens is not None:
        return f"{base} [tokens: {tokens}]"
    return base

def check_env_variables(required_vars):
    """
    Check that required environment variables are set.

    Args:
        required_vars: List of required environment variable names

    Exits with code 1 if any are missing.
    """
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("ERROR. The following required environment variables are missing:")
        for var in missing_vars:
            print(f"- {var}")
        print("Please set these variables before starting the application.")
        sys.exit(1)

def setup_directories(upload_folder="uploads", report_folder="reports"):
    """
    Create upload and report directories if they don't exist.

    Args:
        upload_folder: Path for upload directory
        report_folder: Path for report directory
    """
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(report_folder, exist_ok=True)

def setup_directory(report_folder="reports"):
    os.makedirs(report_folder, exist_ok=True)

def get_config_value(settings_dict, key, env_name, default=None, cast_type=str):
    """
    Retrieves a value based on priority:
    1. From the provided settings dictionary.
    2. From environment variables.
    3. From a default.
    """
    val = settings_dict.get(key)

    if val is None:
        val = os.getenv(env_name, default)

    if cast_type == bool and not isinstance(val, bool):
        return bool(int(val))

    return cast_type(val)

def get_icon_as_base64(filename, max_size=(256, 256)):
    """
    Safely reads an icon, resizes it, and returns it as a base64 string.
    Returns None if the file is invalid or missing.
    """
    if filename is None:
        return None

    base_path = "api/agents/custom/icons"
    file_path = os.path.join(base_path, filename)

    # 1. Check if file exists
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return None

    try:
        with Image.open(file_path) as img:
            # 2. Handle color modes (ensure transparency support)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")

            # 3. Smart Resize (only scales down, maintains aspect ratio)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 4. Save to memory buffer with optimization
            buffered = BytesIO()
            img.save(buffered, format="PNG", optimize=True)

            # 5. Encode to Base64
            img_bytes = buffered.getvalue()
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')

            return f"data:image/png;base64,{img_base64}"

    except UnidentifiedImageError:
        logging.error(f"The file {filename} is not a valid image or is corrupted.")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred processing {filename}: {e}")
        return None

def generate_chat_title(llm, user_query, session_id=None):
    """
    Generates a short title using the LLM based on the first question.

    Args:
        llm: UniformLLM instance to use for generation
        user_query: The user's first message
        session_id: Optional Langfuse session ID (thread_id) for tracing
    """
    try:
        logging.debug(f"Generating title for query: {user_query[:30]}...")

        prompt = PromptTemplate.from_template(CONV_HISTORY_TITLE_GENERATION_PROMPT)
        chain = prompt | llm.llm | StrOutputParser()

        chain_config = langfuse.build_config(
            model_id=f"{llm.provider_name}.{llm.model_name}",
            session_id=session_id,
            run_name="generate_chat_title"
        )

        response = chain.invoke({"user_query": user_query}, config=chain_config)
        logging.debug(f"Raw LLM response for title generation: {response}")

        titles = custom_tag_parser(response, 'title', default='')

        if titles and titles[0]:
            new_title = titles[0].strip()
        else:
            new_title = response.strip().strip('"').strip("'").replace('<title>', '').replace('</title>', '')

        logging.debug(f"Successfully generated title: {new_title}")
        return new_title

    except Exception as e:
        logging.error(f"Error generating title: {str(e)}")
        return (user_query[:30] + '...') if len(user_query) > 30 else user_query

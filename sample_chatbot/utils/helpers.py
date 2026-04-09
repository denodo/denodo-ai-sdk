"""
General helper utilities.
"""
import base64
import os
import sys
import logging
from io import BytesIO
from PIL import Image, UnidentifiedImageError

def setup_user_details(user_details, username=''):
    """
    Format user details for inclusion in prompts.

    Args:
        user_details: User-provided details string
        username: User's username

    Returns:
        Formatted string with user details
    """
    if not user_details and not username:
        return ""

    prefix = "These are the details about the user you are talking to:"

    if username and user_details:
        return f"{prefix} Username: {username}\n\n{user_details}"
    elif username:
        return f"{prefix} Username: {username}"
    else:
        return f"{prefix} {user_details}"

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
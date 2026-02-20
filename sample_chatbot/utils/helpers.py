"""
General helper utilities.
"""

import os
import sys

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
"""
Entry point for running the Flask chatbot application.
"""

# Load environment variables first, before importing app
# This ensures ENV vars are available when modules like Langfuse check them at import time
from dotenv import load_dotenv

from utils.chatbot_env import chatbot_env_startup_notice, resolve_chatbot_env_path

_chatbot_env_notice = chatbot_env_startup_notice()
if _chatbot_env_notice:
    print(_chatbot_env_notice)

load_dotenv(resolve_chatbot_env_path())

from sample_chatbot.app import create_app, run_app  # noqa: E402

app = create_app()

if __name__ == '__main__':
    run_app(app)
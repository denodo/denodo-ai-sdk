"""
Entry point for running the Flask chatbot application.
"""

# Load environment variables first, before importing app
# This ensures ENV vars are available when modules like Langfuse check them at import time
from dotenv import load_dotenv

load_dotenv('sample_chatbot/chatbot_config.env')

from sample_chatbot.app import create_app, run_app  # noqa: E402

app = create_app()

if __name__ == '__main__':
    run_app(app)
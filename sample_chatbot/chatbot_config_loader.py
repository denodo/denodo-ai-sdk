from dotenv import load_dotenv

def load_config():
    chatbot_config_files = [
        'sample_chatbot/chatbot_config.env',
        'sample_chatbot/chatbot_prompts.env'
    ]
    for config_file in chatbot_config_files:
        load_dotenv(config_file)
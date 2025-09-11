from dotenv import load_dotenv

def load_config():
    chatbot_config_files = [
        'api/utils/sdk_config.env',
        'api/utils/sdk_prompts.env'
    ]
    for config_file in chatbot_config_files:
        load_dotenv(config_file)
import os
import logging

from utils.utils import TokenCounter, RefreshableBotoSession

class UniformLLM:
    VALID_PROVIDERS = [
        "OpenAI",
        "AzureOpenAI",
        "Bedrock",
        "Google",
        "Anthropic",
        "NVIDIA",
        "Groq",
        "Ollama",
        "Mistral"
        ]
    
    def __init__(self, provider_name, model_name, temperature = 0, max_tokens = 2048): 
        self.provider_name = provider_name
        self.model_name = model_name
        self.llm = None
        self.temperature = temperature # Temperature in OpenAI goes from 0 to 2, in AWS/Vertex from 0 to 1
        self.max_tokens = max_tokens
        self.callback = None
        self.tokens = self.calculate_tokens()

        if self.provider_name is None:
            raise ValueError("Provider name not set.")

        if self.provider_name.lower() not in list(map(str.lower, self.VALID_PROVIDERS)):
            logging.warning(f"Provider '{self.provider_name}' not in standard list. Creating custom OpenAI-compatible provider.")
            logging.info(f"Expected environment variables for custom provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required)")
            logging.info(f"- {self.provider_name.upper()}_BASE_URL (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            self.setup_custom()
            return

        if self.provider_name.lower() == "openai":
            self.setup_openai()
        elif self.provider_name.lower() == "azureopenai":
            self.setup_azure_openai()
        elif self.provider_name.lower() == "bedrock":
            self.setup_bedrock()
        elif self.provider_name.lower() == "google":
            self.setup_google()
        elif self.provider_name.lower() == "nvidia":
            self.setup_nvidia()
        elif self.provider_name.lower() == "anthropic":
            self.setup_anthropic()
        elif self.provider_name.lower() == "groq":
            self.setup_groq()
        elif self.provider_name.lower() == "ollama":
            self.setup_ollama()
        elif self.provider_name.lower() == "mistral":
            self.setup_mistral()
    
    def setup_ollama(self):
        from langchain_ollama.chat_models import ChatOllama

        self.llm = ChatOllama(model = self.model_name, temperature = self.temperature, max_tokens = self.max_tokens)
        self.callback = TokenCounter(self.llm)

    def setup_nvidia(self):
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        api_key = os.getenv('NVIDIA_API_KEY')
        base_url = os.getenv('NVIDIA_BASE_URL')
        
        if api_key is None:
            raise ValueError("NVIDIA_API_KEY environment variable not set.")
        
        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        if base_url is not None:
            kwargs["base_url"] = base_url
            
        self.llm = ChatNVIDIA(**kwargs)
        self.callback = TokenCounter(self.llm)

    def setup_anthropic(self):
        from langchain_anthropic import ChatAnthropic

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key is None:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

        self.llm = ChatAnthropic(model_name = self.model_name, api_key = api_key, temperature = self.temperature, max_tokens = self.max_tokens)
        self.callback = TokenCounter(self.llm)

    def setup_groq(self):
        from langchain_groq import ChatGroq

        api_key = os.getenv('GROQ_API_KEY')
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable not set.")

        self.llm = ChatGroq(model_name = self.model_name, groq_api_key = api_key, temperature = self.temperature, max_tokens = self.max_tokens, streaming = True)
        self.callback = TokenCounter(self.llm)
    
    def setup_google(self):
        from langchain_google_vertexai import ChatVertexAI
        from vertexai.generative_models import HarmCategory, HarmBlockThreshold

        google_credentials_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if google_credentials_file is None:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

        safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH
        }

        self.llm = ChatVertexAI(
            model_name=self.model_name,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            safety_settings=safety_settings
        )
        self.llm = self.llm.bind(safety_settings=safety_settings)

        self.callback = TokenCounter(self.llm)

    def setup_openai(self):
        from langchain_openai import ChatOpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL')
        proxy = os.getenv('OPENAI_PROXY')
        organization_id = os.getenv('OPENAI_ORG_ID')

        if api_key is None:
            raise ValueError("OPENAI_API_KEY environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
            "temperature": self.temperature * 2,
            "max_tokens": self.max_tokens,
        }

        if base_url is not None:
            kwargs["base_url"] = base_url

        if proxy is not None:
            kwargs["openai_proxy"] = proxy

        if organization_id is not None:
            kwargs["organization"] = organization_id

        self.llm = ChatOpenAI(**kwargs)
        self.callback = TokenCounter(self.llm)

    def setup_azure_openai(self):
        from langchain_openai import AzureChatOpenAI

        api_version = os.getenv("AZURE_API_VERSION")
        api_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_proxy = os.getenv("AZURE_OPENAI_PROXY")

        if api_version is None or api_endpoint is None:
            raise ValueError("AzureOpenAI environment variables not set.")

        if api_key is None and api_proxy is None:
            raise ValueError("AzureOpenAI API key or proxy not set. One of them is required as authentication method.")

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "azure_deployment": self.model_name,
            "temperature": self.temperature * 2,
        }

        if api_key is not None:
            kwargs["openai_api_key"] = api_key
        else:
            logging.warning("AzureOpenAI API key not set. Using default authentication.")

        if api_proxy is not None:
            kwargs["openai_proxy"] = api_proxy
        else:
            logging.warning("AzureOpenAI proxy not set. Using direct connection.")

        self.llm = AzureChatOpenAI(**kwargs)
        self.callback = TokenCounter(self.llm)

    def setup_bedrock(self):
        from langchain_aws import ChatBedrock

        AWS_REGION = os.getenv("AWS_REGION")
        AWS_PROFILE_NAME = os.getenv("AWS_PROFILE_NAME")
        AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN")
        AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
        AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

        if AWS_REGION is None:
            raise ValueError("AWS_REGION environment variable must be set (even when using IAM credentials).")

        refreshable_session_instance = RefreshableBotoSession(
            region_name = AWS_REGION,
            profile_name = AWS_PROFILE_NAME,
            sts_arn = AWS_ROLE_ARN,
            access_key = AWS_ACCESS_KEY_ID,
            secret_key = AWS_SECRET_ACCESS_KEY
        )

        session = refreshable_session_instance.refreshable_session()
        client = session.client('bedrock-runtime')

        self.llm = ChatBedrock(
            client = client,
            model = self.model_name,
            model_kwargs = {
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
        )

        self.callback = TokenCounter(self.llm)

    def setup_mistral(self):
        from langchain_mistralai import ChatMistralAI

        api_key = os.getenv('MISTRAL_API_KEY')
        if api_key is None:
            raise ValueError("MISTRAL_API_KEY environment variable not set.")

        self.llm = ChatMistralAI(model = self.model_name, mistral_api_key = api_key, temperature = self.temperature, max_tokens = self.max_tokens)
        self.callback = TokenCounter(self.llm)

    def setup_custom(self):
        from langchain_openai import ChatOpenAI

        api_key = os.getenv(f'{self.provider_name.upper()}_API_KEY')
        base_url = os.getenv(f'{self.provider_name.upper()}_BASE_URL')
        proxy = os.getenv(f'{self.provider_name.upper()}_PROXY')

        if api_key is None:
            raise ValueError(f"{self.provider_name.upper()}_API_KEY environment variable not set.")
        if base_url is None:
            raise ValueError(f"{self.provider_name.upper()}_BASE_URL environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": self.temperature * 2,
            "max_tokens": self.max_tokens,
        }

        if proxy is not None:
            kwargs["openai_proxy"] = proxy

        self.llm = ChatOpenAI(**kwargs)
        self.callback = TokenCounter(self.llm)

    def calculate_tokens(self):
        tokens = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
        }

        if self.callback is not None:
            tokens['input_tokens'] += self.callback.prompt_tokens
            tokens['output_tokens'] += self.callback.completion_tokens
            tokens['total_tokens'] += self.callback.total_tokens
        return tokens

    @staticmethod
    def get_providers():
        return UniformLLM.VALID_PROVIDERS

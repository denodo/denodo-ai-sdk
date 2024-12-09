import os
import logging

from utils.utils import RefreshableBotoSession

class UniformEmbeddings:
    VALID_PROVIDERS = [
        "OpenAI",
        "AzureOpenAI",
        "Bedrock",
        "Google",
        "Ollama",
        "Mistral",
        "NVIDIA"
    ]

    def __init__(self, provider_name, model_name):
        self.provider_name = provider_name
        self.model_name = model_name
        self.model = None

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
        elif self.provider_name.lower() == "ollama":
            self.setup_ollama()
        elif self.provider_name.lower() == "mistral":
            self.setup_mistral()
        elif self.provider_name.lower() == "nvidia":
            self.setup_nvidia()
    
    def setup_ollama(self):
        from langchain_community.embeddings import OllamaEmbeddings

        self.model = OllamaEmbeddings(model = self.model_name)

    def setup_nvidia(self):
        from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

        api_key = os.getenv('NVIDIA_API_KEY')
        base_url = os.getenv('NVIDIA_BASE_URL')

        if api_key is None:
            raise ValueError("NVIDIA_API_KEY environment variable not set.")
        
        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
        }

        if base_url is not None:
            kwargs["base_url"] = base_url

        self.model = NVIDIAEmbeddings(**kwargs)

    def setup_google(self):
        from langchain_google_vertexai import VertexAIEmbeddings

        api_key = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if api_key is None:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

        self.model = VertexAIEmbeddings(model_name = self.model_name)

    def setup_openai(self):
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL')
        proxy = os.getenv('OPENAI_PROXY')
        organization_id = os.getenv('OPENAI_ORG_ID')
        dimensions = os.getenv('OPENAI_EMBEDDINGS_DIMENSIONS')
        
        if api_key is None:
            raise ValueError("OPENAI_API_KEY environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "openai_api_key": api_key,
            "check_embedding_ctx_length": False,
        }

        if base_url is not None:
            kwargs["openai_api_base"] = base_url

        if proxy is not None:
            kwargs["openai_proxy"] = proxy

        if organization_id is not None:
            kwargs["organization"] = organization_id

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.model = OpenAIEmbeddings(**kwargs)

    def setup_azure_openai(self):
        from langchain_openai import AzureOpenAIEmbeddings

        api_version = os.getenv("AZURE_API_VERSION")
        api_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_proxy = os.getenv("AZURE_OPENAI_PROXY")
        dimensions = os.getenv('AZUREOPENAI_EMBEDDINGS_DIMENSIONS')

        if api_version is None or api_endpoint is None:
            raise ValueError("AzureOpenAI environment variables not set.")

        if api_key is None and api_proxy is None:
            raise ValueError("AzureOpenAI API key or proxy not set. One of them is required as authentication method.")

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "deployment": self.model_name,
            "check_embedding_ctx_length": False,
        }

        if api_key is not None:
            kwargs["openai_api_key"] = api_key
        else:
            logging.warning("AzureOpenAI API key not set. Using proxy for authentication.")

        if api_proxy is not None:
            kwargs["openai_proxy"] = api_proxy
        else:
            logging.warning("AzureOpenAI proxy not set. Using API key for authentication.")

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.model = AzureOpenAIEmbeddings(**kwargs)

    def setup_bedrock(self):
        from langchain_aws import BedrockEmbeddings

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

        self.model = BedrockEmbeddings(
            client = client,
            model_id = self.model_name
        )

    def setup_mistral(self):
        from langchain_mistralai import MistralAIEmbeddings

        api_key = os.getenv('MISTRAL_API_KEY')
        if api_key is None:
            raise ValueError("MISTRAL_API_KEY environment variable not set.")

        self.model = MistralAIEmbeddings(model = self.model_name, mistral_api_key = api_key)

    def setup_custom(self):
        from langchain_openai import OpenAIEmbeddings

        provider_upper = self.provider_name.upper()
        api_key = os.getenv(f'{provider_upper}_API_KEY')
        base_url = os.getenv(f'{provider_upper}_BASE_URL')
        proxy = os.getenv(f'{provider_upper}_PROXY')
        
        if api_key is None:
            raise ValueError(f"{provider_upper}_API_KEY environment variable not set.")
        if base_url is None:
            raise ValueError(f"{provider_upper}_BASE_URL environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "openai_api_key": api_key,
            "openai_api_base": base_url,
            "check_embedding_ctx_length": False,
        }

        if proxy is not None:
            kwargs["openai_proxy"] = proxy

        self.model = OpenAIEmbeddings(**kwargs)
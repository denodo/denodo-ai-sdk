import os
import httpx
import logging

from langchain.storage import LocalFileStore
from utils.utils import RefreshableBotoSession
from langchain.embeddings import CacheBackedEmbeddings

class UniformEmbeddings:
    VALID_PROVIDERS = [
        "OpenAI",
        "AzureOpenAI",
        "Bedrock",
        "Google",
        "Ollama",
        "Mistral",
        "NVIDIA",
        "GoogleAIStudio"
    ]

    def __init__(self, provider_name, model_name):
        self.provider_name = provider_name
        self.model_name = model_name
        self.model = None
        self.store = LocalFileStore("./cache/embeddings/")
        self.base_embeddings = None

        if self.provider_name.lower() not in list(map(str.lower, self.VALID_PROVIDERS)):
            logging.warning(f"Provider '{self.provider_name}' not in standard list. Creating custom OpenAI-compatible provider.")
            logging.info("Expected environment variables for custom provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required)")
            logging.info(f"- {self.provider_name.upper()}_BASE_URL (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            self.setup_custom()

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
        elif self.provider_name.lower() == "googleaistudio":
            self.setup_google_ai_studio()

        if ":" in self.model_name:
            self.model = self.base_embeddings
        else:
            self.model = CacheBackedEmbeddings.from_bytes_store(
                self.base_embeddings,
                self.store,
                namespace=self.model_name,
                query_embedding_cache=True,
            )

    def setup_google_ai_studio(self):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = os.getenv('GOOGLE_AI_STUDIO_API_KEY')
        if api_key is None:
            raise ValueError("GOOGLE_AI_STUDIO_API_KEY environment variable not set.")
        
        self.base_embeddings = GoogleGenerativeAIEmbeddings(
            model=self.model_name,
            google_api_key=api_key
        )

    
    def setup_ollama(self):
        from langchain_community.embeddings import OllamaEmbeddings
        base_url = os.getenv('OLLAMA_API_BASE_URL')
        
        if base_url:
            self.base_embeddings = OllamaEmbeddings(model = self.model_name, base_url = base_url)
        else:
            self.base_embeddings = OllamaEmbeddings(model = self.model_name)

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

        self.base_embeddings = NVIDIAEmbeddings(**kwargs)

    def setup_google(self):
        from langchain_google_vertexai import VertexAIEmbeddings

        api_key = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if api_key is None:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")

        self.base_embeddings = VertexAIEmbeddings(model_name = self.model_name)

    def setup_openai(self):
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL')
        proxy = os.getenv('OPENAI_PROXY_URL')
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
            _http_client = httpx.Client(proxy = proxy, verify = False)
            _http_async_client = httpx.AsyncClient(proxy = proxy, verify = False)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client

        if organization_id is not None:
            kwargs["organization"] = organization_id

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.base_embeddings = OpenAIEmbeddings(**kwargs)

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
            _http_client = httpx.Client(proxy = api_proxy, verify = False)
            _http_async_client = httpx.AsyncClient(proxy = api_proxy, verify = False)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client
        else:
            logging.warning("AzureOpenAI proxy not set. Using API key for authentication.")

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.base_embeddings = AzureOpenAIEmbeddings(**kwargs)

    def setup_bedrock(self):
        from langchain_aws import BedrockEmbeddings

        AWS_REGION = os.getenv("AWS_REGION")
        AWS_PROFILE_NAME = os.getenv("AWS_PROFILE_NAME")
        AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN")
        AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
        AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

        refreshable_session_instance = RefreshableBotoSession(
            region_name = AWS_REGION,
            profile_name = AWS_PROFILE_NAME,
            sts_arn = AWS_ROLE_ARN,
            access_key = AWS_ACCESS_KEY_ID,
            secret_key = AWS_SECRET_ACCESS_KEY
        )

        session = refreshable_session_instance.refreshable_session()

        client = session.client('bedrock-runtime')

        self.base_embeddings = BedrockEmbeddings(
            client = client,
            model_id = self.model_name
        )

    def setup_mistral(self):
        from langchain_mistralai import MistralAIEmbeddings

        api_key = os.getenv('MISTRAL_API_KEY')
        if api_key is None:
            raise ValueError("MISTRAL_API_KEY environment variable not set.")

        self.base_embeddings = MistralAIEmbeddings(model = self.model_name, mistral_api_key = api_key)

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

        self.base_embeddings = OpenAIEmbeddings(**kwargs)
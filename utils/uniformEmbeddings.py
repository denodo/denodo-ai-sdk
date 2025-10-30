import os
import httpx
import logging

from langchain.storage import LocalFileStore
from utils.utils import RefreshableBotoSession, get_custom_headers_from_env
from langchain.embeddings import CacheBackedEmbeddings

class UniformEmbeddings:
    VALID_PROVIDERS = [
        "OpenAI",
        "Azure",
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

        if self.provider_name.lower() == "openai":
            self.setup_openai()
        elif self.provider_name.lower() == "azure":
            self.setup_azure()
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
        elif self.provider_name.lower().startswith("azure_"):
            logging.info(f"Provider '{self.provider_name}' detected as custom Azure-compatible provider.")
            logging.info("Expected environment variables for custom Azure provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required if no proxy)")
            logging.info(f"- {self.provider_name.upper()}_ENDPOINT (required)")
            logging.info(f"- {self.provider_name.upper()}_API_VERSION (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            self.setup_custom_azure()
        elif self.provider_name.lower() not in list(map(str.lower, self.VALID_PROVIDERS)):
            logging.warning(f"Provider '{self.provider_name}' not in standard list. Creating custom OpenAI-compatible provider.")
            logging.info("Expected environment variables for custom provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required)")
            logging.info(f"- {self.provider_name.upper()}_BASE_URL (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            self.setup_custom()

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
        custom_headers = get_custom_headers_from_env("OPENAI")

        # If no API key is provided, assume auth is handled by custom headers.
        # OpenAIEmbeddings requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError("OPENAI_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "model": self.model_name,
            "openai_api_key": api_key,
            "check_embedding_ctx_length": False,
        }

        if base_url is not None:
            kwargs["openai_api_base"] = base_url

        if proxy is not None or custom_headers:
            client_kwargs = {}
            if proxy:
                client_kwargs["proxy"] = proxy
                verify_ssl_env = os.getenv('OPENAI_PROXY_VERIFY_SSL', '0')
                client_kwargs["verify"] = (verify_ssl_env == '1')
            if custom_headers:
                client_kwargs["headers"] = custom_headers

            _http_client = httpx.Client(**client_kwargs)
            _http_async_client = httpx.AsyncClient(**client_kwargs)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client

        if organization_id is not None:
            kwargs["organization"] = organization_id

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.base_embeddings = OpenAIEmbeddings(**kwargs)

    def setup_azure(self):
        from langchain_openai import AzureOpenAIEmbeddings

        api_version = os.getenv("AZURE_API_VERSION")
        api_endpoint = os.getenv("AZURE_ENDPOINT")
        api_key = os.getenv("AZURE_API_KEY")
        api_proxy = os.getenv("AZURE_PROXY")
        dimensions = os.getenv('AZURE_EMBEDDINGS_DIMENSIONS')
        custom_headers = get_custom_headers_from_env("AZURE")

        if api_version is None or api_endpoint is None:
            raise ValueError("Azure environment variables not set.")

        # If no API key is provided, assume auth is handled by custom headers.
        # AzureOpenAIEmbeddings requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError("AZURE_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "deployment": self.model_name,
            "check_embedding_ctx_length": False,
            "openai_api_key": api_key,
        }

        if api_proxy is not None or custom_headers:
            client_kwargs = {}
            if api_proxy:
                client_kwargs["proxy"] = api_proxy
                verify_ssl_env = os.getenv('AZURE_PROXY_VERIFY_SSL', '0')
                client_kwargs["verify"] = (verify_ssl_env == '1')
            if custom_headers:
                client_kwargs["headers"] = custom_headers

            _http_client = httpx.Client(**client_kwargs)
            _http_async_client = httpx.AsyncClient(**client_kwargs)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client

        if dimensions is not None:
            kwargs["dimensions"] = int(dimensions)

        self.base_embeddings = AzureOpenAIEmbeddings(**kwargs)

    def setup_custom_azure(self):
        from langchain_openai import AzureOpenAIEmbeddings

        provider_upper = self.provider_name.upper()
        api_version = os.getenv(f"{provider_upper}_API_VERSION")
        api_endpoint = os.getenv(f"{provider_upper}_ENDPOINT")
        api_key = os.getenv(f"{provider_upper}_API_KEY")
        api_proxy = os.getenv(f"{provider_upper}_PROXY")
        dimensions = os.getenv(f'{provider_upper}_EMBEDDINGS_DIMENSIONS')
        custom_headers = get_custom_headers_from_env(self.provider_name)

        if api_version is None or api_endpoint is None:
            raise ValueError(f"Custom Azure provider '{self.provider_name}' environment variables not set.")

        # If no API key is provided, assume auth is handled by custom headers.
        # AzureOpenAIEmbeddings requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError(f"{provider_upper}_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "deployment": self.model_name,
            "check_embedding_ctx_length": False,
            "openai_api_key": api_key,
        }

        if api_proxy is not None or custom_headers:
            client_kwargs = {}
            if api_proxy:
                client_kwargs["proxy"] = api_proxy
                verify_ssl_env = os.getenv(f'{provider_upper}_PROXY_VERIFY_SSL', '0')
                client_kwargs["verify"] = (verify_ssl_env == '1')
            if custom_headers:
                client_kwargs["headers"] = custom_headers

            _http_client = httpx.Client(**client_kwargs)
            _http_async_client = httpx.AsyncClient(**client_kwargs)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client

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
        custom_headers = get_custom_headers_from_env(self.provider_name)

        # If no API key is provided, assume auth is handled by custom headers.
        # OpenAIEmbeddings requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError(f"{provider_upper}_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        if base_url is None:
            raise ValueError(f"{provider_upper}_BASE_URL environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "openai_api_key": api_key,
            "openai_api_base": base_url,
            "check_embedding_ctx_length": False,
        }

        if proxy is not None or custom_headers:
            client_kwargs = {}
            if proxy:
                client_kwargs["proxy"] = proxy
                verify_ssl_env = os.getenv(f'{provider_upper}_PROXY_VERIFY_SSL', '0')
                client_kwargs["verify"] = (verify_ssl_env == '1')
            if custom_headers:
                client_kwargs["headers"] = custom_headers

            _http_client = httpx.Client(**client_kwargs)
            _http_async_client = httpx.AsyncClient(**client_kwargs)

            kwargs["http_client"] = _http_client
            kwargs["http_async_client"] = _http_async_client

        self.base_embeddings = OpenAIEmbeddings(**kwargs)
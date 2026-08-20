import os
import httpx
import logging

from utils.utils import RefreshableBotoSession, get_custom_headers_from_env

class UniformLLM:
    VALID_PROVIDERS = [
        "openai",
        "azure",
        "bedrock",
        "google",
        "googleaistudio",
        "anthropic",
        "nvidia",
        "groq",
        "ollama",
        "mistral",
        "sambanova",
        "openrouter",
        ]

    def __init__(self, provider_name, model_name, temperature = 0.0, max_tokens = 4096):
        self.provider_name = provider_name
        self.model_name = model_name
        self.llm = None
        self.temperature = temperature # NOTE: Temperature in OpenAI goes from 0 to 2
        self.max_tokens = max_tokens
        self.tokens = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0
        }
        self.effort_suffix_profiles = {
            "openai": ["none", "minimal", "low", "medium", "high", "xhigh"],
            "google_gemini": ["low", "medium", "high"],
            "google_anthropic": ["low", "medium", "high", "xhigh", "max"],
        }

        if self.provider_name.lower() == "openai":
            self.setup_openai()
        elif self.provider_name.lower() == "azure":
            self.setup_azure()
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
        elif self.provider_name.lower() == "googleaistudio":
            self.setup_google_ai_studio()
        elif self.provider_name.lower() == "sambanova":
            self.setup_sambanova()
        elif self.provider_name.lower() == "openrouter":
            self.setup_openrouter()
        elif self.provider_name.lower().startswith("azure_"):
            logging.info(f"Provider '{self.provider_name}' detected as custom Azure-compatible provider.")
            logging.info("Expected environment variables for custom Azure provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required if no proxy)")
            logging.info(f"- {self.provider_name.upper()}_ENDPOINT (required)")
            logging.info(f"- {self.provider_name.upper()}_API_VERSION (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            logging.info(f"- {self.provider_name.upper()}_RESPONSES_API (optional, defaults to 0)")
            self.setup_custom_azure()
        elif self.provider_name.lower() not in self.VALID_PROVIDERS:
            logging.warning(f"Provider '{self.provider_name}' not in standard list. Creating custom OpenAI-compatible provider.")
            logging.info("Expected environment variables for custom provider:")
            logging.info(f"- {self.provider_name.upper()}_API_KEY (required)")
            logging.info(f"- {self.provider_name.upper()}_BASE_URL (required)")
            logging.info(f"- {self.provider_name.upper()}_PROXY (optional)")
            logging.info(f"- {self.provider_name.upper()}_RESPONSES_API (optional, defaults to 0)")
            self.setup_custom()

    def _get_use_responses_api(self, provider_prefix, default='0'):
        use_responses_api = os.getenv(f'{provider_prefix}_RESPONSES_API', default) == '1'
        logging.info(
            f"Provider '{self.provider_name}': using Responses API {'yes' if use_responses_api else 'no'} for model: {self.model_name}"
        )
        return use_responses_api

    def _parse_effort_suffix(self, profile_name):
        valid_efforts = self.effort_suffix_profiles[profile_name]
        model = self.model_name
        effort = None
        suffixes = [f"-{level}" for level in valid_efforts]

        if any(model.endswith(suffix) for suffix in suffixes):
            base_model, suffix = model.rsplit("-", 1)
            if suffix in valid_efforts:
                effort = suffix
                model = base_model
                logging.info(
                    f"Provider '{self.provider_name}': reasoning effort '{effort}' via model ID suffix; "
                    f"routing model ID: {model}"
                )

        return model, effort

    def _parse_openrouter_thinking_suffix(self):
        model = self.model_name
        reasoning_enabled = None

        if model.endswith("-no-thinking"):
            model = model[: -len("-no-thinking")]
            reasoning_enabled = False
        elif model.endswith("-thinking"):
            model = model[: -len("-thinking")]
            reasoning_enabled = True

        if reasoning_enabled is not None:
            state = "enabled" if reasoning_enabled else "disabled"
            logging.info(
                f"Provider '{self.provider_name}': reasoning {state} via model ID suffix; "
                f"routing model ID: {model}"
            )

        return model, reasoning_enabled

    def setup_openrouter(self):
        from langchain_openai import ChatOpenAI

        api_key = os.getenv('OPENROUTER_API_KEY')
        base_url = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
        preferred_providers = os.getenv('OPENROUTER_PREFERRED_PROVIDERS')

        if api_key is None:
            raise ValueError("OPENROUTER_API_KEY environment variable not set.")

        model, reasoning_enabled = self._parse_openrouter_thinking_suffix()

        kwargs = {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        extra_body = {}
        if preferred_providers:
            preferred_providers = preferred_providers.split(',')
            extra_body["provider"] = {
                "order": preferred_providers,
                "allow_fallbacks": True
            }
        if reasoning_enabled is not None:
            extra_body["reasoning"] = {"enabled": reasoning_enabled}

        if extra_body:
            kwargs["extra_body"] = extra_body

        self.llm = ChatOpenAI(**kwargs)

    def setup_sambanova(self):
        from langchain_sambanova import ChatSambaNovaCloud

        api_key = os.getenv('SAMBANOVA_API_KEY')
        if api_key is None:
            raise ValueError("SAMBANOVA_API_KEY environment variable not set.")

        self.llm = ChatSambaNovaCloud(
            model = self.model_name,
            sambanova_api_key = api_key,
            temperature = self.temperature,
            max_tokens = self.max_tokens)

    def setup_google_ai_studio(self):
        from langchain_google_genai import ChatGoogleGenerativeAI

        google_ai_studio_api_key = os.getenv('GOOGLE_AI_STUDIO_API_KEY')
        if google_ai_studio_api_key is None:
            raise ValueError("GOOGLE_AI_STUDIO_API_KEY environment variable not set.")

        self.llm = ChatGoogleGenerativeAI(
            model = self.model_name,
            api_key = google_ai_studio_api_key,
            temperature = self.temperature,
            max_tokens = self.max_tokens)

    def setup_ollama(self):
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": self.model_name,
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
        }

        if base_url := os.getenv('OLLAMA_API_BASE_URL'):
            kwargs["base_url"] = base_url

        self.llm = ChatOllama(**kwargs)

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
            "max_tokens": self.max_tokens,
        }

        if base_url is not None:
            kwargs["base_url"] = base_url

        self.llm = ChatNVIDIA(**kwargs)

    def setup_anthropic(self):
        from langchain_anthropic import ChatAnthropic

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if api_key is None:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

        self.llm = ChatAnthropic(
            model_name = self.model_name,
            api_key = api_key,
            temperature = self.temperature,
            max_tokens = self.max_tokens,
        )

    def setup_groq(self):
        from langchain_groq import ChatGroq

        api_key = os.getenv('GROQ_API_KEY')
        if api_key is None:
            raise ValueError("GROQ_API_KEY environment variable not set.")

        self.llm = ChatGroq(
            model_name = self.model_name,
            groq_api_key = api_key,
            temperature = self.temperature,
            max_tokens = self.max_tokens,
            streaming = True,
        )

    def setup_google(self):
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Legacy "-enablethinking" suffix from older Google configs. Thinking
        # is no longer forced on through this suffix (Gemini reasoning is now
        # driven by the effort suffixes below); strip it so the literal string
        # is not sent to Vertex AI as a nonexistent model ID.
        if self.model_name.endswith("-enablethinking"):
            self.model_name = self.model_name[: -len("-enablethinking")]
            logging.warning(
                f"Provider '{self.provider_name}': the '-enablethinking' model suffix is deprecated and was "
                f"ignored; using model '{self.model_name}'. Use a reasoning effort suffix instead."
            )

        google_anthropic_deployment = os.getenv("GOOGLE_ANTHROPIC_DEPLOYMENT", "0") == "1"

        if os.getenv('GOOGLE_APPLICATION_CREDENTIALS') is None:
            logging.warning(
                "GOOGLE_APPLICATION_CREDENTIALS environment variable not set. "
                "Attempting to use Application Default Credentials (ADC)."
            )

        google_region = os.getenv("GOOGLE_REGION")

        if google_anthropic_deployment:
            from langchain_google_vertexai.model_garden import ChatAnthropicVertex

            model, effort = self._parse_effort_suffix("google_anthropic")

            params = {
                "model_name": model,
                "max_output_tokens": self.max_tokens,
            }
            if google_region:
                params["location"] = google_region
            if effort:
                params["model_kwargs"] = {
                    "thinking": {"type": "adaptive"},
                    "output_config": {"effort": effort},
                }

            self.llm = ChatAnthropicVertex(**params)
            return

        model, effort = self._parse_effort_suffix("google_gemini")

        if effort and not (model.startswith("gemini-3") or "gemini-3." in model):
            logging.warning(
                f"Provider '{self.provider_name}': model '{model}' does not support reasoning effort suffixes. "
                f"Ignoring '-{effort}' and using model defaults."
            )
            effort = None

        params = {
            "model": model,
            "vertexai": True,
            "temperature": self.temperature,
            "max_output_tokens": self.max_tokens,
        }
        if google_region:
            params["location"] = google_region
        if effort:
            params["thinking_level"] = effort

        self.llm = ChatGoogleGenerativeAI(**params)

    def setup_openai(self):
        from langchain_openai import ChatOpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL')
        proxy = os.getenv('OPENAI_PROXY_URL')
        organization_id = os.getenv('OPENAI_ORG_ID')
        custom_headers = get_custom_headers_from_env("OPENAI")

        # If no API key is provided, assume auth is handled by custom headers.
        # ChatOpenAI requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError("OPENAI_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
        }

        model, effort = self._parse_effort_suffix("openai")

        if effort:
            kwargs["max_completion_tokens"] = self.max_tokens
            kwargs["reasoning_effort"] = effort
            kwargs["model"] = model
        else:
            kwargs["max_tokens"] = self.max_tokens
            kwargs["temperature"] = self.temperature

        if base_url is not None:
            kwargs["base_url"] = base_url

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

        use_responses_api = self._get_use_responses_api('OPENAI', '1')
        kwargs["use_responses_api"] = use_responses_api

        self.llm = ChatOpenAI(**kwargs)

    def setup_azure(self):
        from langchain_openai import AzureChatOpenAI

        api_version = os.getenv("AZURE_API_VERSION")
        api_endpoint = os.getenv("AZURE_ENDPOINT")
        api_key = os.getenv("AZURE_API_KEY")
        api_proxy = os.getenv("AZURE_PROXY")
        custom_headers = get_custom_headers_from_env("AZURE")

        if api_version is None or api_endpoint is None:
            raise ValueError("Azure environment variables not set.")

        # If no API key is provided, assume auth is handled by custom headers.
        # AzureChatOpenAI requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError("AZURE_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "openai_api_key": api_key,
        }

        model, effort = self._parse_effort_suffix("openai")

        if effort:
            kwargs["azure_deployment"] = model
            kwargs["max_completion_tokens"] = self.max_tokens
            kwargs["reasoning_effort"] = effort
        else:
            kwargs["azure_deployment"] = self.model_name
            kwargs["temperature"] = self.temperature

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

        kwargs["use_responses_api"] = self._get_use_responses_api('AZURE', '0')

        self.llm = AzureChatOpenAI(**kwargs)

    def setup_custom_azure(self):
        from langchain_openai import AzureChatOpenAI

        provider_upper = self.provider_name.upper()
        api_version = os.getenv(f"{provider_upper}_API_VERSION")
        api_endpoint = os.getenv(f"{provider_upper}_ENDPOINT")
        api_key = os.getenv(f"{provider_upper}_API_KEY")
        api_proxy = os.getenv(f"{provider_upper}_PROXY")
        custom_headers = get_custom_headers_from_env(self.provider_name)

        if api_version is None or api_endpoint is None:
            raise ValueError(f"Custom Azure provider '{self.provider_name}' environment variables not set.")

        # If no API key is provided, assume auth is handled by custom headers.
        # AzureChatOpenAI requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError(f"{provider_upper}_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        kwargs = {
            "azure_endpoint": api_endpoint,
            "openai_api_version": api_version,
            "openai_api_key": api_key,
        }

        model, effort = self._parse_effort_suffix("openai")

        if effort:
            kwargs["azure_deployment"] = model
            kwargs["max_completion_tokens"] = self.max_tokens
            kwargs["reasoning_effort"] = effort
        else:
            kwargs["azure_deployment"] = self.model_name
            kwargs["temperature"] = self.temperature

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

        kwargs["use_responses_api"] = self._get_use_responses_api(provider_upper, '0')

        self.llm = AzureChatOpenAI(**kwargs)

    def setup_bedrock(self):
        from langchain_aws import ChatBedrock

        AWS_REGION = os.getenv("AWS_REGION")
        AWS_PROFILE_NAME = os.getenv("AWS_PROFILE_NAME")
        AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN")
        AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
        AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
        AWS_CLAUDE_THINKING_TOKENS = os.getenv("AWS_CLAUDE_THINKING_TOKENS", "2000")
        AWS_CUSTOM_URL = os.getenv("AWS_CUSTOM_URL")

        model = self.model_name
        provider = None
        enable_thinking = False

        if model.endswith("-enablethinking"):
            model = model.replace("-enablethinking", "")
            enable_thinking = True
            logging.info(f"Attempting to activate thinking mode on model ID: {model} on provider: {self.provider_name}")

        if "arn:" in model:
            # Check for "provider:arn:..." format
            parts = model.split(":", 1)

            if len(parts) == 2 and parts[1].startswith("arn:"):
                provider = parts[0]
                model = parts[1]

            if not provider:
                raise ValueError(
                    f"Model ID '{self.model_name}' is an ARN, but no provider was specified.\n"
                    "When using an ARN, the provider is mandatory.\n\n"
                    "Please specify the provider in the model ID string: 'anthropic:arn:aws:bedrock:...'"
                )

        refreshable_session_instance = RefreshableBotoSession(
            region_name = AWS_REGION,
            profile_name = AWS_PROFILE_NAME,
            sts_arn = AWS_ROLE_ARN,
            access_key = AWS_ACCESS_KEY_ID,
            secret_key = AWS_SECRET_ACCESS_KEY
        )

        session = refreshable_session_instance.refreshable_session()

        client_kwargs = {'service_name': 'bedrock-runtime'}
        if AWS_CUSTOM_URL:
            client_kwargs['endpoint_url'] = AWS_CUSTOM_URL

        client = session.client(**client_kwargs)

        # Prepare ChatBedrock initialization parameters
        bedrock_kwargs = {
            "client": client,
            "model": model,
            "model_kwargs": {
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            },
        }

        if provider:
            bedrock_kwargs["provider"] = provider

        if enable_thinking:
            bedrock_kwargs["model_kwargs"] = {
                "thinking": {"type": "enabled", "budget_tokens": int(AWS_CLAUDE_THINKING_TOKENS)},
                "max_tokens": self.max_tokens,
            }

        self.llm = ChatBedrock(**bedrock_kwargs)

    def setup_mistral(self):
        from langchain_mistralai import ChatMistralAI

        api_key = os.getenv('MISTRAL_API_KEY')
        if api_key is None:
            raise ValueError("MISTRAL_API_KEY environment variable not set.")

        self.llm = ChatMistralAI(
            model = self.model_name,
            mistral_api_key = api_key,
            temperature = self.temperature,
            max_tokens = self.max_tokens,
            timeout=480
        )

    def setup_custom(self):
        from langchain_openai import ChatOpenAI

        provider_upper = self.provider_name.upper()
        api_key = os.getenv(f'{provider_upper}_API_KEY')
        base_url = os.getenv(f'{provider_upper}_BASE_URL')
        proxy = os.getenv(f'{provider_upper}_PROXY')
        custom_headers = get_custom_headers_from_env(self.provider_name)

        # If no API key is provided, assume auth is handled by custom headers.
        # ChatOpenAI requires a non-empty api_key, so provide a dummy one.
        if api_key is None:
            if not custom_headers:
                raise ValueError(f"{provider_upper}_API_KEY environment variable not set and no custom auth headers found.")
            api_key = "not_used"

        if base_url is None:
            raise ValueError(f"{provider_upper}_BASE_URL environment variable not set.")

        kwargs = {
            "model": self.model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
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

        kwargs["use_responses_api"] = self._get_use_responses_api(provider_upper, '0')

        self.llm = ChatOpenAI(**kwargs)

    @staticmethod
    def get_providers():
        providers = list(UniformLLM.VALID_PROVIDERS)

        # Dynamically detect custom providers configured via environment variables.
        # There can be 2 types of custom providers:
        # 1. OpenAI-compatible (detected via _BASE_URL)
        # 2. Azure-compatible (detected via _ENDPOINT)
        for key in os.environ.keys():
            if key.endswith("_BASE_URL"):
                provider = key.replace("_BASE_URL", "").lower()
                # Exclude ollama_api as it is the env suffix for the standard 'ollama' provider
                if provider and provider not in providers and provider != "ollama_api":
                    providers.append(provider)
            elif key.endswith("_ENDPOINT"):
                provider = key.replace("_ENDPOINT", "").lower()
                if provider.startswith("azure_") and provider not in providers:
                    providers.append(provider)

        return providers

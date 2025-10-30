"""
 Copyright (c) 2025. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import os
import logging

from utils.uniformLLM import UniformLLM
from utils.uniformEmbeddings import UniformEmbeddings
from utils.uniformVectorStore import UniformVectorStore

# --- State Dictionaries ---
# We will store the initialized objects here to reuse them across the app.
_llm_cache = {}
_embedding_model_cache = {}
_vector_store_cache = {}


def get_embedding_model(provider_name, model_name):
    """
    Looks up an embedding model from the cache. If not found, creates and caches it.
    """
    if not provider_name or not model_name:
        raise ValueError("Embeddings provider and model name must be specified.")

    cache_key = (provider_name, model_name)
    if cache_key not in _embedding_model_cache:
        logging.info(f"Initializing new embedding model: {provider_name}/{model_name}")
        _embedding_model_cache[cache_key] = UniformEmbeddings(
            provider_name=provider_name,
            model_name=model_name
        )
    return _embedding_model_cache[cache_key]

def get_llm(provider_name, model_name, temperature = 0.0, max_tokens = 4096):
    """
    Looks up an LLM from the cache. If not found, creates and caches it.
    """
    if not provider_name or not model_name:
        raise ValueError("LLM provider and model name must be specified.")

    cache_key = (provider_name, model_name, temperature, max_tokens)
    if cache_key not in _llm_cache:
        logging.info(f"Initializing new LLM: {provider_name}/{model_name} (temp={temperature}, max_tokens={max_tokens})")
        _llm_cache[cache_key] = UniformLLM(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens
        )
    return _llm_cache[cache_key]

def get_vector_store(
    provider,
    embeddings_provider,
    embeddings_model,
    rate_limit_rpm = 0,
    index_name = "ai_sdk_vector_store"
):
    """
    Looks up a Vector Store from the cache using a composite key that includes
    the provider, index name, and rate limit. This allows caching different
    configurations of the same vector store.
    """
    if not provider:
        raise ValueError("Vector Store provider must be specified.")

    cache_key = (
        provider,
        embeddings_provider,
        embeddings_model,
        index_name,
        rate_limit_rpm
    )

    if cache_key not in _vector_store_cache:
        logging.info(
            f"Initializing new vector store: {provider} with index '{index_name}', "
            f"embeddings: {embeddings_provider}/{embeddings_model}, "
            f"and rate limit {rate_limit_rpm} RPM"
        )

        embedding_model_instance = get_embedding_model(embeddings_provider, embeddings_model)

        _vector_store_cache[cache_key] = UniformVectorStore(
            provider=provider,
            embeddings=embedding_model_instance.model,
            index_name=index_name,
            rate_limit_rpm=rate_limit_rpm
        )

    return _vector_store_cache[cache_key]

def initialize_default_resources():
    """
    Initializes the default resources based on environment variables.
    This function is called once at application startup.
    """
    logging.info("Pre-initializing default resources...")

    # Pre-initialize default LLM
    llm_provider = os.getenv("LLM_PROVIDER")
    llm_model = os.getenv("LLM_MODEL")
    llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    if llm_provider and llm_model:
        get_llm(llm_provider, llm_model, llm_temperature, llm_max_tokens)

    # Pre-initialize thinking LLM
    thinking_llm_provider = os.getenv("THINKING_LLM_PROVIDER")
    thinking_llm_model = os.getenv("THINKING_LLM_MODEL")
    thinking_llm_temperature = float(os.getenv("THINKING_LLM_TEMPERATURE", "0.0"))
    thinking_llm_max_tokens = int(os.getenv("THINKING_LLM_MAX_TOKENS", "10240"))
    if thinking_llm_provider and thinking_llm_model:
        get_llm(thinking_llm_provider, thinking_llm_model, thinking_llm_temperature, thinking_llm_max_tokens)

    # Pre-initialize default vector store and its embedding model
    vector_store_provider = os.getenv("VECTOR_STORE")
    embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER")
    embeddings_model = os.getenv("EMBEDDINGS_MODEL")
    if vector_store_provider and embeddings_provider and embeddings_model:
        get_vector_store(vector_store_provider, embeddings_provider, embeddings_model)

        get_vector_store(
            provider=vector_store_provider,
            embeddings_provider=embeddings_provider,
            embeddings_model=embeddings_model,
            index_name="ai_sdk_sample_data"
        )

    logging.info("Default resources initialized and cached.")
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

def get_llm(provider_name, model_name, temperature = 0.0):
    """
    Looks up an LLM from the cache. If not found, creates and caches it.
    """
    if not provider_name or not model_name:
        raise ValueError("LLM provider and model name must be specified.")

    cache_key = (provider_name, model_name)
    if cache_key not in _llm_cache:
        logging.info(f"Initializing new LLM: {provider_name}/{model_name}")
        _llm_cache[cache_key] = UniformLLM(
            provider_name=provider_name,
            model_name=model_name,
            temperature=temperature
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

    cache_key = (provider, index_name, rate_limit_rpm)
    
    if cache_key not in _vector_store_cache:
        logging.info(f"Initializing new vector store: {provider} with index '{index_name}' and rate limit {rate_limit_rpm} RPM")
        
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
    
    # Pre-initialize default chat LLM
    chat_provider = os.getenv("CHAT_PROVIDER")
    chat_model = os.getenv("CHAT_MODEL")
    if chat_provider and chat_model:
        get_llm(chat_provider, chat_model)

    # Pre-initialize default SQL generation LLM
    sql_gen_provider = os.getenv("SQL_GENERATION_PROVIDER")
    sql_gen_model = os.getenv("SQL_GENERATION_MODEL")
    if sql_gen_provider and sql_gen_model:
        get_llm(sql_gen_provider, sql_gen_model)

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

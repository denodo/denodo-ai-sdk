import traceback

from utils.utils import timed

@timed
def knowledge_query(search_query, vector_store, k=5, document_size_limit_chars=10000):
    try:
        result = vector_store.search(query=search_query, k=k, scores=False)
        information = [f"Result {i+1}: {document.page_content[:document_size_limit_chars]}\n" for i, document in enumerate(result)]
        information = '\n'.join(information)
        return {
            "answer": information
        }
    except Exception as e:
        return {
            "error": f"Knowledge query failed: {e}",
            "traceback": traceback.format_exc()
        }
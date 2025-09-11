import requests
import json
import time

# API_HOST for demo purposes
API_HOST = 'http://localhost:8008'
API_VDB = 'samples_bank'
DATA_CATALOG_USER = 'admin'
DATA_CATALOG_PWD = 'admin'

def get_metadata(database_name, insert = True, incremental = False):
    """Get metadata from VDP and optionally insert it into the vector store."""
    request_params = {
        'vdp_database_names': database_name,
        'insert': insert,
        'incremental': incremental
    }
    response = requests.get(f'{API_HOST}/getMetadata', params=request_params, auth = (DATA_CATALOG_USER, DATA_CATALOG_PWD))

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

def stream_answer_question(question):
    """Stream the answer to a question from the LLM."""
    request_params = {'question': question}
    response = requests.get(f'{API_HOST}/streamAnswerQuestion', params=request_params, stream=True, auth = (DATA_CATALOG_USER, DATA_CATALOG_PWD))

    for chunk in response.iter_lines(decode_unicode = True):
        print(chunk, end='', flush=True)

def answer_question(question, mode="default"):
    """Get the answer to a question from the LLM."""
    request_params = {'question': question, "mode": mode}
    response = requests.get(f'{API_HOST}/answerQuestion', params=request_params, auth = (DATA_CATALOG_USER, DATA_CATALOG_PWD))
    if response.status_code == 200:
        try:
            response_data = response.json()
            print(f"Mode: {mode}")
            print()

            print("Answer:")
            print(response_data.get('answer', 'No answer found.'))
            print()

            print("SQL Query:")
            print(response_data.get('sql_query', 'No SQL query found.'))
            print()

            print("Tokens:")
            tokens = response_data.get('tokens')
            if tokens is not None:
                try:
                    print(json.dumps(tokens, indent=2, ensure_ascii=False))
                except Exception:
                    print(str(tokens))
            else:
                print("No tokens found.")
            print()

            print("Execution result:")
            exec_result = response_data.get('execution_result')
            if exec_result is not None:
                try:
                    print(json.dumps(exec_result, indent=2, ensure_ascii=False))
                except Exception:
                    print(str(exec_result))
            else:
                print("No execution result returned.")
            print()

            print("Tables used:")
            tables_used = response_data.get('tables_used', [])
            if isinstance(tables_used, list) and tables_used:
                for t in tables_used:
                    print(f"- {t}")
            else:
                print("No tables used data returned.")
            print()

            related = response_data.get('related_questions', [])
            if isinstance(related, list) and related:
                print("Related questions:")
                for r in related:
                    print(f"- {r}")
                print()

            print("Timings:")
            print(f"- SQL execution time: {response_data.get('sql_execution_time', 'N/A')}")
            print(f"- Vector store search time: {response_data.get('vector_store_search_time', 'N/A')}")
            print(f"- LLM time: {response_data.get('llm_time', 'N/A')}")
            print(f"- Total execution time: {response_data.get('total_execution_time', 'N/A')}")
        except json.JSONDecodeError:
            print("Error decoding JSON response")
    else:
        response.raise_for_status()

if __name__ == "__main__":
    # =============================
    # Metadata
    # -----------------------------
    # Get metadata and insert it into the vector store (incremental defaults to False)
    start_time = time.time()
    get_metadata(API_VDB)
    print("Metadata retrieved and inserted into the vector store.")
    print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

    question = "How many approved loans do we have?"

    # =============================
    # Streaming answer
    # -----------------------------
    print(f"Question: {question}")
    start_time = time.time()
    stream_answer_question(question)
    print()
    print(f"Streaming finished in: {time.time() - start_time:.2f}s\n")

    # =============================
    # Direct answer
    # -----------------------------
    print(f"Question: {question}")
    start_time = time.time()
    answer_question(question)
    print(f"Time taken: {time.time() - start_time:.2f} seconds\n")

    modes = ["data", "metadata"]

    for mode in modes:
        # =============================
        # Direct answer (mode)
        # -----------------------------
        print(f"Question: {question}")
        start_time = time.time()
        answer_question(question, mode)
        print(f"Time taken: {time.time() - start_time:.2f} seconds\n")
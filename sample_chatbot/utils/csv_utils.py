"""
Functions for CSV file handling, parsing, and document preparation for vector stores.
"""

import os
import csv
import json
import logging
import random

from langchain_core.documents.base import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from utils import langfuse
from utils.utils import custom_tag_parser, calculate_tokens
from sample_chatbot.engine.prompts import GENERATE_CSV_DESCRIPTION

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_CHATBOT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("AI_SDK_DATA_DIR", ".")

if DATA_DIR != ".":
    UPLOADS_PATH = os.path.abspath(os.path.join(DATA_DIR, "uploads"))
else:
    UPLOADS_PATH = os.path.join(REPO_ROOT, "uploads")

ALLOWED_CSV_ROOTS = (
    UPLOADS_PATH,
    os.path.join(SAMPLE_CHATBOT_ROOT, "sample_data", "unstructured"),
)

def _is_allowed_csv_path(csv_file_path):
    resolved_path = os.path.realpath(csv_file_path)

    for allowed_root in ALLOWED_CSV_ROOTS:
        resolved_root = os.path.realpath(allowed_root)
        try:
            if os.path.commonpath([resolved_path, resolved_root]) == resolved_root:
                return True
        except ValueError:
            continue

    return False

def detect_csv_delimiter(csv_file_path, sample_size=8192):
    """
    Detect the delimiter of a CSV file using Python's csv.Sniffer.

    Args:
        csv_file_path: Path to the CSV file
        sample_size: Number of bytes to sample for detection

    Returns:
        Detected delimiter or ';' as fallback
    """
    try:
        with open(csv_file_path, encoding='utf-8') as f:
            sample = f.read(sample_size)
        sniffer = csv.Sniffer()
        # Restrict to plausible delimiters: on files whose first cells are long
        # prose/code blobs the sniffer otherwise detects characters like ' '.
        dialect = sniffer.sniff(sample, delimiters=',;\t|')
        logging.debug(f"[csv_utils] Detected delimiter '{dialect.delimiter}' for {csv_file_path}")
        return dialect.delimiter
    except Exception as e:
        logging.warning(f"[csv_utils] Could not detect CSV delimiter for {csv_file_path}: {e}. Falling back to ';'")
        return ';'

def get_csv_preview(csv_file_path, delimiter=';', num_rows=5, random_sample=False):
    """
    Get a preview of the first N rows of a CSV file, or a random sample.

    Args:
        csv_file_path: Path to the CSV file
        delimiter: CSV delimiter character
        num_rows: Number of rows to preview
        random_sample: If True, read first num_rows*100 rows and randomly select num_rows from them

    Returns:
        Dict with 'columns', 'rows', and optional 'error' keys
    """
    try:
        rows = []
        columns = []
        with open(csv_file_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            columns = reader.fieldnames or []

            if random_sample:
                # Read first num_rows * 100 rows
                max_rows = num_rows * 100
                available_rows = []
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    available_rows.append(row)

                # Randomly select num_rows from available rows
                if len(available_rows) > num_rows:
                    rows = random.sample(available_rows, num_rows)
                else:
                    rows = available_rows
            else:
                # Original behavior: get first num_rows
                for i, row in enumerate(reader):
                    if i >= num_rows:
                        break
                    rows.append(row)

        return {"columns": columns, "rows": rows}
    except Exception as e:
        logging.error(f"Error reading CSV preview: {e}")
        return {"columns": [], "rows": [], "error": str(e)}

def generate_csv_description(llm, csv_file_path, delimiter=';', num_rows=5, session_id=None,
                             vectorized_columns=None):
    """
    Generate a description of the CSV file using the LLM based on the first N rows.

    Args:
        llm: UniformLLM instance to use for generation
        csv_file_path: Path to the CSV file
        delimiter: CSV delimiter character
        num_rows: Number of rows to use for context
        session_id: Optional Langfuse session ID for tracing
        vectorized_columns: Optional list of columns to include in the preview shown
            to the LLM. When provided, the description is generated from those columns
            only, matching what will actually be embedded.

    Returns:
        Generated description string
    """
    logging.debug(f"[csv_utils] Generating description for CSV: {csv_file_path}")
    try:
        preview = get_csv_preview(csv_file_path, delimiter, num_rows, random_sample=True)
        if not preview["rows"]:
            logging.warning(f"[csv_utils] Empty CSV or could not read: {csv_file_path}")
            return "Empty CSV file or could not read contents."

        all_columns = preview["columns"]
        rows = preview["rows"]

        if vectorized_columns:
            columns = [c for c in vectorized_columns if c in all_columns] or all_columns
        else:
            columns = all_columns

        preview_text = f"Columns: {', '.join(columns)}\n\nSample rows:\n"
        for i, row in enumerate(rows, 1):
            row_text = " | ".join([f"{k}: {row.get(k, '')}" for k in columns])
            preview_text += f"Row {i}: {row_text}\n"

        # Build the chain using raw LLM from UniformLLM wrapper
        prompt = PromptTemplate.from_template(GENERATE_CSV_DESCRIPTION)
        chain = prompt | llm.llm | StrOutputParser()

        # Build Langfuse config for tracing
        chain_config = langfuse.build_config(
            model_id=f"{llm.provider_name}.{llm.model_name}",
            session_id=session_id,
            run_name="generate_csv_description"
        )

        # Invoke the chain
        logging.debug(f"[csv_utils] Invoking LLM ({llm.provider_name}.{llm.model_name}) for description")
        response = chain.invoke({"csv_preview": preview_text}, config=chain_config)

        # Parse the description from the response
        descriptions = custom_tag_parser(response, 'description', default='')
        if descriptions and descriptions[0]:
            logging.debug(f"[csv_utils] Successfully generated description ({len(descriptions[0])} chars)")
            return descriptions[0].strip()

        # Fallback: return raw response if no tags found
        logging.debug("[csv_utils] No description tags found, using raw response")
        return response.strip()

    except Exception as e:
        logging.error(f"[csv_utils] Error generating CSV description for {csv_file_path}: {e}")
        return f"CSV file with columns: {', '.join(preview.get('columns', []))}"

def validate_csv_path(csv_file_path, allow_temp=False):
    """
    Validate that the CSV file exists and is readable.

    Args:
        csv_file_path: Path to the CSV file
        allow_temp: Whether to allow server-created temporary CSV files

    Returns:
        Tuple of (valid: bool, error_message: str or None)
    """
    if not csv_file_path:
        return False, "No file path provided"
    if not os.path.exists(csv_file_path):
        return False, f"File not found: {csv_file_path}"
    if not os.path.isfile(csv_file_path):
        return False, f"Path is not a file: {csv_file_path}"
    if not csv_file_path.lower().endswith('.csv'):
        return False, "File must have .csv extension"
    if not allow_temp and not _is_allowed_csv_path(csv_file_path):
        return False, "CSV path must be inside uploads/ or sample_chatbot/sample_data/unstructured/"
    try:
        with open(csv_file_path, encoding='utf-8') as f:
            f.read(1)
        return True, None
    except Exception as e:
        return False, f"Cannot read file: {str(e)}"

def _build_page_content(row, vectorized_columns):
    """`colA: val, colB: val` over the user-selected columns."""
    return ", ".join(f"{c}: {row.get(c, '')}" for c in vectorized_columns)

def csv_to_documents(csv_file, delimiter=";", quotechar='"', source_name=None,
                     vectorized_columns=None, embeddings=None):
    """
    Convert a CSV file to LangChain documents and pre-embed each row.

    Each document gets a unique ID `{source_name}_{row_index}` so multiple
    CSV sources can coexist in one shared vector store, and every original
    column value is preserved in metadata so the CSV can be reconstructed for
    download (including the embedding column).

    Args:
        csv_file: Path to the CSV file
        delimiter: CSV delimiter character
        quotechar: CSV quote character
        source_name: Name used as database_name in metadata (filter key)
        vectorized_columns: list of columns whose values build page_content.
            If None or empty, all columns are used.
        embeddings: optional embeddings model. When provided, each row's
            embedding is computed up-front and stored in metadata as a string
            so it can later be exported with the CSV.

    Returns:
        List of Document, or False on failure.
    """

    rows = []
    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter, quotechar=quotechar)
        columns = list(reader.fieldnames or [])
        for row in reader:
            rows.append({k: ("" if v is None else v) for k, v in row.items()})

    if not rows:
        logging.error(f"[csv_utils] No data was found in the CSV file: {csv_file}")
        return False

    if not source_name:
        filename = os.path.basename(csv_file)
        source_name = os.path.splitext(filename)[0]

    if not vectorized_columns:
        vectorized_columns = columns
    else:
        # Drop columns that aren't actually in the CSV — they'd just be empty.
        vectorized_columns = [c for c in vectorized_columns if c in columns]
        if not vectorized_columns:
            vectorized_columns = columns

    documents = []
    for i, row in enumerate(rows):
        doc_id = f"{source_name}_{i}"
        page_content = _build_page_content(row, vectorized_columns)
        documents.append(Document(
            id=doc_id,
            page_content=page_content,
            metadata={
                "view_name": str(i),
                "view_id": doc_id,
                "document_id": doc_id,
                "database_name": source_name,
                "row_id": i,
                "row": json.dumps(row, ensure_ascii=False),
                "vectorized_columns": json.dumps(vectorized_columns),
            },
        ))

    page_content_tokens = [calculate_tokens(d.page_content) for d in documents]
    logging.info(f"[csv_utils] Min tokens: {min(page_content_tokens)}, Max tokens: {max(page_content_tokens)}, Average tokens: {round(sum(page_content_tokens) / len(page_content_tokens), 0)} for {len(documents)} documents in {csv_file}")
    if embeddings is not None:
        # Pre-embed so we can later export the vector alongside the CSV. The
        # subsequent add_documents will hit the embeddings cache, so this is
        # not a double cost.
        vectors = embeddings.embed_documents([d.page_content for d in documents])
        for d, v in zip(documents, vectors):
            d.metadata["vector"] = str(v)

    logging.info(f"[csv_utils] Converted CSV to {len(documents)} documents (source: {source_name})")
    return documents

def fetch_collection_documents(vector_store, source_name, num_rows):
    """
    Pull every document of a collection back out of the vector store.

    Uses exhaustive view_id batching so it works past `search_batched`'s
    similarity top-k cap.
    """
    BATCH = 25000
    out = []
    for start in range(0, num_rows, BATCH):
        ids = [f"{source_name}_{i}" for i in range(start, min(start + BATCH, num_rows))]
        out.extend(vector_store.search_by_vector(
            vector_store.search_vector,
            k=len(ids),
            view_ids=ids,
        ))
    return out

def collection_to_csv_bytes(vector_store, source_name, num_rows):
    """
    Reconstruct the original CSV from stored row metadata and append an
    `embedding` column from the per-row stored vector.

    Returns CSV bytes (UTF-8) ready to send over HTTP.
    """
    import io

    docs = fetch_collection_documents(vector_store, source_name, num_rows)

    by_row = {}
    columns_order = None
    for d in docs:
        row_json = d.metadata.get("row")
        if not row_json:
            continue
        try:
            row = json.loads(row_json)
        except ValueError:
            continue
        if columns_order is None:
            columns_order = list(row.keys())
        row_id = d.metadata.get("row_id")
        if row_id is None:
            try:
                row_id = int(d.metadata.get("view_name"))
            except (TypeError, ValueError):
                continue
        row["embedding"] = d.metadata.get("vector", "")
        by_row[int(row_id)] = row

    if not by_row:
        return b""

    if columns_order is None:
        columns_order = []
    fieldnames = columns_order + ["embedding"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row_id in sorted(by_row.keys()):
        writer.writerow(by_row[row_id])
    return buf.getvalue().encode("utf-8")

def get_safe_source_name(source_name):
    """
    Convert a source name to a safe string for use in identifiers.

    Args:
        source_name: Original source name

    Returns:
        Safe alphanumeric lowercase string
    """
    return ''.join(filter(str.isalnum, source_name)).lower()

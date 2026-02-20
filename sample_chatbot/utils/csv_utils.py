"""
Functions for CSV file handling, parsing, and document preparation for vector stores.
"""

import os
import csv
import logging
import random

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from utils import langfuse
from utils.utils import custom_tag_parser
from langchain_community.document_loaders.csv_loader import CSVLoader
from sample_chatbot.engine.prompts import GENERATE_CSV_DESCRIPTION

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
        dialect = sniffer.sniff(sample)
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

def generate_csv_description(llm, csv_file_path, delimiter=';', num_rows=5, session_id=None):
    """
    Generate a description of the CSV file using the LLM based on the first N rows.

    Args:
        llm: UniformLLM instance to use for generation
        csv_file_path: Path to the CSV file
        delimiter: CSV delimiter character
        num_rows: Number of rows to use for context
        session_id: Optional Langfuse session ID for tracing

    Returns:
        Generated description string
    """
    logging.debug(f"[csv_utils] Generating description for CSV: {csv_file_path}")
    try:
        preview = get_csv_preview(csv_file_path, delimiter, num_rows, random_sample=True)
        if not preview["rows"]:
            logging.warning(f"[csv_utils] Empty CSV or could not read: {csv_file_path}")
            return "Empty CSV file or could not read contents."

        # Build a text representation of the CSV preview
        columns = preview["columns"]
        rows = preview["rows"]

        preview_text = f"Columns: {', '.join(columns)}\n\nSample rows:\n"
        for i, row in enumerate(rows, 1):
            row_text = " | ".join([f"{k}: {v}" for k, v in row.items()])
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

def validate_csv_path(csv_file_path):
    """
    Validate that the CSV file exists and is readable.

    Args:
        csv_file_path: Path to the CSV file

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
    try:
        with open(csv_file_path, encoding='utf-8') as f:
            f.read(1)
        return True, None
    except Exception as e:
        return False, f"Cannot read file: {str(e)}"

def csv_to_documents(csv_file, delimiter=";", quotechar='"', source_name=None):
    """
    Convert a CSV file to LangChain documents.

    Each document gets a unique ID based on source_name and row index to allow
    multiple CSV sources to coexist in a single vector store.

    Args:
        csv_file: Path to the CSV file
        delimiter: CSV delimiter character
        quotechar: CSV quote character
        source_name: Name to use as database_name in metadata (used for filtering)

    Returns:
        List of documents or False on failure
    """
    logging.debug(f"[csv_utils] Converting CSV to documents: {csv_file}")
    loader = CSVLoader(
        file_path=csv_file,
        csv_args={
            "delimiter": delimiter,
            "quotechar": quotechar,
        },
        encoding="utf-8"
    )

    documents = loader.load()

    if len(documents) == 0:
        logging.error(f"[csv_utils] No data was found in the CSV file: {csv_file}")
        return False

    # Use source_name if provided, otherwise derive from filename
    if not source_name:
        filename = os.path.basename(csv_file)
        source_name = os.path.splitext(filename)[0]

    # Create unique document IDs: {source_name}_{row_index}
    # This allows multiple CSV sources to coexist in a single vector store
    for i, document in enumerate(documents):
        doc_id = f"{source_name}_{i}"
        document.id = doc_id
        document.metadata['view_name'] = str(i)
        document.metadata['view_id'] = doc_id
        document.metadata['document_id'] = doc_id
        document.metadata['database_name'] = source_name

    logging.info(f"[csv_utils] Converted CSV to {len(documents)} documents (source: {source_name})")
    return documents

def get_safe_source_name(source_name):
    """
    Convert a source name to a safe string for use in identifiers.

    Args:
        source_name: Original source name

    Returns:
        Safe alphanumeric lowercase string
    """
    return ''.join(filter(str.isalnum, source_name)).lower()
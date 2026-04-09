"""
Handles CSV file operations including detection, preview, and description generation.
"""

import os
import tempfile
import logging

from sample_chatbot.utils.csv_utils import (
    detect_csv_delimiter,
    get_csv_preview,
    generate_csv_description,
    validate_csv_path,
)

logger = logging.getLogger(__name__)

class CSVService:
    """Service for CSV file operations."""

    def __init__(self, upload_folder="uploads"):
        """
        Initialize the CSV service.

        Args:
            upload_folder: Folder to store uploaded CSV files
        """
        self.upload_folder = upload_folder

    def save_uploaded_file(self, file):
        """
        Save an uploaded file to the upload folder.

        Args:
            file: Uploaded file object

        Returns:
            Path to saved file
        """
        file_path = os.path.join(self.upload_folder, file.filename)
        file.save(file_path)
        logger.debug(f"[CSVService] Saved uploaded file to: {file_path}")
        return file_path

    def save_temp_file(self, file):
        """
        Save an uploaded file to a temporary location.

        Args:
            file: Uploaded file object

        Returns:
            Tuple of (file_path, is_temp)
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
            file.save(tmp.name)
            return tmp.name, True

    def cleanup_temp_file(self, file_path):
        """Clean up a temporary file."""
        try:
            os.unlink(file_path)
        except Exception:
            pass

    def get_preview(self, file_path, delimiter=None, num_rows=5, allow_temp=False):
        """
        Get a preview of a CSV file.

        Args:
            file_path: Path to CSV file
            delimiter: Delimiter to use (auto-detect if None)
            num_rows: Number of rows to preview
            allow_temp: Whether to allow a server-created temporary file

        Returns:
            dict with success, delimiter, columns, rows, error
        """
        logger.debug(f"[CSVService] Getting preview for: {file_path}")
        valid, error = validate_csv_path(file_path, allow_temp=allow_temp)
        if not valid:
            logger.warning(f"[CSVService] Invalid CSV path: {error}")
            return {"success": False, "error": error}

        if delimiter is None:
            delimiter = detect_csv_delimiter(file_path)
            logger.debug(f"[CSVService] Auto-detected delimiter: '{delimiter}'")

        preview = get_csv_preview(file_path, delimiter, num_rows, random_sample=True)
        logger.debug(f"[CSVService] Preview: {len(preview['columns'])} columns, {len(preview['rows'])} rows")

        return {
            "success": True,
            "delimiter": delimiter,
            "columns": preview["columns"],
            "rows": preview["rows"],
            "error": preview.get("error")
        }

    def generate_description(self, llm, file_path, delimiter=None, allow_temp=False):
        """
        Generate a description for a CSV file using LLM.

        Args:
            llm: UniformLLM instance
            file_path: Path to CSV file
            delimiter: Delimiter to use (auto-detect if None)
            allow_temp: Whether to allow a server-created temporary file

        Returns:
            dict with success, description, delimiter, error
        """
        logger.debug(f"[CSVService] Generating description for: {file_path}")
        valid, error = validate_csv_path(file_path, allow_temp=allow_temp)
        if not valid:
            logger.warning(f"[CSVService] Invalid CSV path for description generation: {error}")
            return {"success": False, "error": error}

        if delimiter is None:
            delimiter = detect_csv_delimiter(file_path)
            logger.debug(f"[CSVService] Auto-detected delimiter: '{delimiter}'")

        logger.info("[CSVService] Invoking LLM for description generation")
        description = generate_csv_description(llm, file_path, delimiter)
        logger.debug(f"[CSVService] Generated description ({len(description)} chars)")

        return {
            "success": True,
            "description": description,
            "delimiter": delimiter
        }

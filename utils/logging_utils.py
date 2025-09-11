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
import glob
import logging
from datetime import datetime
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

transaction_id_var: ContextVar[str] = ContextVar('transaction_id', default='system')

class TransactionIdFilter(logging.Filter):
    """
    This filter injects the transaction ID from the context variable into the log record.
    """
    def filter(self, record):
        record.transaction_id = transaction_id_var.get()
        return True

class RotatingLogFileHandler(RotatingFileHandler):
    """
    It inherits from RotatingFileHandler to use its size detection mechanism,
    but on rollover, it creates a completely new file with a timestamp
    instead of renaming the old one.
    """
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        # We store the original filename template (e.g., 'logs/app.log')
        self._base_filename_template = filename

        # Generate the name for the first log file with a timestamp
        initial_filename = self._generate_new_filename()

        # Call the base class constructor with this initial filename
        super().__init__(initial_filename, mode, maxBytes, backupCount, encoding, delay)

    def _generate_new_filename(self):
        """Generates a new filename with a timestamp."""
        base_dir = os.path.dirname(self._base_filename_template)
        filename = os.path.basename(self._base_filename_template)
        name, ext = os.path.splitext(filename)

        # Create the base directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(base_dir, f"{name}_{timestamp}{ext}")

    def doRollover(self):
        """
        Performs the rollover.
        """
        # 1. Close the current file stream (which is already full)
        if self.stream:
            self.stream.close()
            self.stream = None

        # 2. Manage backups BEFORE creating the new file
        self._manage_backups()

        # 3. Generate a new name for the next log file
        self.baseFilename = self._generate_new_filename()

    def _manage_backups(self):
        """
        Deletes the oldest log files if backupCount is exceeded.
        """
        if self.backupCount > 0:
            base_dir = os.path.dirname(self._base_filename_template)
            filename = os.path.basename(self._base_filename_template)
            name, ext = os.path.splitext(filename)

            search_glob = os.path.join(base_dir, f"{name}_*{ext}")

            # We sort the files by name (the timestamp ensures chronological order)
            log_files = sorted(glob.glob(search_glob))

            # The current file hasn't been created yet, so we compare with backupCount.
            # If backupCount is 3, and there are already 3 files, we delete the oldest.
            while len(log_files) >= self.backupCount:
                os.remove(log_files[0])
                log_files.pop(0)

def get_logging_config():
    """
    Builds the logging configuration dictionary by reading environment variables.
    """
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    no_logs_to_file = os.environ.get("NO_LOGS_TO_FILE", "false").lower() == "true"
    handlers_to_use = ['console']

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "transaction_id_filter": {
                "()": TransactionIdFilter,
            }
        },
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "[%(asctime)s] [%(process)d] [%(levelname)s] [%(transaction_id)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
                "filters": ["transaction_id_filter"],
            },
        },
        "loggers": {
            # Root logger for the application
            "": {"handlers": handlers_to_use, "level": log_level},
            # Uvicorn loggers captured to use the same handlers
            "uvicorn.error": {
                "handlers": handlers_to_use,
                "level": log_level,
                "propagate": False
            },
            "uvicorn.access": {
                "handlers": handlers_to_use,
                "level": log_level,
                "propagate": False
            }
        },
    }

    if not no_logs_to_file:
        log_file_path = os.environ.get("LOG_FILE_PATH", "logs/default.log")
        max_log_size_mb = float(os.environ.get("LOG_MAX_SIZE_MB", 1))

        LOGGING_CONFIG["handlers"]["rotating_file"] = {
            "()": RotatingLogFileHandler,
            "filename": log_file_path,
            "maxBytes": max_log_size_mb * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "default",
            "filters": ["transaction_id_filter"],
        }
        for logger in LOGGING_CONFIG["loggers"].values():
            logger['handlers'].append('rotating_file')

    return LOGGING_CONFIG

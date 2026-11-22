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
import asyncio
from contextlib import contextmanager
import re
import sys
import logging
import time
import threading
from datetime import datetime
from contextvars import ContextVar

from loguru import logger
from utils.utils import get_api_data_dir

try:
    import msvcrt
except ImportError:
    msvcrt = None

transaction_id_var: ContextVar[str] = ContextVar('transaction_id', default='system')
username_var: ContextVar[str] = ContextVar('username', default='system')

DEFAULT_MAX_LOG_FILES = 5
VALID_LOG_LEVELS = ("DEBUG", "INFO")
INTERCEPTED_LOGGER_NAMES = ("werkzeug", "uvicorn", "uvicorn.error", "uvicorn.access")
STATIC_EXTENSIONS = (".png", ".svg", ".css", ".js", ".ico", ".woff", ".woff2")
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

_sink_ids = []

def _patcher(record):
    """Injects the transaction id and the user tag from the context variables."""
    username = username_var.get()
    record["extra"]["transaction_id"] = transaction_id_var.get()
    record["extra"]["user_tag"] = "" if username in ("system", "anonymous") else f"[user: {username}] "

def _format(record):
    return "[{time:YYYY-MM-DD HH:mm:ss ZZ}] [{process.id}] [{level}] [{extra[transaction_id]}] {extra[user_tag]}{message}\n{exception}"

def _log_filter(record):
    """Applies the runtime log level and hides noisy access logs of static assets."""
    if record["level"].no < logging.getLogger().level:
        return False
    msg = record["message"]
    if "GET " in msg and any(ext in msg.lower() for ext in STATIC_EXTENSIONS):
        return False
    return True

class InterceptHandler(logging.Handler):
    """Forwards standard library log records to loguru."""
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

class SharedLogFile:
    """
    Log file sink safe to be used by several processes at the same time.

    All processes of a launch append to `<name>_<session id><ext>`. When the file
    exceeds `max_bytes` a new `<name>_<timestamp><ext>` file is started (the one
    created first by any process wins, the rest follow it). Only the newest
    `max_files` files are kept, both at startup and on rotation.
    """
    def __init__(self, base_path, session_id, max_bytes=0, max_files=0):
        self.directory, filename = os.path.split(base_path)
        self.name, self.ext = os.path.splitext(filename)
        self.max_bytes = max_bytes
        self.max_files = max_files
        self._pattern = re.compile(rf"^{re.escape(self.name)}_\d{{8}}_\d{{6}}{re.escape(self.ext)}$")
        self._lock = threading.Lock()

        os.makedirs(self.directory, exist_ok=True)
        self.path = self._path_for(session_id)
        self._touch(self.path)
        self.prune()

    def _path_for(self, stamp):
        return os.path.join(self.directory, f"{self.name}_{stamp}{self.ext}")

    @staticmethod
    def _touch(path):
        with open(path, "a", encoding="utf-8"):
            pass

    def files(self):
        """Log files of this application, oldest first (timestamps sort chronologically)."""
        try:
            names = sorted(n for n in os.listdir(self.directory) if self._pattern.match(n))
        except OSError:
            return []
        return [os.path.join(self.directory, n) for n in names]

    def prune(self):
        if self.max_files <= 0:
            return
        files = self.files()
        excess = len(files) - self.max_files
        for old in files:
            if excess <= 0:
                break
            if old == self.path:
                continue
            try:
                os.remove(old)
                excess -= 1
            except FileNotFoundError:
                excess -= 1
            except OSError:
                pass

    def _is_full(self):
        try:
            return os.path.getsize(self.path) >= self.max_bytes
        except OSError:
            return False

    def _rotate(self):
        files = self.files()
        if files and files[-1] > self.path:
            # Another process already rotated, follow it
            self.path = files[-1]
            if not self._is_full():
                return
        new_path = self._path_for(datetime.now().strftime(TIMESTAMP_FORMAT))
        if new_path <= self.path:
            return
        self.path = new_path
        self._touch(new_path)
        self.prune()

    def _append(self, message):
        with open(self.path, "a", encoding="utf-8") as f:
            if msvcrt is None:
                # POSIX appends of a single write are atomic
                f.write(message)
                return
            # On Windows appends from several processes can overwrite each other:
            # serialize them with a byte-range lock shared by all processes.
            fd = f.fileno()
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.001)
            try:
                f.write(message)
                f.flush()
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def __call__(self, message):
        with self._lock:
            if self.max_bytes > 0 and self._is_full():
                self._rotate()
            self._append(message)

def get_session_id():
    """
    Identifier shared by every process of one launch (it names the log file).
    run.py provides it; otherwise the first process creates it and its
    children inherit it through the environment.
    """
    session_id = os.environ.get("LOG_SESSION_ID")
    if not session_id:
        session_id = datetime.now().strftime(TIMESTAMP_FORMAT)
        os.environ["LOG_SESSION_ID"] = session_id
    return session_id

def _log_base_path():
    # Default log path lives under the API logs directory; individual processes
    # override LOG_FILE_PATH to point to their own subdirectory.
    default_log_path = os.path.join(get_api_data_dir(), "logs", "default.log")
    return os.environ.get("LOG_FILE_PATH", default_log_path)

def _marker_prefix():
    return f".run_once_{os.path.splitext(os.path.basename(_log_base_path()))[0]}_"

def _purge_stale_markers():
    """Removes the run_once markers left by previous launches."""
    directory = os.path.dirname(_log_base_path())
    prefix, current = _marker_prefix(), f"{_marker_prefix()}{get_session_id()}_"
    try:
        for name in os.listdir(directory):
            if name.startswith(prefix) and not name.startswith(current):
                try:
                    os.remove(os.path.join(directory, name))
                except OSError:
                    pass
    except OSError:
        pass

def run_once(key):
    """
    Returns True in exactly one process per launch (and per key), so that startup
    banners are printed once when several workers import the application.
    """
    directory = os.path.dirname(_log_base_path())
    marker = os.path.join(directory, f"{_marker_prefix()}{get_session_id()}_{key}")
    try:
        os.makedirs(directory, exist_ok=True)
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False
    except OSError:
        # Cannot coordinate: better to print the banner twice than never
        return True

def _max_log_files(env_var):
    try:
        value = int(os.environ.get(env_var, DEFAULT_MAX_LOG_FILES))
    except ValueError:
        return DEFAULT_MAX_LOG_FILES
    return value if value > 0 else DEFAULT_MAX_LOG_FILES

def setup_logging(force=False, max_files_env="AI_SDK_LOG_MAX_FILES"):
    """
    Configures loguru from the environment and routes the standard library
    logging (including uvicorn and werkzeug) through it. Idempotent per process.
    `max_files_env` is the variable holding the log file limit of the application
    (AI_SDK_LOG_MAX_FILES for the API, CHATBOT_LOG_MAX_FILES for the chatbot).
    """
    global _sink_ids
    if _sink_ids and not force:
        return

    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    if not isinstance(log_level, int):
        log_level = logging.INFO

    logger.remove()
    logger.configure(patcher=_patcher)
    _sink_ids = [logger.add(sys.stdout, level=0, format=_format, filter=_log_filter, colorize=False)]

    _purge_stale_markers()

    if os.environ.get("NO_LOGS_TO_FILE", "false").lower() != "true":
        sink = SharedLogFile(
            _log_base_path(),
            get_session_id(),
            max_bytes=int(float(os.environ.get("LOG_MAX_SIZE_MB", 1)) * 1024 * 1024),
            max_files=_max_log_files(max_files_env),
        )
        _sink_ids.append(logger.add(sink, level=0, format=_format, filter=_log_filter, colorize=False))

    root = logging.getLogger()
    root.handlers = [InterceptHandler()]
    root.setLevel(log_level)
    for name in INTERCEPTED_LOGGER_NAMES:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = []
        stdlib_logger.propagate = True
        stdlib_logger.setLevel(logging.NOTSET)

def get_log_level():
    """Return the current application log level name, e.g. 'INFO'."""
    return logging.getLevelName(logging.getLogger().getEffectiveLevel())

def set_log_level(level_name):
    """Change the application log level at runtime."""
    level_name = str(level_name).strip().upper()
    if not level_name:
        raise ValueError("log_level is required")
    if level_name not in VALID_LOG_LEVELS:
        valid = ", ".join(VALID_LOG_LEVELS)
        raise ValueError(f"Invalid log level '{level_name}'. Valid levels: {valid}")

    if get_log_level() == level_name:
        os.environ["LOG_LEVEL"] = level_name
        return level_name

    level = getattr(logging, level_name)
    logging.getLogger().setLevel(level)

    os.environ["LOG_LEVEL"] = level_name
    # INFO is hidden once the level is WARNING or higher, so announce at a
    # level the new setting will still emit.
    announce_level = logging.INFO if level < logging.WARNING else level
    logging.log(announce_level, f"Log level changed to {level_name}")
    logging.debug(f"Runtime log level is now {level_name}")
    return level_name


@contextmanager
def llm_call_logging(role, llm):
    """Log each actual model invocation, including errors and cancellation."""
    activity_logger = logging.getLogger(__name__)
    label = f"{role} (provider={llm.provider_name}, model={llm.model_name})"
    activity_logger.info("%s started.", label)
    try:
        yield
    except (asyncio.CancelledError, GeneratorExit):
        activity_logger.info("%s finished (status=cancelled).", label)
        raise
    except BaseException:
        activity_logger.exception("%s finished (status=failed).", label)
        raise
    else:
        activity_logger.info("%s finished (status=completed).", label)

"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""
import os
import json
import time
import logging
import tempfile
import threading

from utils.logging_utils import get_log_level, set_log_level

# Workers are separate processes, so in-memory changes do not propagate.
# This file is the shared source of truth for runtime-overridable settings.
# Each process caches the parsed file and re-stats it at most once a second.

_CACHE_TTL_SECONDS = 1
_cache_lock = threading.Lock()
_cached_path = None
_cached_mtime = None
_cached_config = None
_last_stat = 0.0

def _config_path():
    data_dir = os.environ.get("AI_SDK_DATA_DIR", ".")
    logs_dir = os.path.join(data_dir, "logs") if data_dir != "." else "logs"
    return os.path.join(logs_dir, "runtime_config.json")

def default_runtime_config():
    return {
        "log_level": os.environ.get("LOG_LEVEL", get_log_level() or "INFO").upper(),
    }

def _remember_config(path, mtime, config):
    global _cached_path, _cached_mtime, _cached_config, _last_stat
    _cached_path = path
    _cached_mtime = mtime
    _cached_config = dict(config)
    _last_stat = time.monotonic()

def _cached_config_if_fresh(path):
    if _cached_config is None or _cached_path != path:
        return None
    if time.monotonic() - _last_stat >= _CACHE_TTL_SECONDS:
        return None
    return dict(_cached_config)

def _read_runtime_config(path):
    """Read the shared file, skipping the parse when its mtime is unchanged."""
    config = default_runtime_config()
    try:
        mtime = os.path.getmtime(path)
    except FileNotFoundError:
        _remember_config(path, None, config)
        return dict(config)
    except OSError as e:
        logging.error(f"Could not read runtime config file: {e}")
        _remember_config(path, None, config)
        return dict(config)

    if _cached_config is not None and _cached_path == path and _cached_mtime == mtime:
        _remember_config(path, mtime, _cached_config)
        return dict(_cached_config)

    try:
        with open(path, encoding="utf-8") as config_file:
            stored = json.load(config_file)
    except FileNotFoundError:
        _remember_config(path, None, config)
        return dict(config)
    except (OSError, json.JSONDecodeError) as e:
        logging.error(f"Could not read runtime config file: {e}")
        _remember_config(path, mtime, config)
        return dict(config)

    if isinstance(stored, dict):
        config.update(stored)
    _remember_config(path, mtime, config)
    return dict(config)

def load_runtime_config():
    """Return the shared runtime config, falling back to process defaults.

    Request paths hit this on every call. The parsed file is cached per process
    and the filesystem is checked at most once a second, and only re-read when
    the file's mtime changes.
    """
    path = _config_path()
    with _cache_lock:
        cached = _cached_config_if_fresh(path)
        if cached is not None:
            return cached
        return _read_runtime_config(path)

def save_runtime_config(config):
    """Atomically write the shared runtime config file."""
    path = _config_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix="runtime_config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(config, tmp_file, indent=2)
            tmp_file.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    with _cache_lock:
        _remember_config(path, mtime, config)

def apply_runtime_config(config):
    """Apply runtime settings to this worker process."""
    log_level = config.get("log_level")
    if log_level:
        set_log_level(log_level)

def update_runtime_config(updates):
    """Validate and apply updates in this worker, then persist them for the others."""
    with _cache_lock:
        config = _read_runtime_config(_config_path())
    config.update(updates)
    apply_runtime_config(config)
    config["log_level"] = get_log_level()
    save_runtime_config(config)
    return config

def sync_runtime_config():
    """If the shared file's log_level differs from this process, apply it."""
    config = load_runtime_config()
    log_level = config.get("log_level")
    if not log_level or str(log_level).strip().upper() == get_log_level():
        return

    try:
        apply_runtime_config(config)
    except ValueError as e:
        logging.error(f"Invalid runtime config: {e}")

def reconcile_runtime_config_with_cli():
    """On startup, --log-level wins over a leftover runtime_config.json."""
    path = _config_path()
    if not os.path.exists(path):
        return

    cli_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    with _cache_lock:
        config = _read_runtime_config(path)
    if config.get("log_level") != cli_level:
        config["log_level"] = cli_level
        save_runtime_config(config)

import os
import inspect

from uuid import uuid4
from datetime import datetime
from utils.version import AI_SDK_VERSION
import logging

_ENABLED = bool(os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"))

if _ENABLED:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    _client = Langfuse(release=AI_SDK_VERSION)
    _handler = CallbackHandler()
else:
    _client = None
    _handler = None

def is_enabled():
    return _ENABLED

def get_handler():
    return _handler if _ENABLED else None

def _default_run_name():
    frame = inspect.currentframe()
    if frame and frame.f_back:
        return frame.f_back.f_code.co_name
    return "unknown"

def build_config(model_id=None, session_id=None, run_name=None, user_id=None, extra_metadata=None):
    config = {}

    if run_name:
        config["run_name"] = run_name

    if not _ENABLED or _handler is None:
        return config

    config["callbacks"] = [_handler]

    metadata = {}
    resolved_user_id = user_id or os.getenv("LANGFUSE_USER")
    if resolved_user_id:
        metadata["langfuse_user_id"] = resolved_user_id
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if model_id:
        metadata["model_id"] = model_id
    if extra_metadata:
        metadata.update(extra_metadata)
    if metadata:
        config["metadata"] = metadata

    return config

class trace_context:
    def __init__(self, run_name=None, model_id=None, session_id=None, user_id=None, extra_metadata=None):
        self.run_name = run_name or _default_run_name()
        self.model_id = model_id
        self.session_id = session_id
        self.user_id = user_id
        self.extra_metadata = extra_metadata
        self.config = {}

    def __enter__(self):
        self.config = build_config(
            model_id=self.model_id,
            session_id=self.session_id,
            run_name=self.run_name,
            user_id=self.user_id,
            extra_metadata=self.extra_metadata
        )
        return self.config

    def __exit__(self, exc_type, exc_value, traceback):
        return False

def generate_langfuse_session_id():
    user = os.getenv('LANGFUSE_USER')
    if user:
        current_time = datetime.now().strftime("%Y_%m_%d_%H_%M")
        session_uuid = uuid4().hex[:4]
        return f"{current_time}_{user}_{session_uuid}"
    else:
        return None
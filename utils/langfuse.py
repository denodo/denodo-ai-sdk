import os
import inspect
import logging
import threading

from uuid import uuid4
from datetime import datetime
from utils.version import AI_SDK_VERSION
from utils.logging_utils import username_var

_lock = threading.Lock()
_configured = False
_client = None
_handler = None
_warned_missing_init = False

def init_langfuse():
    """
    Load Langfuse client and LangChain callback handler from the current environment.

    Call once per process after env is available (e.g. after load_dotenv). The API does
    this via state_manager.initialize_default_resources(); the sample chatbot does it at
    the start of create_app.
    Safe to call multiple times; only the first call takes effect.
    """
    global _client, _handler, _configured
    with _lock:
        if _configured:
            return
        _configured = True
        secret = os.getenv("LANGFUSE_SECRET_KEY")
        public = os.getenv("LANGFUSE_PUBLIC_KEY")
        if not (secret and public):
            logging.info("Langfuse disabled: LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY not both set.")
            return
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        _client = Langfuse(release=AI_SDK_VERSION)
        _handler = CallbackHandler()
        logging.info("Langfuse tracing enabled.")

def is_enabled():
    return _handler is not None

def get_handler():
    return _handler

def _default_run_name(depth=1):
    """
    Name a run after the function `depth` frames above this one.

    The run name is also used as the trace name, so callers that sit behind a
    wrapper pass a larger depth to skip the wrapper and reach the code that
    actually started the trace.
    """
    frame = inspect.currentframe()
    for _ in range(depth):
        if frame is None:
            return "unknown"
        frame = frame.f_back
    return frame.f_code.co_name if frame else "unknown"

def resolve_langfuse_user_id(request_user=None):
    """
    Build the Langfuse user id.

    When LANGFUSE_USER is set and there is a request user, returns
    {LANGFUSE_USER}_{REQUEST_USER} (e.g. IT_admin). Otherwise returns whichever
    of the two is available.
    """
    prefix = (os.getenv("LANGFUSE_USER") or "").strip()
    request_user = (request_user or "").strip() or (username_var.get() or "").strip()
    if prefix and request_user:
        return f"{prefix}_{request_user}"
    return request_user or prefix or None

# Langfuse only accepts metadata values that are text of at most 200 characters,
# and throws away anything else without telling us, so values are checked here.
_MAX_METADATA_VALUE_LENGTH = 200

# Keys the Langfuse LangChain callback handler reads from the config metadata to
# fill in the trace attributes. It uses them as they are (langfuse_tags is a
# list, not text) and removes them from the metadata afterwards, so they must be
# left alone here.
_RESERVED_METADATA_KEYS = frozenset({
    "langfuse_session_id",
    "langfuse_user_id",
    "langfuse_tags",
    "langfuse_trace_name",
    "langfuse_prompt",
})

def _clean_metadata_value(key, value):
    """
    Turn a metadata value into text that Langfuse accepts.

    Returns the value as text, or None when it is too long. Langfuse would throw
    a long value away silently, so it is dropped here with a warning instead.
    """
    if not isinstance(value, str):
        value = str(value)
    if len(value) > _MAX_METADATA_VALUE_LENGTH:
        logging.warning(
            f"Langfuse metadata '{key}' is {len(value)} characters, over the "
            f"{_MAX_METADATA_VALUE_LENGTH} character limit. Dropping it."
        )
        return None
    return value

def build_config(model_id=None, session_id=None, run_name=None, user_id=None, extra_metadata=None):
    global _warned_missing_init
    config = {}

    if run_name:
        config["run_name"] = run_name

    if not _configured:
        if not _warned_missing_init:
            logging.warning("Langfuse was not initialized.")
            _warned_missing_init = True
        return config

    if _handler is None:
        return config

    config["callbacks"] = [_handler]

    metadata = {}
    resolved_user_id = resolve_langfuse_user_id(user_id)
    if resolved_user_id:
        metadata["langfuse_user_id"] = resolved_user_id
    if session_id:
        metadata["langfuse_session_id"] = session_id
    # Langfuse names each step from run_name but does not name the trace from
    # it, so the trace name is sent separately to keep traces recognisable.
    if run_name:
        metadata["langfuse_trace_name"] = run_name
    if model_id:
        metadata["model_id"] = model_id
    if extra_metadata:
        metadata.update(extra_metadata)

    cleaned = {}
    for key, value in metadata.items():
        if key in _RESERVED_METADATA_KEYS and not isinstance(value, str):
            cleaned[key] = value
            continue
        text_value = _clean_metadata_value(key, value)
        if text_value is not None:
            cleaned[key] = text_value

    if cleaned:
        config["metadata"] = cleaned

    return config

def _attach_trace_attributes(metadata, run_name):
    """
    Attach the trace attributes to everything Langfuse records from here on.

    Returns the open context, or None when there is nothing to attach. Sending
    these attributes through the config metadata only reaches the first step of
    an asynchronous chain, because the later steps run somewhere the callback
    handler cannot reach. Opening the context here covers all of them.
    """
    if _handler is None or not metadata:
        return None

    extra = {k: v for k, v in metadata.items() if k not in _RESERVED_METADATA_KEYS}
    try:
        from langfuse import propagate_attributes

        context = propagate_attributes(
            user_id=metadata.get("langfuse_user_id"),
            session_id=metadata.get("langfuse_session_id"),
            trace_name=metadata.get("langfuse_trace_name") or run_name,
            tags=metadata.get("langfuse_tags"),
            metadata=extra or None,
        )
        context.__enter__()
        return context
    except Exception:
        logging.warning("Could not attach the Langfuse trace attributes.", exc_info=True)
        return None

class trace_context:
    """
    Scope a group of LLM calls to a single Langfuse trace.

    Gives you the LangChain config to pass to invoke/ainvoke, and keeps the
    trace attributes (user, session, trace name, tags) attached to every step
    recorded inside the block. Use this instead of build_config for
    asynchronous chains, where the config alone only labels the first step.
    """
    def __init__(self, run_name=None, model_id=None, session_id=None, user_id=None, extra_metadata=None):
        self.run_name = run_name or _default_run_name(depth=2)
        self.model_id = model_id
        self.session_id = session_id
        self.user_id = user_id
        self.extra_metadata = extra_metadata
        self.config = {}
        self._attributes = None

    def __enter__(self):
        self.config = build_config(
            model_id=self.model_id,
            session_id=self.session_id,
            run_name=self.run_name,
            user_id=self.user_id,
            extra_metadata=self.extra_metadata
        )
        self._attributes = _attach_trace_attributes(self.config.get("metadata"), self.run_name)
        return self.config

    def __exit__(self, exc_type, exc_value, traceback):
        if self._attributes is not None:
            try:
                self._attributes.__exit__(exc_type, exc_value, traceback)
            except Exception:
                logging.warning("Could not release the Langfuse trace attributes.", exc_info=True)
            self._attributes = None
        return False

def generate_langfuse_session_id():
    user = os.getenv('LANGFUSE_USER')
    if user:
        current_time = datetime.now().strftime("%Y_%m_%d_%H_%M")
        session_uuid = uuid4().hex[:4]
        return f"{current_time}_{user}_{session_uuid}"
    else:
        return None

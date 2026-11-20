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
import re
import shutil

# sample_chatbot/utils/ is the location from 1.5 forward.
# 1.5 still reads sample_chatbot/chatbot_config.env when the utils file is absent.
# That fallback is deprecated in 1.6.
SAMPLE_CHATBOT_DIR = os.path.join(".", "sample_chatbot")
CHATBOT_UTILS_DIR = os.path.join(SAMPLE_CHATBOT_DIR, "utils")
CANONICAL_CHATBOT_ENV = os.path.join(CHATBOT_UTILS_DIR, "chatbot_config.env")
CANONICAL_CHATBOT_EXAMPLE = CANONICAL_CHATBOT_ENV + ".example"
LEGACY_CHATBOT_ENV = os.path.join(SAMPLE_CHATBOT_DIR, "chatbot_config.env")

_ENV_NUMBERED_BACKUP = re.compile(r"\.env\..+\.bak$")

def is_sample_chatbot_env_filename(name):
    """True for *.env, *.env.example, *.env.bak and *.env.*.bak."""
    if name.endswith(".env.example") or name.endswith(".env.bak") or name.endswith(".env"):
        return True
    return _ENV_NUMBERED_BACKUP.search(name) is not None

def list_legacy_chatbot_env_files():
    """Config files still sitting in sample_chatbot/ rather than sample_chatbot/utils/."""
    if not os.path.isdir(SAMPLE_CHATBOT_DIR):
        return []
    found = []
    for name in sorted(os.listdir(SAMPLE_CHATBOT_DIR)):
        path = os.path.join(SAMPLE_CHATBOT_DIR, name)
        if os.path.isfile(path) and is_sample_chatbot_env_filename(name):
            found.append(path)
    return found

def resolve_chatbot_env_path():
    """Prefer the utils file. Fall back to sample_chatbot/chatbot_config.env on 1.5."""
    if os.path.isfile(CANONICAL_CHATBOT_ENV):
        return CANONICAL_CHATBOT_ENV
    if os.path.isfile(LEGACY_CHATBOT_ENV):
        return LEGACY_CHATBOT_ENV
    return CANONICAL_CHATBOT_ENV

LEGACY_ENV_WARNING_TITLE = "Using sample_chatbot/chatbot_config.env"
LEGACY_ENV_WARNING_DETAIL = (
    "To align with the API's sdk_config.env, present in the utils/ folder, "
    "chatbot_config.env will be read from sample_chatbot/utils/chatbot_config.env from now on. "
    "The old path will be deprecated and removed in 1.6. "
    "Please run --migrate to move it."
)

def chatbot_env_startup_notice():
    """Warn when 1.5 is still reading the pre-utils location. Empty when the utils file is in use."""
    if os.path.isfile(CANONICAL_CHATBOT_ENV) or not os.path.isfile(LEGACY_CHATBOT_ENV):
        return ""
    return f"{LEGACY_ENV_WARNING_TITLE}. {LEGACY_ENV_WARNING_DETAIL}"

def move_legacy_chatbot_env_files(paths):
    """Move files into sample_chatbot/utils/. Never overwrite a file already there."""
    os.makedirs(CHATBOT_UTILS_DIR, exist_ok=True)
    moved = []
    skipped = []
    for src in paths:
        dest = os.path.join(CHATBOT_UTILS_DIR, os.path.basename(src))
        if os.path.exists(dest):
            skipped.append(src)
            continue
        shutil.move(src, dest)
        moved.append(dest)
    return moved, skipped

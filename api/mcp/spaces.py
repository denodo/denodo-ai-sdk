"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.

 This software is the confidential and proprietary information of DENODO
 Technologies ("Confidential Information"). You shall not disclose such
 Confidential Information and shall use it only in accordance with the terms
 of the license agreement you entered into with DENODO.
"""

import logging
from functools import partial
from pathlib import Path
import yaml

from utils.status import Status, add_status
from utils.utils import get_agents_spaces_dir

logger = logging.getLogger(__name__)

SPACES_DIR = Path(get_agents_spaces_dir())
ALLOWED_KEYS = {"databases", "tags"}

def _as_name_list(value):
    """One YAML string is one name. A list entry is one name, even when it contains a comma."""
    if not value:
        return []
    if isinstance(value, str):
        name = value.strip()
        return [name] if name else []
    if isinstance(value, list):
        names = []
        for item in value:
            if item is None:
                continue
            name = str(item).strip()
            if name:
                names.append(name)
        return names
    name = str(value).strip()
    return [name] if name else []

def load_spaces(spaces_dir=None, report=None):
    """Load AI Spaces from YAML files. The filename stem is the space name."""
    _report = partial(add_status, report)

    spaces_dir = Path(spaces_dir) if spaces_dir else SPACES_DIR
    spaces = {}

    if not spaces_dir.is_dir():
        logger.info(f"No AI Spaces directory at {spaces_dir}")
        return spaces

    yaml_files = sorted(
        list(spaces_dir.glob("*.yaml")) + list(spaces_dir.glob("*.yml")),
        key=lambda p: p.name.lower(),
    )

    for path in yaml_files:
        file_name = path.name

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if data is None:
                msg = "file is empty"
                logger.warning(f"Skipping {file_name}: {msg}")
                _report(file_name, Status.WARNING)
                continue

            if not isinstance(data, dict):
                err = "expected a mapping with 'databases' and/or 'tags'"
                logger.error(f"Skipping {file_name}: {err}")
                _report(file_name, Status.ERROR)
                continue

            unknown_keys = set(data.keys()) - ALLOWED_KEYS
            if unknown_keys:
                err = f"unexpected keys {sorted(unknown_keys)}; only 'databases' and 'tags' are allowed"
                logger.error(f"Skipping {file_name}: {err}")
                _report(file_name, Status.ERROR)
                continue

            if not any(k in data for k in ALLOWED_KEYS):
                err = "missing required keys: expected 'databases' and/or 'tags'"
                logger.error(f"Skipping {file_name}: {err}")
                _report(file_name, Status.ERROR)
                continue

            databases = _as_name_list(data.get("databases"))
            tags = _as_name_list(data.get("tags"))
            if not databases and not tags:
                err = "expected at least one non-empty 'databases' or 'tags' entry"
                logger.error(f"Skipping {file_name}: {err}")
                _report(file_name, Status.ERROR)
                continue

            name = path.stem
            if name in spaces:
                msg = f"duplicate AI Space '{name}' (ignored)"
                logger.warning(f"Skipping {file_name}: {msg}")
                _report(file_name, Status.WARNING)
                continue

            spaces[name] = (databases, tags)
            _report(name, Status.OK)
            logger.info(
                f"Loaded AI Space '{name}' "
                f"(databases={spaces[name][0]!r}, tags={spaces[name][1]!r})"
            )

        except yaml.YAMLError as e:
            err = f"YAML syntax error: {e}"
            logger.error(f"{file_name}: {err}")
            _report(file_name, Status.ERROR)

        except Exception as e:
            err = f"failed to load: {e}"
            logger.exception(f"{file_name}: {err}")
            _report(file_name, Status.ERROR)

    return spaces

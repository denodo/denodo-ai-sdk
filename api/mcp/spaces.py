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
import yaml

from pathlib import Path

logger = logging.getLogger(__name__)

SPACES_DIR = Path("api/agents/spaces")

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
            name = str(item).strip()
            if name:
                names.append(name)
        return names
    name = str(value).strip()
    return [name] if name else []

def load_spaces(spaces_dir=None):
    """Load AI Spaces from YAML files. The filename stem is the space name."""
    spaces_dir = Path(spaces_dir) if spaces_dir else SPACES_DIR
    spaces = {}

    if not spaces_dir.is_dir():
        logger.info(f"No AI Spaces directory at {spaces_dir}")
        return spaces

    for path in [*spaces_dir.glob("*.yaml"), *spaces_dir.glob("*.yml")]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                logger.error(f"Skipping {path.name}: expected a mapping with 'databases' and/or 'tags'.")
                continue

            name = path.stem
            if name in spaces:
                logger.warning(f"Duplicate AI Space '{name}' from {path.name}; using this file.")

            spaces[name] = (
                _as_name_list(data.get("databases")),
                _as_name_list(data.get("tags")),
            )
            logger.info(
                f"Loaded AI Space '{name}' "
                f"(databases={spaces[name][0]!r}, tags={spaces[name][1]!r})"
            )
        except Exception:
            logger.exception(f"Failed to load AI Space {path.name}")

    return spaces

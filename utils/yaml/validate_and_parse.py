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
from jsonschema import validate, ValidationError

from api.mcp.spaces import load_spaces
from utils.status import Status, add_status
from utils.utils import get_agents_custom_dir, get_agents_spaces_dir

logger = logging.getLogger(__name__)

def _union_names(*groups):
    seen = set()
    names = []
    for group in groups:
        if isinstance(group, str):
            group = [group] if group.strip() else []
        for name in group or []:
            name = str(name).strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names

def _apply_space_scope(data, spaces, source_name):
    settings = data.get("settings")
    if not isinstance(settings, dict):
        return True

    space_name = str(settings.get("space") or "").strip()
    if not space_name:
        return True

    if space_name not in spaces:
        logger.error(
            f"Validation error in {source_name}: unknown AI Space '{space_name}'. "
            f"Add {get_agents_spaces_dir()}/{space_name}.yaml"
        )
        return False

    space_databases, space_tags = spaces[space_name]
    settings["databases"] = _union_names(space_databases, settings.get("databases"))
    settings["tags"] = _union_names(space_tags, settings.get("tags"))
    logger.info(
        f"Agent '{data.get('id')}' using AI Space '{space_name}' "
        f"(databases={settings['databases']}, tags={settings['tags']})"
    )
    return True

def load_and_validate_agents(report=None):
    """
    Reads YAML files from the custom agents directory, validates them against
    the schema (including slug format), and returns a list of parsed objects.
    """
    _report = partial(add_status, report)

    # Define paths
    agents_dir = Path(get_agents_custom_dir())
    schema_path = Path("utils/yaml/agent_schema.yaml")

    parsed_agents = []
    seen_ids = set()  # To ensure slug IDs are unique across all files

    # 1. Load the schema only once
    if not schema_path.exists():
        err = f"schema file not found: {schema_path}"
        logger.error(err)
        _report("Agent schema", Status.ERROR)
        return parsed_agents

    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        err = f"cannot read schema: {e}"
        logger.error(err)
        _report("Agent schema", Status.ERROR)
        return parsed_agents

    # 2. Check if the agents directory exists
    if not agents_dir.exists() or not agents_dir.is_dir():
        err = f"agents directory does not exist: {agents_dir}"
        logger.error(err)
        _report(str(agents_dir), Status.ERROR)
        return parsed_agents

    # 3. Find all .yaml and .yml files
    yaml_files = sorted(
        list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml")),
        key=lambda p: p.name.lower(),
    )

    if not yaml_files:
        logger.info(f"No YAML files found in the agents directory: {agents_dir}")
        return parsed_agents

    spaces = None

    # 4. Process each file
    for file_path in yaml_files:
        file_name = file_path.name

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                msg = "file is empty"
                logger.warning(f"{file_name}: {msg}")
                _report(file_name, Status.WARNING)
                continue

            # Validate content against the schema (includes slug pattern check)
            validate(instance=data, schema=schema)

            # Extra Logic: Ensure 'id' is globally unique across all files
            agent_id = data.get("id")
            if agent_id in seen_ids:
                err = f"duplicate id '{agent_id}'"
                logger.error(f"Validation error in {file_name}: {err}")
                _report(file_name, Status.ERROR)
                continue

            settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
            space_name = str(settings.get("space") or "").strip()
            if space_name:
                if spaces is None:
                    spaces = load_spaces()
                if not _apply_space_scope(data, spaces, file_name):
                    target_name = data.get("name") or agent_id or file_name
                    _report(target_name, Status.ERROR)
                    continue

            seen_ids.add(agent_id)
            parsed_agents.append(data)
            _report(data.get("name") or agent_id, Status.OK)
            logger.info(f"Successfully loaded and validated: '{agent_id}' ({file_name})")

        except yaml.YAMLError as e:
            err = f"YAML syntax error: {e}"
            logger.error(f"{file_name}: {err}")
            _report(file_name, Status.ERROR)

        except ValidationError as e:
            json_path = getattr(e, "json_path", "")
            if e.validator == "pattern" and "id" in json_path:
                err = "invalid id slug"
            elif e.validator == "required":
                err = e.message
            else:
                err = f"invalid field '{json_path}': {e.message}"

            logger.error(f"Validation error in {file_name}: {err}")
            _report(file_name, Status.ERROR)

        except Exception as e:
            err = f"unexpected error: {e}"
            logger.error(f"{file_name}: {err}")
            _report(file_name, Status.ERROR)

    return parsed_agents

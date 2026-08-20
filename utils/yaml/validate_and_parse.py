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
from pathlib import Path
import yaml
from jsonschema import validate, ValidationError
import json

logger = logging.getLogger(__name__)

def load_and_validate_agents() -> list:
    """
    Reads YAML files from the custom agents directory, validates them against
    the schema (including slug format), and returns a list of parsed objects.
    """
    # Define paths
    agents_dir = Path("api/agents/custom")
    schema_path = Path("utils/yaml/agent_schema.yaml")

    parsed_agents = []
    seen_ids = set()  # To ensure slug IDs are unique across all files

    # 1. Load the schema only once
    if not schema_path.exists():
        logger.error(f"Schema file not found at: {schema_path}")
        return parsed_agents

    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Critical error reading schema: {e}")
        return parsed_agents

    # 2. Check if the agents directory exists
    if not agents_dir.exists() or not agents_dir.is_dir():
        logger.error(f"Directory {agents_dir} does not exist.")
        return parsed_agents

    # 3. Find all .yaml and .yml files
    yaml_files = list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml"))

    if not yaml_files:
        logger.info(f"No YAML files found in the agents {agents_dir} directory.")
        return parsed_agents

    # 4. Process each file
    for file_path in yaml_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                logger.warning(f"Skipping {file_path.name}: File is empty.")
                continue

            # Validate content against the schema (includes slug pattern check)
            validate(instance=data, schema=schema)

            # Extra Logic: Ensure 'id' is globally unique across all files
            agent_id = data.get("id")
            if agent_id in seen_ids:
                logger.error(f"Validation error in {file_path.name}: Duplicate 'id' slug '{agent_id}' already exists.")
                continue

            seen_ids.add(agent_id)
            parsed_agents.append(data)
            logger.info(f"Successfully loaded and validated: '{agent_id}' ({file_path.name})")

        except yaml.YAMLError as e:
            logger.error(f"YAML syntax error in {file_path.name}: {e}")
        except ValidationError as e:
            # Check if the error is specifically related to the slug pattern
            if e.validator == "pattern" and "id" in e.json_path:
                logger.error(
                    f"Validation error in {file_path.name}: The 'id' must be a valid slug (lowercase, numbers, and hyphens only).")
            else:
                logger.error(f"Validation error in {file_path.name} (field '{e.json_path}'): {e.message}")
        except Exception as e:
            logger.error(f"Unexpected error processing {file_path.name}: {e}")

    return parsed_agents

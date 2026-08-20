"""
Checks the configuration prerequisites declared by a specialized agent.

Agents can declare `skills` and `knowledge_bases` in their YAML. Declared
skills must exist on disk under the AI SDK skills/ directory, and declared
knowledge base collections must already exist in the shared vector store as
PUBLIC collections (added through the Knowledge Base Manager). Declared skills
must also not be disabled by the agent's own feature flags (e.g. declaring
'deepquery' while deepquery_enabled is false). An agent with missing
prerequisites cannot be used until they are available.
"""

import logging

from sample_chatbot.engine.skills import discover_skills
from sample_chatbot.services.kb_registry import get_registry_for

logger = logging.getLogger(__name__)

def missing_agent_prerequisites(config):
    """Return the declared skills and knowledge bases that do not exist.

    Returns ``{"skills": [names...], "knowledge_bases": [names...],
    "disabled_skills": [names...]}``; all lists empty when the agent is usable. If the vector store cannot be
    reached, every declared collection is reported missing (the agent could
    not use them anyway).
    """
    missing_skills = []
    disabled_skills = []
    if config.agent_skills:
        available = {
            name for name, meta in discover_skills().items()
            if meta.get("valid", True)
        }
        missing_skills = [name for name in config.agent_skills if name not in available]
        # Declaring a skill whose feature is disabled for this agent (e.g.
        # 'deepquery' with deepquery_enabled: false) is a config contradiction.
        disabled_skills = [name for name in config.agent_skills if name in config.disabled_skills]

    missing_kbs = []
    if config.knowledge_bases:
        declared = list(config.knowledge_bases)
        try:
            registry = get_registry_for(config)
            # Agents can only use PUBLIC collections; a declared name that only
            # exists as a user's private collection counts as missing.
            missing_kbs = [
                name for name in declared
                if not registry.has_collection(name)
                or (registry.get_collection(name) or {}).get('private')
            ]
        except Exception as e:
            logger.error(f"[Agent prerequisites] Could not access the vector store for agent '{config.id}': {e}")
            missing_kbs = declared

    return {"skills": missing_skills, "knowledge_bases": missing_kbs, "disabled_skills": disabled_skills}

def missing_prerequisites_message(missing):
    """Human-readable message for a non-empty missing_agent_prerequisites() result."""
    parts = []
    if missing["skills"]:
        parts.append("Skills: " + ", ".join(missing["skills"]))
    if missing["knowledge_bases"]:
        parts.append("Knowledge bases: " + ", ".join(missing["knowledge_bases"]))
    if missing.get("disabled_skills"):
        parts.append(
            "Skills declared but disabled by this agent's configuration: "
            + ", ".join(missing["disabled_skills"])
            + " (remove them from `skills` or enable the feature)"
        )
    return (
        "This agent is missing the following configuration prerequisites — "
        + ". ".join(parts)
        + ". The agent cannot be used until they are available."
    )

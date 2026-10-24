"""Prompt templates loaded from app/prompt.yaml."""
import logging
from functools import lru_cache

import yaml

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, str]:
    try:
        with open(settings.prompt_file, "r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}
    except FileNotFoundError:
        logger.error("Prompt file not found: %s", settings.prompt_file)
    except yaml.YAMLError as e:
        logger.error("Error parsing prompt file: %s", e)
    return {}


def get_prompt(name: str, **kwargs) -> str:
    """Return a prompt by name, formatted with kwargs when given."""
    template = load_prompts().get(name, DEFAULT_SYSTEM_PROMPT)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError) as e:
        logger.warning("Missing format key in prompt '%s': %s", name, e)
        context = "\n".join(f"{k}: {v}" for k, v in kwargs.items())
        return f"{template}\n\nContext data:\n{context}"

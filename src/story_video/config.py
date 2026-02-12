"""Configuration loading and merging for the Story Video Generator.

Reads configuration from a YAML file, merges with Pydantic model defaults,
and applies CLI overrides. Returns a fully validated, frozen AppConfig instance.

This module handles only configuration loading — no API keys, no file I/O
beyond reading config.yaml, no pipeline logic.
"""

from pathlib import Path
from typing import Any

import yaml

from story_video.models import AppConfig

__all__ = ["load_config"]


def load_config(
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load application configuration with three-way merge.

    Merge precedence: Pydantic defaults < config.yaml < CLI overrides.

    The merge works on plain dicts before constructing the frozen AppConfig:
    1. Start with an empty dict (Pydantic fills in defaults during validation).
    2. Deep-merge values from config.yaml (if provided).
    3. Apply CLI overrides using dotted-key notation on top.
    4. Validate the merged dict through Pydantic to produce an AppConfig.

    Args:
        config_path: Path to config.yaml. If None, uses only defaults.
        cli_overrides: Dict of dotted-key overrides from CLI args.
            Example: {"tts.voice": "alloy", "pipeline.autonomous": True}
            Keys use dot notation matching config sections.

    Returns:
        Fully validated AppConfig instance.

    Raises:
        FileNotFoundError: If config_path is provided but doesn't exist.
        ValueError: If config file contains invalid YAML or is not a mapping.
        pydantic.ValidationError: If merged config fails validation.
    """
    # Merge precedence: Pydantic defaults < config.yaml < CLI overrides
    config_dict: dict[str, Any] = {}

    if config_path is not None:
        config_dict = _load_yaml(config_path)

    if cli_overrides:
        _apply_dotted_overrides(config_dict, cli_overrides)

    return AppConfig(**config_dict)


def _load_yaml(config_path: Path) -> dict[str, Any]:
    """Read and parse a YAML config file, returning a plain dict.

    Args:
        config_path: Path to the YAML file.

    Returns:
        Parsed YAML content as a dict. Returns an empty dict if the file
        is empty or contains only comments.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains invalid YAML or is not a mapping.
    """
    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise FileNotFoundError(msg)

    text = config_path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in configuration file {config_path}: {exc}"
        raise ValueError(msg) from exc

    # safe_load returns None for empty files or files with only comments
    if data is None:
        return {}

    if not isinstance(data, dict):
        msg = (
            f"Configuration file {config_path} must contain a YAML mapping (dict), "
            f"got {type(data).__name__}"
        )
        raise ValueError(msg)

    return data


def _apply_dotted_overrides(
    config_dict: dict[str, Any],
    overrides: dict[str, Any],
) -> None:
    """Apply dotted-key CLI overrides to a config dict in place.

    Each key in overrides uses dot notation to address nested config fields.
    For example, "tts.voice" sets config_dict["tts"]["voice"].

    Args:
        config_dict: The config dict to modify (mutated in place).
        overrides: Dict of dotted keys to values.
    """
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        target = config_dict
        # Navigate to the parent dict, creating intermediate dicts as needed
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            next_target = target[part]
            if not isinstance(next_target, dict):
                msg = (
                    f"Cannot apply override '{dotted_key}': "
                    f"'{part}' is {type(next_target).__name__}, not a mapping"
                )
                raise ValueError(msg)
            target = next_target
        # Set the leaf value
        target[parts[-1]] = value

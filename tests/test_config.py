"""Tests for story_video.config — Configuration loading and merging.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the load_config function.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from story_video.config import load_config
from story_video.models import AppConfig

# ---------------------------------------------------------------------------
# Defaults-only tests (no file, no CLI overrides)
# ---------------------------------------------------------------------------


class TestLoadConfigDefaultsOnly:
    """load_config with no arguments returns Pydantic defaults."""

    def test_returns_app_config_instance(self):
        config = load_config()
        assert isinstance(config, AppConfig)

    def test_story_defaults(self):
        config = load_config()
        assert config.story.target_duration_minutes == 30
        assert config.story.words_per_minute == 150

    def test_tts_defaults(self):
        config = load_config()
        assert config.tts.voice == "nova"
        assert config.tts.provider == "openai"

    def test_pipeline_defaults(self):
        config = load_config()
        assert config.pipeline.autonomous is False


# ---------------------------------------------------------------------------
# Loading from YAML file
# ---------------------------------------------------------------------------


class TestLoadConfigFromYaml:
    """load_config reads a YAML file and merges with defaults."""

    def test_loads_yaml_values_with_defaults_for_rest(self, tmp_path):
        """YAML values loaded; unspecified fields get Pydantic defaults."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("tts:\n  voice: alloy\n")
        config = load_config(config_path=yaml_file)
        assert config.tts.voice == "alloy"
        # Unspecified TTS fields get defaults
        assert config.tts.provider == "openai"
        assert config.tts.model == "gpt-4o-mini-tts"
        # Other sections are entirely defaults
        assert config.story.target_duration_minutes == 30
        assert config.video.fps == 30

    def test_loads_multiple_sections(self, tmp_path):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "story:\n"
            "  target_duration_minutes: 60\n"
            "tts:\n"
            "  voice: echo\n"
            "pipeline:\n"
            "  autonomous: true\n"
        )
        config = load_config(config_path=yaml_file)
        assert config.story.target_duration_minutes == 60
        assert config.tts.voice == "echo"
        assert config.pipeline.autonomous is True

    def test_empty_or_comments_only_yaml_gives_defaults(self, tmp_path):
        """Empty file and comments-only file both produce defaults."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        config = load_config(config_path=empty_file)
        assert config.story.target_duration_minutes == 30
        assert config.tts.voice == "nova"

        comments_file = tmp_path / "comments.yaml"
        comments_file.write_text("# This is a comment\n# Another comment\n")
        config2 = load_config(config_path=comments_file)
        assert config2.story.target_duration_minutes == 30

    def test_unknown_yaml_keys_raise_validation_error(self, tmp_path):
        """Extra keys in YAML that don't match any config section are rejected."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("nonexistent_section:\n  foo: bar\n")
        with pytest.raises(ValidationError):
            load_config(config_path=yaml_file)


# ---------------------------------------------------------------------------
# CLI overrides
# ---------------------------------------------------------------------------


class TestLoadConfigCLIOverrides:
    """CLI overrides (dotted keys) override both defaults and YAML values."""

    def test_override_single_value_keeps_defaults(self):
        """Single CLI override applied; unoverridden fields keep defaults."""
        config = load_config(cli_overrides={"tts.voice": "echo"})
        assert config.tts.voice == "echo"
        assert config.tts.provider == "openai"
        assert config.story.target_duration_minutes == 30

    def test_override_multiple_values_no_yaml(self):
        config = load_config(
            cli_overrides={
                "tts.voice": "alloy",
                "video.fps": 60,
                "pipeline.autonomous": True,
            }
        )
        assert config.tts.voice == "alloy"
        assert config.video.fps == 60
        assert config.pipeline.autonomous is True

    def test_override_story_config(self):
        config = load_config(cli_overrides={"story.target_duration_minutes": 120})
        assert config.story.target_duration_minutes == 120

    def test_empty_overrides_dict_is_no_op(self):
        config = load_config(cli_overrides={})
        assert config.tts.voice == "nova"


# ---------------------------------------------------------------------------
# Merge precedence: defaults < YAML < CLI
# ---------------------------------------------------------------------------


class TestMergePrecedence:
    """Merge precedence: Pydantic defaults < config.yaml < CLI overrides."""

    def test_cli_overrides_yaml(self, tmp_path):
        """CLI override wins over YAML value."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("tts:\n  voice: alloy\n")
        config = load_config(
            config_path=yaml_file,
            cli_overrides={"tts.voice": "echo"},
        )
        # YAML says "alloy", CLI says "echo" — CLI wins
        assert config.tts.voice == "echo"

    def test_cli_overrides_yaml_in_same_section(self, tmp_path):
        """CLI overrides one field in a section while YAML sets another."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("tts:\n  voice: alloy\n  speed: 1.5\n")
        config = load_config(
            config_path=yaml_file,
            cli_overrides={"tts.voice": "echo"},
        )
        # CLI overrides voice, YAML speed is preserved
        assert config.tts.voice == "echo"
        assert config.tts.speed == 1.5

    def test_three_way_merge(self, tmp_path):
        """All three sources contribute to the final config."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "tts:\n  voice: alloy\n  speed: 1.2\nstory:\n  target_duration_minutes: 45\n"
        )
        config = load_config(
            config_path=yaml_file,
            cli_overrides={"tts.voice": "echo", "pipeline.autonomous": True},
        )
        # CLI wins for tts.voice
        assert config.tts.voice == "echo"
        # YAML wins for tts.speed (not overridden by CLI)
        assert config.tts.speed == 1.2
        # YAML wins for story.target_duration_minutes (not overridden by CLI)
        assert config.story.target_duration_minutes == 45
        # CLI sets pipeline.autonomous
        assert config.pipeline.autonomous is True
        # Pydantic default for video.fps (not in YAML or CLI)
        assert config.video.fps == 30


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestLoadConfigErrors:
    """Error cases for load_config."""

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_config(config_path=Path("/tmp/nonexistent/config.yaml"))

    def test_invalid_yaml_raises_value_error(self, tmp_path):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("invalid: yaml: content: [unbalanced")
        with pytest.raises(ValueError, match="[Ii]nvalid YAML"):
            load_config(config_path=yaml_file)

    def test_invalid_yaml_includes_path_in_error(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("{{{{not yaml")
        with pytest.raises(ValueError, match=str(yaml_file)):
            load_config(config_path=yaml_file)

    def test_invalid_config_values_raise_validation_error(self, tmp_path):
        """Pydantic rejects invalid values (e.g., negative FPS)."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("video:\n  fps: -1\n")
        with pytest.raises(ValidationError):
            load_config(config_path=yaml_file)

    def test_invalid_cli_override_raises_validation_error(self):
        """Pydantic rejects invalid CLI override values."""
        with pytest.raises(ValidationError):
            load_config(cli_overrides={"video.fps": -1})

    def test_yaml_not_a_dict_raises_value_error(self, tmp_path):
        """YAML that parses to a non-dict (e.g., a list) is invalid."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="[Mm]apping|[Dd]ict"):
            load_config(config_path=yaml_file)

    def test_dotted_override_on_non_dict_intermediate_raises(self, tmp_path):
        """Dotted override where an intermediate key is not a dict raises ValueError."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("tts: some_string\n")
        with pytest.raises(ValueError, match="Cannot apply override.*'tts'.*not a mapping"):
            load_config(config_path=yaml_file, cli_overrides={"tts.voice": "alloy"})


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestLoadConfigDeterminism:
    """load_config is deterministic — same inputs produce same outputs."""

    def test_repeated_calls_give_same_result(self, tmp_path):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("tts:\n  voice: alloy\n")
        config1 = load_config(config_path=yaml_file)
        config2 = load_config(config_path=yaml_file)
        assert config1 == config2

    def test_defaults_only_is_deterministic(self):
        config1 = load_config()
        config2 = load_config()
        assert config1 == config2

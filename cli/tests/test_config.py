"""Tests for configuration loading and validation."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from myurly.config import Config, ConfigError


def test_valid_config_is_loaded(config: Config) -> None:
    """A valid configuration file is loaded and exposed through the properties."""
    assert config.database_host == "127.0.0.1"
    assert config.database_port == 27017
    assert config.short_url_domain == "myur.ly"
    assert config.short_url_length == 6
    assert config.renew_expiration_on_new_minify is False


def test_repr_hides_password(config: Config) -> None:
    """The password is not shown in the string representation of the configuration."""
    assert "secret" not in repr(config)


def test_missing_file_raises(tmp_path: Path) -> None:
    """A missing configuration file raises ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        Config(tmp_path / "missing.json")


def test_invalid_json_raises(tmp_path: Path) -> None:
    """A configuration file that is not valid JSON raises ConfigError."""
    path = tmp_path / "config.json"
    path.write_text("{not json")
    with pytest.raises(ConfigError, match="not valid JSON"):
        Config(path)


@pytest.mark.parametrize(
    "section, key, value",
    [
        ("app", "short_url_length", 3),  # below minimum
        ("app", "short_url_expiration_seconds", 0),  # below minimum
        ("database", "port", "27017"),  # wrong type
        ("app", "unknown_option", True),  # additional property
    ],
)
def test_schema_violation_raises(
    config_dict: dict, write_config: Callable[[dict], Path], section: str, key: str, value: Any
) -> None:
    """A configuration that does not conform to the JSON schema raises ConfigError."""
    config_dict[section][key] = value
    with pytest.raises(ConfigError, match="Invalid configuration"):
        Config(write_config(config_dict))


def test_missing_required_key_raises(config_dict: dict, write_config: Callable[[dict], Path]) -> None:
    """A configuration missing a required key raises ConfigError."""
    del config_dict["app"]["short_url_domain"]
    with pytest.raises(ConfigError, match="Invalid configuration"):
        Config(write_config(config_dict))

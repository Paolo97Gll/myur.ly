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


@pytest.mark.parametrize(
    "domain",
    [
        "https://myur.ly",  # scheme included
        "myur.ly/",  # trailing slash
        "myur.ly:8080",  # port included
        "localhost",  # not a domain name
        "192.168.1.1",  # IP address
        "-invalid.com",  # label starting with a hyphen
        "",  # empty
    ],
)
def test_invalid_short_url_domain_raises(config_dict: dict, write_config: Callable[[dict], Path], domain: str) -> None:
    """A short URL domain that is not a valid domain name raises ConfigError."""
    config_dict["app"]["short_url_domain"] = domain
    with pytest.raises(ConfigError, match="not a valid domain"):
        Config(write_config(config_dict))


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1:27017",  # port included
        "mongodb://mongo",  # URI instead of host
        "bad host",  # space
        "999.1.1.1",  # invalid IPv4 address
        "-invalid",  # label starting with a hyphen
        "",  # empty
    ],
)
def test_invalid_database_host_raises(config_dict: dict, write_config: Callable[[dict], Path], host: str) -> None:
    """A database host that is not a valid hostname or IP address raises ConfigError."""
    config_dict["database"]["host"] = host
    with pytest.raises(ConfigError, match="not a valid host"):
        Config(write_config(config_dict))


@pytest.mark.parametrize("host", ["localhost", "mongo-db", "db.example.com", "10.0.0.5", "::1"])
def test_valid_database_host_is_accepted(config_dict: dict, write_config: Callable[[dict], Path], host: str) -> None:
    """Hostnames, service names and IP addresses are accepted as database host."""
    config_dict["database"]["host"] = host
    assert Config(write_config(config_dict)).database_host == host

"""Application configuration, loaded from a JSON file and validated against a JSON schema."""

import json
import logging
from copy import deepcopy
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).parent / "config.schema.json"


class ConfigError(Exception):
    """Custom exception for configuration errors."""


class Config:
    """Configuration class for the application."""

    def __init__(self, config_path: Path):
        """Initializes the Config class by loading and validating the configuration from a JSON file.

        Parameters
        ----------
        config_path : Path
            Path to the JSON configuration file.
        """
        self.__logger = logging.getLogger(__name__)
        self.__config = self.__load_config(Path(config_path))

    def __repr__(self) -> str:
        local_config = deepcopy(self.__config)
        local_config["database"]["password"] = "****"
        return f"Config({local_config})"

    @property
    def database_host(self) -> str:
        """Returns the MongoDB host from the configuration."""
        return self.__config["database"]["host"]

    @property
    def database_port(self) -> int:
        """Returns the MongoDB port from the configuration."""
        return self.__config["database"]["port"]

    @property
    def database_username(self) -> str:
        """Returns the MongoDB username from the configuration."""
        return self.__config["database"]["username"]

    @property
    def database_password(self) -> str:
        """Returns the MongoDB password from the configuration."""
        return self.__config["database"]["password"]

    @property
    def database_name(self) -> str:
        """Returns the MongoDB database name from the configuration."""
        return self.__config["database"]["database_name"]

    @property
    def collection_name(self) -> str:
        """Returns the MongoDB collection name from the configuration."""
        return self.__config["database"]["collection_name"]

    @property
    def db_timeout_seconds(self) -> int:
        """Returns the timeout for database operations from the configuration."""
        return self.__config["app"]["db_timeout_seconds"]

    @property
    def short_url_domain(self) -> str:
        """Returns the domain for shortened URLs from the configuration."""
        return self.__config["app"]["short_url_domain"]

    @property
    def short_url_length(self) -> int:
        """Returns the length of the shortened URL path from the configuration."""
        return self.__config["app"]["short_url_length"]

    @property
    def short_url_expiration_seconds(self) -> int:
        """Returns the expiration time for shortened URLs in seconds from the configuration."""
        return self.__config["app"]["short_url_expiration_seconds"]

    @property
    def max_generation_attempts(self) -> int:
        """Returns the maximum number of attempts to generate a unique short URL."""
        return self.__config["app"]["max_generation_attempts"]

    @property
    def renew_expiration_on_new_minify(self) -> bool:
        """Returns whether to renew the expiration time for an existing shortened URL when it is minified again."""
        return self.__config["app"]["renew_expiration_on_new_minify"]

    def __load_config(self, config_path: Path) -> dict:
        """Loads the configuration from the JSON file and validates it against the JSON schema.

        Parameters
        ----------
        config_path : Path
            Path to the JSON configuration file.

        Returns
        -------
        config : dict
            The validated configuration, as parsed from the JSON file.

        Raises
        ------
        ConfigError
            If the config file is not found, is not valid JSON, or does not conform to
            the configuration JSON schema.
        """
        # load configuration from JSON file
        try:
            self.__logger.debug("Reading configuration from %s", config_path)
            with config_path.open() as f:
                config = json.load(f)
        except FileNotFoundError as e:
            raise ConfigError(f"Config file {config_path} not found") from e
        except OSError as e:
            raise ConfigError(f"Error reading config file {config_path}") from e
        except json.JSONDecodeError as e:
            raise ConfigError(f"Config file {config_path} is not valid JSON") from e
        self.__logger.debug("Configuration read successfully")
        # validate configuration against JSON schema
        try:
            self.__logger.debug("Reading schema from %s", _SCHEMA_PATH)
            with _SCHEMA_PATH.open() as f:
                schema = json.load(f)
            self.__logger.debug("Schema read successfully")
            self.__logger.debug("Validating configuration against schema")
            jsonschema.validate(instance=config, schema=schema)
        except jsonschema.ValidationError as e:
            raise ConfigError(
                f"Invalid configuration in {config_path}: {e.message} (at {'.'.join(map(str, e.path))})"
            ) from e
        self.__logger.debug("Configuration successfully loaded")
        return config

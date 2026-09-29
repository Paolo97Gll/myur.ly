"""Shared fixtures for the myur.ly test suite."""

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Final

import mongomock
import pytest
from myurly.config import Config
from myurly.url_handler import UrlHandler

BASE_CONFIG: Final[dict[str, dict[str, Any]]] = {
    "database": {
        "host": "127.0.0.1",
        "port": 27017,
        "username": "user",
        "password": "secret",
        "database_name": "myurly",
        "collection_name": "urls",
    },
    "app": {
        "db_timeout_seconds": 3,
        "short_url_domain": "myur.ly",
        "short_url_length": 6,
        "short_url_expiration_seconds": 30,
        "max_generation_attempts": 3,
        "renew_expiration_on_new_minify": False,
    },
}


@pytest.fixture
def config_dict() -> dict:
    """A valid configuration dictionary, safe to modify in each test."""
    return deepcopy(BASE_CONFIG)


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[[dict], Path]:
    """Provide a function that writes a configuration dictionary to a temporary JSON file."""

    def _write(data: dict) -> Path:
        """Write the configuration to a temporary JSON file.

        Parameters
        ----------
        data : dict
            The configuration to write.

        Returns
        -------
        path : Path
            Path to the written JSON file.
        """
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data))
        return path

    return _write


@pytest.fixture
def config(config_dict: dict, write_config: Callable[[dict], Path]) -> Config:
    """A Config object loaded from the valid configuration."""
    return Config(write_config(config_dict))


@pytest.fixture
def mongo_client() -> mongomock.MongoClient:
    """An in-memory MongoDB client, returning timezone-aware datetimes like the real one."""
    return mongomock.MongoClient(tz_aware=True)


@pytest.fixture
def collection(mongo_client: mongomock.MongoClient) -> mongomock.Collection:
    """In-memory collection with the same indexes created by database/mongo-init.js."""
    coll = mongo_client[BASE_CONFIG["database"]["database_name"]][BASE_CONFIG["database"]["collection_name"]]
    coll.create_index("original_url", unique=True)
    coll.create_index("shortened_path", unique=True)
    return coll


@pytest.fixture
def handler(collection: mongomock.Collection, config: Config) -> UrlHandler:
    """A UrlHandler backed by the in-memory collection."""
    return UrlHandler(collection, config)

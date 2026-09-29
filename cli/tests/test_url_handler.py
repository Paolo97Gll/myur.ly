"""Tests for URL minification and expansion."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import mongomock
import pytest
from myurly.config import Config
from myurly.url_handler import (
    CHARACTERS,
    ExpandError,
    MinifyError,
    NonExistingOrExpiredError,
    UrlHandler,
)
from pymongo.errors import DuplicateKeyError

URL = "https://www.example.com/path?q=search"
PREFIX = "https://myur.ly/"


def expire(collection: mongomock.Collection, original_url: str) -> None:
    """Move the expiration of an entry into the past, simulating the passing of time.

    Parameters
    ----------
    collection : mongomock.Collection
        The collection containing the entry.
    original_url : str
        The original URL of the entry to expire.
    """
    collection.update_one(
        {"original_url": original_url},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )


def duplicate_key_error(field: str) -> DuplicateKeyError:
    """Build a DuplicateKeyError as raised by MongoDB for a unique index violation.

    Parameters
    ----------
    field : str
        The field of the violated unique index.

    Returns
    -------
    error : DuplicateKeyError
        The duplicate key error, with the keyPattern details.
    """
    return DuplicateKeyError("E11000 duplicate key error", 11000, {"keyPattern": {field: 1}})


# mongomock does not fill DuplicateKeyError.details, so the duplicate key cases use a mocked collection.
@pytest.fixture
def mock_collection() -> MagicMock:
    """A mocked collection where no existing entry is found."""
    coll = MagicMock()
    coll.find_one.return_value = None
    return coll


#########
# minify


def test_minify_returns_short_url(handler: UrlHandler) -> None:
    """The short URL has the configured domain, length and character set."""
    short_url = handler.minify_url(URL)
    path = short_url.removeprefix(PREFIX)
    assert short_url.startswith(PREFIX)
    assert len(path) == 6
    assert all(c in CHARACTERS for c in path)


def test_minify_is_idempotent(handler: UrlHandler, collection: mongomock.Collection) -> None:
    """Minifying the same URL twice returns the same short URL and stores a single entry."""
    assert handler.minify_url(URL) == handler.minify_url(URL)
    assert collection.count_documents({}) == 1


def test_minify_different_urls_give_different_short_urls(handler: UrlHandler) -> None:
    """Different original URLs get different short URLs."""
    assert handler.minify_url(URL) != handler.minify_url("https://www.example.com/other")


def test_minify_rejects_short_url(handler: UrlHandler) -> None:
    """A URL that is already a short URL cannot be minified."""
    short_url = handler.minify_url(URL)
    with pytest.raises(MinifyError):
        handler.minify_url(short_url)


def test_minify_after_expiration_creates_new_short_url(handler: UrlHandler, collection: mongomock.Collection) -> None:
    """An expired original URL can be minified again, replacing the expired entry."""
    old_short_url = handler.minify_url(URL)
    expire(collection, URL)
    new_short_url = handler.minify_url(URL)
    assert handler.expand_url(new_short_url) == URL
    assert collection.count_documents({}) == 1
    # the old short URL is no longer valid (unless the new one got the same random path by chance)
    if new_short_url != old_short_url:
        with pytest.raises(NonExistingOrExpiredError):
            handler.expand_url(old_short_url)


@pytest.mark.parametrize("renew", [False, True])
def test_minify_renew_expiration(
    config_dict: dict, write_config: Callable[[dict], Path], collection: mongomock.Collection, renew: bool
) -> None:
    """Minifying an existing URL renews its expiration only if renew_expiration_on_new_minify is set."""
    config_dict["app"]["renew_expiration_on_new_minify"] = renew
    handler = UrlHandler(collection, Config(write_config(config_dict)))
    handler.minify_url(URL)
    # set a known, still valid, expiration (BSON dates have millisecond precision, too coarse to compare two calls)
    soon = datetime.now(timezone.utc) + timedelta(seconds=5)
    collection.update_one({"original_url": URL}, {"$set": {"expires_at": soon}})
    handler.minify_url(URL)
    new_expiration = collection.find_one({"original_url": URL})["expires_at"]  # type: ignore[index]
    assert (new_expiration > soon) is renew


def test_minify_retries_on_short_path_collision(mock_collection: MagicMock, config: Config) -> None:
    """A collision on the shortened path is retried with a new path."""
    mock_collection.find_one_and_update.side_effect = [
        duplicate_key_error("shortened_path"),
        {"shortened_path": "xyz123"},
    ]
    assert UrlHandler(mock_collection, config).minify_url(URL) == PREFIX + "xyz123"
    assert mock_collection.find_one_and_update.call_count == 2


def test_minify_gives_up_after_max_attempts(mock_collection: MagicMock, config: Config) -> None:
    """After max_generation_attempts collisions, minify raises MinifyError."""
    mock_collection.find_one_and_update.side_effect = duplicate_key_error("shortened_path")
    with pytest.raises(MinifyError, match="Too many attempts"):
        UrlHandler(mock_collection, config).minify_url(URL)
    assert mock_collection.find_one_and_update.call_count == config.max_generation_attempts


def test_minify_concurrent_insert_returns_existing(mock_collection: MagicMock, config: Config) -> None:
    """If another process inserts the same original URL concurrently, its short URL is returned."""
    # another process inserted the same original URL between our lookup and our upsert
    mock_collection.find_one.side_effect = [None, {"shortened_path": "abc123"}]
    mock_collection.find_one_and_update.side_effect = duplicate_key_error("original_url")
    assert UrlHandler(mock_collection, config).minify_url(URL) == PREFIX + "abc123"


#########
# expand


def test_expand_returns_original_url(handler: UrlHandler) -> None:
    """Expanding a short URL returns the original URL."""
    assert handler.expand_url(handler.minify_url(URL)) == URL


def test_expand_non_existing_raises(handler: UrlHandler) -> None:
    """Expanding a short URL that was never generated raises NonExistingOrExpiredError."""
    with pytest.raises(NonExistingOrExpiredError):
        handler.expand_url(PREFIX + "abcdef")


def test_expand_expired_raises(handler: UrlHandler, collection: mongomock.Collection) -> None:
    """Expanding an expired short URL raises NonExistingOrExpiredError."""
    short_url = handler.minify_url(URL)
    expire(collection, URL)
    with pytest.raises(NonExistingOrExpiredError):
        handler.expand_url(short_url)


def test_expand_wrong_domain_raises(handler: UrlHandler) -> None:
    """Expanding a URL outside the short URL domain raises ExpandError, not NonExistingOrExpiredError."""
    with pytest.raises(ExpandError) as exc_info:
        handler.expand_url("https://other.com/abcdef")
    assert not isinstance(exc_info.value, NonExistingOrExpiredError)

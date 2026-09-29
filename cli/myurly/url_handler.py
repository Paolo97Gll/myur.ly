"""URL shortening and expansion, backed by a MongoDB collection."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from string import ascii_letters, digits
from typing import Final
from urllib.parse import urlparse

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config import Config

CHARACTERS: Final = ascii_letters + digits


class UrlHandlerError(Exception):
    """Base class for exceptions in the UrlHandler."""


class MinifyError(UrlHandlerError):
    """Custom exception for errors that occur during the URL minification process."""


class ExpandError(UrlHandlerError):
    """Custom exception for errors that occur during the URL expansion process."""


class NonExistingOrExpiredError(ExpandError):
    """Custom exception for errors that occur when trying to expand a non-existing or expired shortened URL."""


class UrlHandler:
    """A class for handling URL shortening and expansion."""

    def __init__(self, urls_collection: Collection, config: Config):
        """Initialize the UrlHandler.

        Parameters
        ----------
        urls_collection : Collection
            The MongoDB collection to store URL mappings.
        config : Config
            The configuration object.
        """
        self.__urls_collection = urls_collection
        self.__config = config
        self.__shortened_url_prefix = f"https://{self.__config.short_url_domain}/"
        self.__logger = logging.getLogger(__name__)

    def minify_url(self, original_url: str) -> str:
        """Minify a URL by creating a shortened version. This method checks if the original URL already
        exists in the database and, if required, renews its expiration. If it does not exist, it generates
        a new shortened path and stores it in the database.

        Parameters
        ----------
        original_url : str
            The original URL to be minified.

        Returns
        -------
        shortened_url : str
            The shortened URL.
        """
        return self.__shortened_url_from_shortened_path(self.__minify_url(original_url))

    def __minify_url(self, original_url: str) -> str:
        """Minify a URL by creating a shortened version. This version of the method returns only the
        shortened path, not the full shortened URL.

        Parameters
        ----------
        original_url : str
            The original URL to be minified.

        Returns
        -------
        shortened_path : str
            The shortened path.

        Raises
        ------
        MinifyError
            If an error occurs during the URL minification process.
        """
        self.__logger.debug("Minifying URL: %s", original_url)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.__config.short_url_expiration_seconds)
        # check if the original URL is not a minified URL
        if original_url.startswith(self.__shortened_url_prefix):
            raise MinifyError("Cannot minify a URL that is already a shortened URL.")
        # check if the URL already exists in the database and, if required, renew its expiration
        self.__logger.debug("Checking if URL already exists in the database: %s", original_url)
        if self.__config.renew_expiration_on_new_minify:
            existing_entry = self.__urls_collection.find_one_and_update(
                {"original_url": original_url, "expires_at": {"$gte": now}},
                {"$set": {"expires_at": expires_at}},
                return_document=ReturnDocument.AFTER,
            )
        else:
            existing_entry = self.__urls_collection.find_one(
                {"original_url": original_url, "expires_at": {"$gte": now}},
            )
        if existing_entry:
            self.__logger.debug(
                "URL already exists in the database, returning existing shortened path: %s",
                existing_entry["shortened_path"],
            )
            return existing_entry["shortened_path"]
        self.__logger.debug("URL does not exist in the database, generating a new shortened path.")
        # generate a new shortened URL and store it in the database
        for _ in range(self.__config.max_generation_attempts):
            shortened_path = self.__generate_shortened_path()
            try:
                # insert the new URL mapping into the database, or update the existing one if it has expired
                self.__logger.debug(
                    "Attempting to insert new URL mapping into the database: %s -> %s", original_url, shortened_path
                )
                new_entry = self.__urls_collection.find_one_and_update(
                    {"original_url": original_url, "expires_at": {"$lt": now}},
                    {
                        "$set": {
                            "original_url": original_url,
                            "shortened_path": shortened_path,
                            "expires_at": expires_at,
                        }
                    },
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                return new_entry["shortened_path"]  # type: ignore[index]
            except DuplicateKeyError as e:
                if e.details and "keyPattern" in e.details:
                    if "original_url" in e.details["keyPattern"]:
                        # if the duplicate key error is due to original_url, return the existing shortened_path
                        self.__logger.debug(
                            "Duplicate key error due to original_url, probably another user has already created a shortened URL for this original URL."
                        )
                        existing_entry = self.__urls_collection.find_one(
                            {"original_url": original_url, "expires_at": {"$gte": now}}
                        )
                        if existing_entry:
                            self.__logger.debug(
                                "Returning existing shortened path for original URL: %s",
                                existing_entry["shortened_path"],
                            )
                            return existing_entry["shortened_path"]
                    else:
                        # if the duplicate key error is due to the shortened_path, try again with a new shortened_path
                        self.__logger.debug(
                            "Duplicate key error due to shortened_path, trying again with a new shortened path."
                        )
                else:
                    raise MinifyError("Unexpected duplicate key error while minifying URL") from e
        raise MinifyError("Too many attempts to generate a unique shortened URL.")

    def expand_url(self, shortened_url: str) -> str:
        """Expand a shortened URL to retrieve the original URL. This method checks if the shortened URL exists
        in the database and is not expired. If it exists, it returns the original URL; otherwise, it raises a
        NonExistingOrExpiredError.

        Parameters
        ----------
        shortened_url : str
            The shortened URL to expand.

        Returns
        -------
        original_url : str
            The original URL.

        Raises
        ------
        ExpandError
            If the shortened URL is malformed.
        NonExistingOrExpiredError
            If the shortened URL does not exist or is expired.
        """
        self.__logger.debug("Expanding URL: %s", shortened_url)
        now = datetime.now(timezone.utc)
        # retrieve the original URL from the database, if it exists and is not expired
        self.__logger.debug("Retrieving original URL from the database for shortened URL: %s", shortened_url)
        try:
            shortened_path = self.__shortened_path_from_shortened_url(shortened_url)
        except ValueError as e:
            raise ExpandError("Error occurred while expanding URL") from e
        existing_entry = self.__urls_collection.find_one(
            {"shortened_path": shortened_path, "expires_at": {"$gte": now}}
        )
        if existing_entry:
            self.__logger.debug(
                "Found existing entry for shortened URL, returning original URL: %s", existing_entry["original_url"]
            )
            return existing_entry["original_url"]
        raise NonExistingOrExpiredError("Shortened URL not found or expired.")

    def __generate_shortened_path(self) -> str:
        """Generate a random shortened path.

        Returns
        -------
        shortened_path : str
            The generated shortened path.
        """
        return "".join(secrets.choice(CHARACTERS) for _ in range(self.__config.short_url_length))

    def __shortened_path_from_shortened_url(self, shortened_url: str) -> str:
        """Get the shortened path from the full shortened URL.

        Parameters
        ----------
        shortened_url : str
            The full shortened URL from which to extract the shortened path.

        Returns
        -------
        shortened_path : str
            The shortened path extracted from the full shortened URL.

        Raises
        ------
        ValueError
            If the shortened URL does not start with the expected prefix, indicating an invalid format.
        """
        if not shortened_url.startswith(self.__shortened_url_prefix):
            raise ValueError("Invalid shortened URL format, does not match expected prefix.")
        return shortened_url[len(self.__shortened_url_prefix) :]

    def __shortened_url_from_shortened_path(self, shortened_path: str) -> str:
        """Generate the full shortened URL from the shortened path, by concatenating the domain
        prefix and the shortened path.

        Parameters
        ----------
        shortened_path : str
            The shortened path to be appended to the domain prefix. Generate it using the
            `__generate_shortened_path` method.

        Returns
        -------
        shortened_url : str
            The full shortened URL.
        """
        return f"{self.__shortened_url_prefix}{shortened_path}"

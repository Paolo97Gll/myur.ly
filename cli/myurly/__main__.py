"""Command-line entry point for the myur.ly URL shortener."""

import argparse
import logging
import sys
from pathlib import Path

import validators
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .config import Config, ConfigError
from .url_handler import (
    ExpandError,
    MinifyError,
    NonExistingOrExpiredError,
    UrlHandler,
)


def parse_args() -> argparse.Namespace:
    """Parse and validate the command line arguments."""

    def url_check(url: str) -> str:
        """Check that the URL is a valid http(s) URL."""
        if validators.url(
            url,
            validate_scheme=lambda scheme: scheme.lower() in ("http", "https"),
            strict_query=False,
        ):
            return url
        raise argparse.ArgumentTypeError(f"Invalid URL: {url}")

    parser = argparse.ArgumentParser(description="myur.ly - A simple URL shortener")
    parser.add_argument(
        "--config", default="./config.json", type=Path, help="path to the configuration file (default: ./config.json)"
    )
    parser.add_argument("--debug", action="store_true", help="enable debug mode")
    parser.add_argument(
        "--debug-db", action="store_true", help="enable debug mode for pymongo, only effective if --debug is also set"
    )
    parser_options = parser.add_mutually_exclusive_group(required=True)
    parser_options.add_argument("--minify", type=url_check, help="URL to minify")
    parser_options.add_argument("--expand", type=url_check, help="URL to expand")
    args = parser.parse_args()
    return args


def main(args: argparse.Namespace) -> int:
    """Run the minify or expand command requested in args.

    Returns
    -------
    exit_code : int
        0 on success, 1 if the shortened URL does not exist or is expired, 3 on any other error.
    """
    logger = logging.getLogger(__name__)

    # load configuration and validate it
    try:
        logger.debug("Loading configuration")
        config = Config(args.config)
        logger.debug("Configuration loaded successfully: %s", config)
    except ConfigError as e:
        logger.error("Config loading failed: %s", e, exc_info=args.debug)
        return 3
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=args.debug)
        return 3

    # start mongodb client
    logger.debug("Connecting to MongoDB")
    try:
        with MongoClient(
            host=config.database_host,
            port=config.database_port,
            username=config.database_username,
            password=config.database_password,
            authSource=config.database_name,
            timeoutMS=config.db_timeout_seconds * 1000,
            tz_aware=True,
        ) as client:

            # check if the connection to MongoDB is ok and get collection
            client.admin.command("ping")
            urls_collection = client[config.database_name][config.collection_name]
            logger.debug(
                "Connected to MongoDB, using db %s and collection %s", config.database_name, config.collection_name
            )

            url_handler = UrlHandler(urls_collection, config)
            # minify url
            if args.minify is not None:
                logger.debug("Minifying URL: %s", args.minify)
                shortened_url = url_handler.minify_url(args.minify)
                print(shortened_url)
            # expand url
            else:
                logger.debug("Expanding URL: %s", args.expand)
                original_url = url_handler.expand_url(args.expand)
                print(original_url)

    except NonExistingOrExpiredError as e:
        logger.error(e)
        return 1
    except MinifyError as e:
        logger.error("Cannot minify URL: %s", e, exc_info=args.debug)
        return 3
    except ExpandError as e:
        logger.error("Cannot expand URL: %s", e, exc_info=args.debug)
        return 3
    except PyMongoError as e:
        logger.error("Database error: %s", e, exc_info=args.debug)
        return 3
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=args.debug)
        return 3

    return 0


def cli() -> None:
    """Console script entry point: parse the arguments, configure logging and run main()."""
    args = parse_args()

    # configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format=(
            "[%(asctime)s] (%(levelname)s) %(module)s - %(funcName)s: %(message)s"
            if args.debug
            else "[%(levelname)s] %(message)s"
        ),
    )
    logging.getLogger("pymongo").setLevel(logging.DEBUG if args.debug_db else logging.WARNING)

    # run main function and exit with the returned code
    sys.exit(main(args))


if __name__ == "__main__":
    cli()

"""Tests for the command-line entry point."""

import argparse
from collections.abc import Callable
from pathlib import Path

import mongomock
import pytest
from myurly import __main__ as cli
from pymongo.errors import ServerSelectionTimeoutError

URL = "https://www.example.com/path?q=search"


def make_args(config_path: Path, minify: str | None = None, expand: str | None = None) -> argparse.Namespace:
    """Build the arguments for main() as parse_args() would return them.

    Parameters
    ----------
    config_path : Path
        Path to the JSON configuration file.
    minify : str | None
        URL to minify, if any.
    expand : str | None
        URL to expand, if any.

    Returns
    -------
    args : argparse.Namespace
        The command line arguments.
    """
    return argparse.Namespace(config=config_path, debug=False, debug_db=False, minify=minify, expand=expand)


@pytest.fixture
def config_path(config_dict: dict, write_config: Callable[[dict], Path]) -> Path:
    """Path to a valid configuration file."""
    return write_config(config_dict)


@pytest.fixture(autouse=True)
def fake_mongo(monkeypatch: pytest.MonkeyPatch, mongo_client: mongomock.MongoClient) -> None:
    """Make main() use the in-memory mongomock client instead of a real MongoDB server."""

    def fake_client(**kwargs) -> mongomock.MongoClient:
        """Ignore the connection parameters and return the in-memory client."""
        return mongo_client

    monkeypatch.setattr(cli, "MongoClient", fake_client)


###################
# argument parsing


@pytest.mark.parametrize("option", ["--minify", "--expand"])
def test_parse_args_accepts_valid_url(monkeypatch: pytest.MonkeyPatch, option: str) -> None:
    """A valid URL is accepted by both --minify and --expand."""
    monkeypatch.setattr("sys.argv", ["myurly", f"{option}={URL}"])
    args = cli.parse_args()
    assert getattr(args, option.lstrip("-")) == URL


@pytest.mark.parametrize(
    "argv",
    [
        [],  # no command
        ["--minify=not-a-url"],  # malformed URL
        ["--minify=ftp://example.com/file"],  # unsupported scheme
        [f"--minify={URL}", f"--expand={URL}"],  # mutually exclusive options
    ],
)
def test_parse_args_rejects_invalid_input(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    """Invalid command line arguments make argparse exit with code 2."""
    monkeypatch.setattr("sys.argv", ["myurly", *argv])
    with pytest.raises(SystemExit) as exc_info:
        cli.parse_args()
    assert exc_info.value.code == 2


#######
# main


def test_main_minify_then_expand(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Minify prints a short URL, and expanding it prints the original URL, both with exit code 0."""
    assert cli.main(make_args(config_path, minify=URL)) == 0
    short_url = capsys.readouterr().out.strip()
    assert short_url.startswith("https://myur.ly/")

    assert cli.main(make_args(config_path, expand=short_url)) == 0
    assert capsys.readouterr().out.strip() == URL


def test_main_expand_non_existing_returns_1(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Expanding a non-existing short URL prints nothing and returns exit code 1."""
    assert cli.main(make_args(config_path, expand="https://myur.ly/abcdef")) == 1
    assert capsys.readouterr().out == ""


def test_main_expand_wrong_domain_returns_3(config_path: Path) -> None:
    """Expanding a URL outside the short URL domain returns exit code 3."""
    assert cli.main(make_args(config_path, expand="https://other.com/abcdef")) == 3


def test_main_invalid_config_returns_3(tmp_path: Path) -> None:
    """A missing configuration file returns exit code 3."""
    assert cli.main(make_args(tmp_path / "missing.json", minify=URL)) == 3


def test_main_database_error_returns_3(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable database returns exit code 3."""

    def unreachable(**kwargs) -> mongomock.MongoClient:
        """Simulate a MongoDB server that cannot be reached."""
        raise ServerSelectionTimeoutError("no server")

    monkeypatch.setattr(cli, "MongoClient", unreachable)
    assert cli.main(make_args(config_path, minify=URL)) == 3

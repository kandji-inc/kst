import contextlib
import getpass
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Generator
from importlib.resources import as_file, files
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from kst import git
from kst.api import ApiConfig


# --- Pytest Modifications ---
def pytest_addoption(parser):
    # Add the --run-live option to the pytest command line
    parser.addoption("--run-live", action="store_true", default=False, help="run live tests")


def pytest_collection_modifyitems(config, items):
    # Skip live tests unless the --run-live option is given
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="use --run-live option to run live test")
    for item in items:
        if "allow_http" in item.keywords:
            item.add_marker(skip_live)


def pytest_report_header(config, start_path) -> str:
    """Add the basetemp directory to the report header."""
    return f"basetemp: {tempfile.gettempdir()}/pytest-of-{getpass.getuser()}"


# --- Auto-Use Fixtures ---
@pytest.fixture(autouse=True)
def no_http_requests(monkeypatch, request, response_factory):
    """Disable http requests in tests."""

    if "allow_http" not in request.keywords:

        def urlopen_mock(*args, **kwargs):
            raise RuntimeError("No HTTP requests allowed in unit tests.")

        def fake_get_ping(url, *args, **kwargs) -> requests.Response:
            if url.endswith("/app/v1/ping"):
                return response_factory(200, b'"pong"')
            return requests.get(url, *args, **kwargs)

        monkeypatch.setattr("urllib3.connectionpool.HTTPConnectionPool.urlopen", urlopen_mock)
        monkeypatch.setattr("requests.get", fake_get_ping)
    else:

        class TestSession(requests.sessions.Session):
            """Adds a source=kst-test param to all requests."""

            def prepare_request(self, request):
                request.params |= {"source": "kst-test"}
                request = super().prepare_request(request)
                return request

        # If the test allows http requests, use a fake session that adds a source=kst-test param to all requests
        monkeypatch.setattr("requests.sessions.Session", TestSession)
        monkeypatch.setattr("requests.Session", TestSession)


@pytest.fixture(autouse=True)
def git_locate_git_cache_clear():
    """Clear the cache before each test."""
    git.locate_git.cache_clear()


@pytest.fixture(autouse=True)
def git_locate_root_cache_clear():
    """Clear the cache before each test."""
    git.locate_root.cache_clear()


@pytest.fixture(autouse=True)
def tmp_path_cd(tmp_path: Path):
    """Change working directory to a temporary directory and return the path."""
    with contextlib.chdir(tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True, scope="session")
def load_env(request: pytest.FixtureRequest, response_factory):
    """Load KST environment variables."""

    if request.config.getoption("--run-live"):
        # override ensures that the environment variables are loaded even if they are already set
        load_dotenv(override=True)
        if "KST_TENANT" not in os.environ or "KST_TOKEN" not in os.environ:
            raise OSError("Missing required environment variables.")
        yield
    else:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("KST_TENANT", "https://xxxxxxxx.api.kandji.io")
            mp.setenv("KST_TOKEN", "00000000-0000-0000-0000-000000000000")
            yield


# --- General Use Fixtures ---
@pytest.fixture
def resources():
    """Return the path to the resources directory"""
    with as_file(files("tests.resources")) as resources_dir:
        yield resources_dir


@pytest.fixture(scope="session")
def config(load_env) -> ApiConfig:
    """Return an ApiConfig object populated with environment variables."""
    return ApiConfig(tenant_url=os.environ["KST_TENANT"], api_token=os.environ["KST_TOKEN"])


@pytest.fixture
def git_repo(tmp_path: Path):
    """Initialize a git repository in a temporary directory and return the path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", repo, "init"], check=True, capture_output=True)
    return repo


@pytest.fixture
def git_remote(tmp_path, git_repo: Path):
    """Initialize a git repository with a remote in a temporary directory and return the repo path."""
    repo = git_repo
    remote = tmp_path / "remote"
    subprocess.run(
        ["git", "-C", repo, "commit", "--allow-empty", "-m", "Initial commit"], check=True, capture_output=True
    )

    remote.mkdir()
    subprocess.run(["git", "-C", remote, "init", "--bare"], check=True, capture_output=True)

    subprocess.run(["git", "-C", repo, "remote", "add", "origin", remote], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "push", "-u", "origin", "main"], check=True, capture_output=True)

    return remote


@pytest.fixture
def tmp_path_repo(tmp_path: Path) -> Path:
    """Return a temporary directory for a repository."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".kst").touch()
    (repo_path / "profiles").mkdir()
    (repo_path / "scripts").mkdir()
    subprocess.run(["git", "-C", repo_path, "init"], check=True, capture_output=True)
    return repo_path


@pytest.fixture
def tmp_path_repo_cd(tmp_path_repo: Path) -> Generator[Path]:
    """Change to the repository directory and return the path."""
    with contextlib.chdir(tmp_path_repo):
        yield tmp_path_repo


@pytest.fixture
def file_factory(tmp_path: Path) -> Callable[[Path, str], None]:
    """Return a function that creates a file at a given path in a temp directory with the given content."""

    def create_at_path(path: Path, content: str) -> None:
        path = tmp_path / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as file:
            file.write(content)

    return create_at_path


@pytest.fixture(scope="session")
def response_factory() -> Callable[[int, dict | bytes], requests.Response]:
    """Return a requests.Response object with the given status code and content."""

    def _response(status_code: int, content: dict | bytes) -> requests.Response:
        response = requests.Response()
        response.status_code = status_code
        if isinstance(content, dict) or isinstance(content, list):
            response._content = json.dumps(content).encode("utf-8")
        elif isinstance(content, bytes):
            response._content = content
        else:
            pytest.fail("Invalid response content passed to response_factory.")
        return response

    return _response

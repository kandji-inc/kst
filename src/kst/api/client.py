import io
import json
import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

from kst.console import OutputConsole
from kst.exceptions import ApiClientError

console = OutputConsole(logging.getLogger(__name__))


class ApiConfig(BaseModel):
    """A Container for API configuration values.

    Attributes:
        url (HttpUrl): API URL for the Kandji tenant. Must use the https:// schema.
        api_token (str): API authentication token for the Kandji tenant.

    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(alias="tenant_url")
    api_token: str = Field(repr=False)

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v) -> str:
        """Ensure the url is using https and is a valid Kandji API URL."""
        # Ensure the URL is a string with a https schema

        if isinstance(v, str) and (parsed_url := urlparse(v)).scheme in ("", "http"):
            if parsed_url.netloc == "":
                # handle misclassified netloc: https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlparse
                v = parsed_url._replace(scheme="https", netloc=parsed_url.path, path="").geturl()
            else:
                v = parsed_url._replace(scheme="https").geturl()

        v = v.rstrip("/")  # Normalize without trailing slash

        if not re.fullmatch(r"https://[A-Za-z0-9-]+\.api(\.eu)?\.kandji\.io", v):
            raise ValueError(
                "The Tenant URL must be a valid Kandji API URL. "
                "Please ensure the URL is in the format https://<tenant>.api.kandji.io or https://<tenant>.api.eu.kandji.io."
            )
        return v

    @field_validator("api_token", mode="after")
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Ensure the api_token is a uuid4 string."""
        if not re.fullmatch(r"[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", v):
            raise ValueError(
                "The API token must be a valid UUID4 string. "
                "Please ensure the token is in the format 12345678-1234-5678-1234-123456789012."
            )
        return v


class ApiClient:
    """Basic API client for interacting with the Kandji API.

    The ApiClient class is a thin wrapper around a requests.Session which handles converting
    resource paths to fully resolved API resources. It also manages passing credential's with
    requests.

    Attributes:
        session (requests.Session): The underlying session used by the client.

    Methods:
        request: Make an generic HTTP request
        get: Make a GET HTTP request
        patch: Make a PATCH HTTP request
        post: Make a POST HTTP request
        delete: Make a DELETE HTTP request
        close: Close the internal session object.
    """

    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._update_header()

    @property
    def session(self) -> requests.Session:
        """Get the session object for the client.

        Returns:
            requests.Session: The internal session object

        Raises:
            ApiClientError: Raised when the session is not open.

        """

        if self._session is None:
            raise ApiClientError("No open session available.")

        return self._session

    def close(self) -> None:
        """Close the internal session object."""
        if self._session is not None:
            self.session.close()
            self._session = None

    def _update_header(self):
        """Update the session headers with the API token."""
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self._config.api_token}",
                "Accept": "application/json",
            }
        )

    def _make_url(self, path: str):
        """Convert a relative path to a fully qualified URL."""
        return urljoin(self._config.url, path)

    def request(self, method: str, url: str, *args, **kwargs) -> requests.Response:
        """Make a generic HTTP request.

        Handles logging and ensures the source query parameter is included.

        Returns:
            requests.Response: The response object from the request

        Raises:
            requests.ConnectionError: Raised when the API connection fails
            requests.HTTPError: Raised when the HTTP request returns an unsuccessful status code

        """

        try:
            console.debug(f"Making {method} request to {url}")

            # Add the source=kst param to all requests
            kwargs["params"] = kwargs.get("params", {}) | {"source": "kst"}

            response = self.session.request(method, url, *args, **kwargs)

            console.debug(f"Response status code: {response.status_code}")

            try:
                headers = "\n" + json.dumps(dict(response.headers), indent=2)
            except json.JSONDecodeError:
                headers = response.headers
            console.debug(f"Response headers: {headers}")

            try:
                content = "\n" + json.dumps(response.json(), indent=2)
            except json.JSONDecodeError:
                content = response.text
            console.debug(f"Response content: {content}")

            response.raise_for_status()
        except requests.ConnectionError as error:
            console.error(f"Connection error occurred: {error}")
            raise
        except requests.HTTPError as error:
            console.error(f"HTTP error occurred: {error.response.status_code}")
            console.error(f"Response content: {error.response.text}")
            raise

        return response

    def get(self, path: str) -> requests.Response:
        """Make a GET HTTP request to the resolved API endpoint at path."""
        return self.request("GET", self._make_url(path))

    def patch(
        self,
        path: str,
        data: dict | None = None,
        json: dict | None = None,
        files: list[tuple[str, tuple[str, io.BufferedReader, str]]] | None = None,
    ) -> requests.Response:
        """Make a PATCH HTTP request to the resolved API endpoint at path."""
        return self.request("PATCH", self._make_url(path), data=data, json=json, files=files)

    def post(
        self,
        path: str,
        data: dict | None = None,
        json: dict | None = None,
        files: list[tuple[str, tuple[str, io.BufferedReader, str]]] | None = None,
    ) -> requests.Response:
        """Make a POST HTTP request to the resolved API endpoint at path."""
        return self.request("POST", self._make_url(path), data=data, json=json, files=files)

    def delete(self, path: str) -> requests.Response:
        """Make a DELETE HTTP request to the resolved API endpoint at path."""
        return self.request("DELETE", self._make_url(path))

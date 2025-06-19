import io
import json
import logging

import requests

from kst.console import OutputConsole
from kst.exceptions import ApiClientError

console = OutputConsole(logging.getLogger(__name__))


class S3ApiClient:
    """An API client for interacting with S3 endpoints.

    This client handles file uploads to S3 using presigned URLs and POST data
    provided by the Kandji API for custom app uploads.

    Attributes:
        session (requests.Session): The internal HTTP session object

    """

    def __init__(self):
        self._session = requests.Session()

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

    def request(self, method: str, url: str, *args, **kwargs) -> requests.Response:
        try:
            console.debug(f"Making {method} request to {url}")

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

    def post(
        self, url: str, data: dict, files: list[tuple[str, tuple[str, io.BufferedReader, str]]]
    ) -> requests.Response:
        """Make a POST request with file upload to S3.

        Args:
            url (str): The S3 presigned POST URL
            data (dict): The POST data for S3 upload
            files (list): List of files to upload in the format expected by requests

        Returns:
            requests.Response: The HTTP response from S3

        Raises:
            requests.ConnectionError: Raised when connection to S3 fails
            requests.HTTPError: Raised when the HTTP request returns an unsuccessful status code

        """
        return self.request("POST", url, data=data, files=files)

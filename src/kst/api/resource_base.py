from contextlib import AbstractContextManager
from typing import Protocol, Self, override

from kst.exceptions import ApiClientError

from .client import ApiClient, ApiConfig
from .s3_client import S3ApiClient


class ResourceBase(AbstractContextManager, Protocol):
    """An API client wrapper for interacting with the resource endpoints

    Attributes:
        client (ApiClient): An ApiClient object with an open Session

    """

    _path: str = ""
    _config: ApiConfig
    _client: ApiClient | None = None
    _s3_client: S3ApiClient | None = None

    def __init__(self, config: ApiConfig) -> None:
        """Initialize a new CustomProfilesResource obj.

        Args:
            config (ApiConfig): An ApiConfig object with necessary configuration
            path (str): The path to the resource endpoint

        """
        self._config = config
        self._client: ApiClient | None = None
        self._s3_client: S3ApiClient | None = None

    @property
    def client(self) -> ApiClient:
        if self._client is None:
            raise ApiClientError("No open client available.")

        return self._client

    @property
    def s3_client(self) -> S3ApiClient:
        if self._s3_client is None:
            raise ApiClientError("No open S3 client available.")

        return self._s3_client

    @override
    def __enter__(self) -> Self:
        """Open a new ApiClient session using with block and return self."""
        self._client = ApiClient(self._config)
        self._s3_client = S3ApiClient()
        return self

    @override
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Disconnect the ApiClient session when exiting the with block."""
        self.client.close()
        self._client = None
        self.s3_client.close()
        self._s3_client = None

    def open(self) -> None:
        """Manually open a new ApiClient session."""
        self.__enter__()

    def close(self) -> None:
        """Manually disconnect the ApiClient session."""
        self.__exit__(None, None, None)

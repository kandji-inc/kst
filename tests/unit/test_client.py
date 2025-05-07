from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from kst.api import ApiClient, ApiConfig
from kst.exceptions import ApiClientError


@pytest.fixture
def fake_client(config) -> Generator[ApiClient]:
    client = ApiClient(config=config)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def patch_requests(monkeypatch, response_factory):
    request_calls: list[tuple[tuple, dict]] = []

    def mock_request(self, *args, **kwargs):
        request_calls.append((args, kwargs))
        return response_factory(status_code=200, content=b"")

    monkeypatch.setattr("requests.sessions.Session.request", mock_request)
    return request_calls


class TestApiConfig:
    def test_valid_config(self):
        valid_configs = [
            "https://xxxxxxxx.api.kandji.io",
            "https://xxxxxxxx.api.kandji.io/",
            "https://xxxxxxxx.api.eu.kandji.io",
            "http://xxxxxxxx.api.kandji.io",
            "http://xxxxxxxx.api.kandji.io/",
            "http://xxxxxxxx.api.eu.kandji.io",
            "xxxxxxxx.api.kandji.io",
            "xxxxxxxx.api.kandji.io/",
            "xxxxxxxx.api.eu.kandji.io",
        ]
        for tenant_url in valid_configs:
            config = ApiConfig(tenant_url=tenant_url, api_token="00000000-0000-0000-0000-000000000000")
            assert urlparse(config.url).scheme == "https"
            assert config.api_token == "00000000-0000-0000-0000-000000000000"

    def test_invalid_url(self):
        invalid_urls = [
            "ftp://xxxxxxxx.api.kandji.io",  # Invalid scheme
            "https://xxxxxxxx.api.kandji.io:8080",  # Port numbers are not allowed
            "http://xxxxxxxx.kandji.io",  # Invalid netloc
            "https://invalid-url.com",  # Invalid netloc
        ]
        for url in invalid_urls:
            with pytest.raises(ValidationError) as exc:
                ApiConfig(tenant_url=url, api_token="00000000-0000-0000-0000-000000000000")
            assert "The Tenant URL must be a valid Kandji API URL" in exc.value.errors()[0]["msg"]

    def test_invalid_token(self):
        invalid_tokens = [
            "",  # empty string
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",  # Invalid character
            "abcd",  # Too short
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # Not a UUID4
        ]
        for token in invalid_tokens:
            with pytest.raises(ValidationError) as exc:
                ApiConfig(tenant_url="xxxxxxxx.api.kandji.io", api_token=token)
            assert "The API token must be a valid UUID4 string." in exc.value.errors()[0]["msg"]


class TestApiClient:
    def test_no_session(self, fake_client):
        fake_client.close()
        with pytest.raises(ApiClientError):
            fake_client.session

    def test_source_param(self, fake_client, patch_requests):
        """Test that the source parameter is added to all requests."""
        fake_client.get("/get")
        fake_client.patch("/patch")
        fake_client.post("/post")
        fake_client.delete("/delete")

        for call in patch_requests:
            assert call[1]["params"]["source"] == "kst"

        # Ensure that other parameters are not overwritten
        fake_client.request("GET", "https://example.com", params={"page": 3, "source": r"¯\_(ツ)_/¯"})
        assert patch_requests[-1][1]["params"] == {"page": 3, "source": "kst"}

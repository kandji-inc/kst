from io import BufferedReader
from pathlib import Path
from typing import Any

import pytest


def test_upload_to_s3_successful_path(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    app_path = tmp_path / "test_app.pkg"
    app_path.write_text("dummy app data")

    def mock_post_request(self, url: str, data: dict[str, Any], files: list[tuple[str, tuple[str, BufferedReader]]]):
        file_obj = files[0][1][1]
        if not file_obj.closed:
            file_obj.close()
        return response_factory(204, {})

    monkeypatch.setattr("kst.api.s3_client.S3ApiClient.post", mock_post_request)

    # Simulate uploading an app
    response = custom_apps_resource.upload_to_s3(
        file=app_path,
        post_url="post_url",
        post_data={
            "key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            "x-amz-algorithm": "...",
            "x-amz-credential": "...",
            "x-amz-date": "...",
            "x-amz-security-token": "...",
            "policy": "...",
            "x-amz-signature": "...",
        },
    )

    assert response is True


def test_upload_to_s3_successful_buffered_reader(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    app_path = tmp_path / "test_app.pkg"
    app_path.write_text("dummy app data")

    def mock_post_request(self, url: str, data: dict[str, Any], files: list[tuple[str, tuple[str, BufferedReader]]]):
        file_obj = files[0][1][1]
        if not file_obj.closed:
            file_obj.close()
        return response_factory(204, {})

    monkeypatch.setattr("kst.api.s3_client.S3ApiClient.post", mock_post_request)

    # Simulate uploading an app
    response = custom_apps_resource.upload_to_s3(
        file=app_path.open("rb"),
        post_url="post_url",
        post_data={
            "key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            "x-amz-algorithm": "...",
            "x-amz-credential": "...",
            "x-amz-date": "...",
            "x-amz-security-token": "...",
            "policy": "...",
            "x-amz-signature": "...",
        },
    )

    assert response is True


def test_no_file_error(custom_apps_resource):
    with pytest.raises(FileNotFoundError, match="does not exist or is not readable"):
        custom_apps_resource.upload_to_s3(file=Path("/path/to/nowhere"), post_url="post_url", post_data={})


def test_directory_passed_as_file_error(custom_apps_resource, tmp_path):
    dir_path = tmp_path / "test_directory"
    dir_path.mkdir()

    with pytest.raises(FileNotFoundError, match="does not exist or is not readable"):
        custom_apps_resource.upload_to_s3(file=dir_path, post_url="post_url", post_data={})


def test_response_error(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    def mock_post_request(self, url: str, data: dict[str, Any], files: list[tuple[str, tuple[str, BufferedReader]]]):
        return response_factory(400, {"error": "Invalid request"})

    monkeypatch.setattr("kst.api.s3_client.S3ApiClient.post", mock_post_request)
    app_path = tmp_path / "test_app.pkg"
    app_path.write_text("dummy app data")
    with pytest.raises(ConnectionError, match="Invalid request"):
        custom_apps_resource.upload_to_s3(file=app_path, post_url="post_url", post_data={"key": "value"})

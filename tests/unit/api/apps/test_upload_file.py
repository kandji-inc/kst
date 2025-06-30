import pytest
from pydantic import ValidationError

from .conftest import create_without_upload_and_delete_factory


def test_upload_file_with_path(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    def mock_post_request(self, path, data):
        json_data = {
            "file_key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_upload.pkg",
            "post_url": "https://s3.amazonaws.com/test-bucket",
            "post_data": {
                "key": "(field to post along with file to S3 -- the key for the uploaded file)",
                "x-amz-algorithm": "(field to post along with file to S3)",
                "x-amz-credential": "(field to post along with file to S3)",
                "x-amz-date": "(field to post along with file to S3)",
                "x-amz-security-token": "(field to post along with file to S3)",
                "policy": "(field to post along with file to S3)",
                "x-amz-signature": "(field to post along with file to S3)",
            },
            "name": "test_upload.pkg",
            "expires": "2023-10-01T00:00:00Z",
        }
        return response_factory(200, json_data)

    def mock_s3_post_request(self, url, data, files, extra_params):
        return response_factory(204, {})

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)
    monkeypatch.setattr("kst.api.client.ApiClient.s3_post", mock_s3_post_request)

    temp_file = tmp_path / "test_upload.pkg"
    temp_file.write_text("This is a test file for upload.")

    file_key = custom_apps_resource._upload_file(temp_file)

    assert file_key == "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_upload.pkg"


def test_upload_file_with_buffered_reader(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    def mock_post_request(self, path, data):
        if path.endswith("/upload"):
            json_data = {
                "file_key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_upload.pkg",
                "post_url": "https://s3.amazonaws.com/test-bucket",
                "post_data": {
                    "key": "(field to post along with file to S3 -- the key for the uploaded file)",
                    "x-amz-algorithm": "(field to post along with file to S3)",
                    "x-amz-credential": "(field to post along with file to S3)",
                    "x-amz-date": "(field to post along with file to S3)",
                    "x-amz-security-token": "(field to post along with file to S3)",
                    "policy": "(field to post along with file to S3)",
                    "x-amz-signature": "(field to post along with file to S3)",
                },
                "name": "test_upload.pkg",
                "expires": "2023-10-01T00:00:00Z",
            }
            return response_factory(200, json_data)
        return response_factory(500, {"error": "Unexpected path"})

    def mock_s3_post_request(self, url, data, files, extra_params):
        return response_factory(204, {})

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)
    monkeypatch.setattr("kst.api.client.ApiClient.s3_post", mock_s3_post_request)

    temp_file = tmp_path / "test_upload.pkg"
    temp_file.write_text("This is a test file for upload.")

    with temp_file.open("rb") as file_obj:
        file_key = custom_apps_resource._upload_file(file_obj)

    assert file_key == "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_upload.pkg"


def test_upload_file_with_nonexistent_path(custom_apps_resource, tmp_path):
    nonexistent_file = tmp_path / "nonexistent.pkg"

    with pytest.raises(FileNotFoundError, match="The file .* does not exist or is not readable"):
        custom_apps_resource._upload_file(nonexistent_file)


def test_upload_file_with_invalid_type(custom_apps_resource):
    with pytest.raises(ValueError, match="Invalid file type provided. Must be a Path or BufferedReader object."):
        custom_apps_resource._upload_file("not_a_path_or_buffered_reader")


def test_upload_file_s3_upload_failure(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    def mock_post_request(self, path, data):
        json_data = {
            "file_key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_upload.pkg",
            "post_url": "https://s3.amazonaws.com/test-bucket",
            "post_data": {
                "key": "(field to post along with file to S3 -- the key for the uploaded file)",
                "x-amz-algorithm": "(field to post along with file to S3)",
                "x-amz-credential": "(field to post along with file to S3)",
                "x-amz-date": "(field to post along with file to S3)",
                "x-amz-security-token": "(field to post along with file to S3)",
                "policy": "(field to post along with file to S3)",
                "x-amz-signature": "(field to post along with file to S3)",
            },
            "name": "test_upload.pkg",
            "expires": "2023-10-01T00:00:00Z",
        }
        return response_factory(200, json_data)

    def mock_s3_post_request_failure(self, url, data, files, extra_params):
        return response_factory(403, {})

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)
    monkeypatch.setattr("kst.api.client.ApiClient.s3_post", mock_s3_post_request_failure)

    temp_file = tmp_path / "test_upload.pkg"
    temp_file.write_text("This is a test file for upload.")

    with pytest.raises(ConnectionError, match="Failed to upload file to S3"):
        custom_apps_resource._upload_file(temp_file)


def test_upload_file_api_response_validation_error(monkeypatch, response_factory, custom_apps_resource, tmp_path):
    def mock_post_request_invalid_json(self, path, data):
        return response_factory(200, b"invalid json response")

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request_invalid_json)

    temp_file = tmp_path / "test_upload.pkg"
    temp_file.write_text("This is a test file for upload.")

    with pytest.raises(ValidationError):
        custom_apps_resource._upload_file(temp_file)


@pytest.mark.allow_http
def test_upload_file_live(config, custom_apps_resource, request, tmp_path):
    temp_file = tmp_path / "live_test_upload.pkg"
    temp_file.write_text("This is a live test file for upload.")

    file_key = custom_apps_resource._upload_file(temp_file)
    request.addfinalizer(create_without_upload_and_delete_factory(config, file_key))
    assert file_key is not None
    assert isinstance(file_key, str)
    assert len(file_key) > 0

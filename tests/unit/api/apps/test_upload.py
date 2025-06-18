import pytest
from pydantic import ValidationError

from kst.api.apps import CustomAppUploadPayload


def test_successful_upload(monkeypatch, response_factory, custom_apps_resource):
    def mock_post_request(self, path, data):
        json_data = {
            "name": "test.pkg",
            "expires": "2023-10-06T19:07:11.391656Z",
            "post_url": "(url of S3 bucket to POST to)",
            "post_data": {
                "key": "(field to post along with file to S3 -- the key for the uploaded file)",
                "x-amz-algorithm": "(field to post along with file to S3)",
                "x-amz-credential": "(field to post along with file to S3)",
                "x-amz-date": "(field to post along with file to S3)",
                "x-amz-security-token": "(field to post along with file to S3)",
                "policy": "(field to post along with file to S3)",
                "x-amz-signature": "(field to post along with file to S3)",
            },
            "file_key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_ae245110.pkg",
        }
        return response_factory(201, json_data)

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)

    response = custom_apps_resource.upload(name="test.pkg")

    assert isinstance(response, CustomAppUploadPayload)
    assert response.post_url == "(url of S3 bucket to POST to)"
    assert (
        response.file_key
        == "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_ae245110.pkg"
    )


def test_response_error(monkeypatch, response_factory, custom_apps_resource):
    def mock_post_request(self, path, data):
        return response_factory(400, {"error": "Invalid request"})

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)

    with pytest.raises(ValidationError):
        custom_apps_resource.upload(name="test.pkg")

import pytest
from pydantic import ValidationError

from kst.api import CustomAppPayload


def test_successful_create(monkeypatch, response_factory, custom_apps_resource):
    def mock_post_request(self, path, data):
        # Add an id to the response data since create returns the created object
        json_data = {
            "id": "test-app-id-12345",
            "name": "Custom Apps Test",
            "file_key": "companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            "install_type": "package",
            "install_enforcement": "install_once",
            "audit_script": "",
            "unzip_location": "",
            "active": True,
            "restart": False,
            "preinstall_script": "",
            "postinstall_script": "",
            "file_url": "(temporary download link from S3)",
            "sha256": "30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58",  # pragma: allowlist secret
            "file_size": 1048576,
            "file_updated": "2023-10-05T21:25:19Z",
            "created_at": "2023-10-13T17:25:45.868709Z",
            "updated_at": "2023-10-13T17:25:45.868789Z",
            "show_in_self_service": True,
            "self_service_category_id": "e6f6d5b4-0659-4b37-872c-5471115d453b",
            "self_service_recommended": True,
        }
        return response_factory(201, json_data)

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)

    response = custom_apps_resource.create(
        name="Custom Apps Test",
        file_key="companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
        install_type="package",
        install_enforcement="install_once",
        audit_script="",
        preinstall_script="",
        postinstall_script="",
        restart=False,
        active=True,
        show_in_self_service=True,
        self_service_category_id="e6f6d5b4-0659-4b37-872c-5471115d453b",
        self_service_recommended=True,
        unzip_location="",
    )

    assert isinstance(response, CustomAppPayload)
    assert response.id == "test-app-id-12345"
    assert response.name == "Custom Apps Test"


def test_json_response_error(monkeypatch, response_factory, custom_apps_resource):
    def mock_post_request(self, path, data):
        return response_factory(201, b"not a json response")

    monkeypatch.setattr("kst.api.client.ApiClient.post", mock_post_request)
    with pytest.raises(ValidationError):
        custom_apps_resource.create(
            name="Custom Apps Test",
            file_key="companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            install_type="package",
            install_enforcement="install_once",
            audit_script="",
            preinstall_script="",
            postinstall_script="",
            restart=False,
            active=True,
        )

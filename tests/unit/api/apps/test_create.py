import pytest
from pydantic import ValidationError

from kst.api import CustomAppPayload, InstallEnforcement, InstallType

from .conftest import delete_app_factory


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
        install_type=InstallType.PACKAGE,
        install_enforcement=InstallEnforcement.INSTALL_ONCE,
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
            install_type=InstallType.PACKAGE,
            install_enforcement=InstallEnforcement.INSTALL_ONCE,
            audit_script="",
            preinstall_script="",
            postinstall_script="",
            restart=False,
            active=True,
        )


def test_create_with_missing_unzip_location(custom_apps_resource):
    with pytest.raises(ValueError, match="unzip_location must be provided when install_type is 'zip'"):
        custom_apps_resource.create(
            name="Missing Unzip Location Test",
            file_key="companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            install_type=InstallType.ZIP,  # Valid install type
            install_enforcement=InstallEnforcement.INSTALL_ONCE,
            audit_script="",
            preinstall_script="",
            postinstall_script="",
            restart=False,
            active=True,
        )


def test_create_with_invalid_audit_script(custom_apps_resource):
    with pytest.raises(
        ValueError, match="audit_script can only be used with install_enforcement 'continuously_enforce'"
    ):
        custom_apps_resource.create(
            name="Invalid Audit Script Test",
            file_key="companies/companies/d934a231-e183-4951-b0a0-763e20572c1d/library/custom_apps/test_18cf0dfc.pkg",
            install_type=InstallType.PACKAGE,
            install_enforcement=InstallEnforcement.INSTALL_ONCE,  # Invalid enforcement for audit script
            audit_script="#!/bin/bash\necho 'Audit script'",
            preinstall_script="",
            postinstall_script="",
            restart=False,
            active=True,
        )


@pytest.mark.allow_http
def test_successful_create_live(config, setup_live_apps_upload_to_s3, custom_apps_resource, request):
    file_key = setup_live_apps_upload_to_s3
    response = custom_apps_resource.create(
        name="Live Test App",
        file_key=file_key,
        install_type=InstallType.ZIP,
        install_enforcement=InstallEnforcement.CONTINUOUSLY_ENFORCE,
        audit_script="#!/bin/bash\necho 'Audit script'",
        preinstall_script="#!/bin/bash\necho 'Pre-install script'",
        postinstall_script="#!/bin/bash\necho 'Post-install script'",
        restart=False,
        active=True,
        show_in_self_service=False,
        unzip_location="/var/tmp",
    )
    request.addfinalizer(delete_app_factory(config, response.id))
    assert response.id is not None
    assert response.name == "Live Test App"
    assert response.install_type == "zip"
    assert response.install_enforcement == "continuously_enforce"
    assert response.audit_script == "#!/bin/bash\necho 'Audit script'"
    assert response.preinstall_script == "#!/bin/bash\necho 'Pre-install script'"
    assert response.postinstall_script == "#!/bin/bash\necho 'Post-install script'"
    assert response.restart is False
    assert response.active is True
